"""Ingestão de currículos em qualquer formato.

A estratégia é normalizar tudo para texto (markdown simples) antes da
extração estruturada:

- PDF nato-digital  -> pdfplumber (texto + tabelas)
- PDF escaneado     -> rasteriza com pdf2image e aplica OCR (pytesseract)
- DOCX              -> python-docx (parágrafos + tabelas), OCR nas imagens embutidas
- Imagem (jpg/png)  -> OCR direto
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Limiar: se um PDF render menos que isso de texto por página, tratamos
# como escaneado e caímos para OCR.
MIN_CARACTERES_POR_PAGINA = 40

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}


def carregar_curriculo(caminho: str | Path) -> str:
    """Lê um arquivo de CV em qualquer formato suportado e devolve texto."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    ext = caminho.suffix.lower()
    if ext == ".pdf":
        return _carregar_pdf(caminho)
    if ext in {".docx", ".doc"}:
        return _carregar_docx(caminho)
    if ext in EXTENSOES_IMAGEM:
        return _ocr_imagem_arquivo(caminho)
    if ext in {".txt", ".md"}:
        return caminho.read_text(encoding="utf-8", errors="replace")

    raise ValueError(f"Formato não suportado: {ext}")


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------

def _carregar_pdf(caminho: Path) -> str:
    import pdfplumber

    partes: list[str] = []
    paginas_pobres = 0

    with pdfplumber.open(caminho) as pdf:
        total_paginas = len(pdf.pages)
        for i, pagina in enumerate(pdf.pages, start=1):
            texto = _texto_pagina(pagina)
            tabelas = _tabelas_para_markdown(pagina.extract_tables())
            conteudo = "\n\n".join(p for p in (texto.strip(), tabelas) if p)

            if len(conteudo) < MIN_CARACTERES_POR_PAGINA:
                paginas_pobres += 1
            partes.append(f"## Página {i}\n\n{conteudo}")

    # Heurística: maioria das páginas sem texto -> PDF escaneado -> OCR
    if total_paginas and paginas_pobres / total_paginas > 0.5:
        logger.info("PDF aparenta ser escaneado; aplicando OCR em %s", caminho.name)
        return _ocr_pdf(caminho)

    return _descolar_texto("\n\n".join(partes))


_RE_COLA_CAMELCASE = re.compile(r"(?<=[a-zà-öø-ü])(?=[A-ZÀ-ÖØ-Ü])")
_RE_COLA_VIRGULA = re.compile(r",(?=[A-Za-zÀ-ü])")
_RE_COLA_PARENTESE = re.compile(r"(?<=[\wà-ü])(?=\()")
_RE_COLA_TRAVESSAO = re.compile(r"(?<=[^\s])([—–])(?=[^\s])")
_RE_COLA_HIFEN = re.compile(r"(?<=[^\s\d])-(?=[^\s\d])")
_RE_COLA_PREP = re.compile(
    r"([a-zà-ü]{4,})(em|de|da|do|das|dos|ao|aos)(?=[A-ZÀ-Ö])"
)
# "Bar-\nbosa" -> "Barbosa": palavra hifenizada na quebra de linha
_RE_HIFEN_QUEBRA = re.compile(r"(?<=[a-zà-ü])-\n(?=[a-zà-ü])")


def _descolar_texto(texto: str) -> str:
    """Recupera espaços em PDFs com kerning apertado (ex.: gerados em LaTeX).

    Nesses arquivos o pdfplumber devolve palavras coladas
    ("OntarioTechUniversity", "GraduateResearchAssistant"). Só atua quando o
    sintoma é generalizado no documento, para não tocar em nomes legítimos
    como "JavaScript" em CVs normais.
    """
    # glifos sem mapeamento unicode no PDF ("(cid:107)04/2021...")
    texto = re.sub(r"\(cid:\d+\)", " ", texto)
    linhas = [l for l in texto.splitlines() if l.strip()]
    if not linhas:
        return texto
    coladas = sum(
        1 for l in linhas
        if _RE_COLA_CAMELCASE.search(l) or _RE_COLA_VIRGULA.search(l)
        or _RE_COLA_TRAVESSAO.search(l) or _RE_COLA_HIFEN.search(l)
        or _RE_COLA_PREP.search(l)
    )
    if coladas / len(linhas) < 0.12:
        return texto
    texto = _RE_HIFEN_QUEBRA.sub("", texto)
    texto = _RE_COLA_TRAVESSAO.sub(r" \1 ", texto)
    texto = _RE_COLA_HIFEN.sub(" - ", texto)
    texto = _RE_COLA_PREP.sub(r"\1 \2 ", texto)
    texto = _RE_COLA_CAMELCASE.sub(" ", texto)
    texto = _RE_COLA_PARENTESE.sub(" ", texto)
    return _RE_COLA_VIRGULA.sub(", ", texto)


def _texto_pagina(pagina) -> str:
    """Extrai o texto da página respeitando layouts de duas colunas.

    `extract_text` intercala as colunas linha a linha, embaralhando o
    conteúdo. Se houver uma "calha" vertical clara separando dois blocos
    de palavras, extraímos cada coluna separadamente (esquerda -> direita).
    """
    texto_simples = (pagina.extract_text() or "").strip()
    corte = _detectar_corte_colunas(pagina)
    if corte is not None:
        x0, topo, x1, base = pagina.bbox
        try:
            esquerda = pagina.crop((x0, topo, corte, base)).extract_text() or ""
            direita = pagina.crop((corte, topo, x1, base)).extract_text() or ""
        except Exception:  # bbox inválida em PDFs malformados
            return texto_simples
        combinado = "\n\n".join(p for p in (esquerda.strip(), direita.strip()) if p)
        return combinado or texto_simples
    # calha imperfeita (header/títulos cruzam o meio): detecta pela
    # consistência dos espaços horizontais dentro das linhas
    corte = _detectar_corte_por_gaps(pagina)
    if corte is not None:
        texto = _texto_colunas_por_palavras(pagina, corte)
        if texto:
            return texto
    return texto_simples


def _detectar_corte_colunas(pagina) -> float | None:
    """Procura um x de corte no meio da página que nenhuma palavra cruza."""
    try:
        palavras = pagina.extract_words() or []
    except Exception:
        return None
    if len(palavras) < 40:
        return None
    largura = float(pagina.width)
    melhor = None
    melhor_equilibrio = 0.0
    for fracao in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        x = largura * fracao
        cruzam = sum(1 for w in palavras if w["x0"] < x - 2 and w["x1"] > x + 2)
        # tolera pouquíssimas palavras cruzando (ex.: título no topo da página)
        if cruzam > max(2, len(palavras) * 0.01):
            continue
        esquerda = [w for w in palavras if w["x1"] <= x]
        direita = [w for w in palavras if w["x0"] >= x]
        menor = min(esquerda, direita, key=len)
        if len(menor) < 15:
            continue
        # evita "dividir" uma coluna de datas/números do texto principal
        alfabeticas = sum(
            1 for w in menor if sum(c.isalpha() for c in w["text"]) >= 3
        )
        if alfabeticas / len(menor) < 0.5:
            continue
        equilibrio = len(menor) / len(palavras)
        if equilibrio > melhor_equilibrio:
            melhor = x
            melhor_equilibrio = equilibrio
    return melhor


def _detectar_corte_por_gaps(pagina) -> float | None:
    """Detecta duas colunas mesmo quando títulos/header cruzam o meio.

    Varre o terço central procurando o x com a MENOR quantidade de palavras
    atravessando (a calha). Aceita poucas travessias (header em largura
    total), diferente do detector estrito que exige calha limpa.
    """
    try:
        palavras = pagina.extract_words() or []
    except Exception:
        return None
    if len(palavras) < 60:
        return None
    largura = float(pagina.width)

    melhor_cov, melhor_x = None, None
    for x in range(int(largura * 0.3), int(largura * 0.7), 3):
        cov = sum(1 for w in palavras if w["x0"] < x - 1 and w["x1"] > x + 1)
        if melhor_cov is None or cov < melhor_cov:
            melhor_cov, melhor_x = cov, x
    n_linhas = len({int(w["top"] // 8) for w in palavras})
    if melhor_cov > max(4, n_linhas * 0.08):
        return None
    esquerda = sum(1 for w in palavras if w["x1"] <= melhor_x)
    direita = sum(1 for w in palavras if w["x0"] >= melhor_x)
    if min(esquerda, direita) < 15:
        return None
    return float(melhor_x)


def _texto_colunas_por_palavras(pagina, corte: float) -> str:
    """Reconstrói o texto separando palavras à esquerda/direita do corte.

    Palavras que cruzam o corte (header em largura total) ficam na coluna em
    que têm maior área. Cada coluna é remontada linha a linha pelo eixo y.
    """
    try:
        palavras = pagina.extract_words() or []
    except Exception:
        return ""
    # topo da página (nome/contato) costuma ocupar a largura toda: mantém
    # como bloco próprio para não partir o nome entre as colunas
    limite_header = float(pagina.height) * 0.12
    header, esquerda, direita = [], [], []
    for w in palavras:
        if w["top"] < limite_header:
            header.append(w)
            continue
        meio = (w["x0"] + w["x1"]) / 2
        (esquerda if meio < corte else direita).append(w)

    def montar(coluna) -> str:
        coluna.sort(key=lambda w: (int(w["top"] // 4), w["x0"]))
        linhas, atual, topo = [], [], None
        for w in coluna:
            if topo is not None and w["top"] - topo > 4:
                linhas.append(" ".join(atual))
                atual = []
            atual.append(w["text"])
            topo = w["top"]
        if atual:
            linhas.append(" ".join(atual))
        return "\n".join(linhas)

    partes = [montar(c) for c in (header, esquerda, direita) if c]
    return "\n\n".join(p for p in partes if p.strip())


def _ocr_pdf(caminho: Path) -> str:
    from pdf2image import convert_from_path

    imagens = convert_from_path(str(caminho), dpi=300)
    partes = []
    for i, imagem in enumerate(imagens, start=1):
        texto = _ocr_imagem_pil(imagem)
        partes.append(f"## Página {i} (OCR)\n\n{texto}")
    return "\n\n".join(partes)


def _tabelas_para_markdown(tabelas) -> str:
    """Converte tabelas extraídas (lista de listas) em markdown."""
    if not tabelas:
        return ""
    blocos = []
    for tabela in tabelas:
        linhas_md = []
        for j, linha in enumerate(tabela):
            celulas = [(c or "").replace("\n", " ").strip() for c in linha]
            linhas_md.append("| " + " | ".join(celulas) + " |")
            if j == 0:
                linhas_md.append("|" + "---|" * len(celulas))
        blocos.append("\n".join(linhas_md))
    return "\n\n".join(blocos)


# ----------------------------------------------------------------------
# DOCX
# ----------------------------------------------------------------------

def _carregar_docx(caminho: Path) -> str:
    if caminho.suffix.lower() == ".doc":
        raise ValueError(
            "Formato .doc legado não é suportado diretamente. "
            "Converta para .docx (ex.: `libreoffice --headless --convert-to docx`)."
        )

    import docx

    documento = docx.Document(str(caminho))
    partes: list[str] = []

    # Itera na ordem real do documento (parágrafos e tabelas intercalados)
    for bloco in _iterar_blocos(documento):
        if bloco["tipo"] == "paragrafo":
            texto = bloco["obj"].text.strip()
            if texto:
                partes.append(texto)
        else:  # tabela
            partes.append(_tabela_docx_para_markdown(bloco["obj"]))

    # OCR nas imagens embutidas (foto, infográfico de skills etc.)
    texto_imagens = _ocr_imagens_docx(documento)
    if texto_imagens:
        partes.append("## Texto extraído de imagens embutidas (OCR)\n\n" + texto_imagens)

    return "\n\n".join(partes)


def _iterar_blocos(documento):
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    corpo = documento.element.body
    for filho in corpo.iterchildren():
        if filho.tag.endswith("}p"):
            yield {"tipo": "paragrafo", "obj": Paragraph(filho, documento)}
        elif filho.tag.endswith("}tbl"):
            yield {"tipo": "tabela", "obj": Table(filho, documento)}


def _tabela_docx_para_markdown(tabela) -> str:
    # células mescladas aparecem repetidas em linha.cells -> dedup por linha
    linhas_celulas: list[list[str]] = []
    for linha in tabela.rows:
        celulas: list[str] = []
        for celula in linha.cells:
            texto = celula.text.strip()
            if not celulas or celulas[-1] != texto:
                celulas.append(texto)
        linhas_celulas.append(celulas)

    # Tabela usada como layout (células com parágrafos inteiros): vira texto
    # corrido preservando as quebras de linha internas.
    eh_layout = any(
        "\n" in c or len(c) > 100 for cels in linhas_celulas for c in cels
    )
    if eh_layout:
        vistos: set[str] = set()
        blocos = []
        for cels in linhas_celulas:
            for c in cels:
                if c and c not in vistos:
                    vistos.add(c)
                    blocos.append(c)
        return "\n\n".join(blocos)

    linhas_md = []
    for j, celulas in enumerate(linhas_celulas):
        linhas_md.append("| " + " | ".join(celulas) + " |")
        if j == 0:
            linhas_md.append("|" + "---|" * len(celulas))
    return "\n".join(linhas_md)


def _ocr_imagens_docx(documento) -> str:
    from PIL import Image

    textos = []
    for rel in documento.part.rels.values():
        if "image" not in rel.reltype:
            continue
        try:
            dados = rel.target_part.blob
            imagem = Image.open(io.BytesIO(dados))
            texto = _ocr_imagem_pil(imagem).strip()
            if texto:
                textos.append(texto)
        except Exception as exc:  # imagem corrompida ou formato exótico
            logger.warning("Falha ao processar imagem embutida: %s", exc)
    return "\n\n".join(textos)


# ----------------------------------------------------------------------
# OCR
# ----------------------------------------------------------------------

def _ocr_imagem_arquivo(caminho: Path) -> str:
    from PIL import Image

    with Image.open(caminho) as imagem:
        return _ocr_imagem_pil(imagem)


def _ocr_imagem_pil(imagem) -> str:
    import pytesseract
    from PIL import Image

    # por+eng cobre a maioria dos CVs brasileiros com termos técnicos em inglês
    texto = pytesseract.image_to_string(imagem, lang="por+eng")
    if imagem.width >= 1600:
        return texto

    # imagem pequena: upscale 2x (e variante em tons de cinza) recuperam
    # datas/texto fino, mas podem piorar outros trechos (ex.: texto claro em
    # banners coloridos). Faz as passadas e fica com a de melhor qualidade.
    from PIL import ImageOps

    maior = imagem.resize((imagem.width * 2, imagem.height * 2), Image.LANCZOS)
    cinza = ImageOps.autocontrast(maior.convert("L"))
    candidatos = [
        texto,
        pytesseract.image_to_string(maior, lang="por+eng"),
        pytesseract.image_to_string(cinza, lang="por+eng"),
    ]
    return max(candidatos, key=_qualidade_ocr)


def _qualidade_ocr(texto: str) -> tuple[int, int]:
    """Pontua um resultado de OCR: datas legíveis pesam mais que volume."""
    anos = len(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", texto))
    palavras = sum(1 for p in texto.split() if sum(c.isalpha() for c in p) >= 3)
    return (anos, palavras)

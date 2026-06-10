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


def _descolar_texto(texto: str) -> str:
    """Recupera espaços em PDFs com kerning apertado (ex.: gerados em LaTeX).

    Nesses arquivos o pdfplumber devolve palavras coladas
    ("OntarioTechUniversity", "GraduateResearchAssistant"). Só atua quando o
    sintoma é generalizado no documento, para não tocar em nomes legítimos
    como "JavaScript" em CVs normais.
    """
    linhas = [l for l in texto.splitlines() if l.strip()]
    if not linhas:
        return texto
    coladas = sum(1 for l in linhas if _RE_COLA_CAMELCASE.search(l))
    if coladas / len(linhas) < 0.3:
        return texto
    texto = _RE_COLA_CAMELCASE.sub(" ", texto)
    return re.sub(r",(?=[A-Za-zÀ-ü])", ", ", texto)


def _texto_pagina(pagina) -> str:
    """Extrai o texto da página respeitando layouts de duas colunas.

    `extract_text` intercala as colunas linha a linha, embaralhando o
    conteúdo. Se houver uma "calha" vertical clara separando dois blocos
    de palavras, extraímos cada coluna separadamente (esquerda -> direita).
    """
    texto_simples = (pagina.extract_text() or "").strip()
    corte = _detectar_corte_colunas(pagina)
    if corte is None:
        return texto_simples
    x0, topo, x1, base = pagina.bbox
    try:
        esquerda = pagina.crop((x0, topo, corte, base)).extract_text() or ""
        direita = pagina.crop((corte, topo, x1, base)).extract_text() or ""
    except Exception:  # bbox inválida em PDFs malformados
        return texto_simples
    combinado = "\n\n".join(p for p in (esquerda.strip(), direita.strip()) if p)
    return combinado or texto_simples


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

    # por+eng cobre a maioria dos CVs brasileiros com termos técnicos em inglês
    return pytesseract.image_to_string(imagem, lang="por+eng")

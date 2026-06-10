"""Extração estruturada SEM LLM: texto bruto do CV -> objeto Curriculo.

Estratégia totalmente local, baseada em heurísticas:

1. Regexes globais para dados de contato (email, telefone, LinkedIn, GitHub...).
2. Segmentação do texto em seções pelos títulos usuais de CV
   ("Experiência", "Formação", "Habilidades", "Idiomas"...), com
   comparação insensível a caixa e acentos.
3. Um parser dedicado por seção (datas, separadores, tabelas markdown
   vindas da ingestão de DOCX/PDF, listas com vírgulas ou bullets).

Funciona bem para CVs razoavelmente estruturados. Layouts muito fora do
padrão podem ter campos não reconhecidos (ficam null/lista vazia).
"""
from __future__ import annotations

import re
import unicodedata

from .esquema import Certificacao, Contato, Curriculo, Experiencia, Formacao, Idioma

# ----------------------------------------------------------------------
# Normalização e constantes
# ----------------------------------------------------------------------

def _norm(texto: str) -> str:
    """minúsculas + sem acentos, para comparações robustas."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


# Aliases de títulos de seção (já normalizados) -> chave interna
_ALIAS_SECOES: dict[str, str] = {}
for chave, aliases in {
    "contato": ["contato", "contatos", "dados pessoais", "dados de contato", "contact"],
    "resumo": ["resumo", "resumo profissional", "objetivo", "objetivo profissional",
               "sobre", "sobre mim", "perfil", "perfil profissional", "apresentacao", "summary"],
    "experiencias": ["experiencia", "experiencias", "experiencia profissional",
                     "experiencia de trabalho", "experiencias de trabalho",
                     "experiencias profissionais", "historico profissional",
                     "atuacao profissional", "trajetoria profissional",
                     "experience", "work experience", "professional experience",
                     "employment", "employment history", "work history",
                     "academic experience"],
    "formacoes": ["formacao", "formacao academica", "formacao educacional",
                  "formacoes", "educacao",
                  "escolaridade", "education", "academic background",
                  "academic education"],
    "habilidades": ["habilidades", "competencias", "skills", "hard skills", "soft skills",
                    "conhecimentos", "conhecimentos tecnicos", "tecnologias", "ferramentas",
                    "qualificacoes", "pontos fortes",
                    "technical skills", "areas of specialization", "core competencies"],
    "idiomas": ["idiomas", "linguas", "languages"],
    "certificacoes": ["certificacoes", "certificados", "certificacao",
                      "cursos", "cursos e certificacoes", "certifications"],
    "projetos": ["projetos", "projetos pessoais", "portfolio", "projects"],
    "publicacoes": ["publicacoes", "artigos", "publications", "selected publications"],
    "adicionais": ["informacoes adicionais", "outras informacoes", "informacoes complementares",
                   "atividades complementares", "additional information",
                   "grants, honors & awards", "honors & awards", "awards", "grants",
                   "scholarly and professional academic activities",
                   "volunteer work", "volunteering", "trabalho voluntario"],
}.items():
    for alias in aliases:
        _ALIAS_SECOES[alias] = chave

# títulos colados sem espaços ("EXPERIÊNCIAPROFISSIONAL" em PDFs de kerning ruim)
_ALIAS_SECOES_SEM_ESPACO = {
    alias.replace(" ", ""): chave for alias, chave in _ALIAS_SECOES.items()
}

# Palavras que indicam cargo/título profissional
_PALAVRAS_CARGO = (
    "engenheir", "desenvolvedor", "programador", "analista", "cientista",
    "arquitet", "gerente", "coordenador", "diretor", "lider", "tech lead",
    "especialista", "consultor", "designer", "tecnico", "estagiar",
    "assistente", "auxiliar", "supervisor", "professor", "pesquisador",
    "administrador", "dba", "devops", "qa", "tester", "scrum", "product",
    "gestor", "presidente", "representante", "vendedor", "head", "operador",
    "superintendente", "instrutor", "encarregado", "almoxarife", "comprador",
    "recepcionista", "controller",
    "contador", "auditor", "advogad", "enfermeir", "atendente", "motorista",
    "cozinheir", "dentista", "farmaceutic", "psicolog", "fisioterapeut",
    "nutricionist", "veterinari", "balconista", "acougueir", "repositor",
    "secretari", "porteiro", "vigilante", "zelador", "faxineir", "garcom",
    "garconete", "padeiro", "costureir", "soldador", "eletricista",
    "encanador", "pedreiro", "marceneir", "mecanic", "estoquista",
    "trainee", "aprendiz", "agente", "embaixador", "voluntari", "tutor",
    "freelancer", "entregador",
    "pleno", "junior", "senior", "sr", "jr",
    # cargos em inglês (CVs acadêmicos/internacionais)
    "researcher", "developer", "engineer", "architect", "manager",
    "director", "assistant", "internship", "artist", "instructor", "teacher",
)

_MES = r"(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|feb|apr|may|aug|sep|oct|dec|ene|abr)[a-zç]*"
_ANO = r"(?:19|20)\d{2}"
# aceita "Mar/2021", "março de 2021", "Set. de 2022", "8/2025", "07 / 2023",
# "26/08/2024", "Out_2024", ISO "2023-10" e ano 2 dígitos após mês ("Nov/01", "01/24")
_DATA = (
    rf"{_ANO}-(?:0?[1-9]|1[0-2])(?!\d)"
    rf"|(?:\d{{1,2}}\s*[./-]\s*){{0,2}}(?:{_MES}[._/\s]*(?:de\s+)?)?{_ANO}"
    rf"|(?:{_MES}|\d{{1,2}})\s*[/.]\s*\d{{2}}(?!\d)"
)
_FIM_ABERTO = (
    r"atual(?:mente|meme)?|presente|hoje|(?:o\s+)?momento|(?:os\s+)?dias\s+atuais"
    r"|em\s+andamento|current|present"
)
# separadores de intervalo: "-", "–", "--", "a", "à", "até", "até o", "/",
# e ","/"(" apenas quando seguidos de fim aberto ("Fev/2024, Atual", "2025 (ATUAL)")
_SEP_PERIODO = (
    rf"(?:[-–—]{{1,2}}(?:\s*at[eé](?:\s+o)?)?|at[eé](?:\s+o)?|à|a\b|/"
    rf"|,(?=\s*(?:{_FIM_ABERTO}))|\((?=\s*(?:{_FIM_ABERTO}))"
    rf"|=(?=\s*(?:{_FIM_ABERTO}|\d)))"  # OCR lê travessão como "="
)
_RE_PERIODO = re.compile(
    rf"(?i)\b({_DATA})\s*{_SEP_PERIODO}\s*({_DATA}|{_FIM_ABERTO})\b"
)
# início aberto: "desde 08/2024", "Desde Setembro de 2023"
_RE_DESDE = re.compile(rf"(?i)\bdesde\s+({_DATA})\b")

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+\w")
_RE_LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[\w\-/%.]+", re.I)
_RE_GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-/%.]+", re.I)
_RE_URL = re.compile(r"https?://[\w\-./%?=&#]+", re.I)
_RE_TELEFONE = re.compile(r"(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}")
# identificador ORCID ("orcid.org/0000-0003-2334-1919") não é telefone
_RE_ORCID = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dXx]\b")
_RE_CIDADE_UF = re.compile(
    r"([A-ZÀ-Ü][\wÀ-ü. ]{2,40}?)\s*[-–,/]\s*([A-Z]{2})\b(?:\s*[,/-]\s*(Brasil|Brazil|Portugal))?"
)
_RE_ANO = re.compile(r"\b(?:19|20)\d{2}\b")
_RE_ANOS_INTERVALO = re.compile(
    rf"\(?\s*((?:19|20)\d{{2}})\s*(?:-|–|—|a|ate|até)\s*((?:19|20)\d{{2}}|{_FIM_ABERTO})\s*\)?",
    re.I,
)
_RE_CARGO_FINAL = re.compile(
    r"^(.+?)\s+("
    r"(?:diretor|gerente|gestor|coordenador|supervisor|analista|assistente|auxiliar|"
    r"consultor|especialista|presidente|representante|"
    r"engenheir\w*|desenvolvedor\w*|administrador\w*)"
    r"(?:\s+[\wÀ-ü]+){0,4}"
    r")$",
    re.I,
)
_RE_PREFIXO_CARGO = re.compile(r"(?i)^(?:cargos?|fun[cç][aã]o(?:es)?)\s*[:\-]\s*(.+)$")
_RE_PREFIXO_EMPRESA = re.compile(r"(?i)^empresas?\s*[:\-]\s*(.+)$")
_RE_PREFIXO_PERIODO = re.compile(r"(?i)^per[ií]odos?\s*[:\-]\s*(.+)$")
# "2020 PalominoSys, Ontario, Canada": ano isolado abrindo a linha + empresa.
# Comum em CVs acadêmicos; só vale DENTRO da seção de experiência (ano_solto).
_RE_ANO_EMPRESA = re.compile(r"^((?:19|20)\d{2})\s+(?P<resto>[A-ZÀ-Ü].{3,70})$")
# "Empresa – 12/24": data única (mês/ano) no fim da linha, sem intervalo
_RE_DATA_SOLTA = re.compile(
    rf"(?i)^(?P<cabeca>[^|•▪\-–—:]{{2,55}}?)\s*[-–—(]\s*"
    rf"(?P<data>(?:{_MES}|\d{{1,2}})\s*[._/]\s*(?:(?:19|20)\d{{2}}|\d{{2}}))\s*\)?\s*\.?\s*$"
)
_RE_SUFIXO_EMPRESA = re.compile(r"(?i)\b(ltda|s\.a\.?|s/a|eireli|m\.?e\.?i)\b")
# "Curitiba, PR": localidade pura não é nome de empresa
_RE_SO_LOCAL = re.compile(r"^[A-ZÀ-Ü][\wÀ-ü.\s]{1,30},\s*[A-Z]{2}$")
_RE_CANDIDATO = re.compile(r"(?i)^candidat[oa]s?\s*[:\-]\s*(.+)$")
_RE_NOME_IDADE = re.compile(r"^(.{4,60}?)\s*[—–-]+\s*\d{1,3}\s*anos\b")

_SEPARADORES = (" — ", " – ", " - ", " | ", " @ ")
_RE_COLA_TRAV_LINHA = re.compile(r"(?<=[^\s])([—–])(?=[^\s])")
_RE_COLA_HIFEN_LINHA = re.compile(r"(?<=[^\s\d])-(?=[^\s\d])")
_RE_COLA_PREP_LINHA = re.compile(
    r"([a-zà-ü]{4,})(em|de|da|do|das|dos|ao|aos)(?=[A-ZÀ-Ö])"
)
_PREPS_COLADAS_TOKEN = ("aos", "ao", "em")
_PREPS_COLADAS_EMPRESA = ("nos", "nas", "no", "na", "aos", "ao", "em")
_BLOCKLIST_PREFIXO_PREP = frozenset((
    "universidade", "sociedade", "faculdade", "comunidade", "atividade",
))
_CORRECOES_EMPRESA = (
    (re.compile(r"(?i)\bi\s+food\b"), "iFood"),
    (re.compile(r"(?i)\bmerca\s+do\s+livre\b"), "Mercado Livre"),
    (re.compile(r"(?i)\bm\.dias\b"), "M. Dias"),
)
_RE_COLA_CAMEL_LINHA = re.compile(r"(?<=[a-zà-öø-ü])(?=[A-ZÀ-ÖØ-Ü])")
_CABECALHOS_INTERNOS = frozenset((
    "voluntariado", "experiencia de pesquisa", "experiencias de pesquisa",
    "experienciadepesquisa", "experienciadetrabalho", "responsabilidades principais",
    "responsabilidadesprincipais", "perfil",
))
_RE_COMPLEMENTO_EMPRESA = re.compile(r"(?i)^grupo de \d+ empresas?$")
_FRAGMENTOS_EMPRESA = frozenset(("hora", "ital", "mail", "chat"))
_NIVEIS_FORMACAO = (
    ("doutorado", "doutorado"), ("phd", "doutorado"),
    ("mestrado", "mestrado"), ("mba", "especialização"),
    ("especializacao", "especialização"), ("pos-graduacao", "especialização"),
    ("pos graduacao", "especialização"),
    ("bacharelado", "graduação"), ("bacharel", "graduação"),
    ("licenciatura", "graduação"), ("graduacao", "graduação"),
    ("tecnologo", "tecnólogo"), ("tecnico", "técnico"), ("ensino medio", "ensino médio"),
)
_SITUACOES = ("concluido", "concluida", "em andamento", "cursando", "trancado", "incompleto")
_NIVEIS_IDIOMA = (
    "nativo", "fluente", "avancado", "intermediario", "basico", "proficiente",
    "a1", "a2", "b1", "b2", "c1", "c2", "leitura", "tecnico",
    "native", "fluent", "advanced", "intermediate", "basic", "proficien",
)


def _tem_nivel_idioma(texto: str) -> bool:
    n = _norm(texto)
    # word boundary evita falsos positivos ("IISA2021" contém "a2")
    return any(re.search(rf"(?<![a-z0-9]){re.escape(p)}", n) for p in _NIVEIS_IDIOMA)


# ----------------------------------------------------------------------
# Função principal
# ----------------------------------------------------------------------

def extrair_curriculo(texto: str) -> Curriculo:
    """Converte o texto bruto de um CV em um objeto Curriculo validado."""
    linhas = _limpar_linhas(texto)
    secoes = _segmentar_secoes(linhas)
    preambulo = secoes.get("preambulo", [])

    # formulários ("DADOS PESSOAIS" / "NOME COMPLETO ...") guardam o nome na
    # seção de contato; incluí-la na busca não afeta CVs comuns.
    nome, titulo = _extrair_nome_e_titulo(preambulo + secoes.get("contato", [])[:10])
    contato = _extrair_contato(texto, preambulo + secoes.get("contato", []))

    # Currículo Lattes tem estrutura própria ("Atuação Profissional" ->
    # "Vínculo institucional"); o caminho genérico superextrai (anos de
    # produção científica viram âncoras de experiência).
    experiencias = _experiencias_lattes(texto)
    if not experiencias:
        experiencias = _extrair_experiencias(secoes.get("experiencias", []), ano_solto=True)
        experiencias = _complementar_experiencias_perdidas(experiencias, secoes)
    if not experiencias:
        # CVs sem título de experiência: o bloco pode vir "colado" em outra
        # seção (fim da formação, resumo etc.) sem novo cabeçalho.
        for chave in (
            "formacoes", "resumo", "adicionais", "idiomas",
            "habilidades", "certificacoes", "preambulo",
        ):
            linhas_secao = secoes.get(chave, [])
            if not linhas_secao:
                continue
            resto, linhas_exp = _separar_formacao_de_experiencias(linhas_secao)
            if linhas_exp:
                extraidas = _extrair_experiencias(linhas_exp)
                if extraidas:
                    experiencias = extraidas
                    secoes[chave] = resto
                    break
    if not experiencias:
        # blocos "Empresa: ... / Cargo: ... / Período: 7 meses" sem datas;
        # podem estar repartidos entre seções (quebra de página com cabeçalho)
        encontrados = []
        for chave in ("experiencias", "formacoes", "resumo", "adicionais", "preambulo"):
            extraidas, resto = _experiencias_rotuladas(secoes.get(chave, []))
            if extraidas:
                encontrados.append((chave, extraidas, resto))
        if sum(len(e) for _, e, _ in encontrados) >= 2:
            for chave, extraidas, resto in encontrados:
                experiencias += extraidas
                secoes[chave] = resto
    linhas_formacao = secoes.get("formacoes", [])

    if nome is None:
        nome = _nome_em_linhas(linhas[:80])
    if nome is None:
        # PDFs de colunas (ex.: export do LinkedIn): a sidebar vem antes e o
        # nome aparece só no topo da coluna principal, fora do preâmbulo.
        candidatos = []
        for idx, linha in enumerate(linhas[:80]):
            candidato = _candidato_nome(linha)
            if _parece_nome(candidato) and not _parece_titulo(candidato):
                candidatos.append((idx, candidato))
        # prefere candidato seguido de headline de cargo ("Fulano" / "Diretor...")
        nome = next(
            (
                c for idx, c in candidatos
                if any(_parece_titulo(l) for l in linhas[idx + 1 : idx + 3])
            ),
            None,
        )
        if nome is None and candidatos:
            # evita instituição/universidade quando há nome de pessoa no documento
            pessoas = [c for _, c in candidatos if len(c.split()) >= 2 and len(c) <= 45]
            nome = max(pessoas, key=lambda c: len(c.split()), default=candidatos[0][1])
    if nome is None or not _parece_nome(nome):
        nome_email = _nome_do_email(contato.email)
        if nome_email:
            nome = nome_email

    return Curriculo(
        nome_completo=nome,
        titulo_profissional=titulo,
        resumo=_juntar(secoes.get("resumo", [])),
        contato=contato,
        formacoes=_extrair_formacoes(linhas_formacao),
        experiencias=experiencias,
        habilidades=_extrair_habilidades(secoes.get("habilidades", [])),
        idiomas=_extrair_idiomas(secoes.get("idiomas", [])),
        certificacoes=_extrair_certificacoes(secoes.get("certificacoes", [])),
        projetos=_extrair_itens(secoes.get("projetos", [])),
        publicacoes=_extrair_itens(secoes.get("publicacoes", [])),
        informacoes_adicionais=_juntar(secoes.get("adicionais", [])),
    )


# ----------------------------------------------------------------------
# Pré-processamento e segmentação
# ----------------------------------------------------------------------

def _limpar_linhas(texto: str) -> list[str]:
    linhas = []
    for linha in texto.splitlines():
        linha = linha.strip()
        # marcadores inseridos pela ingestão ("## Página 1", "## ... (OCR)")
        if re.match(r"^#+\s*(página|pagina|texto extraído|texto extraido)", linha, re.I):
            continue
        linhas.append(linha)
    return _explodir_tabelas(_juntar_periodos_quebrados(linhas))


_RE_DATA_SOZINHA = re.compile(rf"^(?:{_DATA})$")
_RE_FIM_SOZINHO = re.compile(rf"^(?:{_DATA}|{_FIM_ABERTO})$", re.I)
# colunas embaralhadas pelo OCR: "12/2020 a Empresa: X" / "12/2021 Cargo: Y"
_RE_PERIODO_CORTADO = re.compile(
    rf"(?i)^(?P<data>{_DATA})\s*(?P<sep>a|at[eé])\s+(?P<resto>\D.+)$"
)
_RE_DATA_NO_INICIO = re.compile(rf"(?i)^(?P<data>{_DATA})\s+(?P<resto>\D.+)$")


def _juntar_periodos_quebrados(linhas: list[str]) -> list[str]:
    """Reagrupa períodos quebrados em várias linhas pelo layout.

    Ex.: "2022-01" / "—" / "atual" vira "2022-01 — atual".
    """
    saida: list[str] = []
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if _RE_DATA_SOZINHA.match(linha) and i + 2 < len(linhas):
            sep, fim = linhas[i + 1], linhas[i + 2]
            if re.fullmatch(r"[-–—]|a|até|ate", sep, re.I) and _RE_FIM_SOZINHO.match(fim):
                saida.append(f"{linha} {sep} {fim}")
                i += 3
                continue
        # OCR de duas colunas: "12/2020 a Empresa: X" / [linha da outra coluna]
        # / "12/2021 Cargo: Y" — junta o período e preserva o resto.
        # Não se aplica se a linha já contém um período completo
        # ("Agosto de 1998 a dezembro de 1999").
        m1 = _RE_PERIODO_CORTADO.match(linha)
        if m1 and _RE_PERIODO.search(linha):
            m1 = None
        if m1:
            m2 = salto = None
            for s in (1, 2):
                if i + s < len(linhas) and not _RE_PERIODO.search(linhas[i + s - 1] if s > 1 else ""):
                    m2 = _RE_DATA_NO_INICIO.match(linhas[i + s])
                    if m2:
                        salto = s
                        break
            if m2:
                saida.append(f"{m1.group('data')} {m1.group('sep')} {m2.group('data')}")
                saida.append(m1.group("resto"))
                saida.extend(linhas[i + 1 : i + salto])
                saida.append(m2.group("resto"))
                i += salto + 1
                continue
        saida.append(linha)
        i += 1
    return saida


def _explodir_tabelas(linhas: list[str]) -> list[str]:
    """Converte células de tabelas markdown em linhas comuns de texto.

    Tabelas de DOCX/PDF ou repetem conteúdo que já apareceu como texto
    corrido (descartamos via dedupe) ou são o único lugar onde o conteúdo
    existe (CVs montados inteiramente em tabelas).
    """
    vistos = {_norm(l) for l in linhas if l and not l.startswith("|")}
    saida: list[str] = []
    for linha in linhas:
        if not linha.startswith("|"):
            saida.append(linha)
            continue
        if re.match(r"^\|[\s\-|]+\|?$", linha):  # separador |---|---|
            continue
        for celula in linha.strip("|").split("|"):
            celula = celula.strip()
            chave = _norm(celula)
            if len(celula) < 2 or chave in vistos:
                continue
            vistos.add(chave)
            saida.append(celula)
    return saida


def _chave_secao(linha: str) -> str | None:
    """Devolve a chave da seção se a linha for um título de seção."""
    limpa = _norm(linha).strip("#:•-– ").strip()
    if not limpa or len(limpa) > 60:
        return None
    chave = _ALIAS_SECOES.get(limpa) or _ALIAS_SECOES_SEM_ESPACO.get(limpa.replace(" ", ""))
    if chave:
        return chave
    # complemento entre parênteses: "Experiências (Treinamentos)"
    sem_parens = re.sub(r"\s*\(.*?\)\s*$", "", limpa)
    if sem_parens != limpa and sem_parens in _ALIAS_SECOES:
        return _ALIAS_SECOES[sem_parens]
    # títulos decorados com emoji/símbolos: "💼 Experiência Profissional"
    so_texto = re.sub(r"[^a-z0-9&, ]+", " ", limpa)
    so_texto = re.sub(r"\s{2,}", " ", so_texto).strip()
    return _ALIAS_SECOES.get(so_texto) if so_texto != limpa else None


def _segmentar_secoes(linhas: list[str]) -> dict[str, list[str]]:
    secoes: dict[str, list[str]] = {"preambulo": []}
    atual = "preambulo"
    for linha in linhas:
        chave = _chave_secao(linha)
        if chave:
            atual = chave
            secoes.setdefault(atual, [])
            continue
        if linha:
            secoes[atual].append(linha)
    return secoes


def _juntar(linhas: list[str]) -> str | None:
    texto = " ".join(l for l in linhas if l).strip()
    return texto or None


# ----------------------------------------------------------------------
# Nome, título e contato
# ----------------------------------------------------------------------

# linhas que parecem nome mas não são (cabeçalhos de relatório, estado civil...)
_PALAVRAS_NAO_NOME = (
    "relatorio", "curriculo", "curriculum", "prezad", "candidato",
    "brasileir", "casad", "solteir", "divorciad", "competencia",
    "empregador", "admissao", "desligamento", "anexo", "processo seletivo",
    "assinatura", "instituicao",
    # títulos de seção que o OCR pode soltar no meio do preâmbulo
    "experiencia", "habilidade", "formacao", "educacao", "idioma",
    "objetivo", "qualificac", "profissional", "informacoes", "adiciona",
    "instituto", "mental", "caps", "voluntariado", "pesquisa",
)

_IDIOMAS_COMUNS = ("portugues", "ingles", "espanhol", "frances", "alemao", "italiano")


def _parece_nome(linha: str) -> bool:
    if not linha or len(linha) > 60 or any(c.isdigit() for c in linha):
        return False
    if "@" in linha or "|" in linha or "/" in linha or "http" in linha.lower():
        return False
    if re.search(r"[-–—]", linha) or ":" in linha or "(" in linha or ")" in linha:
        return False
    if any(p in _norm(linha) for p in _PALAVRAS_NAO_NOME):
        return False
    palavras = [p for p in re.split(r"\s+", linha) if p]
    if len(palavras) < 2:
        return False
    maiusculas = sum(1 for p in palavras if p[0].isupper())
    return maiusculas / len(palavras) >= 0.6


def _parece_titulo(linha: str) -> bool:
    if not linha or len(linha) > 80 or "@" in linha or "http" in linha.lower():
        return False
    return any(p in _norm(linha) for p in _PALAVRAS_CARGO)


def _candidato_nome(linha: str) -> str:
    """Isola o possível nome em linhas com colunas concatenadas ou prefixos.

    Ex.: "FULANO DE TAL      Casado, 12/06/1987" ou "Contato Fulano de Tal".
    """
    candidato = re.split(r"\s{2,}|\t", linha.strip())[0]
    candidato = re.sub(r"(?i)^contato\s+", "", candidato)
    # rótulo de formulário: "NOME COMPLETO Renata ..." / "NOMECOMPLETO Renata ..."
    candidato = re.sub(r"(?i)^nome(?:\s*completo)?\s*[:\-]?\s+", "", candidato)
    candidato = candidato.strip(" ,;.|")
    # "LEONARDONOGUEIRASOUZA": nome em caixa alta totalmente colado
    if re.fullmatch(r"[A-ZÀ-Ü]{10,}", candidato):
        segmentado = _segmentar_nome_colado(candidato)
        if segmentado:
            return segmentado
    return candidato


# prenomes e sobrenomes frequentes no Brasil, para segmentar nomes colados
_PARTES_NOME = frozenset((
    # prenomes
    "ana", "maria", "jose", "joao", "antonio", "francisco", "carlos", "paulo",
    "pedro", "lucas", "luiz", "luis", "marcos", "gabriel", "rafael", "daniel",
    "marcelo", "bruno", "eduardo", "felipe", "rodrigo", "manoel", "mateus",
    "matheus", "andre", "fernando", "fabio", "leonardo", "gustavo", "guilherme",
    "leandro", "tiago", "thiago", "ricardo", "vinicius", "diego", "sergio",
    "claudio", "samuel", "henrique", "alexandre", "murilo", "otavio", "davi",
    "david", "caio", "vitor", "victor", "igor", "renato", "renata", "juliana",
    "fernanda", "patricia", "aline", "sandra", "camila", "amanda", "bruna",
    "jessica", "leticia", "julia", "beatriz", "larissa", "mariana", "vanessa",
    "gabriela", "daniela", "carla", "debora", "sara", "sofia", "sophia",
    "helena", "alice", "laura", "isabela", "isabella", "luiza", "clara",
    "cecilia", "marina", "monica", "simone", "adriana", "cristiane",
    "cristina", "viviane", "tatiane", "regina", "rita", "rosa", "eduarda",
    "emilia", "clarice", "bianca", "erick", "lorenzo", "raquel", "priscila",
    "natalia", "michele", "michelle", "karina", "carolina", "isadora",
    "valentina", "miguel", "arthur", "artur", "bernardo", "heitor", "theo",
    "lorenzo", "benjamin", "nicolas", "joaquim", "emanuel", "raul", "cesar",
    "william", "wesley", "wallace", "jonathan", "jefferson", "anderson",
    "robson", "cleber", "everton", "elton", "edson", "wilson", "nelson",
    # sobrenomes
    "silva", "santos", "oliveira", "souza", "sousa", "rodrigues", "ferreira",
    "alves", "pereira", "lima", "gomes", "ribeiro", "carvalho", "almeida",
    "lopes", "soares", "fernandes", "vieira", "barbosa", "rocha", "dias",
    "nascimento", "andrade", "moreira", "nunes", "marques", "machado",
    "mendes", "freitas", "cardoso", "ramos", "goncalves", "santana",
    "teixeira", "araujo", "costa", "pinto", "martins", "melo", "castro",
    "campos", "correia", "correa", "cavalcante", "cavalcanti", "monteiro",
    "moura", "dantas", "nogueira", "batista", "barros", "franca", "franco",
    "pires", "azevedo", "cunha", "medeiros", "macedo", "torres", "reis",
    "aguiar", "farias", "miranda", "sales", "duarte", "brito", "fonseca",
    "magalhaes", "borges", "rezende", "resende", "sampaio", "assis",
    "tavares", "xavier", "peixoto", "porto", "bezerra", "trindade",
    "guimaraes", "leite", "coelho", "neves", "siqueira", "bastos", "queiroz",
    "prado", "amaral", "vasconcelos", "morais", "moraes", "paiva", "mota",
    "motta", "viana", "salgado", "neto", "filho", "junior",
))
_CONECTIVOS_NOME = ("de", "da", "do", "dos", "das", "e")


def _segmentar_nome_colado(token: str) -> str | None:
    """Divide "LEONARDONOGUEIRASOUZA" em "LEONARDO NOGUEIRA SOUZA".

    Programação dinâmica sobre um léxico de nomes comuns; só devolve algo se
    a string INTEIRA for segmentável em 2+ partes conhecidas.
    """
    s = _norm(token)
    n = len(s)
    melhor: dict[int, list[int]] = {0: []}
    for i in range(n):
        cortes = melhor.get(i)
        if cortes is None:
            continue
        for j in range(i + 2, n + 1):
            parte = s[i:j]
            if parte in _PARTES_NOME or parte in _CONECTIVOS_NOME:
                if j not in melhor or len(melhor[j]) > len(cortes) + 1:
                    melhor[j] = cortes + [j]
    cortes = melhor.get(n)
    if not cortes or len(cortes) < 2:
        return None
    pedacos, inicio = [], 0
    for fim in cortes:
        pedacos.append(token[inicio:fim])
        inicio = fim
    return " ".join(pedacos)


def _extrair_nome_e_titulo(preambulo: list[str]) -> tuple[str | None, str | None]:
    nome = None
    # padrões explícitos: "Candidato: Fulano" / "Fulano — 44 anos"
    for linha in preambulo[:12]:
        candidato = linha
        m_rotulo = _RE_CANDIDATO.match(linha)
        if m_rotulo:
            candidato = m_rotulo.group(1).strip()
        m_idade = _RE_NOME_IDADE.match(candidato)
        if m_idade:
            candidato = m_idade.group(1).strip()
        if (m_rotulo or m_idade) and _parece_nome(candidato):
            nome = candidato
            break
    if nome is None:
        for linha in preambulo[:5]:
            candidato = _candidato_nome(linha)
            if _parece_nome(candidato) and not _parece_titulo(candidato):
                nome = candidato
                break
    if nome is None:
        # nome quebrado em uma palavra por linha ("ALEXANDRA" / "PILAR")
        pedacos = []
        for linha in preambulo[:3]:
            if re.fullmatch(r"[A-Za-zÀ-ü'\-]{2,20}", linha.strip()):
                pedacos.append(linha.strip())
            else:
                break
        if len(pedacos) >= 2:
            candidato = " ".join(pedacos)
            if _parece_nome(candidato):
                nome = candidato
    if nome is None:  # fallback: primeira linha plausível, mesmo que pareça cargo
        for linha in preambulo[:3]:
            candidato = _candidato_nome(linha)
            if _parece_nome(candidato):
                nome = candidato
                break

    titulo = None
    for linha in preambulo[:6]:
        if linha != nome and _parece_titulo(linha):
            titulo = linha
            break
    return nome, titulo


def _nome_em_linhas(linhas: list[str]) -> str | None:
    """Nome em "banner": uma palavra MAIÚSCULA por linha ("ALEXANDRA"/"PILAR").

    Em PDFs de duas colunas o banner do topo pode cair no meio do texto,
    fora do preâmbulo. Procura sequências de 2+ linhas desse tipo.
    """
    sequencia: list[str] = []
    for linha in linhas + [""]:
        linha = linha.strip()
        if (
            re.fullmatch(r"[A-ZÀ-Ü][A-ZÀ-Ü'\-]{1,19}", linha)
            and not _chave_secao(linha)
            and _norm(linha) not in _IDIOMAS_COMUNS
        ):
            sequencia.append(linha)
            continue
        if len(sequencia) >= 2:
            candidato = " ".join(sequencia)
            if _parece_nome(candidato):
                return candidato
        sequencia = []
    return None


def _extrair_contato(texto_completo: str, linhas_contato: list[str]) -> Contato:
    contato = Contato()

    m = _RE_EMAIL.search(texto_completo)
    contato.email = m.group(0) if m else None

    m = _RE_LINKEDIN.search(texto_completo)
    contato.linkedin = m.group(0).rstrip(".,;") if m else None

    m = _RE_GITHUB.search(texto_completo)
    contato.github = m.group(0).rstrip(".,;") if m else None

    for url in _RE_URL.findall(texto_completo):
        if "linkedin.com" not in url.lower() and "github.com" not in url.lower():
            contato.site = url.rstrip(".,;")
            break

    spans_orcid = [m.span() for m in _RE_ORCID.finditer(texto_completo)]
    for m in _RE_TELEFONE.finditer(texto_completo):
        bruto = m.group(0)
        digitos = re.sub(r"\D", "", bruto)
        # evita confundir intervalos de anos (ex.: "2012-2016") com telefone
        if not (10 <= len(digitos) <= 13) or _RE_ANOS_INTERVALO.search(bruto):
            continue
        if any(ini < m.end() and m.start() < fim for ini, fim in spans_orcid):
            continue
        # trecho de uma sequência numérica maior (DOI, código de barras...)
        antes = texto_completo[m.start() - 1 : m.start()]
        depois = texto_completo[m.end() : m.end() + 1]
        if antes.isdigit() or depois.isdigit():
            continue
        contato.telefone = bruto.strip()
        break

    for linha in linhas_contato:
        m = _RE_CIDADE_UF.search(linha)
        if m:
            contato.cidade = m.group(1).strip()
            contato.estado = m.group(2)
            if m.group(3):
                contato.pais = m.group(3)
            break
    if contato.pais is None and re.search(r"\bbrasil\b", _norm(texto_completo)):
        contato.pais = "Brasil"

    return contato


# ----------------------------------------------------------------------
# Experiências
# ----------------------------------------------------------------------

def _complementar_experiencias_perdidas(
    experiencias: list[Experiencia], secoes: dict[str, list[str]],
) -> list[Experiencia]:
    """Recupera experiências deslocadas por PDF de colunas (ex.: após 'Idiomas')."""
    vistos = {(e.cargo, e.empresa, e.inicio) for e in experiencias}
    extras: list[Experiencia] = []
    for chave in ("idiomas", "contato", "preambulo"):
        linhas = secoes.get(chave, [])
        if not linhas:
            continue
        for exp in _extrair_experiencias(linhas, ano_solto=True):
            chave_exp = (exp.cargo, exp.empresa, exp.inicio)
            if chave_exp not in vistos and _experiencia_valida(exp):
                extras.append(exp)
                vistos.add(chave_exp)
    return experiencias + extras


def _extrair_experiencias(linhas: list[str], ano_solto: bool = False) -> list[Experiencia]:
    linhas = [_descolar_linha(l) for l in linhas]
    tabela, comuns = _separar_tabela(linhas)
    experiencias = _experiencias_de_tabela(tabela)
    experiencias += _experiencias_de_linhas(comuns, ano_solto)
    for exp in experiencias:
        exp.cargo = _descolar_cargo(exp.cargo)
        if exp.empresa:
            exp.empresa = _normalizar_empresa(_limpar_empresa_local(exp.empresa))
    return [e for e in experiencias if _experiencia_valida(e)]


def _separar_tabela(linhas: list[str]) -> tuple[list[str], list[str]]:
    tabela = [l for l in linhas if l.startswith("|")]
    comuns = [l for l in linhas if not l.startswith("|")]
    return tabela, comuns


def _experiencias_de_tabela(linhas_tabela: list[str]) -> list[Experiencia]:
    """Interpreta tabelas markdown (vindas de DOCX/PDF) com colunas nomeadas."""
    if len(linhas_tabela) < 2:
        return []

    def celulas(linha: str) -> list[str]:
        return [c.strip() for c in linha.strip("|").split("|")]

    cabecalho = [_norm(c) for c in celulas(linhas_tabela[0])]
    mapa: dict[int, str] = {}
    for i, col in enumerate(cabecalho):
        if "cargo" in col or "funcao" in col or "posicao" in col:
            mapa[i] = "cargo"
        elif "empresa" in col or "companhia" in col or "organizacao" in col:
            mapa[i] = "empresa"
        elif "periodo" in col or "data" in col or "duracao" in col:
            mapa[i] = "periodo"
        elif "descricao" in col or "atividade" in col or "responsabilidade" in col:
            mapa[i] = "descricao"
        elif "tecnologia" in col or "ferramenta" in col:
            mapa[i] = "tecnologias"
    if not mapa:
        return []

    experiencias = []
    for linha in linhas_tabela[1:]:
        if re.match(r"^\|[\s\-|]+\|?$", linha):  # separador |---|---|
            continue
        valores = celulas(linha)
        exp = Experiencia()
        for i, valor in enumerate(valores):
            campo = mapa.get(i)
            if not campo or not valor:
                continue
            if campo == "periodo":
                exp.inicio, exp.fim = _dividir_periodo(valor)
            elif campo == "tecnologias":
                exp.tecnologias = _dividir_lista(valor)
            else:
                setattr(exp, campo, valor)
        if exp.cargo or exp.empresa:
            experiencias.append(exp)
    return experiencias


def _experiencias_de_linhas(linhas: list[str], ano_solto: bool = False) -> list[Experiencia]:
    linhas = [l for l in linhas if l]
    if not linhas:
        return []

    # formulário de concurso ("ADMISSÃO ... / EMPREGADOR ... / CARGO/FUNÇÃO ...")
    if any(_RE_FORM_ADMISSAO.match(l) for l in linhas) and any(
        re.match(r"(?i)^empregador\b", l) for l in linhas
    ):
        return _experiencias_de_formulario(linhas)

    ancoras = _ancoras_experiencia(linhas, ano_solto)
    experiencias = []
    for n, (inicio_bloco, periodo) in enumerate(ancoras):
        fim_bloco = ancoras[n + 1][0] if n + 1 < len(ancoras) else len(linhas)
        # Em PDFs com colunas misturadas, podem existir linhas de sidebar entre
        # o cabeçalho e o período. Mantemos cabeçalho + linhas de cargo + período.
        bloco = [linhas[inicio_bloco]]
        for i in range(inicio_bloco + 1, periodo):
            if len(linhas[i]) <= 80 and (
                _tem_palavra_cargo(linhas[i]) or _parece_linha_empresa(linhas[i])
            ):
                bloco.append(linhas[i])
        if periodo != inicio_bloco:
            bloco.append(linhas[periodo])
        bloco.extend(linhas[periodo + 1 : fim_bloco])
        experiencias.append(_montar_experiencia(bloco, ano_solto))
    return experiencias


def _ancoras_experiencia(linhas: list[str], ano_solto: bool = False) -> list[tuple[int, int]]:
    """Cada período (ex.: "Mar/2021 - atual") ancora uma experiência.

    Devolve pares (índice do cabeçalho, índice do período). O cabeçalho com
    cargo/empresa pode estar na própria linha do período ou em linhas acima.
    Com ano_solto=True (seção de experiência explícita), "2020 Empresa, País"
    também ancora; fora dela, ano isolado nunca ancora (anos de formação).
    """
    ancoras: list[tuple[int, int]] = []
    for p, linha in enumerate(linhas):
        if linha.startswith("|"):
            continue
        m = _RE_PERIODO.search(linha) or _RE_DESDE.search(linha)
        if m:
            antes = _limpar_rotulo(linha[: m.start()])
            depois = _limpar_rotulo(linha[m.end():])
            # "📍 Brasília, DF" ao lado do período é localidade, não cabeçalho
            if depois and _RE_SO_LOCAL.match(depois):
                depois = ""
            if antes and _RE_SO_LOCAL.match(antes):
                antes = ""
        else:
            m = _match_data_solta(linha)
            if m is None and ano_solto:
                m = _RE_ANO_EMPRESA.match(linha)
                if m:
                    # layout acadêmico "2020 Empresa, País": a própria linha é o
                    # cabeçalho (o cargo vem DEPOIS; nunca buscar acima)
                    ultimo = ancoras[-1][0] if ancoras else -1
                    if p > ultimo:
                        ancoras.append((p, p))
                    continue
            elif m:
                antes = _limpar_rotulo(m.group("cabeca"))
                depois = ""
            if not m:
                continue
        cabeca = antes if len(antes) >= 4 else depois
        periodo_no_inicio = len(antes) < 4 and len(depois) >= 4
        ultimo_cab = ancoras[-1][0] if ancoras else -1
        ultimo_per = ancoras[-1][1] if ancoras else -1

        if cabeca and _tem_palavra_cargo(cabeca):
            cabecalho = p
            _, empresa = _dividir_cargo_empresa(cabeca)
            # "GERENTE GERAL OUT/2023 - ATUAL" com a empresa na linha anterior
            if empresa is None and p - 1 > ultimo_per and _parece_linha_empresa(linhas[p - 1]):
                cabecalho = p - 1
        elif periodo_no_inicio and not _chave_secao(cabeca):
            cabecalho = p  # "2020 - 2021 - EMPRESA": âncora forte na própria linha
            # "Teaching Assistant" / "2018-2020 Empresa": cargo curto logo acima
            if (
                p - 1 > ultimo_per
                and len(linhas[p - 1]) <= 60
                and not linhas[p - 1].endswith(".")
                and _parece_cabecalho_experiencia(linhas[p - 1])
                and _dividir_cargo_empresa(linhas[p - 1])[1] is None
            ):
                cabecalho = p - 1
        else:
            acima = _buscar_cabecalho_experiencia(linhas, p, depois_de=ultimo_per)
            if acima is not None and acima > ultimo_per:
                cabecalho = acima
                # estilo LinkedIn: "Empresa" / "Cargo" / "período" em 3 linhas
                if (
                    _dividir_cargo_empresa(linhas[acima])[1] is None
                    and acima - 1 > ultimo_per
                    and _parece_linha_empresa(linhas[acima - 1])
                    and not _tem_palavra_cargo(linhas[acima - 1])
                ):
                    cabecalho = acima - 1
            elif len(cabeca) >= 4 and not _chave_secao(cabeca):
                cabecalho = p
            elif (
                p - 1 > ultimo_per
                and _parece_linha_empresa(linhas[p - 1])
                # se a linha de baixo tem razão social (Ltda/S.A.), ela vence
                and not (
                    p + 1 < len(linhas)
                    and _RE_SUFIXO_EMPRESA.search(linhas[p + 1][:60])
                )
            ):
                cabecalho = p - 1
            else:
                cabecalho = p

        if _eh_cabecalho_interno(linhas[cabecalho]):
            cabecalho = p
        if cabecalho > ultimo_cab:
            ancoras.append((cabecalho, p))
    return ancoras


def _match_data_solta(linha: str) -> re.Match | None:
    """Match conservador de "Empresa – 12/24" (data única no fim da linha)."""
    m = _RE_DATA_SOLTA.match(linha)
    if not m:
        return None
    cabeca = m.group("cabeca").strip()
    # rejeita frases comuns: preposição antes da data ou palavras minúsculas
    if re.search(r"(?i)\b(em|no|na|de|do|da|ate|até|desde|por|a)$", cabeca):
        return None
    conectivos = {"de", "da", "do", "das", "dos", "e", "&"}
    for palavra in cabeca.split():
        if palavra.lower() in conectivos:
            continue
        if not (palavra[0].isupper() or palavra[0].isdigit()):
            return None
    return m


def _texto_cabecalho_inline(linha: str, m: re.Match) -> str:
    """Texto útil da linha do período (antes dele; senão, depois dele)."""
    antes = _limpar_rotulo(linha[: m.start()])
    depois = _limpar_rotulo(linha[m.end():])
    return antes if len(antes) >= 4 else depois


def _limpar_rotulo(texto: str) -> str:
    # pictogramas decorativos ("📅 04/2015", "📍 Brasília, DF")
    texto = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", " ", texto)
    texto = re.sub(r"\(\s*\)", " ", texto)          # parênteses esvaziados pelo período
    texto = texto.strip(" \t-–—|,•:")
    texto = re.sub(r"\(\s*\d{0,2}\s*$", "", texto)  # resto de "( 07" cortado pelo período
    texto = re.sub(r"^\)\s*", "", texto)
    # duração após o período: "(1 ano 8 meses)", "(9 meses)"
    texto = re.sub(r"(?i)^\(?\s*\d+\s*(?:anos?|m[eê]s(?:es)?)[^)]*\)?\s*", "", texto)
    # rótulos soltos que sobram quando o período é removido da linha
    texto = re.sub(r"(?i)\s*[-–—]?\s*local de trabalho\s*:.*$", "", texto)
    texto = re.sub(r"(?i)^per[ií]odos?$", "", texto)
    return texto.strip(" \t-–—|,•:")


def _tem_palavra_cargo(texto: str) -> bool:
    n = _norm(texto)
    return any(p in n for p in _PALAVRAS_CARGO)


_PREPOSICOES_COLADAS = ("das", "dos", "de", "da", "do")


def _descolar_token(token: str) -> str:
    """Separa preposição colada no fim de token ("Especialistaem" -> "Especialista em")."""
    if len(token) < 7 or not re.match(r"^[a-zA-Zà-üÀ-Ü]+$", token):
        return token
    baixo = token.lower()
    for prep in _PREPS_COLADAS_TOKEN:
        if baixo.endswith(prep) and len(token) > len(prep) + 4:
            return f"{token[: -len(prep)]} {prep}"
    return token


def _descolar_token_empresa(token: str) -> str:
    """De-glue agressivo em nomes de empresa/instituição colados pelo PDF."""
    if not token or not re.match(r"^[a-zA-Zà-üÀ-Ü0-9.&]+$", token):
        return token
    baixo = token.lower()
    # "Labde" -> "Lab de" (radical curto sem acento)
    m = re.match(r"^([a-z]{3,4})(de|da|do)$", baixo)
    if m and len(token) <= 5 and m.group(1) not in _BLOCKLIST_PREFIXO_PREP:
        return f"{token[: len(m.group(1))]} {m.group(2)}"
    if baixo.endswith("icae"):
        return token[:-1] + " e"
    for prep in ("no", "na"):
        if not baixo.endswith(prep) or len(token) <= len(prep) + 7:
            continue
        if prep == "na" and not re.search(r"[rstl]na$", baixo):
            continue
        if prep == "no" and not re.search(r"(?:itono|[st]no)$", baixo):
            continue
        return f"{token[: -len(prep)]} {prep}"
    return token


def _linha_eh_titulo_projeto(linha: str) -> bool:
    return bool(re.match(r"(?i)^projeto\s*:", linha.strip()))


def _normalizar_empresa(texto: str | None) -> str | None:
    if not texto:
        return texto
    texto = " ".join(_descolar_token_empresa(t) for t in texto.split())
    for pat, repl in _CORRECOES_EMPRESA:
        texto = pat.sub(repl, texto)
    return re.sub(r"\s{2,}", " ", texto).strip()


def _descolar_linha(linha: str) -> str:
    """Recupera espaços em linhas coladas (PDFs kickresume e similares)."""
    linha = _RE_COLA_TRAV_LINHA.sub(r" \1 ", linha)
    linha = _RE_COLA_HIFEN_LINHA.sub(" - ", linha)
    linha = _RE_COLA_PREP_LINHA.sub(r"\1 \2 ", linha)
    linha = re.sub(r"([a-zà-ü]{4,})(e)(?=[A-ZÀ-Ö])", r"\1 \2 ", linha)
    linha = _RE_COLA_CAMEL_LINHA.sub(" ", linha)
    return re.sub(r"\s{2,}", " ", linha).strip()


def _eh_cabecalho_interno(linha: str) -> bool:
    """Subseções dentro de experiência (VOLUNTARIADO, EXPERIÊNCIA DE PESQUISA...)."""
    if not linha or len(linha) > 60:
        return False
    compacto = re.sub(r"[^a-z]", "", _norm(linha))
    return compacto in _CABECALHOS_INTERNOS


def _parece_descricao(linha: str) -> bool:
    """Bullets e frases de responsabilidade não são cabeçalho de experiência."""
    linha = linha.strip()
    if not linha:
        return True
    if linha.startswith(("•", "–", "-", "*", "●")):
        return True
    if linha.endswith("."):
        return True
    if re.match(r"(?i)^(?:atuar|garantir|particip|respons|desenvolv|lider|organiz|manter|encontr)", linha):
        return True
    if re.match(r"(?i)^responsabilidades?\b", linha):
        return True
    return False


def _nome_do_email(email: str | None) -> str | None:
    """Infere nome a partir do local-part: daniel.nogueira50@gmail.com."""
    if not email or "@" not in email:
        return None
    partes = [p for p in re.split(r"[._\d]+", email.split("@", 1)[0]) if len(p) >= 2]
    if len(partes) < 2:
        return None
    candidato = " ".join(p.capitalize() for p in partes[:4])
    return candidato if _parece_nome(candidato) else None


def _descolar_cargo(texto: str | None) -> str | None:
    """Separa preposição colada ao fim de palavra de cargo ("Atendentede Caixa").

    Só divide quando o radical restante contém palavra do léxico de cargos,
    o que evita falsos positivos como "Universidade" ou "Grande".
    """
    if not texto:
        return texto
    saida = []
    for token in texto.split():
        for prep in _PREPOSICOES_COLADAS:
            radical = token[: -len(prep)]
            if (
                len(radical) >= 4
                and _norm(token).endswith(prep)
                and _tem_palavra_cargo(radical)
            ):
                token = f"{radical} {prep}"
                break
        saida.append(token)
    return " ".join(saida)


def _parece_cabecalho_experiencia(linha: str) -> bool:
    if not linha or len(linha) > 140 or linha.startswith("|") or _chave_secao(linha):
        return False
    if _eh_cabecalho_interno(linha) or _parece_descricao(linha):
        return False
    # rótulos internos do bloco anterior não podem virar cabeçalho do próximo
    if re.match(r"(?i)^(?:cargos?|fun[cç][aã]o|principais atividades|atividades)\b", linha):
        return False
    return _tem_palavra_cargo(linha)


def _parece_linha_empresa(linha: str) -> bool:
    linha = linha.strip()
    if not linha or len(linha) > 70 or linha.startswith(("|", "•", "–", "-", "*", "●")):
        return False
    if linha.endswith((".", ":", ";")) or "@" in linha or "http" in linha.lower():
        return False
    if _RE_PERIODO.search(linha) or _chave_secao(linha) or _eh_cabecalho_interno(linha):
        return False
    if _parece_descricao(linha):
        return False
    if _linha_eh_titulo_projeto(linha):
        return False
    # fragmento de bullet quebrado em linha isolada ("hora" de "última hora")
    if len(linha.split()) == 1 and len(linha) < 10 and linha.islower():
        return False
    return True


def _linha_fecha_bloco_anterior(linhas: list[str], inicio: int, fim: int) -> bool:
    """Empresa com separador entre cargo candidato e o período indica bloco anterior fechado."""
    for linha in linhas[inicio + 1 : fim]:
        if _parece_descricao(linha) or not linha.strip():
            continue
        if any(sep in linha for sep in _SEPARADORES):
            return True
        if _RE_SUFIXO_EMPRESA.search(linha[:80]):
            return True
    return False


def _buscar_cabecalho_experiencia(
    linhas: list[str], indice_periodo: int, depois_de: int = -1,
) -> int | None:
    # PDFs com colunas podem intercalar 1-3 linhas de sidebar antes do período.
    for i in range(indice_periodo - 1, max(depois_de, indice_periodo - 5), -1):
        if i <= depois_de:
            break
        if _RE_PERIODO.search(linhas[i]) or _RE_DESDE.search(linhas[i]):
            return None
        if _eh_cabecalho_interno(linhas[i]):
            return None
        if _parece_cabecalho_experiencia(linhas[i]):
            if _linha_fecha_bloco_anterior(linhas, i, indice_periodo):
                return None
            return i
        if linhas[i].endswith("."):
            return None
    return None


# título de curso, não de cargo: "Técnico em Mecânica", "Bacharelado em..."
_RE_TITULO_CURSO = re.compile(
    r"(?i)^(bacharel|licenciatura|gradua[cç]|mba\b|mestr|doutor|p[oó]s[- ]gradua"
    r"|ensino|curso|tecn[oó]logo|t[eé]cnico em)\b"
)


def _separar_formacao_de_experiencias(linhas: list[str]) -> tuple[list[str], list[str]]:
    """Corta a seção de formação na primeira âncora forte de experiência."""
    for cabecalho, periodo in _ancoras_experiencia(linhas):
        forte = (
            _tem_palavra_cargo(linhas[periodo])
            or _tem_palavra_cargo(linhas[cabecalho])
            or _RE_PREFIXO_EMPRESA.match(linhas[periodo]) is not None
            or _RE_PREFIXO_EMPRESA.match(linhas[cabecalho]) is not None
        )
        if not forte:
            # "EMPRESA – Nov/01 a Dez/03" seguido de "Cargo: ..." também é âncora forte
            forte = any(
                _RE_PREFIXO_CARGO.match(l) for l in linhas[periodo + 1 : periodo + 4]
            )
        if not forte:
            # cargo logo abaixo do período ("04/2021–01/2023" / "Analista de...")
            # desde que não seja título de curso ("Técnico em Mecânica")
            forte = any(
                _tem_palavra_cargo(l) and not _RE_TITULO_CURSO.match(l)
                for l in linhas[periodo + 1 : periodo + 3]
                if len(l) <= 70 and not l.endswith(".")
            )
        if not forte:
            # razão social (Ltda/S.A.) junto ao período também indica experiência
            vizinhanca = [linhas[cabecalho]] + linhas[periodo : periodo + 2]
            forte = any(_RE_SUFIXO_EMPRESA.search(l[:80]) for l in vizinhanca)
        if forte:
            return linhas[:cabecalho], linhas[cabecalho:]
    return linhas, []


_RE_LATTES_INSTITUICAO = re.compile(
    r"(?P<nome>[A-ZÀ-Ü][\w&à-üÀ-Ü/.\- ]{3,90}), (?P<sigla>[A-ZÀ-Ü][A-ZÀ-Ü0-9./ \-]{1,20}),"
    r" (?P<pais>[A-ZÀ-Ü][a-zà-ü]+)\."
)
_RE_LATTES_VINCULO = re.compile(r"V[ií]nculo institucional")
_RE_LATTES_PERIODO = re.compile(
    r"(?P<ini>(?:19|20)\d{2})\s*-\s*(?P<fim>(?:19|20)\d{2}|[Aa]tual)"
    r"(?:\s*V[ií]nculo:\s*(?P<vinc>[^,.\n]*))?"
    r"(?:[^\n]{0,80}?Enquadramento Funcional:\s*(?P<funcao>[^,.\n]*))?",
    re.S,
)


def _experiencias_lattes(texto: str) -> list[Experiencia]:
    """Vínculos da seção "Atuação Profissional" de um currículo Lattes.

    Formato fixo da plataforma: nome da instituição ("X, SIGLA, Brasil."),
    seguido de blocos "Vínculo institucional" com período, vínculo e
    enquadramento funcional. O pdfplumber duplica trechos em dumps de tabela,
    então a varredura é por posição no texto, com deduplicação.
    """
    if len(_RE_LATTES_VINCULO.findall(texto)) < 2:
        return []
    inicio = texto.find("Atuação Profissional")
    if inicio == -1:
        return []
    # não corta em seções seguintes: "Linhas de pesquisa", "Projetos" etc.
    # aparecem como subseções dentro da própria Atuação Profissional, e o
    # marcador "Vínculo institucional" já delimita o que interessa.
    trecho = texto[inicio:]

    instituicoes = [
        (m.start(), f"{m.group('nome').strip()} ({m.group('sigla')})")
        for m in _RE_LATTES_INSTITUICAO.finditer(trecho)
    ]
    experiencias: list[Experiencia] = []
    vistos: set[tuple] = set()
    for mv in _RE_LATTES_VINCULO.finditer(trecho):
        m = _RE_LATTES_PERIODO.search(trecho, mv.end(), mv.end() + 400)
        if not m:
            continue
        empresa = None
        for pos, nome_inst in instituicoes:
            if pos > mv.start():
                break
            empresa = nome_inst
        cargo = (m.group("funcao") or m.group("vinc") or "").strip(" -") or None
        # dumps de tabela do pdfplumber duplicam vínculos com texto levemente
        # diferente; deduplica por período + primeira palavra do cargo
        chave = (
            m.group("ini"),
            m.group("fim").lower(),
            # só os 6 primeiros caracteres: dumps truncam palavras ("Profess")
            _norm(cargo.split()[0])[:6] if cargo else (empresa or "").lower()[:20],
        )
        if chave in vistos:
            continue
        vistos.add(chave)
        experiencias.append(Experiencia(
            cargo=cargo,
            empresa=empresa,
            inicio=m.group("ini"),
            fim="atual" if m.group("fim").lower() == "atual" else m.group("fim"),
        ))
    return experiencias


_RE_FORM_ADMISSAO = re.compile(r"(?i)^admiss[aã]o\b\s*[:\-]?\s*(.*)$")
_RE_FORM_CAMPO = re.compile(
    r"(?i)^(desligamento|empregador|cargo\s*/?\s*fun[cç][aã]o|atividades?)\b\s*[:\-]?\s*(.*)$"
)


def _experiencias_de_formulario(linhas: list[str]) -> list[Experiencia]:
    """Formulário de processo seletivo com campos rotulados, um por linha:

    ADMISSÃO 2021-12 / DESLIGAMENTO atual / EMPREGADOR X / CARGO/FUNÇÃO Y /
    ATIVIDADES ...  Cada "ADMISSÃO" abre uma nova experiência.
    """
    experiencias: list[Experiencia] = []
    exp: Experiencia | None = None
    for linha in linhas:
        m_adm = _RE_FORM_ADMISSAO.match(linha)
        if m_adm:
            exp = Experiencia(inicio=m_adm.group(1).strip() or None)
            experiencias.append(exp)
            continue
        if exp is None:
            continue
        m = _RE_FORM_CAMPO.match(linha)
        if not m or not m.group(2).strip():
            continue
        campo, valor = _norm(m.group(1)), m.group(2).strip()
        if campo == "desligamento":
            _, exp.fim = _normalizar_fim(exp.inicio or "", valor)
        elif campo == "empregador":
            exp.empresa = valor
        elif campo.startswith("cargo"):
            exp.cargo = valor
        elif exp.descricao is None:
            exp.descricao = valor
    return [e for e in experiencias if e.empresa or e.cargo]


def _experiencias_rotuladas(linhas: list[str]) -> tuple[list[Experiencia], list[str]]:
    """Blocos "Empresa: X" / "Cargo: Y" / "Período: 7 meses" sem datas.

    Usado como último recurso quando nenhuma âncora de período foi achada
    (quem decide o mínimo de blocos para aceitar é o chamador).
    Devolve (experiências, linhas restantes antes do primeiro bloco).
    """
    indices = [i for i, l in enumerate(linhas) if _RE_PREFIXO_EMPRESA.match(l)]
    if not indices:
        return [], linhas
    experiencias = []
    for n, inicio in enumerate(indices):
        fim = indices[n + 1] if n + 1 < len(indices) else len(linhas)
        rotulo = _RE_PREFIXO_EMPRESA.match(linhas[inicio]).group(1)
        exp = Experiencia(empresa=_limpar_rotulo(rotulo) or None)
        descricao: list[str] = []
        for linha in linhas[inicio + 1 : fim]:
            m_cargo = _RE_PREFIXO_CARGO.match(linha)
            if m_cargo and exp.cargo is None:
                exp.cargo = m_cargo.group(1).strip()
                continue
            m_per = _RE_PREFIXO_PERIODO.match(linha)
            if m_per and exp.inicio is None:
                m_int = _RE_PERIODO.search(m_per.group(1))
                if m_int:
                    exp.inicio, exp.fim = _normalizar_fim(m_int.group(1), m_int.group(2))
                    continue
            descricao.append(linha)
        exp.descricao = " ".join(descricao).strip()[:1200] or None
        experiencias.append(exp)
    return experiencias, linhas[: indices[0]]


def _montar_experiencia(bloco: list[str], ano_solto: bool = False) -> Experiencia:
    exp = Experiencia()
    descricao: list[str] = []
    cargo_explicito = False  # cargo vindo de um rótulo "Cargo: ..." tem prioridade
    apos_periodo = -1  # índice da linha logo após a do período
    apos_cargo = -1  # índice da linha logo após um cargo pós-período

    for i, linha in enumerate(bloco):
        if linha.startswith("|"):
            continue
        m = None
        if exp.inicio is None:
            m = _RE_PERIODO.search(linha)
            if m:
                exp.inicio, exp.fim = _normalizar_fim(m.group(1), m.group(2))
            else:
                m = _RE_DESDE.search(linha)
                if m:
                    exp.inicio, exp.fim = _normalizar_fim(m.group(1), "atual")
                else:
                    m = _match_data_solta(linha)
                    if m is None and ano_solto:
                        m = _RE_ANO_EMPRESA.match(linha)
                        if m:
                            exp.inicio = m.group(1)
                    elif m:
                        exp.inicio = re.sub(r"\s*([./])\s*", r"\1", m.group("data"))
        if m:
            apos_periodo = i + 1
            if m.re is _RE_DATA_SOLTA:
                cabeca = _limpar_rotulo(m.group("cabeca"))
            elif m.re is _RE_ANO_EMPRESA:
                # "2020 Empresa, País": o resto é sempre empresa (nomes como
                # "X Architecture Consulting" têm palavra de cargo por engano)
                if exp.empresa is None:
                    exp.empresa = _limpar_rotulo(m.group("resto")) or None
                continue
            else:
                cabeca = _texto_cabecalho_inline(linha, m)
            if cabeca and _RE_SO_LOCAL.match(cabeca):
                cabeca = ""  # "• Curitiba, PR" ao lado do período é localidade
            if cabeca:
                m_emp = _RE_PREFIXO_EMPRESA.match(cabeca)
                if m_emp:
                    cargo, empresa = None, m_emp.group(1).strip()
                elif _tem_palavra_cargo(cabeca):
                    cargo, empresa = _dividir_cargo_empresa(cabeca)
                    # "Gerente Geral — Brasil e Cone Sul": região fica no cargo
                    if cargo and empresa and _parece_regiao(empresa):
                        cargo, empresa = _limpar_rotulo(cabeca), None
                else:
                    # sem palavra de cargo, "Empresa – Localidade" é tudo empresa
                    cargo, empresa = None, cabeca
                if exp.cargo is None:
                    exp.cargo = cargo
                if exp.empresa is None:
                    exp.empresa = empresa
            continue
        m_cargo = _RE_PREFIXO_CARGO.match(linha)
        if m_cargo:
            if exp.cargo is None or not cargo_explicito:
                exp.cargo = m_cargo.group(1).strip()
                cargo_explicito = True
            else:
                descricao.append(linha)
            continue
        m_emp_rotulo = _RE_PREFIXO_EMPRESA.match(linha)
        if m_emp_rotulo and exp.empresa is None:
            exp.empresa = m_emp_rotulo.group(1).strip()
            continue
        if i == 0:
            if _linha_eh_titulo_projeto(linha):
                descricao.append(linha)
                continue
            m_emp = _RE_PREFIXO_EMPRESA.match(linha)
            if m_emp:
                exp.empresa = m_emp.group(1).strip()
            else:
                exp.cargo, exp.empresa = _dividir_cargo_empresa(linha)
                # "Gerente Geral — Brasil e Cone Sul": região é parte do cargo,
                # não empresa (a empresa real vem em outra linha)
                if exp.cargo and exp.empresa and _parece_regiao(exp.empresa):
                    exp.cargo = _limpar_rotulo(linha)
                    exp.empresa = None
            continue
        m_tec = re.match(r"(?i)^(?:tecnologias|stack|ferramentas)\s*[:\-]\s*(.+)$", linha)
        if m_tec:
            exp.tecnologias = _dividir_lista(m_tec.group(1))
            continue
        # linha de cargo "solta" entre a empresa e o período (estilo LinkedIn)
        if (
            exp.inicio is None
            and exp.cargo is None
            and len(linha) <= 80
            and _tem_palavra_cargo(linha)
        ):
            exp.cargo = _limpar_rotulo(linha)
            continue
        # linha logo abaixo do período: cargo, ou "cargo — empresa" na mesma linha
        if i == apos_periodo and not _parece_descricao(linha) and not _eh_cabecalho_interno(linha):
            linha_d = _descolar_linha(linha)
            emp_principal = _empresa_principal_linha(linha_d)
            if emp_principal and exp.empresa is None:
                exp.empresa = emp_principal
                apos_cargo = i + 1
                continue
            prox = _descolar_linha(bloco[i + 1]) if i + 1 < len(bloco) else ""
            c, emp = _dividir_cargo_empresa(linha_d)
            # "Embaixador" / "CAPS — ..." sem palavra de cargo no léxico
            if (
                c is None
                and emp
                and prox
                and not any(s in linha_d for s in ("—", "–", " - ", "|"))
                and (
                    any(s in prox for s in ("—", "–", " - "))
                    or _parece_linha_empresa(prox)
                )
                and len(linha_d) <= 60
            ):
                if exp.cargo is None:
                    exp.cargo = _limpar_rotulo(linha_d)
                apos_cargo = i + 1
                continue
            if c and exp.cargo is None:
                exp.cargo = c
            if emp and exp.empresa is None:
                exp.empresa = emp
            if c or emp:
                apos_cargo = i + 1
                continue
            if (
                exp.cargo is None
                and len(linha_d) <= 100
                and _tem_palavra_cargo(linha_d)
            ):
                exp.cargo = _limpar_rotulo(linha_d)
                apos_cargo = i + 1
                continue
        # empresa logo abaixo do cargo ("período" / "Contador Trainee" / "Deloitte")
        if i == apos_cargo and exp.empresa is None and _parece_linha_empresa(linha):
            exp.empresa = linha.strip()
            continue
        # layout "Cargo — período" / "Empresa": linha logo após o período
        if (
            i == apos_periodo
            and exp.empresa is None
            and exp.cargo is not None
            and _parece_linha_empresa(linha)
            and not _tem_palavra_cargo(linha)
            and not _RE_SO_LOCAL.match(linha)
        ):
            exp.empresa = linha.strip()
            continue
        # layout "Cargo" / "Empresa" / "período": linha de empresa entre o
        # cabeçalho de cargo e o período
        if (
            exp.inicio is None
            and exp.cargo is not None
            and exp.empresa is None
            and _parece_linha_empresa(linha)
            and not _tem_palavra_cargo(linha)
        ):
            exp.empresa = linha.strip()
            continue
        descricao.append(linha)

    # empresa na linha seguinte ao "Cargo (período)": "LOJAS RIACHUELO S.A."
    if descricao and (exp.empresa is None or len(exp.empresa) <= 3):
        candidata = descricao[0].strip(" .;,")
        m_suf = _RE_SUFIXO_EMPRESA.search(candidata[:60])
        if m_suf and not _RE_PERIODO.search(candidata):
            exp.empresa = candidata[: m_suf.end()].strip(" .;,–-")
            resto_linha = candidata[m_suf.end():].strip(" .;,–-")
            descricao = ([resto_linha] if resto_linha else []) + descricao[1:]

    if exp.empresa and _linha_eh_titulo_projeto(exp.empresa):
        descricao.insert(0, exp.empresa)
        exp.empresa = None
    if exp.cargo and not exp.empresa:
        for linha in bloco:
            cand = _normalizar_empresa(linha.strip())
            if (
                cand
                and _parece_linha_empresa(cand)
                and not _linha_eh_titulo_projeto(cand)
                and not _tem_palavra_cargo(cand)
            ):
                exp.empresa = cand
                break

    exp.descricao = " ".join(descricao).strip() or None
    return exp


def _sem_prefixo_empresa(texto: str | None) -> str | None:
    """Remove o rótulo "Empresa:" do início ("Empresa: Estaleiro X" -> "Estaleiro X")."""
    if not texto:
        return texto
    m = _RE_PREFIXO_EMPRESA.match(texto)
    return m.group(1).strip() if m else texto


# regiões/abrangências que aparecem como complemento de cargo, não empresa
_PALAVRAS_REGIAO = frozenset((
    "brasil", "cone", "sul", "norte", "nordeste", "sudeste", "centro-oeste",
    "centro", "oeste", "leste", "europa", "america", "americas", "latina",
    "latam", "emea", "apac", "global", "internacional", "nacional", "regional",
    "mercosul", "africa", "asia", "oceania", "iberia", "andina", "caribe",
))
_CONECTIVOS_REGIAO = frozenset(("e", "de", "da", "do", "das", "dos", "&", "+"))


def _parece_regiao(texto: str) -> bool:
    """"Brasil e Cone Sul", "Nordeste", "América Latina" — abrangência, não empresa."""
    palavras = _norm(texto).replace(",", " ").split()
    if not palavras:
        return False
    relevantes = [p for p in palavras if p not in _CONECTIVOS_REGIAO]
    return bool(relevantes) and all(p in _PALAVRAS_REGIAO for p in relevantes)


def _empresa_principal_linha(linha: str) -> str | None:
    """"Empresa Ltda. – Grupo de 17 empresas" -> razão social à esquerda."""
    linha = _limpar_rotulo(linha)
    for sep in _SEPARADORES:
        if sep not in linha:
            continue
        esq, dir_ = (_limpar_rotulo(p) for p in linha.rsplit(sep, 1))
        if _RE_COMPLEMENTO_EMPRESA.match(_norm(dir_)):
            return (_sem_prefixo_empresa(esq) or "").rstrip(".")
    return None


def _limpar_empresa_local(texto: str | None) -> str | None:
    """Remove localidade colada à empresa ("Autônomo — Belém, PA" -> "Autônomo")."""
    if not texto:
        return texto
    principal = _empresa_principal_linha(texto)
    if principal:
        return principal
    for sep in _SEPARADORES:
        if sep not in texto:
            continue
        esq, dir_ = (_limpar_rotulo(p) for p in texto.rsplit(sep, 1))
        if _parece_regiao(dir_):
            return esq or None
        if _RE_SO_LOCAL.match(dir_):
            # "Autônomo — Belém, PA" perde só a cidade; instituições mantêm o sufixo
            if _norm(esq) in ("autonomo", "autonoma", "freelancer") or len(esq.split()) <= 2:
                return esq or None
    if _RE_SO_LOCAL.match(texto.strip()):
        return None
    return texto


def _experiencia_valida(exp: Experiencia) -> bool:
    if exp.cargo is None and exp.empresa is None:
        return False
    for campo in (exp.cargo, exp.empresa):
        if campo and _eh_cabecalho_interno(campo):
            return False
    if exp.cargo and _norm(exp.cargo).startswith("perfil"):
        return False
    if exp.empresa and _norm(exp.empresa).startswith("perfil"):
        return False
    # fragmentos de bullet/OCR colados ("ital", "hora"), não siglas (JSL, C&A)
    if exp.empresa:
        emp_n = _norm(exp.empresa)
        if emp_n in _FRAGMENTOS_EMPRESA:
            return False
        if len(exp.empresa) <= 4 and exp.empresa.lower() == exp.empresa:
            return False
        if re.search(r"\(\d{2}\)|\bru[aá]\b|@\w", emp_n):
            return False
    if exp.inicio and re.match(r"^\d{2}/\d{2}\s+\d{4}$", exp.inicio.strip()):
        return False
    return True


def _dividir_cargo_empresa(linha: str) -> tuple[str | None, str | None]:
    linha = _descolar_linha(_limpar_rotulo(linha))
    linha = " ".join(_descolar_token(t) for t in linha.split())
    if not linha:
        return None, None
    for sep in _SEPARADORES:
        if sep not in linha:
            continue
        esq, dir_ = (_limpar_rotulo(p) for p in linha.rsplit(sep, 1))
        if _tem_palavra_cargo(dir_):
            return _descolar_cargo(dir_), _limpar_empresa_local(_sem_prefixo_empresa(esq))
        if _tem_palavra_cargo(esq) and not _tem_palavra_cargo(dir_) and not _parece_regiao(dir_):
            return _descolar_cargo(esq), _limpar_empresa_local(_sem_prefixo_empresa(dir_))
        esq, dir_ = (_limpar_rotulo(p) for p in linha.split(sep, 1))
        if _tem_palavra_cargo(dir_) and not _tem_palavra_cargo(esq):
            return _descolar_cargo(dir_), _limpar_empresa_local(_sem_prefixo_empresa(esq))
        return _descolar_cargo(esq) if _tem_palavra_cargo(esq) else None, _limpar_empresa_local(_sem_prefixo_empresa(dir_))
    m = _RE_CARGO_FINAL.match(linha)
    if m:
        empresa, cargo = (_limpar_rotulo(p) for p in m.groups())
        return cargo, _sem_prefixo_empresa(empresa)
    if _tem_palavra_cargo(linha):
        return linha, None
    return None, _sem_prefixo_empresa(linha) or None


def _dividir_periodo(valor: str) -> tuple[str | None, str | None]:
    m = _RE_PERIODO.search(valor)
    if m:
        return _normalizar_fim(m.group(1), m.group(2))
    return (valor.strip() or None), None


def _normalizar_fim(inicio: str, fim: str) -> tuple[str, str]:
    if re.fullmatch(_FIM_ABERTO, fim.strip(), re.I):
        fim = "atual"
    # "07 / 2023" -> "07/2023"
    inicio = re.sub(r"\s*([./])\s*", r"\1", inicio.strip())
    fim = re.sub(r"\s*([./])\s*", r"\1", fim.strip())
    return inicio, fim


# ----------------------------------------------------------------------
# Formações
# ----------------------------------------------------------------------

def _extrair_formacoes(linhas: list[str]) -> list[Formacao]:
    formacoes = []
    for linha in linhas:
        linha = linha.strip("•-–⇨ ").strip()
        # linhas muito longas são parágrafos descritivos, não itens de formação
        if len(linha) < 5 or len(linha) > 160 or linha.startswith("|"):
            continue
        formacoes.append(_montar_formacao(linha))
    return [f for f in formacoes if f.curso or f.instituicao]


def _montar_formacao(linha: str) -> Formacao:
    formacao = Formacao()

    m = _RE_ANOS_INTERVALO.search(linha)
    if m:
        formacao.ano_inicio = m.group(1)
        fim = m.group(2)
        formacao.ano_fim = None if re.fullmatch(_FIM_ABERTO, fim, re.I) else fim
        linha = _RE_ANOS_INTERVALO.sub("", linha)
    else:
        anos = _RE_ANO.findall(linha)
        if anos:
            formacao.ano_fim = anos[-1]

    for situacao in _SITUACOES:
        m_sit = re.search(rf"\b{re.escape(situacao)}\b", _norm(linha))
        if m_sit:
            formacao.situacao = (
                "concluído" if situacao.startswith("conclu") else situacao
            )
            # remove a palavra da linha original (posições batem: _norm preserva o tamanho)
            linha = linha[: m_sit.start()] + linha[m_sit.end():]
            break

    partes = _dividir_por_separadores(linha)
    if partes:
        formacao.curso = partes[0] or None
        if len(partes) > 1:
            formacao.instituicao = partes[1] or None

    if formacao.curso:
        norm_curso = _norm(formacao.curso)
        for chave, nivel in _NIVEIS_FORMACAO:
            if chave in norm_curso:
                formacao.nivel = nivel
                break
    return formacao


def _dividir_por_separadores(linha: str) -> list[str]:
    for sep in _SEPARADORES:
        if sep in linha:
            return [p.strip(" -–—,()") for p in linha.split(sep) if p.strip(" -–—,()")]
    limpa = linha.strip(" -–—,()")
    return [limpa] if limpa else []


# ----------------------------------------------------------------------
# Habilidades, idiomas, certificações e listas genéricas
# ----------------------------------------------------------------------

def _dividir_lista(texto: str) -> list[str]:
    itens = re.split(r"[,;•|\n]", texto)
    resultado = []
    for item in itens:
        item = item.strip(" -–—\t.")
        if 1 < len(item) <= 60 and item not in resultado:
            resultado.append(item)
    return resultado


def _extrair_habilidades(linhas: list[str]) -> list[str]:
    return _dividir_lista(", ".join(l for l in linhas if not l.startswith("|")))


def _extrair_idiomas(linhas: list[str]) -> list[Idioma]:
    idiomas: list[Idioma] = []
    texto = " ".join(linhas)

    # Formato "Idioma (nível)" possivelmente em lista
    for m in re.finditer(r"([A-Za-zÀ-ü ]{3,30}?)\s*\(([^)]{2,30})\)", texto):
        idioma, nivel = m.group(1).strip(" ,;-"), m.group(2).strip()
        if idioma and _tem_nivel_idioma(nivel):
            idiomas.append(Idioma(idioma=idioma, nivel=nivel))

    if idiomas:
        return idiomas

    # Formato "Idioma - nível" / "Idioma: nível" por linha
    for linha in linhas:
        linha = linha.strip("•- ")
        m = re.match(r"([A-Za-zÀ-ü ]{3,30}?)\s*[:\-–]\s*(.+)$", linha)
        if m and _tem_nivel_idioma(m.group(2)):
            idiomas.append(Idioma(idioma=m.group(1).strip(), nivel=m.group(2).strip()))
        elif linha and len(linha) <= 30:
            idiomas.append(Idioma(idioma=linha))
    return idiomas


def _extrair_certificacoes(linhas: list[str]) -> list[Certificacao]:
    certificacoes = []
    for linha in linhas:
        linha = linha.strip("•- ").strip()
        if len(linha) < 3:
            continue
        ano = None
        m = _RE_ANO.search(linha)
        if m:
            ano = m.group(0)
            linha = (linha[: m.start()] + linha[m.end():]).strip(" -–—,")
        partes = _dividir_por_separadores(linha)
        nome = partes[0] if partes else linha
        emissor = partes[1] if len(partes) > 1 else None
        certificacoes.append(Certificacao(nome=nome, emissor=emissor, ano=ano))
    return certificacoes


def _extrair_itens(linhas: list[str]) -> list[str]:
    itens = []
    for linha in linhas:
        linha = linha.strip("•-– ").strip()
        if linha:
            itens.append(linha)
    return itens

"""Testes de regressao para padroes reais encontrados nos CVs."""
from leitor_cv.extracao import extrair_curriculo


def test_extrai_experiencias_com_titulo_experiencia_de_trabalho():
    texto = """
    ALEXANDRE BROLLO
    abrollo2012@gmail.com

    EXPERIENCIA DE TRABALHO
    Jardinagem
    Cavalos
    AB Contabil Diretor
    Academia
    2016 - Atual
    Gestao de equipe, relatorios e indicadores em BI.
    BCF Administradora de Bens Gerente de Projetos
    IDIOMAS 2022 - 2023
    Executei em paralelo atividades de implantacao de processos.
    HFLEX Empreendimentos- Grupo FMG Gerente de Area
    2016 - 2021
    Contratado em modelo PJ, responsavel pela implantacao dos condominios.
    Condominio Atmosfera Gerente Administrativo
    HABILIDADES 2012 - 2015
    Gerenciamento de equipes operacionais e fluxo de caixa.
    Condominio Estrelas Gerente Administrativo
    2010 - 2012
    Gestao de pessoas e reunioes de alinhamento.
    Hotel Golden Tulip Gerente Administrativo
    CAMPO PARA LEITURA IA 2008- 2010
    Controle de compras, custos e atendimento ao cliente.
    Gula Gula Gerente Administrativo
    2006 - 2008
    Controle de fluxo de caixa, DRE e reunioes com diretoria.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 7
    assert cv.experiencias[0].empresa == "AB Contabil"
    assert cv.experiencias[0].cargo == "Diretor"
    assert cv.experiencias[0].inicio == "2016"
    assert cv.experiencias[0].fim == "atual"
    assert cv.experiencias[1].empresa == "BCF Administradora de Bens"
    assert cv.experiencias[1].cargo == "Gerente de Projetos"


def test_experiencias_em_bullets_com_mes_numerico():
    # Padrao do AntonioBarros.pdf: tudo na mesma linha, datas "8/2025", "(02/2022 a 06/2022)"
    texto = """
    Antonio George Santos Barros
    tonirjbr@hotmail.com

    EXPERIENCIAS PROFISSIONAIS:
    - MS ARQUITETURA - GERENTE DE OBRAS - 8/2025 - ATUAL
    Compatibilizacao de projeto e planejamento da obra.
    - LECADO - SUPERVISOR OPERACIONAL - 10/2023 - 7-2025
    Gestao de equipe e controle de estoque.
    - Acailand - Consultor de Gestao Comercial - (02/2022 a 06/2022) - Loja Fechou
    Gestao administrativa, operacional e financeira.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 3
    assert cv.experiencias[0].empresa == "MS ARQUITETURA"
    assert cv.experiencias[0].cargo == "GERENTE DE OBRAS"
    assert cv.experiencias[0].inicio == "8/2025"
    assert cv.experiencias[0].fim == "atual"
    assert cv.experiencias[2].empresa == "Acailand"
    assert cv.experiencias[2].cargo == "Consultor de Gestao Comercial"


def test_experiencias_sem_titulo_apos_formacao_com_empresa_na_linha_anterior():
    # Padrao do av1_Curriculo Andre Cardoso.pdf: nao ha titulo "EXPERIENCIA";
    # o bloco vem depois da formacao, com empresa numa linha e cargo+periodo na seguinte.
    texto = """
    ANDRE CARDOSO
    FORMACAO ACADEMICA
    MBA em Gestao Comercial Fundacao Getulio Vargas - FGV
    Graduacao em Gestao de Negocios e Empreendedorismo - concluido em 2004. Unia
    TELHANORTE (SAINT GOBAIN)
    GERENTE GERAL OUT/2023 - ATUAL
    Responsavel pela gestao e planejamento estrategico da unidade.
    LEROY MERLIN
    GERENTE COMERCIAL AGO/2022 - SET/2023
    Gestao de equipe, compras e resultados.
    C&A
    GESTOR DE EQUIPE AGO/2001 - DEZ/2004
    Responsavel por departamentos e equipes operacionais.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 3
    assert cv.experiencias[0].empresa == "TELHANORTE (SAINT GOBAIN)"
    assert cv.experiencias[0].cargo == "GERENTE GERAL"
    assert cv.experiencias[0].inicio == "OUT/2023"
    assert cv.experiencias[0].fim == "atual"
    assert cv.experiencias[2].empresa == "C&A"
    assert cv.experiencias[2].cargo == "GESTOR DE EQUIPE"
    assert len(cv.formacoes) == 2


def test_experiencias_com_prefixo_cargo_e_periodo_no_inicio():
    # Padrao do CURRICULO PAULO TEIXEIRA: "2020 - 2021 - EMPRESA" e "Cargo: X" na linha seguinte
    texto = """
    Paulo Roberto da Silva Teixeira
    EXPERIENCIA PROFISSIONAL
    2020 - 2021 - UNINTER & Residencia Educacao (Polo Aracaju)
    Cargo: Gestor do Polo
    Principais Atividades: Responsavel pela capacitacao comercial dos colaboradores.
    2018 - 2020 - PRATIK GARDEN
    Cargo: Gerente Comercial
    Principais Atividades: Criacao da marca e do e-commerce.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].empresa == "UNINTER & Residencia Educacao (Polo Aracaju)"
    assert cv.experiencias[0].cargo == "Gestor do Polo"
    assert cv.experiencias[0].inicio == "2020"
    assert cv.experiencias[0].fim == "2021"
    assert cv.experiencias[1].empresa == "PRATIK GARDEN"
    assert cv.experiencias[1].cargo == "Gerente Comercial"


def test_periodos_por_extenso_com_de_estilo_linkedin():
    # Padrao dos exports do LinkedIn (Ricardo Almeida): "janeiro de 2024 - agosto de 2025"
    texto = """
    Ricardo Almeida
    Experiencia
    CiX - Citizen Experience
    Superintendente Administrativo
    janeiro de 2024 - agosto de 2025 (1 ano 8 meses)
    Gestao nacional da empresa.
    Grupo Viasul
    Diretor executivo
    fevereiro de 2022 - outubro de 2022 (9 meses)
    Gestao completa das operacoes.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].inicio == "janeiro de 2024"
    assert cv.experiencias[0].fim == "agosto de 2025"
    assert cv.experiencias[1].cargo == "Diretor executivo"


def test_separadores_alternativos_de_periodo():
    # "a" com crase (Jefferson), "/" espacado (Renato Baruel), "--" (Oine Mathias)
    texto = """
    Fulano de Tal
    Experiencia Profissional
    Operador de telemarketing - Teleperformance S.A - 12/2016 \u00e0 03/2021
    Atendimento por voz e redes sociais.
    Mudrost Engenharia
    Cargo: Engenheiro Civil
    Per\u00edodo: 03/2022 / Atual
    Execucao de obras publicas.
    Instrutor de cursos - Qualynorte (AM)- Ago/2022 -- Nov/2023
    Ferramentas da qualidade.
    """

    cv = extrair_curriculo(texto)

    periodos = {(e.inicio, e.fim) for e in cv.experiencias}
    assert ("12/2016", "03/2021") in periodos
    assert ("03/2022", "atual") in periodos
    assert ("Ago/2022", "Nov/2023") in periodos


def test_anos_com_dois_digitos_e_inicio_aberto_desde():
    # Anos curtos "01/24 a 03/25" (Weslley) e "desde 08/2024" (Sergio Franchi)
    texto = """
    Fulano de Tal
    Experiencia Profissional
    XCMG-Brasil \x96 01/24 a 03/25
    Gerente Comercial
    Mutare Desenvolvimento Humano \x96 desde 08/2024
    Diretor de Solucoes Empresariais
    """

    cv = extrair_curriculo(texto)

    periodos = {(e.inicio, e.fim) for e in cv.experiencias}
    assert ("01/24", "03/25") in periodos
    assert ("08/2024", "atual") in periodos


def test_blocos_rotulados_empresa_cargo_periodo_sem_datas():
    # Padrao do Raffael: "Empresa : X" / "Cargo : Y" / "Periodo : 7 meses",
    # sem intervalo de datas em nenhuma linha.
    texto = """
    Raffael Galvao Marques
    Experiencia Profissional
    Empresa : BUREAU VERITAS - (ATUAL)
    Cargo : Coordenador de Qualidade
    Periodo : 7 meses
    Atuacao em obras rodoviarias.
    Empresa : TUV Rheinland
    Cargo : Coordenador de Planejamento
    Periodo : 2 anos e 10 meses
    Gestao de ensaios e relatorios.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].empresa == "BUREAU VERITAS - (ATUAL)"
    assert cv.experiencias[0].cargo == "Coordenador de Qualidade"
    assert cv.experiencias[1].empresa == "TUV Rheinland"


def test_empresa_na_linha_seguinte_ao_cargo_com_periodo():
    # Padrao do Cristian: "Cargo (ago 2018 - out 2019)" com a razao social na linha de baixo
    texto = """
    Cristian Pinheiro
    Experiencia
    Operador de Caixa (out 2019 - fev 2022)
    LOJAS RIACHUELO S.A.
    Processamento de transacoes financeiras no caixa.
    Supervisor de Loja (fev 2022 - mar 2024)
    MARISA LOJAS S.A.
    Supervisao das operacoes diarias da loja.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].cargo == "Operador de Caixa"
    assert cv.experiencias[0].empresa == "LOJAS RIACHUELO S.A"
    assert cv.experiencias[1].empresa == "MARISA LOJAS S.A"


def test_experiencias_fora_de_secao_com_razao_social_apos_periodo():
    # Padrao do personal Book: periodo numa linha e "Empresa Ltda. - detalhes" na seguinte,
    # tudo dentro de outra secao (sem titulo de experiencia).
    texto = """
    Claudemir Morais Rodrigues
    Idiomas:
    Ingles - Intermediario
    Abril 2023 \u2014 marco de 2024
    Fluzao Atacadao da Construcao Ltda. \u2013 Grupo de 17 empresas
    Coordenacao de equipe de controladoria.
    Janeiro de 2022 \u2014 abril de 2023
    Lacca Distribuidora LTDA. \u2013 Grupo de 3 empresas
    Internalizacao da contabilidade.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].empresa == "Fluzao Atacadao da Construcao Ltda"
    assert cv.experiencias[0].inicio == "Abril 2023"
    assert cv.experiencias[1].empresa == "Lacca Distribuidora LTDA"


def test_tabelas_markdown_viram_linhas_e_nome_em_banner():
    # Celulas de tabela sem cabecalho nomeado devem virar texto; nome "ALEXANDRA"/"PILAR"
    # quebrado em duas linhas tambem deve ser reconhecido.
    texto = """
    ALEXANDRA
    PILAR
    | Experiencia Profissional |
    | Analista Operacional - Empresa Modelo - 2024 - 2025 |
    """

    cv = extrair_curriculo(texto)

    assert cv.nome_completo == "ALEXANDRA PILAR"
    assert len(cv.experiencias) == 1
    assert cv.experiencias[0].inicio == "2024"


def test_nome_em_relatorio_de_candidato():
    # Padrao dos BOOKs: "RELATORIO DO CANDIDATO" nao e nome; o nome vem em "Candidato: X - NN anos"
    texto = """
    RELATORIO DO CANDIDATO
    Gerente de Operacoes & Logistica
    Candidato: Andre Cardoso - 44 anos
    Resumo de trajetoria
    """

    cv = extrair_curriculo(texto)

    assert cv.nome_completo == "Andre Cardoso"
    assert cv.titulo_profissional == "Gerente de Operacoes & Logistica"


def test_cv_academico_ingles_ano_isolado_e_cargo_abaixo():
    # Estilo academico/LaTeX: "ANO Empresa, Pais" e o cargo na linha seguinte;
    # ano isolado so ancora DENTRO da secao de experiencia explicita.
    texto = """
    Andrei Bosco Bezerra Torres
    orcid.org/0000-0003-2334-1919
    Professional Experience
    2021-present Ontario Tech University, Ontario, Canada
    Graduate Research Assistant
    Conducting research studies related to gamification.
    2020 Palomino Sys, Ontario, Canada
    Research and Development internship
    Explored immersive visualization in virtual reality.
    2012 Studio PO, Ceara, Brazil
    CG Artist
    Researched and implemented 3D effects.
    Education
    2018-2022 Ph.D. in Computer Science, Ontario Tech University
    Languages
    Portuguese(native)
    English(professional proficiency-CLB9+)
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 3
    assert cv.experiencias[0].cargo == "Graduate Research Assistant"
    assert cv.experiencias[0].fim == "atual"
    assert cv.experiencias[1].empresa == "Palomino Sys, Ontario, Canada"
    assert cv.experiencias[1].inicio == "2020"
    assert cv.experiencias[2].cargo == "CG Artist"
    # ORCID nao pode virar telefone
    assert cv.contato.telefone is None
    # niveis de idioma em ingles
    assert any(i.idioma == "Portuguese" for i in cv.idiomas)
    # ano da formacao nao vira experiencia
    assert len(cv.formacoes) == 1


def test_formulario_concurso_admissao_empregador():
    texto = """
    ANEXO IV
    MODELO DE CURRICULO - PROCESSO SELETIVO
    DADOS PESSOAIS
    NOME COMPLETO Renata Nogueira Nogueira
    CIDADE/UF Porto Alegre/RS
    EXPERIENCIA PROFISSIONAL
    ADMISSAO 2021-12
    DESLIGAMENTO atual
    EMPREGADOR Mercado Envios
    CARGO/FUNCAO Conferente
    ATIVIDADES Apoio em inventarios ciclicos.
    ADMISSAO 2017-02
    DESLIGAMENTO 2021-02
    EMPREGADOR JSL
    CARGO/FUNCAO Conferente Junior
    ATIVIDADES Separacao de pedidos por coletor.
    """

    cv = extrair_curriculo(texto)

    assert cv.nome_completo == "Renata Nogueira Nogueira"
    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].empresa == "Mercado Envios"
    assert cv.experiencias[0].cargo == "Conferente"
    assert cv.experiencias[0].inicio == "2021-12"
    assert cv.experiencias[0].fim == "atual"
    assert cv.experiencias[1].empresa == "JSL"



def test_lattes_vinculos_institucionais():
    texto = """
    Filipe Maciel de Moura
    Endereço para acessar este CV: http://lattes.cnpq.br/123
    Atuação Profissional
    Universidade Estadual do Ceará, UECE, Brasil.
    Vínculo institucional
    2018 - Atual Vínculo: Doutorando em Geografia, Enquadramento Funcional: Pesquisador de Doutorado,
    Carga horária: 40, Regime: Dedicação exclusiva.
    Vínculo institucional
    2015 - 2017 Vínculo: Mestrando em Geografia, Enquadramento Funcional: Mestrando, Regime:
    Dedicação exclusiva.
    Companhia Hidro Elétrica do São Francisco, CHESF, Brasil.
    Vínculo institucional
    2012 - 2013 Vínculo: Estágio, Enquadramento Funcional: Estagiário, Carga horária: 30.
    Produções
    2020 Artigo sobre geoprocessamento. Revista X.
    2019 Outro artigo. Revista Y.
    2018 Mais um artigo. Revista Z.
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 3
    assert cv.experiencias[0].cargo == "Pesquisador de Doutorado"
    assert cv.experiencias[0].empresa == "Universidade Estadual do Ceará (UECE)"
    assert cv.experiencias[0].fim == "atual"
    assert cv.experiencias[2].empresa == "Companhia Hidro Elétrica do São Francisco (CHESF)"
def test_layout_periodo_cargo_empresa_voluntariado():
    # Padrao kickresume (078): periodo / cargo curto / empresa na linha seguinte
    texto = """
    Daniel Costa Nogueira
    EXPERIENCIA
    2020 - ATUAL
    Tutor Freelancer
    Autonomo - Belem, PA
    - Tutoria em Portugues e Matematica
    VOLUNTARIADO
    2021 - ATUAL BELEM, PA
    Embaixador
    CAPS - Centro de Atencao Psicossocial
      - Representou a instituicao em campanhas
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].cargo == "Tutor Freelancer"
    assert cv.experiencias[0].empresa == "Autonomo"
    assert cv.experiencias[1].cargo == "Embaixador"
    assert "CAPS" in (cv.experiencias[1].empresa or "")


def test_cargo_empresa_mesma_linha_colada_kickresume():
    # Padrao kickresume (084): cargo e empresa colados na mesma linha
    texto = """
    Carolina Teixeira Martins
    EXPERIENCIA DE TRABALHO
    JAN.2021 - ATUAL MACEIO, AL
    Especialistaem Suporteao Cliente Digital - i Food
    Responsabilidades principais:
    - Atender clientes via chat
    07/2018 - 01/2021 RECIFE, PE
    Agente de Suporte ao Cliente - Mercado Livre
    """

    cv = extrair_curriculo(texto)

    assert len(cv.experiencias) == 2
    assert cv.experiencias[0].cargo == "Especialista em Suporte ao Cliente Digital"
    assert cv.experiencias[0].empresa == "iFood"
    assert cv.experiencias[1].cargo == "Agente de Suporte ao Cliente"
    assert cv.experiencias[1].empresa == "Mercado Livre"

def test_normalizar_empresa_colada_kickresume():
    from leitor_cv.extracao import _normalizar_empresa

    assert _normalizar_empresa("Programa PIBIC — Realização Acadêmicae Inclusão") == (
        "Programa PIBIC — Realização Acadêmica e Inclusão"
    )
    assert _normalizar_empresa("Labde Preconceitono Ambiente de Trabalho") == (
        "Lab de Preconceito no Ambiente de Trabalho"
    )
    assert _normalizar_empresa("i Food") == "iFood"
    assert _normalizar_empresa("Merca do Livre") == "Mercado Livre"
    assert _normalizar_empresa("Racismo Estruturalna América Latina") == (
        "Racismo Estrutural na América Latina"
    )

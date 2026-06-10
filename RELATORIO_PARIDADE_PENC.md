# Relatório — Paridade do extrator heurístico do PENC com o `leitor_cv`

**Data:** 09/06/2026
**Escopo:** o que mudar no `penc/` (heurística v1, sem LLM) para alcançar o resultado
do `leitor_cv` no holdout real de 47 CVs (`CV Galpao/`, mesmo corpus do report 015).
**Autoria:** análise comparativa executada lado a lado, mesmo dataset, mesma régua.

---

## 1. Sumário executivo

Rodamos os dois extratores heurísticos sobre os **mesmos 47 CVs reais** e medimos
contra o mesmo baseline LLM (nome do candidato + nº de experiências por CV):

| Métrica (régua de contagem) | leitor_cv | penc heurístico | Delta |
|---|---|---|---|
| Experiências capturadas | **314/332 (95%)** | 216/332 (65%) | **+30 p.p.** |
| Nomes corretos | **47/47 (100%)** | 43/47 (91%) | +9 p.p. |
| CVs com 0 experiências extraídas | **0** | 4 | -4 |
| CVs com erro (formato) | **0** | 1 (JPG) | -1 |

> **Nota sobre métricas:** o scorecard interno do penc reporta `work_experience
> F1 = 0,01` para a heurística — métrica campo-a-campo (cargo+empresa+datas
> exatos vs ground truth). A régua deste relatório é mais permissiva (contagem
> de entries + nome por containment), mas é a MESMA para os dois lados, então a
> diferença relativa é real. As mudanças abaixo melhoram ambas as réguas, pois
> atacam o recall de entries (pré-condição de qualquer F1 de valor).

A diferença **não** vem de ML nem de mais código: vem de **cinco decisões de
desenho** da heurística. Todas são portáveis para o penc sem nova dependência
obrigatória, sem LLM e sem quebrar a arquitetura existente
(`StrategyExtractor` / parsers por seção).

---

## 2. Metodologia

- Corpus: 47 arquivos de `CV Galpao/` (PDF nato, PDF escaneado, DOCX, JPG,
  exports do LinkedIn, layouts 2-colunas/sidebar, CVs em tabela).
- Baseline: extração manual por LLM (nome + nº de experiências), registrada em
  `testes/galpao_llm_vs_app/comparativo_llm_vs_app.json`.
- penc executado via `parse_curriculum(path)` com estratégia default
  (`heuristic`), commit `629010b`.
- Resultado por CV em `testes/galpao_llm_vs_app/comparativo_penc.json`.

### Maiores perdas do penc por CV (entries capturadas)

| Arquivo | LLM | leitor_cv | penc | Causa-raiz (ver §3) |
|---|---|---|---|---|
| jaqueline-santos 2.pdf | 15 | 15 | 4 | âncora por dash não casa; datas "Set/2023" |
| av1_Currículo André Cardoso.pdf | 8 | 12 | 0 | sem título de seção; "CARGO PERÍODO" sem dash |
| CV_RAPHAEL RODRIGUES.pdf | 8 | 8 | 1 | datas variadas; header sem dash |
| Elton Nascimento.pdf | 8 | 8 | 1 | idem |
| CURRICULO VANDEI 08-07.docx | 6 | 6 | 1 | datas por extenso "ABRIL DE 2010" |
| Cristian Pinheiro (sidebar) | 5 | 5 | 1 | 2-colunas desligado por default; empresa na linha seguinte |
| Thiago Jacomassi.docx | 7 | 7 | 2 | blocos rotulados "Empresa:/Cargo:" |
| Eng.RenatoBaruel.pdf | 4 | 4 | 0 | separador "/" e datas espaçadas "07 / 2023" |
| Ricardo Almeida (LinkedIn) ×3 | 13 | 14 | 10 | datas "janeiro de 2024 - agosto de 2025 (1 ano 8 meses)" |
| CURRÍCULO RAFFAEL.pdf | 6 | 6 | 6* | (*penc acerta contagem aqui; manter) |

### Nomes que o penc erra

| Arquivo | penc | Causa |
|---|---|---|
| Currículo Alexandra Pilar .pdf | `None` | nome em banner "ALEXANDRA"/"PILAR" (1 palavra/linha), 2 colunas |
| FELIPE BERNARDO...docx | `None` | nome concatenado com estado civil na mesma linha |
| PEDRO HENRIQUE MENDES.pdf | `"F o r m a ç õ e s"` | texto espaçado letra a letra; falta filtro anti-cabeçalho |
| Valtemir.Santos_CV_2025.docx | `None` | nome + "Brasileiro, ..." na mesma linha (tab) |

---

## 3. Diagnóstico — as cinco causas-raiz

### 3.1 (CRÍTICA) Âncora de entry errada: dash em vez de período

`parsers/experience.py` ancora cada experiência na linha
`"Cargo — Empresa"` (`_ENTRY_HEADER = ^(.+?)\s+[—–-]\s+(.+)$`). Isso só
funciona quando o CV usa exatamente esse layout. Nos 47 CVs reais, a maioria
usa variações sem dash ("EMPRESA" numa linha, "CARGO out/2023 - atual" na
outra; "Cargo (ago 2018 - out 2019)"; "Período: 03/2022 / Atual"; etc.).

**O leitor_cv inverte a âncora: o RANGE DE DATAS é a âncora** (todo CV data
suas experiências; quase nenhum usa dash consistente). O cabeçalho
(cargo/empresa) é resolvido ao redor da âncora:
na própria linha (antes/depois do range), em até 4 linhas acima
(pulando linhas de sidebar), na linha imediatamente anterior
(empresa em linha própria) ou na linha seguinte (razão social `Ltda/S.A.`).

É a mudança de maior impacto isolado: explica ~2/3 do gap.

### 3.2 (CRÍTICA) Gramática de datas estreita

Os patterns do penc (`parsers/patterns.py` + regexes locais de
`experience.py`) não cobrem formatos frequentes no corpus real:

| Formato real (corpus) | Exemplo | penc | leitor_cv |
|---|---|---|---|
| Mês por extenso com "de" | `janeiro de 2024 - agosto de 2025` | parcial | OK |
| Duração após o range | `... (1 ano 8 meses)` | vira ruído | OK (removida) |
| Ano 2 dígitos | `Nov/01 a Dez/03`, `01/24 a 03/25` | não | OK |
| Separador espaçado | `07 / 2023`, `2024- 2025` | não | OK (normalizado) |
| Crase/até/duplo-dash | `12/2016 à 03/2021`, `Ago/22 -- Nov/23` | não | OK |
| Fim aberto amplo | `o momento`, `dias atuais`, `em andamento` | parcial | OK |
| Início aberto | `desde 08/2024` | não | OK (fim=atual) |
| Vírgula/parêntese antes de fim aberto | `Fev/2024, Atual`, `2025 (ATUAL)` | não | OK |
| Underscore | `Out_2024` | não | OK |

### 3.3 (ALTA) Reading-order geométrico existe, mas está DESLIGADO

`extractors/reading_order.py` já implementa a linearização por calha
(Estudo 003) — porém `Settings.reading_order` default é `"off"`
(`core/config.py`). Resultado: nos PDFs sidebar/2-colunas (20% do corpus,
medido no próprio Estudo 003) o `identify_sections` recebe texto embaralhado
e a seção `experience` vem truncada ou vazia (caso Cristian: 1/5).

No leitor_cv a divisão de colunas é **default-on** com guardas equivalentes
(calha sem palavras cruzando, mínimo de palavras por lado, filtro
anti-coluna-de-datas) e não regrediu nenhum CV de 1 coluna do corpus.

### 3.4 (ALTA) Sem recuperação de experiências fora da seção rotulada

O penc só extrai experiência do body da seção `experience` retornada por
`identify_sections`. Nos CVs sem título de seção (André Cardoso: 0 entries),
com título não-padrão, ou com o histórico "colado" em outra seção após quebra
de página (personal Book: histórico dentro de "Idiomas:"), o recall é zero.

O leitor_cv tem três fallbacks encadeados, todos com salvaguardas:

1. **Corte por âncora forte**: varre as demais seções (formação, resumo,
   adicionais, idiomas, habilidades, certificações, preâmbulo) procurando a
   primeira âncora de período "forte" (linha com palavra de cargo, prefixo
   `Cargo:`/`Empresa:` próximo, ou razão social `Ltda/S.A.` na vizinhança) e
   corta a seção ali: a cauda vira input do parser de experiência, a cabeça
   permanece na seção original. Sem âncora forte, não corta (formações com
   anos não viram experiência).
2. **Blocos rotulados**: `Empresa: X` / `Cargo: Y` / `Período: 7 meses`
   (sem range de datas!) — exige 2 ou mais blocos no documento para aceitar;
   blocos podem estar repartidos entre seções (quebra de página).
3. **Empresa por razão social**: se a entry ficou sem empresa e a primeira
   linha da descrição contém sufixo societário (`Ltda`, `S.A.`, `S/A`,
   `EIRELI`, `MEI`) nos primeiros 60 chars, promove o trecho a empresa.

### 3.5 (MÉDIA) Estruturas que o texto linear não carrega

- **Tabelas**: pypdfium2/mammoth devolvem texto corrido; CVs montados
  inteiramente em tabelas DOCX (personal Book, CV_Bage) chegam com células
  coladas numa linha só. O leitor_cv (a) extrai tabelas como estrutura
  (pdfplumber `extract_tables` no PDF; células do DOCX preservando quebras
  internas) e (b) "explode" células em linhas comuns com dedupe contra o
  texto corrido (tabelas de PDF duplicam conteúdo já extraído).
- **OCR**: o penc é digital-only (ADR 0004). No corpus há 1 JPG e PDFs
  escaneados, que dão 0 entries por definição. O leitor_cv usa tesseract
  (por+eng) com heurística de detecção (<40 chars/página indica escaneado).

---

## 4. Mudanças recomendadas no penc (por módulo)

Ordenadas por impacto/esforço. Estimativas de ganho calculadas reprocessando
o corpus real com cada técnica isolada no leitor_cv.

### P0-1 — Reescrever âncora de entry para "período-primeiro"
**Módulo:** `services/parsers/experience.py`
**Ganho estimado:** +18–20 p.p. de recall de entries (~60–70 entries)

1. Criar `find_period_anchors(lines) -> list[(header_idx, period_idx)]`:
   - âncora = linha com match de `DATE_RANGE` ampliado (ver P0-2) ou `desde <data>`;
   - cabeçalho resolvido nesta ordem:
     a. texto útil na própria linha (antes do range; senão, depois);
     b. se contém palavra de cargo, é o cabeçalho; se além disso não tem
        empresa e a linha anterior parece "linha de empresa" (curta, sem
        pontuação final, sem range, sem alias de seção), o cabeçalho passa a
        ser a linha anterior (par empresa/cargo em linhas separadas);
     c. senão, procurar até 4 linhas acima por linha com palavra de cargo
        (pula linhas de sidebar intercaladas — comum em PDFs de colunas),
        rejeitando rótulos internos (`Cargo:`, `Atividades:`);
     d. fallback: a própria linha do período.
   - invariante anti-sobreposição: o cabeçalho de uma âncora nunca recua para
     antes do período da âncora anterior.
2. Montar a entry com o bloco `[cabeçalho .. próxima âncora)`:
   - range vira `start_date/end_date` (normalizar fim aberto para `atual`;
     remover espaços em separadores: `07 / 2023` vira `07/2023`);
   - `Cargo:`-prefixado tem prioridade sobre cargo inferido;
   - linha "solta" de cargo entre empresa e período (estilo LinkedIn:
     Empresa / Cargo / período em 3 linhas) vira `position`;
   - separar cargo×empresa na linha única testando o ÚLTIMO separador
     primeiro (`" — ", " – ", " - ", " | "`): se o lado direito tem palavra de
     cargo, ele é o cargo mesmo que o esquerdo também tenha
     ("MS ARQUITETURA - GERENTE DE OBRAS");
   - manter o léxico de palavras de cargo num catálogo
     (`parsers/catalogs.py`) — o nosso tem ~35 lemas, incluindo
     `superintendente, encarregado, almoxarife, comprador, recepcionista,
     controller, instrutor`.
3. Manter os modos atuais (tabular ADMISSÃO/… e header com dash) como
   detectores que rodam ANTES; o período-primeiro é o caminho geral.

Referência de implementação: `leitor_cv/extracao.py` ->
`_ancoras_experiencia`, `_montar_experiencia`, `_dividir_cargo_empresa`
(funções puras, sem dependências — port direto).

### P0-2 — Ampliar a gramática de datas
**Módulo:** `services/parsers/patterns.py`
**Ganho estimado:** +6–8 p.p. (incluído em parte no P0-1; medido junto)

Gramática de referência (validada no corpus, em sintaxe Python):

```python
MES  = r"(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-zç]*"
ANO  = r"(?:19|20)\d{2}"
DATA = (rf"(?:\d{{1,2}}\s*[./-]\s*){{0,2}}(?:{MES}[._/\s]*(?:de\s+)?)?{ANO}"
        rf"|(?:{MES}|\d{{1,2}})\s*[/.]\s*\d{{2}}(?!\d)")          # Nov/01, 01/24
FIM_ABERTO = (r"atual(?:mente)?|presente|hoje|(?:o\s+)?momento"
              r"|(?:os\s+)?dias\s+atuais|em\s+andamento|current|present")
SEP = (rf"(?:[-–—]{{1,2}}(?:\s*at[eé](?:\s+o)?)?|at[eé](?:\s+o)?|à|a\b|/"
       rf"|,(?=\s*(?:{FIM_ABERTO}))|\((?=\s*(?:{FIM_ABERTO})))")
RANGE = rf"(?i)\b({DATA})\s*{SEP}\s*({DATA}|{FIM_ABERTO})\b"
DESDE = rf"(?i)\bdesde\s+({DATA})\b"      # início aberto -> end = "atual"
```

Pós-processamento obrigatório: remover duração entre parênteses após o range
(`"(1 ano 8 meses)"`, `"(9 meses)"`) antes de interpretar o resto da linha
como cargo/empresa.

### P0-3 — Ligar `reading_order=geometric` por default
**Módulo:** `core/config.py` (1 linha) + validação dos limiares
**Ganho estimado:** +4–6 p.p. de entries e +3 nomes

O código já existe e foi validado no Estudo 003. Ajustes que aplicamos no
equivalente nosso e que valem revisar nos limiares do penc:

- aceitar **sidebar estreita**: lado menor com 15+ palavras e 5%+ do total
  (o default `_MIN_SIDE_WORDS_FRAC = 0.10` perde a sidebar do CV do Cristian,
  que tem 27/320, cerca de 8%);
- rejeitar "coluna de datas": exigir que 50%+ das palavras do lado menor
  tenham 3+ caracteres alfabéticos (senão um CV com anos alinhados à direita
  é fatiado e as datas se separam dos cargos);
- tolerar 1–2% de palavras cruzando a calha (título/banner no topo).

Caso a flag global preocupe, ligar apenas quando a seção `experience` sair
vazia na primeira passada (retry com reordenação) — zero risco de regressão.

### P1-1 — Fallbacks de recuperação de experiência
**Módulos:** `services/curriculum_service.py` + `parsers/experience.py`
**Ganho estimado:** +5–7 p.p. (André Cardoso 0 para 8+, Thiago 2 para 7, personal Book)

Encadear após a extração normal, SOMENTE se `work_experience == []`:

1. **Corte por âncora forte** nas demais seções (ordem: education, summary,
   additional, languages, skills, certifications, header-body):
   - âncora forte = período + (palavra de cargo na linha/cabeçalho, OU
     `Cargo:` em até 3 linhas abaixo, OU prefixo `Empresa:`, OU razão social
     `Ltda|S\.A\.|S/A|EIRELI` nos primeiros 80 chars da vizinhança);
   - a cauda da seção vai para o parser de experiência; a cabeça permanece.
2. **Blocos rotulados** `Empresa:/Cargo:/Período:` sem range de datas:
   - aceitar apenas com 2+ blocos no documento (anti-falso-positivo);
   - blocos podem estar repartidos entre seções;
   - `Período: 7 meses` (duração, não range) gera datas nulas e a duração
     vai para o summary.
3. **Promoção de empresa por razão social** na 1ª linha do summary quando a
   entry ficou sem empresa (ou com empresa de até 3 chars).

### P1-2 — Tabelas como estrutura (PDF e DOCX)
**Módulos:** `extractors/pdf.py`, `extractors/docx.py`
**Ganho estimado:** +3–4 p.p. + 1 nome (personal Book 4 para 9, CV_Bage nome)

- **PDF**: pdfplumber já é dependência (fallback). Extrair
  `page.extract_tables()` além do texto; serializar células como linhas
  próprias com **dedupe por texto normalizado** contra o corpo da página
  (pdfplumber duplica o conteúdo da tabela no `extract_text`).
- **DOCX**: mammoth lineariza tabelas. Usar python-docx (já auxiliar) para
  tabelas: dedupe de células mescladas (a mesma célula repete em
  `row.cells`); se alguma célula tem `\n` ou mais de 100 chars, é **tabela de
  layout**: emitir o texto da célula preservando quebras internas (o CV
  inteiro pode morar numa célula); senão manter o formato tabular atual.

### P1-3 — Cascata de extração de nome
**Módulos:** `parsers/header.py`, `extractors/name_resolution.py`
**Ganho:** 43/47 para 47/47 no corpus

Adicionar à cascata existente (heurística + geometria ADR 0005):

1. **Cortar colunas concatenadas** antes de testar a linha: dividir em
   `\s{2,}|\t` e testar o primeiro segmento
   (`"FELIPE BERNARDO ...      Casado, 12/06/1987"` vira Felipe; Valtemir idem).
2. Remover prefixo `Contato ` (LinkedIn serializa "Contato" + nome).
3. **Banner multi-linha**: 2+ linhas consecutivas de UMA palavra MAIÚSCULA
   cada (2+ chars, sem ser alias de seção nem nome de idioma), juntar
   ("ALEXANDRA"/"PILAR").
4. Endurecer `is_probable_person_name`: rejeitar linha com `/`, `:`, `(`,
   `)`, ` - `, dígitos, e palavras de bloqueio
   (`competências, relatório, currículo, brasileiro(a), casado(a), ...`) —
   evita `"F o r m a ç õ e s"` (normalizar espaços letra-a-letra antes).
5. **Fallback global**: se nada achado no header, varrer as primeiras ~80
   linhas; preferir candidato cuja linha seguinte parece headline de cargo
   (nome no topo da coluna principal em exports LinkedIn).

### P2-1 — OCR opt-in (decisão de produto)
**Módulos:** novo `extractors/ocr.py` + `core/config.py`
**Ganho:** +2–3 p.p. + suporte a JPG/PNG (1 arquivo do corpus + escaneados)

Conflita com o ADR 0004 (digital-only) — portanto é decisão, não bug:

- flag `OCR_ENABLED=false` default; quando ligada, heurística de detecção
  (<40 chars/página em mais de 50% das páginas: rasterizar a 300dpi e aplicar
  tesseract `por+eng`);
- licenças OK para o gate do penc: tesseract = Apache-2.0;
  pdf2image = MIT. Atenção: pdf2image invoca o binário `poppler`
  (GPL-2) **via subprocess** — não há linking, mas o time deve registrar a
  avaliação jurídica no ADR; alternativa permissiva: rasterizar com o próprio
  pypdfium2 (`render()`), eliminando o poppler.

### P2-2 — Higiene de rótulos
**Módulo:** `parsers/experience.py` (função de limpeza compartilhada)

Pequenos ganhos de precisão de valor (afetam o F1 do scorecard):

- remover restos do recorte do período: parênteses esvaziados `"( )"`,
  `"( 07"` truncado, `")"` inicial;
- remover rótulo `Período`/`Períodos` que sobra quando o range é removido;
- remover cauda `"- Local de trabalho: ..."`;
- strip de `Empresa:` no valor final de company;
- normalizar `2024- 2025` para `2024 - 2025` antes do match.

---

## 5. Plano de execução sugerido

| Fase | Itens | Esforço | Recall esperado (régua de contagem) |
|---|---|---|---|
| 1 | P0-1 + P0-2 (âncora por período + datas) | 2–3 dias + testes | 65% para ~85% |
| 2 | P0-3 (reading order on) + P1-1 (fallbacks) | 1–2 dias | ~85% para ~91% |
| 3 | P1-2 (tabelas) + P1-3 (nomes) | 1–2 dias | ~91% para ~94% + nomes 100% |
| 4 | P2-1 (OCR opt-in) + P2-2 (higiene) | 1 dia | ~94% para ~95–96% |

Critérios de aceite por fase (usar a infra de benchmark já existente do penc):

1. `make benchmark DATASET=fixtures STRATEGY=heuristic` sem regressão;
2. rodar o manifest do holdout real (47 CVs) e comparar `work_experience`
   count-recall e F1 com o baseline da fase anterior;
3. todo padrão novo ganha fixture sintética em `tests/fixtures/` +
   teste unitário do parser (mesma disciplina dos 12 testes de regressão do
   `leitor_cv`, que cobrem: datas LinkedIn, separadores alternativos, anos de
   2 dígitos, "desde", blocos rotulados, empresa na linha seguinte,
   experiência fora de seção, tabela markdown, nome em banner).

---

## 6. Riscos e salvaguardas

| Risco | Salvaguarda (já validada no leitor_cv) |
|---|---|
| Formações com anos virarem experiência nos fallbacks | corte só em âncora FORTE (cargo/razão social/rótulo); ano isolado nunca ancora |
| Reading-order fatiar CV de 1 coluna | exigir calha sem palavras cruzando + 15+ palavras e 50%+ alfabéticas no lado menor |
| Dedupe de tabela descartar conteúdo legítimo | dedupe por texto normalizado exato, por documento |
| Blocos rotulados gerarem falso positivo | exigir 2+ blocos `Empresa:` |
| Data solta no fim da linha (P0-2) ancorar frases | aceitar apenas mês/ano (nunca ano isolado), rejeitar preposição antes da data e palavras minúsculas no prefixo |
| Regressão no scorecard F1 | benchmark gate por fase (infra `benchmark/` do penc já cobre) |

---

## 7. Apêndice — mapa de portabilidade

| Técnica | Onde está no leitor_cv (`leitor_cv/extracao.py` / `ingestao.py`) | Destino no penc |
|---|---|---|
| Âncoras por período | `_ancoras_experiencia`, `_RE_PERIODO`, `_RE_DESDE` | `parsers/experience.py` |
| Montagem da entry | `_montar_experiencia`, `_texto_cabecalho_inline` | `parsers/experience.py` |
| Cargo vs empresa | `_dividir_cargo_empresa`, `_RE_CARGO_FINAL`, `_SEPARADORES` | `parsers/experience.py` + `catalogs.py` |
| Gramática de datas | `_DATA`, `_SEP_PERIODO`, `_FIM_ABERTO`, `_normalizar_fim` | `parsers/patterns.py` |
| Corte por âncora forte | `_separar_formacao_de_experiencias` | `curriculum_service.py` |
| Blocos rotulados | `_experiencias_rotuladas`, `_RE_PREFIXO_EMPRESA/_PERIODO` | `parsers/experience.py` |
| Empresa por razão social | `_RE_SUFIXO_EMPRESA` + promoção no `_montar_experiencia` | `parsers/experience.py` |
| Divisão de colunas | `_detectar_corte_colunas`, `_texto_pagina` (`ingestao.py`) | `extractors/reading_order.py` (ajustar limiares) |
| Tabelas PDF/DOCX | `_tabelas_para_markdown`, `_tabela_docx_para_markdown`, `_explodir_tabelas` | `extractors/pdf.py`, `extractors/docx.py` |
| Cascata de nome | `_extrair_nome_e_titulo`, `_candidato_nome`, `_nome_em_linhas`, `_parece_nome` | `parsers/header.py`, `name_resolution.py` |
| OCR | `_ocr_pdf`, `_ocr_imagem_pil` (`ingestao.py`) | novo `extractors/ocr.py` (opt-in) |

Dados completos da comparação: `testes/galpao_llm_vs_app/comparativo_penc.json`
(por CV: nome/contagem do LLM, do leitor_cv e do penc).

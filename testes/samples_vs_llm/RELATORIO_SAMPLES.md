# Benchmark: pasta `samples/` — leitor_cv vs referência (gabarito + LLM)

Data: 10/06/2026 (3ª rodada, após melhorias). Escopo: 599 currículos de `~/Downloads/samples`.

- **Com gabarito embutido** (`dataset.json`, equivale a um baseline LLM perfeito):
  `synth_filled` (168), `synth_filled_v2` (345), `synth_entrylabel` (60) = 573 CVs.
- **Sem gabarito** (baseline LLM feito por leitura manual dos textos): `images/`
  (23 imagens com OCR), `lattes/` (2), `pdf/` (1 — andrei_bosco) = 26 CVs.
- Ignorados: `templates/` (modelos em branco), `_layout_preview/` e
  `_cvrender_preview/` (pré-visualizações), `backup/` (duplicatas),
  `benchmark/runs/` (saídas de outros experimentos), `amostras_jubilato/`
  (subconjunto do CV Galpao, já avaliado no benchmark anterior).

## 1. Resultado nos conjuntos com gabarito (573 CVs)

| Conjunto | CVs | Nomes | Experiências (recall) | Empresas | Cargos |
|---|---|---|---|---|---|
| synth_entrylabel | 60 | **60/60 (100%)** | **118/118 (100%)** | 117/118 (99%) | 118/118 (100%) |
| synth_filled_v2 | 345 | 342/345 (99%) | **719/727 (99%)** | 516/727 (71%) | 522/727 (72%) |
| synth_filled | 168 | 154/168 (92%) | **451/486 (93%)** | 304/486 (63%) | 330/486 (68%) |
| **Total** | **573** | **556/573 (97%)** | **1288/1331 (97%)** | 937/1331 (70%) | 970/1331 (73%) |

### Evolução entre as rodadas

| Métrica (total) | 1ª rodada | 2ª rodada | 3ª rodada |
|---|---|---|---|
| Experiências | 1169/1331 (88%) | 1279/1331 (96%) | **1288/1331 (97%)** |
| Empresas | 693/1331 (52%) | 836/1331 (63%) | **937/1331 (70%)** |
| Cargos | 543/1331 (41%) | 949/1331 (71%) | **970/1331 (73%)** |
| Nomes | 539/573 (94%) | 548/573 (96%) | **556/573 (97%)** |
| Imagens (OCR) | 27/41 (66%) | 34/46 (74%) | **37/46 (80%)** |

### Melhorias da 2ª rodada

1. Formulário de processo seletivo ("ADMISSÃO / DESLIGAMENTO / EMPREGADOR /
   CARGO/FUNÇÃO / ATIVIDADES"): parser dedicado, um campo por linha.
2. De-glue refinado para PDFs com kerning apertado (evidência combinada,
   hifenização de quebra de linha, espaço antes de parêntese).
3. Descolagem de preposição em cargos ("Atendentede Caixa") validada pelo
   léxico de cargos.
4. Parser dedicado para currículo Lattes (vínculos de "Atuação Profissional",
   com deduplicação dos dumps de tabela do pdfplumber).
5. OCR com passadas múltiplas para imagens pequenas (original + upscale 2x +
   tons de cinza; vence o texto com mais datas legíveis).
6. Períodos quebrados em 3 linhas ("2022-01" / "—" / "atual") reagrupados.
7. Glifos sem unicode "(cid:NNN)" removidos; seções com parênteses
   ("Experiências (Treinamentos)") reconhecidas.
8. Guarda de descrição: linha terminando em "." não vira cabeçalho de
   experiência.

### Melhorias da 3ª rodada

1. **Local com pictograma** ("📍 Brasília, DF" ao lado do período) deixa de
   virar empresa; emojis são limpos dos rótulos e a busca sobe para o
   cargo/empresa nas linhas acima.
2. **Travessão de região** ("Gerente Geral — Brasil e Cone Sul"): léxico de
   abrangências geográficas mantém a região no cargo; a empresa real é
   capturada na linha vizinha. Novos layouts: "Cargo — período" / "Empresa" e
   rótulo "Empresa:" em qualquer linha do bloco.
3. **Nomes MAIÚSCULOS colados** ("LEONARDONOGUEIRASOUZA"): segmentação por
   programação dinâmica sobre léxico de ~250 prenomes/sobrenomes; só divide
   se a string inteira for segmentável (+8 nomes no v2).
4. **Datas corrompidas por OCR**: separador "=" ("02/2023 = present") e
   reagrupamento de período partido por colunas embaralhadas ("12/2020 a
   Empresa: X" / "12/2021 Cargo: Y"), com guarda para linhas que já contêm
   período completo.
5. **Duas colunas sem calha limpa** (kickresume): detector por cobertura
   mínima (x com menos palavras atravessando, tolera header em largura
   total) + reconstrução do texto palavra a palavra preservando o header.
   O caso `103_analista_marketing` foi de 1/6 para 6/6 com todos os
   cargos/empresas corretos.

Onde ainda perde: alguns kickresume com texto muito fragmentado (078, 084),
empresas em linhas com múltiplos travessões e nomes ausentes do texto
extraído (banners com fonte decorada).

## 2. Resultado nos arquivos sem gabarito (26 CVs, baseline LLM manual)

Detalhe por arquivo em `baseline_llm_sem_gabarito.json`.

| Grupo | Nomes corretos | Experiências (recall) |
|---|---|---|
| images (20 legíveis*) | 14/18** | **37/46 (80%)** — antes 27/41 (66%) |
| lattes (2) | 2/2 | Filipe 11 de 16 vínculos, Alessandro 16 de ~20 — **sem superextração** (antes: 19 e 85 com ruído) |
| pdf andrei_bosco (1) | 1/1 | 12/12 (100%) |

\* 3 imagens têm OCR ilegível (30, 39, thumbnail1) — nem um humano extrairia
experiências do texto OCR; excluídas do recall.
\** Algumas imagens não contêm o nome legível no OCR (nome em banner com
fonte decorada); nesses casos o app devolve o título profissional ou nada.

Ganhos com OCR multi-passada + reparo de datas: 34_historiador (0→3),
37_administrador (0→3), 26_logistica (0→1), thumbnail2 (0→2),
31_advogada (1→2), 42_gestora (1→2).

## 3. Verificação de não-regressão

- `pytest`: **15/15** testes passando (2 novos: formulário de concurso e
  Lattes).
- Benchmark CV Galpao (47 CVs reais): **experiências 316/332 (95%) e nomes
  47/47** — um CV melhorou (CV_Bage: 2→4 experiências), nenhum piorou.
  Durante a 3ª rodada uma regressão em `jose carlos de oliveira.pdf` foi
  detectada e corrigida (períodos completos sendo refundidos).

## 4. Como reproduzir

```bash
PYTHONPATH=. .venv/bin/python testes/comparar_samples.py
```

Saídas: `comparativo_samples.json` / `.csv` (por CV) e `sem_gabarito/` (texto
normalizado + JSON extraído de cada arquivo sem gabarito).

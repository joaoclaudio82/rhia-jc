# Benchmark: pasta `samples/` — leitor_cv vs referência (gabarito + LLM)

Data: 10/06/2026 (4ª rodada). Escopo: 599 currículos de `~/Downloads/samples`.

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
| synth_entrylabel | 60 | **60/60 (100%)** | **118/118 (100%)** | 102/118 (86%) | 118/118 (100%) |
| synth_filled_v2 | 345 | 335/345 (97%) | **715/727 (98%)** | 507/727 (70%) | 611/727 (84%) |
| synth_filled | 168 | 154/168 (92%) | **436/486 (90%)** | 319/486 (66%) | 345/486 (71%) |
| **Total** | **573** | **549/573 (95,8%)** | **1269/1331 (95,3%)** | 928/1331 (69,7%) | 1074/1331 (80,7%) |

### Evolução entre as rodadas

| Métrica (total) | 1ª rodada | 2ª rodada | 3ª rodada | 4ª rodada |
|---|---|---|---|---|
| Experiências | 1169/1331 (88%) | 1279/1331 (96%) | 1288/1331 (97%) | **1269/1331 (95,3%)** |
| Empresas | 693/1331 (52%) | 836/1331 (63%) | 937/1331 (70%) | **928/1331 (69,7%)** |
| Cargos | 543/1331 (41%) | 949/1331 (71%) | 970/1331 (73%) | **1074/1331 (80,7%)** |
| Nomes | 539/573 (94%) | 548/573 (96%) | 556/573 (97%) | **549/573 (95,8%)** |
| Imagens (OCR) | 27/41 (66%) | 34/46 (74%) | 37/46 (80%) | 37/46 (80%) |

A 4ª rodada troca volume bruto por qualidade: filtros anti-ruído e pós-validação
removem falsos positivos (CPF, nascimento, publicações Lattes, formação como
experiência). **Cargos sobem +7,7 p.p.**; experiências e nomes caem ~2 p.p. por
contagem mais conservadora.

### Casos kickresume 078 e 084 (4ª rodada)

| Arquivo | Exp | Empresas | Cargos | Nome |
|---|---:|---:|---:|---|
| 078 PDF | 8/8 | 8/8 | 8/8 | ok |
| 078 DOCX | 8/8 | 8/8 | 8/8 | ok |
| 084 PDF | 7/7 | 7/7 | 6/7 | ok |
| 084 DOCX | 7/7 | 3/7 | 5/7 | ok |

### Melhorias da 4ª rodada

1. **Detecção de template** (`lattes` / `academico` / `tradicional`) para escolher
   estratégia de extração.
2. **Parser Lattes reescrito**: busca case-insensitive, normalização de
   `Vínculo\ninstitucional`, instituição por lista numerada, corte de seção
   corrigido (removido `Produção` solto que truncava a seção em ~900 chars).
3. **Filtros anti-ruído**: CPF, nascimento, identidade, publicações Lattes,
   formação acadêmica como âncora de experiência.
4. **Formação**: agrupamento de bullets `?`, explosão de parágrafos longos,
   limite de 25 itens.
5. **Pós-validação** com deduplicação em experiências e formações.
6. **Testes `novoscvs/`**: 46 regras de qualidade em 13 PDFs reais (sem gabarito).

### Melhorias da 3ª rodada

1. **Local com pictograma** ("?? Brasília, DF" ao lado do período) deixa de
   virar empresa; emojis são limpos dos rótulos e a busca sobe para o
   cargo/empresa nas linhas acima.
2. **Travessão de região** ("Gerente Geral — Brasil e Cone Sul"): léxico de
   abrangências geográficas mantém a região no cargo; a empresa real é
   capturada na linha vizinha.
3. **Nomes MAIÚSCULOS colados** ("LEONARDONOGUEIRASOUZA"): segmentação por
   programação dinâmica sobre léxico de ~250 prenomes/sobrenomes.
4. **Datas corrompidas por OCR**: separador "=" e reagrupamento de período
   partido por colunas embaralhadas.
5. **Duas colunas sem calha limpa** (kickresume): detector por cobertura
   mínima + reconstrução palavra a palavra. O caso `103_analista_marketing`
   foi de 1/6 para 6/6.

Onde ainda perde: empresas em linhas com múltiplos travessões (~70% recall),
nomes ausentes do texto extraído (banners com fonte decorada), alguns DOCX
kickresume (084 DOCX: empresas 3/7).

## 2. Resultado nos arquivos sem gabarito (26 CVs, baseline LLM manual)

Detalhe por arquivo em `baseline_llm_sem_gabarito.json`.

| Grupo | Nomes corretos | Experiências (recall) |
|---|---|---|
| images (20 legíveis*) | 14/18** | **37/46 (80%)** |
| lattes (2) | 2/2 | Filipe 11 de 16 vínculos, Alessandro 16 de ~20 — sem superextração |
| pdf andrei_bosco (1) | 1/1 | 12/12 (100%) |

\* 3 imagens têm OCR ilegível (30, 39, thumbnail1) — excluídas do recall.
\** Algumas imagens não contêm o nome legível no OCR (banner com fonte decorada).

## 3. Verificação de não-regressão

- `pytest testes/test_extracao_regressoes.py`: **18/18** testes.
- `pytest testes/test_novoscvs.py`: **46/46** testes (13 PDFs reais em `novoscvs/`).
- Total: **64/64** testes passando.

## 4. Como reproduzir

```bash
PYTHONPATH=. .venv/bin/python testes/comparar_samples.py
PYTHONPATH=. .venv/bin/python testes/processar_novoscvs.py   # requer PDFs locais
PYTHONPATH=. .venv/bin/python -m pytest testes/ -q
```

Saídas: `comparativo_samples.json` / `.csv` (por CV) e `sem_gabarito/` (texto
normalizado + JSON extraído de cada arquivo sem gabarito).

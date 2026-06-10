# Leitor de Currículos

App em Python que lê currículos em **qualquer formato** (PDF nato-digital, PDF escaneado, DOCX com tabelas e imagens, ou imagem solta) e extrai todas as informações em JSON estruturado e validado.

## Arquitetura (2 etapas)

```
arquivo (pdf/docx/imagem)
        │
        ▼
[1] INGESTÃO  (ingestao.py)
    normaliza tudo para texto/markdown:
    • PDF digital  -> pdfplumber (texto + tabelas em markdown)
    • PDF escaneado -> detecção automática + OCR (pdf2image + tesseract)
    • DOCX -> parágrafos e tabelas na ordem real + OCR das imagens embutidas
    • Imagem -> OCR direto (por+eng)
        │
        ▼
[2] EXTRAÇÃO  (extracao.py)  — 100% local, sem LLM
    • regexes para contato (email, telefone, LinkedIn, GitHub, cidade/UF)
    • segmentação por títulos de seção ("Experiência", "Formação",
      "Habilidades", "Idiomas"...), insensível a caixa e acentos
    • parsers por seção: datas/períodos, cargo×empresa, tabelas markdown,
      listas com vírgulas ou bullets
    • resultado validado contra o esquema Pydantic (esquema.py)
        │
        ▼
Curriculo (JSON validado)
```

A extração é totalmente determinística e gratuita (nenhuma chamada de API).
O trade-off: funciona bem para CVs razoavelmente estruturados com seções
nomeadas; em layouts muito fora do padrão, campos não reconhecidos ficam
null/lista vazia (nunca são inventados).

## Instalação

```bash
# Dependências de sistema (Ubuntu/Debian)
sudo apt install tesseract-ocr tesseract-ocr-por poppler-utils

pip install -r requirements.txt
```

No macOS: `brew install tesseract tesseract-lang poppler`.

## Uso

```bash
# CLI: extrai JSON completo
python -m leitor_cv curriculo.pdf
python -m leitor_cv curriculo.docx --saida resultado.json

# Só a etapa de ingestão (debug)
python -m leitor_cv curriculo.pdf --apenas-texto

# Interface web + API HTTP
uvicorn leitor_cv.api:app --reload
# abra http://localhost:8000 no navegador (upload com visualização do resultado)
curl -F "arquivo=@curriculo.pdf" http://localhost:8000/curriculos
```

## Uso como biblioteca

```python
from leitor_cv.ingestao import carregar_curriculo
from leitor_cv.extracao import extrair_curriculo

texto = carregar_curriculo("cv.pdf")
cv = extrair_curriculo(texto)        # objeto Pydantic Curriculo
print(cv.nome_completo, cv.contato.email)
print(cv.model_dump_json(indent=2))
```

## Esquema extraído

`nome_completo`, `titulo_profissional`, `resumo`, `contato` (email, telefone,
linkedin, github, cidade...), `formacoes`, `experiencias` (com tecnologias),
`habilidades`, `idiomas`, `certificacoes`, `projetos`, `publicacoes`,
`informacoes_adicionais`.

Para adicionar campos, edite `esquema.py` e implemente o parser
correspondente em `extracao.py`.

## Pontos de evolução

- Processamento em lote (pasta inteira -> CSV/parquet)
- Fila assíncrona (Celery/SQS) para volume alto
- Mais aliases de seção e formatos de data em `extracao.py` conforme
  novos modelos de CV aparecerem
- Cache por hash do arquivo para não reprocessar o mesmo CV

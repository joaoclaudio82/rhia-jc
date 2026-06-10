"""API HTTP + interface web para leitura de currículos.

Rodar:
    uvicorn leitor_cv.api:app --reload

Endpoints:
    GET  /            -> interface web (upload + visualização)
    POST /curriculos  (multipart, campo "arquivo") -> JSON estruturado do CV
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .esquema import Curriculo
from .extracao import extrair_curriculo
from .ingestao import EXTENSOES_IMAGEM, carregar_curriculo

app = FastAPI(title="Leitor de Currículos", version="0.1.0")

EXTENSOES_SUPORTADAS = {".pdf", ".docx", ".txt", ".md"} | EXTENSOES_IMAGEM
_PAGINA_WEB = Path(__file__).parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
def pagina_inicial() -> FileResponse:
    return FileResponse(_PAGINA_WEB, media_type="text/html")


@app.post("/curriculos", response_model=Curriculo)
async def ler_curriculo(arquivo: UploadFile = File(...)) -> Curriculo:
    ext = Path(arquivo.filename or "").suffix.lower()
    if ext not in EXTENSOES_SUPORTADAS:
        raise HTTPException(415, f"Formato não suportado: {ext}")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
        tmp.write(await arquivo.read())
        tmp.flush()
        try:
            texto = carregar_curriculo(tmp.name)
        except Exception as exc:
            raise HTTPException(422, f"Falha na leitura do arquivo: {exc}") from exc

    if not texto.strip():
        raise HTTPException(422, "Nenhum texto pôde ser extraído do arquivo.")

    return extrair_curriculo(texto)


@app.get("/saude")
def saude() -> dict:
    return {"status": "ok"}

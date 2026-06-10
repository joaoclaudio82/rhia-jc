"""Interface de linha de comando do leitor de currículos.

Uso:
    python -m leitor_cv caminho/do/curriculo.pdf
    python -m leitor_cv cv.docx --saida resultado.json
    python -m leitor_cv cv.pdf --apenas-texto   # só a etapa de ingestão
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ingestao import carregar_curriculo


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="leitor_cv",
        description="Lê currículos em PDF, DOCX ou imagem e extrai dados estruturados.",
    )
    parser.add_argument("arquivo", type=Path, help="Caminho do currículo")
    parser.add_argument("--saida", type=Path, default=None, help="Arquivo JSON de saída")
    parser.add_argument(
        "--apenas-texto",
        action="store_true",
        help="Mostra só o texto normalizado, sem extrair os campos",
    )
    args = parser.parse_args()

    texto = carregar_curriculo(args.arquivo)

    if args.apenas_texto:
        print(texto)
        return

    from .extracao import extrair_curriculo

    curriculo = extrair_curriculo(texto)
    saida_json = json.dumps(curriculo.model_dump(), ensure_ascii=False, indent=2)

    if args.saida:
        args.saida.write_text(saida_json, encoding="utf-8")
        print(f"Resultado salvo em {args.saida}", file=sys.stderr)
    else:
        print(saida_json)


if __name__ == "__main__":
    main()

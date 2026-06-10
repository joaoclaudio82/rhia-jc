#!/usr/bin/env python3
"""Reprocessa PDFs em novoscvs/ e grava resultados_extracao.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leitor_cv.extracao import extrair_curriculo
from leitor_cv.ingestao import carregar_curriculo

NOVOSCVS = ROOT / "novoscvs"
SAIDA = NOVOSCVS / "resultados_extracao.json"


def main() -> None:
    resultados = []
    pdfs = sorted(NOVOSCVS.glob("*.pdf"))
    for pdf in pdfs:
        item = {"arquivo": pdf.name, "erro": None}
        try:
            cv = extrair_curriculo(carregar_curriculo(pdf))
            item.update({
                "nome": cv.nome_completo,
                "titulo": cv.titulo_profissional,
                "email": cv.contato.email,
                "telefone": cv.contato.telefone,
                "experiencias": len(cv.experiencias),
                "formacoes": len(cv.formacoes),
                "habilidades": len(cv.habilidades),
                "experiencias_detalhe": [
                    {
                        "cargo": e.cargo,
                        "empresa": e.empresa,
                        "inicio": e.inicio,
                        "fim": e.fim,
                    }
                    for e in cv.experiencias[:12]
                ],
            })
        except Exception as exc:
            item["erro"] = str(exc)
        resultados.append(item)
        print(f"{pdf.name}: exp={item.get('experiencias', '?')} form={item.get('formacoes', '?')}")

    SAIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSalvo em {SAIDA}")


if __name__ == "__main__":
    main()

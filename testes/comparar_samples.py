"""Benchmark do leitor_cv contra os gabaritos da pasta samples/.

Conjuntos com ground truth (dataset.json): synth_filled, synth_filled_v2,
synth_entrylabel. Para pastas sem gabarito (images, lattes, pdf) apenas
gera o texto normalizado + extracao do app para leitura manual (baseline LLM).

Uso:
    python testes/comparar_samples.py
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

from leitor_cv.extracao import extrair_curriculo
from leitor_cv.ingestao import carregar_curriculo

SAMPLES = Path("/Users/joaoclaudio/Downloads/samples")
SAIDA = Path(__file__).parent / "samples_vs_llm"
DATASETS = ("synth_filled", "synth_filled_v2", "synth_entrylabel")
SEM_GABARITO = ("images", "lattes", "pdf")


def norm(s: str | None) -> str:
    d = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in d if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def contem(a: str | None, b: str | None) -> bool:
    na, nb = norm(a), norm(b)
    return bool(na and nb) and (na in nb or nb in na)


def avaliar_dataset(nome_ds: str) -> list[dict]:
    base = SAMPLES / nome_ds
    dados = json.load(open(base / "dataset.json"))
    entries = dados["entries"] if isinstance(dados, dict) else dados
    resultados = []
    for e in entries:
        arq = base / e["file"]
        gab = e["expected"]
        linha = {
            "dataset": nome_ds,
            "arquivo": e["file"],
            "nome_gab": gab.get("name"),
            "exp_gab": len(gab.get("work_experience") or []),
        }
        try:
            cv = extrair_curriculo(carregar_curriculo(arq))
        except Exception as exc:
            linha.update(erro=str(exc)[:120], nome_app=None, exp_app=0,
                         nome_ok=False, exp_capturadas=0,
                         empresas_ok=0, cargos_ok=0)
            resultados.append(linha)
            continue
        empresas_app = [norm(x.empresa) for x in cv.experiencias if x.empresa]
        cargos_app = [norm(x.cargo) for x in cv.experiencias if x.cargo]
        emp_ok = sum(
            1 for w in (gab.get("work_experience") or [])
            if any(contem(w.get("company"), ea) for ea in empresas_app)
        )
        car_ok = sum(
            1 for w in (gab.get("work_experience") or [])
            if any(contem(w.get("position"), ca) for ca in cargos_app)
        )
        linha.update(
            erro=None,
            nome_app=cv.nome_completo,
            exp_app=len(cv.experiencias),
            nome_ok=contem(gab.get("name"), cv.nome_completo),
            exp_capturadas=min(len(cv.experiencias), linha["exp_gab"]),
            empresas_ok=emp_ok,
            cargos_ok=car_ok,
        )
        resultados.append(linha)
    return resultados


def dump_sem_gabarito() -> None:
    destino = SAIDA / "sem_gabarito"
    destino.mkdir(parents=True, exist_ok=True)
    for pasta in SEM_GABARITO:
        for arq in sorted((SAMPLES / pasta).iterdir()):
            if arq.is_dir() or arq.name.startswith("."):
                continue
            slug = re.sub(r"\W+", "_", f"{pasta}_{arq.stem}")[:80]
            try:
                texto = carregar_curriculo(arq)
                cv = extrair_curriculo(texto)
            except Exception as exc:
                (destino / f"{slug}_ERRO.txt").write_text(str(exc), encoding="utf-8")
                continue
            (destino / f"{slug}.txt").write_text(texto, encoding="utf-8")
            (destino / f"{slug}_app.json").write_text(
                cv.model_dump_json(indent=1), encoding="utf-8"
            )


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    todos: list[dict] = []
    for ds in DATASETS:
        resultados = avaliar_dataset(ds)
        todos += resultados
        n = len(resultados)
        nomes = sum(1 for r in resultados if r["nome_ok"])
        gab = sum(r["exp_gab"] for r in resultados)
        capt = sum(r["exp_capturadas"] for r in resultados)
        emp = sum(r["empresas_ok"] for r in resultados)
        car = sum(r["cargos_ok"] for r in resultados)
        erros = sum(1 for r in resultados if r["erro"])
        print(f"{ds}: {n} CVs | nomes {nomes}/{n} | "
              f"exps {capt}/{gab} ({100*capt/gab:.0f}%) | "
              f"empresas {emp}/{gab} ({100*emp/gab:.0f}%) | "
              f"cargos {car}/{gab} ({100*car/gab:.0f}%) | erros {erros}")

    json.dump(todos, open(SAIDA / "comparativo_samples.json", "w"),
              ensure_ascii=False, indent=1)
    with open(SAIDA / "comparativo_samples.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        w.writeheader()
        w.writerows(todos)

    dump_sem_gabarito()
    print("ok ->", SAIDA)


if __name__ == "__main__":
    main()

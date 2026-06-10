# -*- coding: utf-8 -*-
"""Regras minimas de qualidade nos CVs reais de novoscvs/."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from leitor_cv.extracao import _norm, extrair_curriculo
from leitor_cv.ingestao import carregar_curriculo

_NOVOSCVS = Path(__file__).resolve().parent.parent / "novoscvs"
_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")

PDFS = sorted(_NOVOSCVS.glob("*.pdf"))
# Lattes com estrutura de vinculos (exclui PDFs vazios ou sem parser)
_LATTES_SEM_VINCULO = frozenset(("curriculo lattes", "janeiro lattes"))
LATTES_PDFS = [
    p for p in PDFS
    if "lattes" in p.name.lower()
    and _norm(p.stem) not in _LATTES_SEM_VINCULO
]


def _extrair(arquivo: Path):
    texto = carregar_curriculo(arquivo)
    return extrair_curriculo(texto)


@pytest.mark.parametrize("arquivo", PDFS, ids=lambda p: p.name)
def test_nome_extraido(arquivo: Path):
    cv = _extrair(arquivo)
    assert cv.nome_completo, f"nome vazio em {arquivo.name}"


@pytest.mark.parametrize("arquivo", PDFS, ids=lambda p: p.name)
def test_sem_cpf_em_experiencias(arquivo: Path):
    cv = _extrair(arquivo)
    for exp in cv.experiencias:
        for campo in (exp.cargo, exp.empresa, exp.descricao):
            if campo:
                assert not _RE_CPF.search(campo), f"CPF em experiencia: {campo!r} ({arquivo.name})"


@pytest.mark.parametrize("arquivo", PDFS, ids=lambda p: p.name)
def test_sem_nascimento_em_experiencias(arquivo: Path):
    cv = _extrair(arquivo)
    for exp in cv.experiencias:
        for campo in (exp.cargo, exp.empresa):
            if campo:
                n = campo.lower()
                assert "nascimento" not in n, f"dado pessoal em exp: {campo!r} ({arquivo.name})"
                assert "carteira de identidade" not in n


@pytest.mark.parametrize("arquivo", LATTES_PDFS, ids=lambda p: p.name)
def test_lattes_tem_vinculos(arquivo: Path):
    cv = _extrair(arquivo)
    com_empresa = [e for e in cv.experiencias if e.empresa and e.inicio]
    assert len(com_empresa) >= 2, (
        f"Lattes com poucos vinculos ({len(com_empresa)}): {arquivo.name}"
    )


def test_juliana_formacoes_limitadas():
    arquivo = _NOVOSCVS / "CurriculumatualJulianaVianaJales.docx.pdf"
    if not arquivo.exists():
        pytest.skip("PDF Juliana ausente")
    cv = _extrair(arquivo)
    assert len(cv.formacoes) <= 25


def test_joao_paulo_poucas_experiencias_ruidosas():
    matches = list(_NOVOSCVS.glob("Curriculum*Jo*Paulo*.pdf"))
    if not matches:
        pytest.skip("PDF Joao Paulo ausente")
    arquivo = matches[0]
    cv = _extrair(arquivo)
    assert len(cv.experiencias) <= 15, (
        f"superextracao de experiencias ({len(cv.experiencias)})"
    )

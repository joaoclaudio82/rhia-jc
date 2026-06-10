"""Esquema de dados estruturados extraídos de um currículo."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Contato(BaseModel):
    email: Optional[str] = None
    telefone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    site: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    pais: Optional[str] = None


class Formacao(BaseModel):
    curso: Optional[str] = None
    nivel: Optional[str] = Field(
        None, description="Ex.: técnico, graduação, especialização, mestrado, doutorado"
    )
    instituicao: Optional[str] = None
    ano_inicio: Optional[str] = None
    ano_fim: Optional[str] = None
    situacao: Optional[str] = Field(None, description="concluído, em andamento, trancado")


class Experiencia(BaseModel):
    cargo: Optional[str] = None
    empresa: Optional[str] = None
    inicio: Optional[str] = None
    fim: Optional[str] = Field(None, description="'atual' se ainda estiver no cargo")
    descricao: Optional[str] = None
    tecnologias: list[str] = Field(default_factory=list)


class Idioma(BaseModel):
    idioma: str
    nivel: Optional[str] = None


class Certificacao(BaseModel):
    nome: str
    emissor: Optional[str] = None
    ano: Optional[str] = None


class Curriculo(BaseModel):
    """Representação estruturada e completa de um CV."""

    nome_completo: Optional[str] = None
    titulo_profissional: Optional[str] = None
    resumo: Optional[str] = None
    contato: Contato = Field(default_factory=Contato)
    formacoes: list[Formacao] = Field(default_factory=list)
    experiencias: list[Experiencia] = Field(default_factory=list)
    habilidades: list[str] = Field(default_factory=list)
    idiomas: list[Idioma] = Field(default_factory=list)
    certificacoes: list[Certificacao] = Field(default_factory=list)
    projetos: list[str] = Field(default_factory=list)
    publicacoes: list[str] = Field(default_factory=list)
    informacoes_adicionais: Optional[str] = None

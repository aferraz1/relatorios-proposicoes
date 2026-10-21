"""Capa A4 do relatório de gestão e acompanhamento de proposições."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Pessoa:
    """Pessoa citada na capa (parlamentar ou assessor)."""

    cargo: str
    nome: str
    email: str | None = None
    telefone: str | None = None

    @property
    def url_whatsapp(self) -> str | None:
        """Link de conversa no WhatsApp a partir dos dígitos do telefone."""
        return "https://wa.me/" + re.sub(r"\D", "", self.telefone) if self.telefone else None


@dataclass(frozen=True)
class Capa:
    """Textos da capa; as imagens e fontes vêm de ``recursos/``."""

    data_emissao: date
    titulo: list[str]
    area: list[str]
    destaque: list[str]
    parlamentar: Pessoa
    assessor: Pessoa
    escritorio: str
    partido: str

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Capa:
        """Cria a capa a partir do dicionário lido do JSON."""
        return cls(
            data_emissao=date.fromisoformat(dados["data_emissao"]),
            titulo=dados["titulo"],
            area=dados["area"],
            destaque=dados["destaque"],
            parlamentar=Pessoa(**dados["parlamentar"]),
            assessor=Pessoa(**dados["assessor"]),
            escritorio=dados["escritorio"],
            partido=dados["partido"],
        )

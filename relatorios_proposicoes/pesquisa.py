"""Base local da pesquisa facetada de proposições."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# Tabelas de referência do formato compacto: cada registro de ``L`` aponta para elas por índice.
TABELAS = ("TP", "S", "O", "T", "TC", "A", "AP", "RG", "L")
CAMPOS_REGISTRO = 16


@dataclass(frozen=True)
class BasePesquisa:
    """Proposições coletadas na API de Dados Abertos, no formato compacto lido pela página.

    Cada registro de ``L`` é ``[id, siglaTipo, numero, ano, dataApresentacao, ementa,
    keywords, situacao, orgao, apreciacao, regime, ultimaMovimentacao, descricaoTramitacao,
    autores, totalAutores, temas]``; situação, órgão, apreciação, regime, autores e temas
    são índices nas tabelas ``S``, ``O``, ``AP``, ``RG``, ``A`` e ``T``.
    """

    coleta: date
    descricao_base: str
    nota_cobertura: str
    detalhes: dict[str, dict[str, str]]
    tabelas: dict[str, list[Any]]

    @property
    def total(self) -> int:
        """Quantidade de proposições na base."""
        return len(self.tabelas["L"])

    def para_pagina(self) -> dict[str, Any]:
        """Dados serializados para o script da página."""
        return {
            "coleta": self.coleta.isoformat(),
            "descricaoBase": self.descricao_base,
            "detalhes": self.detalhes,
            **self.tabelas,
        }

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> BasePesquisa:
        """Cria a base a partir do JSON, validando as tabelas e os índices dos registros."""
        faltando = [t for t in TABELAS if t not in dados]
        if faltando:
            raise ValueError(f"Base de pesquisa sem as tabelas: {', '.join(faltando)}")
        tabelas = {t: dados[t] for t in TABELAS}
        limites = {7: "S", 8: "O", 9: "AP", 10: "RG"}
        for registro in tabelas["L"]:
            if len(registro) != CAMPOS_REGISTRO:
                raise ValueError(f"Registro {registro[0]} com {len(registro)} campos; esperados {CAMPOS_REGISTRO}")
            for posicao, tabela in limites.items():
                if not 0 <= registro[posicao] < len(tabelas[tabela]):
                    raise ValueError(f"Registro {registro[0]}: índice fora da tabela {tabela}")
            if any(not 0 <= i < len(tabelas["A"]) for i in registro[13]):
                raise ValueError(f"Registro {registro[0]}: autor fora da tabela A")
            if any(not 0 <= i < len(tabelas["T"]) for i in registro[15]):
                raise ValueError(f"Registro {registro[0]}: tema fora da tabela T")
        return cls(
            coleta=date.fromisoformat(dados["coleta"]),
            descricao_base=dados["descricao_base"],
            nota_cobertura=dados["nota_cobertura"],
            detalhes=dados.get("detalhes", {}),
            tabelas=tabelas,
        )

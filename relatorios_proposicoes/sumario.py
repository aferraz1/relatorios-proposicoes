"""Sumário dos relatórios de tramitação, em ordem decrescente de apresentação."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ItemSumario:
    """Proposição listada no sumário, com o arquivo do seu relatório."""

    id: int
    identificacao: str
    apresentacao: date
    ementa: str
    situacao: str
    arquivo: str

    @classmethod
    def de_relatorio(cls, dados: dict[str, Any]) -> ItemSumario:
        """Cria o item a partir do JSON de um relatório de tramitação."""
        p = dados["proposicao"]
        return cls(
            id=p["id"],
            identificacao=p["identificacao"],
            apresentacao=date.fromisoformat(p["apresentacao"]),
            ementa=p["ementa"],
            situacao=dados["situacao"]["descricao"],
            arquivo=f"{nome_arquivo(p['identificacao'])}.html",
        )


@dataclass(frozen=True)
class Sumario:
    """Página de sumário com links para os relatórios gerados na mesma pasta."""

    titulo: str
    sobre: str
    descricao: str
    itens: list[ItemSumario]

    @property
    def tipos(self) -> str:
        """Siglas dos tipos presentes, como ``PL e PLP``."""
        siglas = sorted({i.identificacao.split(" ", 1)[0] for i in self.itens})
        return siglas[0] if len(siglas) == 1 else ", ".join(siglas[:-1]) + " e " + siglas[-1]

    @property
    def introducao(self) -> str:
        """Texto de abertura, com ``{total}`` e ``{tipos}`` preenchidos."""
        return self.descricao.format(total=len(self.itens), tipos=self.tipos)

    @classmethod
    def de_dict(cls, dados: dict[str, Any], pasta: Path) -> Sumario:
        """Cria o sumário lendo os relatórios indicados em ``relatorios`` (padrões relativos a ``pasta``).

        Um id repetido fica com o primeiro arquivo encontrado; a lista sai da apresentação mais
        recente para a mais antiga.
        """
        itens: dict[int, ItemSumario] = {}
        for padrao in dados["relatorios"]:
            caminhos = sorted(pasta.glob(padrao))
            if not caminhos:
                raise ValueError(f"Nenhum relatório encontrado para {padrao!r} em {pasta}")
            for caminho in caminhos:
                item = ItemSumario.de_relatorio(json.loads(caminho.read_text(encoding="utf-8")))
                itens.setdefault(item.id, item)
        ordenados = sorted(itens.values(), key=lambda i: (i.apresentacao, i.id), reverse=True)
        return cls(titulo=dados.get("titulo", "Sumário"), sobre=dados["sobre"], descricao=dados["descricao"], itens=ordenados)


def nome_arquivo(identificacao: str) -> str:
    """Nome-base do relatório a partir da identificação, como ``pl-1680-2025`` para ``PL 1.680/2025``."""
    tipo, resto = identificacao.split(" ", 1)
    numero, ano = resto.replace(".", "").split("/")
    return f"{tipo.lower()}-{numero}-{ano}"

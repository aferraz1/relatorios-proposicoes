"""Modelos de dados do relatório de tramitação e leitura a partir de JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

URL_INTEIRO_TEOR = "https://www.camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor="
URL_FOTO_DEPUTADO = "https://www.camara.leg.br/internet/deputado/bandep/{id}.jpg"

EstadoEstagio = Literal["concluido", "atual", "pendente"]
TipoEvento = Literal["marco", "rotina", "alerta", "atual"]


@dataclass(frozen=True)
class Documento:
    """Documento oficial da Câmara identificado pelo código do inteiro teor."""

    codteor: str
    nome: str

    @property
    def url(self) -> str:
        """URL pública do PDF do documento."""
        return URL_INTEIRO_TEOR + self.codteor

    @classmethod
    def de_dict(cls, dados: dict[str, Any] | None) -> Documento | None:
        """Cria o documento a partir de um dicionário, ou ``None`` se ausente."""
        if not dados:
            return None
        return cls(codteor=str(dados["codteor"]), nome=dados["nome"])


@dataclass(frozen=True)
class Parlamentar:
    """Parlamentar exibido em cartão (autor ou relator)."""

    id: int
    nome: str
    descricao: str
    rotulo: str

    @property
    def url_foto(self) -> str:
        """URL da fotografia oficial do deputado no portal da Câmara."""
        return URL_FOTO_DEPUTADO.format(id=self.id)

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Parlamentar:
        """Cria o parlamentar a partir de um dicionário."""
        return cls(id=int(dados["id"]), nome=dados["nome"], descricao=dados["descricao"], rotulo=dados["rotulo"])


@dataclass(frozen=True)
class Estagio:
    """Etapa do caminho de tramitação (Mesa, comissões, Senado, sanção)."""

    sigla: str
    nome: str
    papel: str
    estado: EstadoEstagio
    inicio: date | None = None
    fim: date | None = None
    comissao: bool = False
    documento: Documento | None = None

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Estagio:
        """Cria o estágio a partir de um dicionário."""
        return cls(
            sigla=dados["sigla"],
            nome=dados["nome"],
            papel=dados["papel"],
            estado=dados["estado"],
            inicio=_data_opcional(dados.get("inicio")),
            fim=_data_opcional(dados.get("fim")),
            comissao=bool(dados.get("comissao", False)),
            documento=Documento.de_dict(dados.get("documento")),
        )


@dataclass(frozen=True)
class Evento:
    """Registro individual do histórico de tramitações."""

    data_hora: datetime
    titulo: str
    texto: str
    tipo: TipoEvento
    etiqueta: str | None = None
    documento: Documento | None = None

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Evento:
        """Cria o evento a partir de um dicionário."""
        return cls(
            data_hora=datetime.fromisoformat(dados["data_hora"]),
            titulo=dados["titulo"],
            texto=dados["texto"],
            tipo=dados["tipo"],
            etiqueta=dados.get("etiqueta"),
            documento=Documento.de_dict(dados.get("documento")),
        )


@dataclass(frozen=True)
class Fase:
    """Agrupamento de eventos por órgão (Mesa ou comissão)."""

    sigla: str
    nome: str
    eventos: list[Evento]

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Fase:
        """Cria a fase a partir de um dicionário."""
        return cls(sigla=dados["sigla"], nome=dados["nome"], eventos=[Evento.de_dict(e) for e in dados["eventos"]])


@dataclass(frozen=True)
class Parecer:
    """Versão de parecer apresentada pelo relator."""

    sigla: str
    nome: str
    data: str
    codteor: str
    aprovado: bool = False

    @property
    def url(self) -> str:
        """URL pública do PDF do parecer."""
        return URL_INTEIRO_TEOR + self.codteor


@dataclass(frozen=True)
class Relatoria:
    """Relatoria do órgão onde houve parecer."""

    orgao_sigla: str
    relator: Parlamentar
    resumo_inicio: str
    resumo_fim: str
    pareceres: list[Parecer]


@dataclass(frozen=True)
class Situacao:
    """Situação atual da proposição."""

    descricao: str
    estado: str
    orgao_sigla: str
    orgao_nome: str
    desde: date
    rotulo_tempo: str = "NESTA SITUAÇÃO HÁ"
    rotulo_indicador: str = "DIAS NA SITUAÇÃO ATUAL"


@dataclass(frozen=True)
class Proposicao:
    """Dados de identificação da proposição."""

    id: int
    casa: str
    identificacao: str
    ementa: str
    explicacao: str
    codteor_inteiro_teor: str
    metadados: list[dict[str, str]]
    apresentacao: date
    rotulo_apreciacao: str
    nota_apreciacao: str
    emendas_apresentadas: int = 0

    @property
    def url_inteiro_teor(self) -> str:
        """URL pública do inteiro teor da proposição."""
        return URL_INTEIRO_TEOR + self.codteor_inteiro_teor


@dataclass(frozen=True)
class MarcoFuturo:
    """Próximo passo previsto na tramitação."""

    titulo: str
    descricao: str


@dataclass(frozen=True)
class Relatorio:
    """Conjunto completo de dados que alimenta o relatório de tramitação."""

    data_consulta: date
    proposicao: Proposicao
    autor: Parlamentar
    situacao: Situacao
    estagios: list[Estagio]
    relatoria: Relatoria | None
    fases: list[Fase]
    proximos_marcos: list[MarcoFuturo] = field(default_factory=list)

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Relatorio:
        """Cria o relatório completo a partir do dicionário lido do JSON."""
        prop = dict(dados["proposicao"])
        prop["apresentacao"] = date.fromisoformat(prop["apresentacao"])
        prop["codteor_inteiro_teor"] = str(prop["codteor_inteiro_teor"])
        situacao = dict(dados["situacao"])
        situacao["desde"] = date.fromisoformat(situacao["desde"])
        relatoria = None
        if dados.get("relatoria"):
            r = dados["relatoria"]
            relatoria = Relatoria(
                orgao_sigla=r["orgao_sigla"],
                relator=Parlamentar.de_dict(r["relator"]),
                resumo_inicio=r["resumo_inicio"],
                resumo_fim=r["resumo_fim"],
                pareceres=[Parecer(**{**p, "codteor": str(p["codteor"])}) for p in r["pareceres"]],
            )
        return cls(
            data_consulta=date.fromisoformat(dados["data_consulta"]),
            proposicao=Proposicao(**prop),
            autor=Parlamentar.de_dict(dados["autor"]),
            situacao=Situacao(**situacao),
            estagios=[Estagio.de_dict(e) for e in dados["estagios"]],
            relatoria=relatoria,
            fases=[Fase.de_dict(f) for f in dados["fases"]],
            proximos_marcos=[MarcoFuturo(**m) for m in dados.get("proximos_marcos", [])],
        )


def carregar_relatorio(caminho: str | Path) -> Relatorio:
    """Lê um arquivo JSON de dados e devolve o :class:`Relatorio` correspondente."""
    with open(caminho, encoding="utf-8") as arquivo:
        return Relatorio.de_dict(json.load(arquivo))


def _data_opcional(valor: str | None) -> date | None:
    """Converte uma data ISO opcional."""
    return date.fromisoformat(valor) if valor else None

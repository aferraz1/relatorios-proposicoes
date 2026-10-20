"""Indicadores derivados dos dados de tramitação (contagens e durações)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from relatorios_proposicoes.modelos import Estagio, Evento, Relatorio

TITULO_RETIRADA_DE_PAUTA = "Retirada de Pauta"


@dataclass(frozen=True)
class Indicador:
    """Valor numérico com rótulo, exibido na grade de indicadores."""

    valor: int
    rotulo: str


@dataclass(frozen=True)
class Progresso:
    """Andamento das comissões de mérito e admissibilidade."""

    concluidas: int
    total: int

    @property
    def percentual(self) -> float:
        """Percentual concluído, de 0 a 100."""
        return 100 * self.concluidas / self.total if self.total else 0.0


def todos_eventos(relatorio: Relatorio) -> list[Evento]:
    """Lista todos os eventos de todas as fases, na ordem do histórico."""
    return [evento for fase in relatorio.fases for evento in fase.eventos]


def total_eventos_com_documento(relatorio: Relatorio) -> int:
    """Conta os eventos que têm documento associado."""
    return sum(1 for evento in todos_eventos(relatorio) if evento.documento)


def ultima_movimentacao(relatorio: Relatorio) -> date | None:
    """Data do evento mais recente do histórico."""
    eventos = todos_eventos(relatorio)
    return max(evento.data_hora for evento in eventos).date() if eventos else None


def dias_na_situacao(relatorio: Relatorio) -> int:
    """Dias corridos desde o início da situação atual até a data da consulta."""
    return (relatorio.data_consulta - relatorio.situacao.desde).days


def duracao_estagio(estagio: Estagio, referencia: date) -> int | None:
    """Duração do estágio em dias; estágios em curso contam até ``referencia``."""
    if estagio.inicio is None:
        return None
    return ((estagio.fim or referencia) - estagio.inicio).days


def progresso_comissoes(relatorio: Relatorio) -> Progresso:
    """Quantas comissões do despacho já concluíram sua análise."""
    comissoes = [e for e in relatorio.estagios if e.comissao]
    return Progresso(concluidas=sum(1 for e in comissoes if e.estado == "concluido"), total=len(comissoes))


def calcular_indicadores(relatorio: Relatorio) -> list[Indicador]:
    """Monta a grade de indicadores de tramitação na ordem de exibição."""
    referencia = relatorio.data_consulta
    indicadores = [Indicador((referencia - relatorio.proposicao.apresentacao).days, "DIAS EM TRAMITAÇÃO")]

    concluidas = [e for e in relatorio.estagios if e.comissao and e.estado == "concluido"]
    if concluidas:
        ultima = concluidas[-1]
        dias = duracao_estagio(ultima, referencia)
        if dias is not None:
            indicadores.append(Indicador(dias, f"DIAS NA {ultima.sigla}"))

    indicadores.append(Indicador(dias_na_situacao(relatorio), relatorio.situacao.rotulo_indicador))
    indicadores.append(
        Indicador(
            sum(1 for e in todos_eventos(relatorio) if e.titulo == TITULO_RETIRADA_DE_PAUTA),
            "RETIRADAS DE PAUTA",
        )
    )
    if relatorio.relatoria:
        indicadores.append(Indicador(len(relatorio.relatoria.pareceres), "VERSÕES DO PARECER"))
    indicadores.append(Indicador(relatorio.proposicao.emendas_apresentadas, "EMENDAS APRESENTADAS"))
    return indicadores

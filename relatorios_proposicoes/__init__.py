"""Relatórios de Tramitação e Análise de Proposições Legislativas."""

from relatorios_proposicoes.modelos import Relatorio, carregar_relatorio
from relatorios_proposicoes.gerador import renderizar_relatorio

__all__ = ["Relatorio", "carregar_relatorio", "renderizar_relatorio"]

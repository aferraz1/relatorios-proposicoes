"""Relatórios de Tramitação e Análise de Proposições Legislativas."""

from relatorios_proposicoes.modelos import Relatorio, carregar_relatorio
from relatorios_proposicoes.gerador import carregar_pagina, renderizar, renderizar_relatorio

__all__ = ["Relatorio", "carregar_pagina", "carregar_relatorio", "renderizar", "renderizar_relatorio"]

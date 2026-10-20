"""Testes do carregamento, dos indicadores e da renderização do relatório."""

from pathlib import Path

import pytest

from relatorios_proposicoes import carregar_relatorio, renderizar_relatorio
from relatorios_proposicoes.gerador import periodo_estagio
from relatorios_proposicoes.indicadores import (
    calcular_indicadores,
    progresso_comissoes,
    total_eventos_com_documento,
    todos_eventos,
    ultima_movimentacao,
)

DADOS = Path(__file__).resolve().parent.parent / "dados" / "pl-1680-2025.json"


@pytest.fixture(scope="module")
def relatorio():
    """Relatório de exemplo do PL 1.680/2025."""
    return carregar_relatorio(DADOS)


def test_contagens_do_historico(relatorio):
    assert len(todos_eventos(relatorio)) == 30
    assert total_eventos_com_documento(relatorio) == 11
    assert ultima_movimentacao(relatorio).isoformat() == "2026-07-02"


def test_indicadores_calculados(relatorio):
    valores = {i.rotulo: i.valor for i in calcular_indicadores(relatorio)}
    assert valores == {
        "DIAS EM TRAMITAÇÃO": 554,
        "DIAS NA CCTI": 380,
        "DIAS SEM RELATOR NA CFT": 110,
        "RETIRADAS DE PAUTA": 5,
        "VERSÕES DO PARECER": 3,
        "EMENDAS APRESENTADAS": 0,
    }


def test_progresso_das_comissoes(relatorio):
    progresso = progresso_comissoes(relatorio)
    assert (progresso.concluidas, progresso.total) == (1, 3)
    assert round(progresso.percentual) == 33


def test_periodo_dos_estagios(relatorio):
    assert [periodo_estagio(e) for e in relatorio.estagios[:4]] == [
        "14/04/25 → 26/05/25",
        "26/05/25 → 10/06/26",
        "DESDE 02/07/26",
        "A INICIAR",
    ]


def test_renderizacao(relatorio):
    html = renderizar_relatorio(relatorio)
    assert "<title>Tramitação do PL 1.680/2025</title>" in html
    assert "30 REGISTROS · 11 COM DOCUMENTO" in html
    assert "110 dias" in html
    assert "1 de 3 · 33%" in html
    assert html.count('class="evento evento--') == 30
    assert html.count('class="estagio estagio--') == 6
    assert "bandep/122974.jpg" in html and "bandep/204511.jpg" in html
    assert "codteor=3132208" in html
    # Links externos sempre abrem em nova aba com rel seguro.
    assert html.count('target="_blank"') == html.count('rel="noopener noreferrer"')


def test_texto_e_escapado(relatorio):
    from dataclasses import replace

    alterado = replace(relatorio, situacao=replace(relatorio.situacao, descricao="<script>x</script>"))
    assert "<script>x</script>" not in renderizar_relatorio(alterado)

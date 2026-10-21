"""Testes do carregamento, dos indicadores e da renderização do relatório."""

from pathlib import Path

import pytest

from relatorios_proposicoes import carregar_relatorio, renderizar_relatorio
from relatorios_proposicoes.gerador import negrito, periodo_estagio
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


@pytest.fixture(scope="module")
def html(relatorio):
    """HTML do relatório de exemplo no tema padrão."""
    return renderizar_relatorio(relatorio)


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
    assert [periodo_estagio(e) for e in relatorio.estagios] == [
        "14/04/25 → 26/05/25",
        "26/05/25 → 10/06/26",
        "DESDE 02/07/26",
        "A INICIAR",
        "A INICIAR",
    ]


def test_termos_de_indexacao(relatorio):
    termos = relatorio.proposicao.termos_indexacao
    assert len(termos) == 15
    # A vírgula dentro de parênteses não separa termos; o ponto final é removido.
    assert "Lei de Licitações e Contratos Administrativos (2021)" in termos
    assert termos[-1] == "Zona Especial de Processamento e Armazenamento Digitais (ZEPAD)"


def test_arvore_e_anexos(relatorio):
    arvore = relatorio.arvore
    assert arvore.resumo == (
        "Nenhuma proposição apensada. Ficam vinculados à matéria 35 documentos acessórios: "
        "8 pareceres e substitutivos, 9 requerimentos e 18 requerimentos de retirada de pauta."
    )
    assert arvore.localizar("RPD 6 CCTI").id == 2543883
    with pytest.raises(KeyError):
        arvore.localizar("PL 0/0000")

    anexos = {c.titulo: c for c in relatorio.anexos}
    assert len(anexos) == 10
    assert [i.sigla for i in anexos["Mensagens, Ofícios e Requerimentos"].itens] == ["REQ 29/2025 CCTI"]
    assert anexos["Histórico de Pareceres, Substitutivos e Votos"].contador == "8"
    assert anexos["Avulsos"].contador == "PDF" and not anexos["Avulsos"].vazia
    assert anexos["Destaques"].vazia and anexos["Redação Final"].vazia
    assert anexos["Relatório de conferência de assinaturas"].mensagem_vazio.endswith("até 20/10/2026.")


def test_documentos_aprovados(relatorio):
    aprovados = relatorio.documentos_aprovados
    assert sorted(aprovados) == ["p2625725", "p2636781", "p2636782"]
    assert aprovados["p2636782"].rotulo_acionador == "SBT-A 1 CCTI · TEXTO VIGENTE"
    # O texto vigente do cabeçalho usa a mesma chave do nó da árvore.
    assert relatorio.versao_valida.documento.valor == "p2636782"


def test_renderizacao(html):
    assert "<title>Tramitação do PL 1.680/2025</title>" in html
    assert '<html lang="pt-BR" data-tema="claro">' in html
    assert "30 REGISTROS · 11 COM DOCUMENTO" in html
    assert "110 dias" in html
    assert "1 de 3 · 33%" in html
    assert html.count('class="evento evento--') == 30
    assert html.count('class="estagio estagio--') == 5
    assert "bandep/122974.jpg" in html and "bandep/204511.jpg" in html
    assert "codteor=3132208" in html
    # Links externos sempre abrem em nova aba com rel seguro.
    assert html.count('target="_blank"') == html.count('rel="noopener noreferrer"')


def test_secoes_do_design(html):
    assert "TEXTO VIGENTE · SBT-A" in html and "TEXTO ORIGINAL" in html
    assert "15 TERMOS" in html
    assert "PARECERES E SUBSTITUTIVOS · CCTI (8)" in html and "+6 RPD" in html
    # Uma janela para a raiz, uma para cada nó da árvore e uma para cada categoria de anexos.
    assert html.count('<dialog class="janela"') == 1 + 8 + 9 + 10
    assert html.count('data-janela="janela-anexo-') == 10
    assert 'id="popover-versao"' in html and 'data-valor-versao="p2636782"' in html
    assert "12 RISCOS · 3 ALTOS" in html and "12 AÇÕES · 3 CRÍTICAS" in html
    assert "8 OPORTUNIDADES" in html and "27 FONTES" in html
    assert "<strong>lei-quadro de data centers</strong>" in html
    # Componentes do documento aprovado acionam o popover em vez de abrir janela: etapa, 4 eventos,
    # link e cartão da relatoria, nó da árvore e o inteiro teor nas janelas do nó e dos anexos.
    assert html.count('data-origem="PRL 3 CCTI · PARECER APROVADO"') == 10


def test_tema_escuro(relatorio):
    assert '<html lang="pt-BR" data-tema="escuro">' in renderizar_relatorio(relatorio, tema="escuro")
    with pytest.raises(ValueError):
        renderizar_relatorio(relatorio, tema="sepia")


def test_texto_e_escapado(relatorio):
    from dataclasses import replace

    alterado = replace(relatorio, situacao=replace(relatorio.situacao, descricao="<script>x</script>"))
    assert "<script>x</script>" not in renderizar_relatorio(alterado)
    assert str(negrito("a **<b>** c")) == "a <strong>&lt;b&gt;</strong> c"

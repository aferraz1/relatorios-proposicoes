"""Testes da capa, da pesquisa de proposições e da linha de comando."""

import json
from pathlib import Path

import pytest

from relatorios_proposicoes.__main__ import main
from relatorios_proposicoes.capa import Capa
from relatorios_proposicoes.gerador import carregar_pagina, renderizar
from relatorios_proposicoes.modelos import Relatorio
from relatorios_proposicoes.pesquisa import BasePesquisa

PASTA_DADOS = Path(__file__).resolve().parent.parent / "dados"


def test_capa():
    capa = carregar_pagina(PASTA_DADOS / "capa.json")
    assert isinstance(capa, Capa)
    assert capa.assessor.url_whatsapp == "https://wa.me/5561982118822"
    html = renderizar(capa)
    assert "Data de emissão: 20/10/2026" in html and "Atualizado em 20/10/2026" in html
    assert 'href="mailto:alexandre.ferraz@gmail.com"' in html
    # Imagens e fontes ficam embutidas: a capa não depende de arquivos externos.
    assert html.count("data:image/") == 7 and html.count("data:font/woff2") == 4
    assert "/_blob/" not in html


def test_pesquisa():
    base = carregar_pagina(PASTA_DADOS / "pesquisa-cti.json")
    assert isinstance(base, BasePesquisa)
    assert base.total == 637
    html = renderizar(base, tema="escuro")
    assert '<html lang="pt-BR" data-tema="escuro">' in html
    assert "Base local: 637 proposições" in html and "21/10/2026" in html
    dados = html.split('<script type="application/json" id="pq-dados">')[1].split("</script>")[0]
    assert "<" not in dados
    assert json.loads(dados)["detalhes"]["2497586"]["arquivo"] == "pl-1680-2025.html"


def test_pesquisa_rejeita_indice_invalido():
    dados = json.loads((PASTA_DADOS / "pesquisa-cti.json").read_text(encoding="utf-8"))
    dados["L"][0][7] = len(dados["S"])
    with pytest.raises(ValueError, match="tabela S"):
        BasePesquisa.de_dict(dados)
    del dados["TP"]
    with pytest.raises(ValueError, match="TP"):
        BasePesquisa.de_dict(dados)


def test_tramitacao_e_o_padrao():
    assert isinstance(carregar_pagina(PASTA_DADOS / "pl-1680-2025.json"), Relatorio)


def test_cli_gera_varias_paginas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main([str(PASTA_DADOS / "capa.json"), str(PASTA_DADOS / "pl-1680-2025.json"), "--tema", "escuro"])
    assert (tmp_path / "saida" / "capa.html").exists()
    assert 'data-tema="escuro"' in (tmp_path / "saida" / "pl-1680-2025.html").read_text(encoding="utf-8")
    assert capsys.readouterr().out.count("Página gerada em") == 2
    with pytest.raises(SystemExit):
        main([str(PASTA_DADOS / "capa.json"), str(PASTA_DADOS / "pl-1680-2025.json"), "-o", "x.html"])


def test_relatorio_pl_649_2021():
    relatorio = carregar_pagina(PASTA_DADOS / "pl-649-2021.json")
    assert relatorio.versao_valida is None and not relatorio.documentos_aprovados
    assert relatorio.relatoria.pareceres[0].rotulo_status == "NÃO VOTADO"
    assert relatorio.arvore.localizar("PL 2630/2020").situacao == "PRONTA PARA PAUTA"
    html = renderizar(relatorio)
    assert "NÃO VOTADO" in html and "SUPERADO" not in html
    assert "2004 dias" in html and 'id="popover-versao"' not in html


def test_sumario():
    from relatorios_proposicoes.sumario import Sumario, nome_arquivo

    sumario = carregar_pagina(PASTA_DADOS / "sumario.json")
    assert isinstance(sumario, Sumario)
    assert len(sumario.itens) == 64 and sumario.tipos == "PL e PLP"
    datas = [i.apresentacao for i in sumario.itens]
    assert datas == sorted(datas, reverse=True)
    # O relatório curado do PL 1.680/2025 entra uma única vez, com o seu arquivo.
    assert [i.arquivo for i in sumario.itens].count("pl-1680-2025.html") == 1
    assert nome_arquivo("PLP 157/2020") == "plp-157-2020"
    html = renderizar(sumario)
    assert "64 proposições (PL e PLP) em tramitação" in html
    assert html.count('class="sumario__item"') == 64
    assert html.index('href="pl-3507-2026.html"') < html.index('href="pl-245-2019.html"')
    assert '<span class="sumario__numero rotulo" aria-hidden="true">01</span>' in html


def test_sumario_sem_relatorios(tmp_path):
    from relatorios_proposicoes.sumario import Sumario

    with pytest.raises(ValueError, match="Nenhum relatório"):
        Sumario.de_dict({"sobre": "", "descricao": "", "relatorios": ["*.json"]}, tmp_path)

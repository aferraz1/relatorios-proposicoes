"""Testes do coletor da API de Dados Abertos (sem rede, com respostas simuladas)."""

import json
from datetime import date

import pytest

from relatorios_proposicoes.coleta import (
    MontadorRelatorio,
    comissoes_do_despacho,
    identificacao,
    main,
    nome_arquivo,
    sigla_acessoria,
    tipo_evento,
)
from relatorios_proposicoes.modelos import Relatorio

API = "https://dadosabertos.camara.leg.br/api/v2"
ORGAOS = {
    4: {"sigla": "MESA", "nome": "Mesa Diretora da Câmara dos Deputados", "apelido": "Mesa Diretora", "codTipoOrgao": 1},
    186: {"sigla": "CCP", "nome": "COORDENAÇÃO DE COMISSÕES PERMANENTES", "apelido": "", "codTipoOrgao": 12000},
    2002: {"sigla": "CCTI", "nome": "Comissão de Ciência, Tecnologia e Inovação", "apelido": "Ciência, Tecnologia e Inovação", "codTipoOrgao": 2},
    2010: {"sigla": "CFT", "nome": "Comissão de Finanças e Tributação", "apelido": "Finanças e Tributação", "codTipoOrgao": 2},
    2003: {"sigla": "CCJC", "nome": "Comissão de Constituição e Justiça e de Cidadania", "apelido": "Constituição e Justiça e de Cidadania", "codTipoOrgao": 2},
    180: {"sigla": "PLEN", "nome": "Plenário", "apelido": "Plenário", "codTipoOrgao": 26},
}


def tramite(seq, data, orgao, descricao, despacho="", url=None):
    return {"sequencia": seq, "dataHora": data, "siglaOrgao": ORGAOS[orgao]["sigla"], "uriOrgao": f"{API}/orgaos/{orgao}",
            "descricaoTramitacao": descricao, "despacho": despacho, "url": url}


class ClienteFalso:
    """Responde às rotas usadas pelo montador com dados fixos."""

    def __init__(self, tramites):
        teor = "https://www.camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor="
        self.rotas = {
            "/proposicoes/1": {
                "id": 1, "siglaTipo": "PL", "numero": 1234, "ano": 2025, "descricaoTipo": "Projeto de Lei",
                "ementa": "Dispõe sobre  testes.", "ementaDetalhada": "", "keywords": "teste, coleta (API, Câmara).",
                "dataApresentacao": "2025-01-10T10:00", "urlInteiroTeor": teor + "100",
                "uriPropPrincipal": None,
                "statusProposicao": {"dataHora": tramites[-1]["dataHora"], "siglaOrgao": "CCP", "uriOrgao": f"{API}/orgaos/186",
                                     "uriUltimoRelator": f"{API}/deputados/20", "regime": "Ordinário (Art. 151, III, RICD)",
                                     "descricaoSituacao": "Aguardando Designação de Relator(a)", "descricaoTramitacao": "Recebimento",
                                     "apreciacao": "Proposição Sujeita à Apreciação Conclusiva pelas Comissões - Art. 24 II"},
            },
            "/proposicoes/1/tramitacoes": tramites,
            "/proposicoes/1/autores": [{"uri": f"{API}/deputados/10", "nome": "Autora", "ordemAssinatura": 1}],
            "/proposicoes/1/temas": [{"tema": "Ciência, Tecnologia e Inovação", "codTema": 62}],
            "/proposicoes/1/relacionadas": [
                {"id": 50, "siglaTipo": "PRL", "numero": "1", "ano": "0", "ementa": "Parecer do Relator"},
                {"id": 51, "siglaTipo": "REQ", "numero": "3", "ano": "2025", "ementa": "Requer audiência"},
            ],
            "/proposicoes/50": {"ementa": "Parecer do Relator (CCTI)", "dataApresentacao": "2025-03-01T10:00",
                                "urlInteiroTeor": teor + "200", "uriOrgaoNumerador": None, "descricaoTipo": "Parecer do Relator"},
            "/proposicoes/51": {"ementa": "Requer audiência", "dataApresentacao": "2025-02-01T10:00", "urlInteiroTeor": teor + "300",
                                "uriOrgaoNumerador": f"{API}/orgaos/2002", "descricaoTipo": "Requerimento"},
            "/deputados/10": {"sexo": "F", "ultimoStatus": {"nome": "Autora", "nomeEleitoral": "Autora", "siglaPartido": "AA", "siglaUf": "MA"}},
            "/deputados/20": {"sexo": "M", "ultimoStatus": {"nome": "Relator", "nomeEleitoral": "Relator", "siglaPartido": "BB", "siglaUf": "SP"}},
            **{f"/orgaos/{k}": v for k, v in ORGAOS.items()},
        }

    def obter(self, caminho):
        return self.rotas[caminho]


DESPACHO = "Às Comissões de Ciência, Tecnologia e Inovação; Finanças e Tributação (Mérito e Art. 54, RICD) e Constituição e Justiça e de Cidadania (Art. 54 RICD)"
APELIDOS = {o["apelido"]: o["sigla"] for o in ORGAOS.values() if o["codTipoOrgao"] == 2}
TEOR = "https://www.camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor="


@pytest.fixture
def dados():
    tramites = [
        tramite(1, "2025-01-10T10:00", 4, "Apresentação de Proposição", "Apresentação do PL", TEOR + "100"),
        tramite(2, "2025-01-20T10:00", 4, "Distribuição", DESPACHO, TEOR + "150"),
        tramite(3, "2025-01-21T10:00", 2002, "Recebimento", "Recebimento pela CCTI."),
        tramite(4, "2025-02-01T10:00", 2002, "Designação de Relator(a)", "Designado relator."),
        tramite(5, "2025-02-05T10:00", 2002, "Retirada de Pauta", "Retirado de pauta."),
        tramite(6, "2025-03-01T10:00", 2002, "Parecer do(a) Relator(a)", "Pela aprovação.", TEOR + "200"),
        tramite(7, "2025-03-10T10:00", 2002, "Aprovação do Parecer", "Aprovado."),
        tramite(9, "2025-03-12T00:00", 186, "Publicação de Proposição", "Parecer publicado."),
        tramite(8, "2025-03-11T10:00", 2010, "Recebimento", "Recebimento pela CFT."),
    ]
    montador = MontadorRelatorio(ClienteFalso(tramites), date(2025, 4, 10), apelidos=APELIDOS)
    return montador.montar(1)


def test_funcoes_auxiliares():
    assert identificacao("PL", 1680, 2025) == "PL 1.680/2025"
    assert tipo_evento("Retirada de Pauta") == "alerta"
    assert tipo_evento("Designação de Relator(a)") == "marco"
    assert tipo_evento("Recebimento") == "rotina"
    assert comissoes_do_despacho(DESPACHO, APELIDOS) == [("CCTI", "Mérito"), ("CFT", "Mérito e Art. 54"), ("CCJC", "Art. 54")]
    item = {"siglaTipo": "PAR", "numero": "1", "ano": "0", "ementa": ""}
    assert sigla_acessoria(item, {"ementa": "Parecer da Comissão (CCTI) ao PL"}, None) == "PAR 1 CCTI"
    assert sigla_acessoria({"siglaTipo": "REQ", "numero": "29", "ano": "2025"}, {}, "CCTI") == "REQ 29/2025 CCTI"
    urgencia = {"siglaTipo": "REQ", "numero": "2888", "ano": "2026"}
    assert sigla_acessoria(urgencia, {"ementa": "Urgência para o fundo (FDNE)"}, None, {"CCTI", "CFT"}) == "REQ 2888/2026"


def test_montagem(dados):
    assert dados["proposicao"]["identificacao"] == "PL 1.234/2025"
    assert dados["proposicao"]["ementa"] == "Dispõe sobre testes."
    assert dados["autor"]["descricao"] == "Deputada Federal · AA/MA"
    # O órgão administrativo (CCP) não vira órgão atual; a situação começa na chegada à CFT.
    assert (dados["situacao"]["orgao_sigla"], dados["situacao"]["desde"], dados["situacao"]["estado"]) == ("CFT", "2025-03-11", "PARADA")
    assert [(e["sigla"], e["estado"]) for e in dados["estagios"]] == [
        ("MESA", "concluido"), ("CCTI", "concluido"), ("CFT", "atual"), ("CCJC", "pendente"), ("REMESSA", "pendente")]
    # Sem PDF no trâmite de aprovação, a etapa usa o último parecer do relator na comissão.
    assert dados["estagios"][1]["documento"] == {"codteor": "200", "nome": "PARECER APROVADO", "id": 50}
    eventos = [e for f in dados["fases"] for e in f["eventos"]]
    assert [f["sigla"] for f in dados["fases"]] == ["MESA", "CCTI", "CFT"]
    assert eventos[0]["etiqueta"] == "INÍCIO"
    assert eventos[-2]["tipo"] == "atual" and eventos[-1]["tipo"] == "rotina"
    assert eventos[4]["etiqueta"] == "1ª RETIRADA"
    assert eventos[5]["documento"] == {"codteor": "200", "nome": "PRL 1 CCTI", "id": 50}
    assert eventos[-1]["texto"].endswith("(CCP)")
    rel = dados["relatoria"]
    assert rel["orgao_sigla"] == "CCTI" and rel["pareceres"][0]["aprovado"]
    assert [g["rotulo"] for g in dados["arvore"]["grupos"]] == ["PARECERES, SUBSTITUTIVOS E VOTOS", "REQUERIMENTOS"]
    assert nome_arquivo(dados) == "pl-1234-2025"


def test_dados_sao_lidos_pelo_relatorio(dados):
    relatorio = Relatorio.de_dict(dados)
    assert relatorio.arvore.resumo.endswith("1 pareceres, substitutivos e votos e 1 requerimentos.")
    assert [c.contador for c in relatorio.anexos][:3] == ["PDF", "1", "1"]
    assert relatorio.proposicao.termos_indexacao == ["teste", "coleta (API, Câmara)"]


def test_cli_atualiza_detalhes_da_pesquisa(tmp_path, dados, monkeypatch):
    base = tmp_path / "base.json"
    base.write_text('{\n  "pagina": "pesquisa",\n  "detalhes": {},\n  "L": [\n    [1,"PL",1234,2025]\n  ]\n}\n', encoding="utf-8")
    monkeypatch.setattr(MontadorRelatorio, "montar", lambda self, i: dados)
    main(["1", "-o", str(tmp_path / "props"), "--pesquisa", str(base), "--data", "2025-04-10"], cliente_fabrica=lambda: None)
    assert (tmp_path / "props" / "pl-1234-2025.json").exists()
    detalhes = json.loads(base.read_text(encoding="utf-8"))["detalhes"]
    assert detalhes == {"1": {"arquivo": "pl-1234-2025.html", "titulo": "Tramitação PL 1.234/2025", "coleta": "2025-04-10"}}


def test_recoleta_preserva_analise(tmp_path, dados, monkeypatch):
    pasta = tmp_path / "props"
    pasta.mkdir()
    (pasta / "pl-1234-2025.json").write_text(json.dumps({**dados, "analise": {"introducao": "manual"}}), encoding="utf-8")
    monkeypatch.setattr(MontadorRelatorio, "montar", lambda self, i: dict(dados))
    main(["1", "-o", str(pasta), "--data", "2025-04-10"], cliente_fabrica=lambda: None)
    assert json.loads((pasta / "pl-1234-2025.json").read_text(encoding="utf-8"))["analise"] == {"introducao": "manual"}


def test_urgencia_deixa_comissoes_para_o_plenario():
    tramites = [
        tramite(1, "2025-01-10T10:00", 4, "Apresentação de Proposição", "Apresentação", TEOR + "100"),
        tramite(2, "2025-01-20T10:00", 4, "Distribuição", DESPACHO),
        tramite(3, "2025-01-21T10:00", 2002, "Recebimento", "Recebimento pela CCTI."),
        tramite(4, "2025-01-25T10:00", 180, "Aprovação de Urgência (154, 155 ou 64 CF)", "Aprovado o requerimento."),
        tramite(5, "2025-01-26T10:00", 2010, "Recebimento", "Recebimento pela CFT."),
        tramite(6, "2025-02-01T10:00", 180, "Designação de Relator(a)", "Designado relator."),
    ]
    dados = MontadorRelatorio(ClienteFalso(tramites), date(2025, 4, 10), apelidos=APELIDOS).montar(1)
    etapas = {e["sigla"]: (e["estado"], e["papel"]) for e in dados["estagios"]}
    assert etapas["CCTI"] == ("pendente", "Mérito · parecer em Plenário")
    assert etapas["CFT"][0] == "pendente" and etapas["PLEN"][0] == "atual"
    assert "Prazo de recurso ao Plenário" not in [m["titulo"] for m in dados["proximos_marcos"]]


def test_apresentacao_no_plenario_nao_cria_etapa():
    tramites = [
        tramite(1, "2025-01-10T10:00", 180, "Apresentação de Proposição", "Apresentação", TEOR + "100"),
        tramite(2, "2025-01-20T10:00", 4, "Distribuição", DESPACHO),
        tramite(3, "2025-01-21T10:00", 2002, "Recebimento", "Recebimento pela CCTI."),
    ]
    dados = MontadorRelatorio(ClienteFalso(tramites), date(2025, 4, 10), apelidos=APELIDOS).montar(1)
    assert "PLEN" not in [e["sigla"] for e in dados["estagios"]]


def test_despacho_revisto_ignora_comissoes_extintas():
    apelidos = {"Desenvolvimento Econômico": "CDE", "Indústria, Comércio e Serviços": "CICS", "Trabalho": "CTRAB",
                "Administração e Serviço Público": "CASP", "Esporte": "CESPO", "Finanças e Tributação": "CFT",
                "Constituição e Justiça e de Cidadania": "CCJC"}
    original = ("Às Comissões de Desenvolvimento Econômico, Indústria, Comércio e Serviços; Trabalho, de Administração "
                "e Serviço Público; Finanças e Tributação (Mérito e Art. 54, RICD) e Constituição e Justiça e de Cidadania (Art. 54 RICD)")
    assert comissoes_do_despacho(original, apelidos) == [
        ("CDE", "Mérito"), ("CTRAB", "Mérito"), ("CFT", "Mérito e Art. 54"), ("CCJC", "Art. 54")]
    revisto = ("Revejo o despacho para determinar a substituição da Comissão de Desenvolvimento Econômico pela Comissão de "
               "Indústria, Comércio e Serviços.[ATUALIZAÇÃO DE DESPACHO: Às Comissões de Indústria, Comércio e Serviços; "
               "Trabalho; Finanças e Tributação (Mérito e Art. 54, RICD) e Constituição e Justiça e de Cidadania (Art. 54 RICD)]")
    assert comissoes_do_despacho(revisto, apelidos) == [
        ("CICS", "Mérito"), ("CTRAB", "Mérito"), ("CFT", "Mérito e Art. 54"), ("CCJC", "Art. 54")]


def test_relator_que_saiu_da_comissao_vira_ex_relator():
    tramites = [
        tramite(1, "2025-01-10T10:00", 4, "Apresentação de Proposição", "Apresentação do PL", TEOR + "100"),
        tramite(2, "2025-01-20T10:00", 4, "Distribuição", DESPACHO, TEOR + "150"),
        tramite(3, "2025-01-21T10:00", 2002, "Recebimento", "Recebimento pela CCTI."),
        tramite(4, "2025-02-01T10:00", 2002, "Designação de Relator(a)", "Designado relator."),
        tramite(5, "2025-04-01T10:00", 2002, "Saída de Relator(a) da Comissão - Sem Parecer Apresentado", "Deixou de ser membro."),
    ]
    relatorio = MontadorRelatorio(ClienteFalso(tramites), date(2025, 4, 10), apelidos=APELIDOS).montar(1)
    assert relatorio["relatoria"]["relator"]["rotulo"] == "EX-RELATOR(A) · CCTI"
    assert "Deixou a relatoria em 01/04/2025" in relatorio["relatoria"]["resumo_fim"]

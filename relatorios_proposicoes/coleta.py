"""Coleta na API de Dados Abertos da Câmara e montagem do JSON do relatório de tramitação.

O JSON gerado segue o formato lido por :meth:`relatorios_proposicoes.modelos.Relatorio.de_dict`.
Seções que dependem de avaliação humana (versão válida e análise estratégica) não são geradas.

Uso::

    python -m relatorios_proposicoes.coleta 2497586 2263584 -o dados/proposicoes
    python -m relatorios_proposicoes.coleta --ids-de dados/pesquisa-pedro-lucas.json \\
        -o dados/proposicoes --pesquisa dados/pesquisa-pedro-lucas.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from relatorios_proposicoes.sumario import nome_arquivo as nome_relatorio

API = "https://dadosabertos.camara.leg.br/api/v2"
SECOES_MANUAIS = ("versao_valida", "analise")

# Tipos de órgão (referencias/orgaos/codTipoOrgao).
TIPOS_COMISSAO = {2, 3, 13000}
TIPOS_PLENARIO = {26, 27}
TIPO_MESA = 1

TIPOS_PRINCIPAIS = {"PL", "PLP", "PEC", "PDL", "PLV", "MPV", "PDC", "PRC", "PLN"}
GRUPOS_ACESSORIOS: list[tuple[str, str, set[str]]] = [
    ("PARECERES, SUBSTITUTIVOS E VOTOS", "pareceres, substitutivos e votos",
     {"PRL", "PRLP", "PRLE", "PAR", "PARF", "SBT", "SBT-A", "SBE", "SBE-A", "SBR", "PPP", "PEP", "PES", "SSP", "VTS", "CVO"}),
    ("EMENDAS", "emendas", {"EMC", "EMC-A", "EMP", "EMR", "ESB", "ERD", "EMA", "EMS"}),
    ("DESTAQUES", "destaques", {"DTQ"}),
    ("REQUERIMENTOS", "requerimentos", {"REQ", "RIC", "INC"}),
    ("RETIRADAS DE PAUTA", "requerimentos de retirada de pauta", {"RPD", "RPDR"}),
    ("REDAÇÃO FINAL E AUTÓGRAFOS", "documentos de redação final e autógrafos", {"RDF", "AA"}),
]

TRAMITES_MARCO = (
    "Apresentação de Proposição", "Distribuição", "Designação de Relator", "Parecer do(a) Relator(a)",
    "Aprovação do Parecer", "Aprovação de Proposição", "Aprovação de Urgência", "Despacho de Apensação",
    "Remessa", "Votação", "Aprovação", "Transformação",
)
TRAMITES_ALERTA = (
    "Retirada de Pauta", "Saída de Relator", "Devolução", "Arquivamento", "Prejudicialidade",
    "Rejeição", "Retirada pelo Autor",
)

ESTADOS_SITUACAO = {
    "Aguardando Designação de Relator(a)": "PARADA",
    "Tramitando em Conjunto": "APENSADA",
    "Aguardando Apreciação pelo Senado Federal": "NO SENADO",
    "Pronta para Pauta": "PRONTA PARA PAUTA",
    "Aguardando Parecer": "EM ANÁLISE",
}

NOTA_CONCLUSIVA = (
    "Etapas na Câmara dos Deputados conforme o RICD: apreciação conclusiva pelas comissões (art. 24, II). "
    "Concluída a última comissão, a Mesa envia o projeto ao Senado Federal, salvo recurso de 1/10 dos "
    "deputados para apreciação pelo Plenário (arts. 58, § 1º, e 132, § 2º)."
)
NOTA_PLENARIO = (
    "Etapas na Câmara dos Deputados conforme o RICD: após os pareceres das comissões, a proposição é "
    "apreciada pelo Plenário e, aprovada, segue ao Senado Federal."
)


# ---------------------------------------------------------------------------
# Acesso à API
# ---------------------------------------------------------------------------
class ClienteApi:
    """Cliente mínimo da API de Dados Abertos, com cache em memória e novas tentativas."""

    def __init__(self, base: str = API, tentativas: int = 4) -> None:
        self.base = base
        self.tentativas = tentativas
        self._cache: dict[str, Any] = {}

    def obter(self, caminho: str) -> Any:
        """Devolve o campo ``dados`` da resposta, seguindo a paginação quando houver."""
        if caminho in self._cache:
            return self._cache[caminho]
        url = caminho if caminho.startswith("http") else self.base + caminho
        dados: Any = None
        while url:
            corpo = self._baixar(url)
            if isinstance(corpo["dados"], list):
                dados = (dados or []) + corpo["dados"]
                url = next((l["href"] for l in corpo.get("links", []) if l["rel"] == "next"), None)
            else:
                dados, url = corpo["dados"], None
        self._cache[caminho] = dados
        return dados

    def _baixar(self, url: str) -> dict[str, Any]:
        erro: Exception | None = None
        for tentativa in range(self.tentativas):
            try:
                pedido = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(pedido, timeout=60) as resposta:
                    return json.load(resposta)
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    raise
                erro = e
            except (urllib.error.URLError, TimeoutError) as e:
                erro = e
            time.sleep(2**tentativa)
        raise RuntimeError(f"Falha ao consultar {url}") from erro


# ---------------------------------------------------------------------------
# Funções auxiliares (puras)
# ---------------------------------------------------------------------------
def codteor(url: str | None) -> str | None:
    """Extrai o ``codteor`` de uma URL de inteiro teor da Câmara."""
    m = re.search(r"codteor=(\d+)", url or "")
    return m.group(1) if m else None


def id_da_uri(uri: str | None) -> int | None:
    """Último segmento numérico de uma URI da API."""
    m = re.search(r"/(\d+)$", uri or "")
    return int(m.group(1)) if m else None


def identificacao(tipo: str, numero: int | str, ano: int | str) -> str:
    """Identificação com separador de milhar, como em ``PL 1.680/2025``."""
    return f"{tipo} {int(numero):,}/{ano}".replace(",", ".")


def data_br(texto: str | None) -> str:
    """Converte ``AAAA-MM-DD...`` em ``dd/mm/aaaa``."""
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if texto else ""


def limpar(texto: str | None) -> str:
    """Remove espaços repetidos e quebras de linha."""
    return re.sub(r"\s+", " ", texto or "").strip()


def tipo_evento(descricao: str) -> str:
    """Classifica o trâmite em marco, alerta ou rotina (o último é marcado depois como atual)."""
    if any(descricao.startswith(t) for t in TRAMITES_ALERTA):
        return "alerta"
    if any(descricao.startswith(t) for t in TRAMITES_MARCO):
        return "marco"
    return "rotina"


def apreciacao_curta(apreciacao: str | None) -> str:
    """Forma curta da apreciação para os metadados do cabeçalho."""
    texto = apreciacao or ""
    if "Conclusiva" in texto:
        return "Conclusiva pelas comissões"
    if "Plenário" in texto:
        return "Plenário"
    return texto or "Indefinida"


def comissoes_do_despacho(despacho: str, apelidos: dict[str, str]) -> list[tuple[str, str]]:
    """Comissões citadas no despacho de distribuição, na ordem do texto, com o papel entre parênteses.

    ``apelidos`` mapeia o nome curto da comissão (ex.: ``Finanças e Tributação``) para a sigla.
    """
    achados = []
    for apelido, sigla in apelidos.items():
        pos = despacho.find(apelido)
        if pos < 0:
            continue
        resto = despacho[pos + len(apelido):]
        m = re.match(r"\s*\(([^)]*)\)", resto)
        papel = m.group(1).replace(", RICD", "").replace(" RICD", "").strip() if m else "Mérito"
        achados.append((pos, sigla, papel))
    achados.sort()
    vistos: set[str] = set()
    return [(s, p) for _, s, p in achados if not (s in vistos or vistos.add(s))]


def sigla_acessoria(item: dict[str, Any], ficha: dict[str, Any], orgao_numerador: str | None,
                    orgaos: set[str] | None = None) -> str:
    """Sigla de documento acessório, como ``PRL 1 CCTI`` ou ``REQ 29/2025 CCTI``.

    Sem órgão numerador, procura na ementa uma sigla entre parênteses; com ``orgaos``, só aceita
    siglas desse conjunto (evita tomar ``(FDNE)`` ou ``(SUS)`` por comissão).
    """
    base = f"{item['siglaTipo']} {item['numero']}"
    if str(item.get("ano") or "0") != "0":
        base += f"/{item['ano']}"
    orgao = orgao_numerador
    if not orgao or orgao in ("MESA", "PLEN"):
        candidatas = re.findall(r"\(([A-Z][A-Z0-9]{1,})\)", ficha.get("ementa") or item.get("ementa") or "")
        orgao = next((c for c in candidatas if orgaos is None or c in orgaos), None)
    return f"{base} {orgao}" if orgao else base


# ---------------------------------------------------------------------------
# Montagem do relatório
# ---------------------------------------------------------------------------
class MontadorRelatorio:
    """Transforma as respostas da API no dicionário do relatório de tramitação."""

    def __init__(self, cliente: ClienteApi, data_consulta: date, apelidos: dict[str, str] | None = None) -> None:
        self.api = cliente
        self.data_consulta = data_consulta
        self._apelidos = apelidos

    # Órgãos e deputados ---------------------------------------------------
    def orgao(self, uri: str | None) -> dict[str, Any]:
        """Ficha do órgão (``sigla``, ``nome``, ``apelido``, ``codTipoOrgao``)."""
        if not uri:
            return {"sigla": "", "nome": "", "apelido": "", "codTipoOrgao": 0}
        return self.api.obter(f"/orgaos/{id_da_uri(uri)}")

    @property
    def apelidos(self) -> dict[str, str]:
        """Nomes curtos das comissões permanentes ativas, para ler os despachos."""
        if self._apelidos is None:
            orgaos = self.api.obter("/orgaos?codTipoOrgao=2&itens=100")
            self._apelidos = {o["apelido"]: o["sigla"] for o in orgaos if o.get("apelido")}
        return self._apelidos

    def parlamentar(self, id_deputado: int, rotulo: str) -> dict[str, Any] | None:
        """Cartão de parlamentar a partir da ficha do deputado."""
        try:
            d = self.api.obter(f"/deputados/{id_deputado}")
        except urllib.error.HTTPError:
            return None
        st = d["ultimoStatus"]
        cargo = "Deputada Federal" if d.get("sexo") == "F" else "Deputado Federal"
        return {
            "id": id_deputado,
            "nome": f"Dep. {st.get('nomeEleitoral') or st['nome']}",
            "descricao": f"{cargo} · {st['siglaPartido']}/{st['siglaUf']}",
            "rotulo": rotulo,
        }

    # Etapas ---------------------------------------------------------------
    @staticmethod
    def _dia(evento: dict[str, Any]) -> str:
        return evento["dataHora"][:10]

    def _classificar_orgaos(self, tramites: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Associa cada trâmite ao órgão efetivo: trâmites administrativos (ex.: CCP) vão para o órgão seguinte."""
        orgaos = [self.orgao(t["uriOrgao"]) for t in tramites]
        legislativo = [o["codTipoOrgao"] in TIPOS_COMISSAO | TIPOS_PLENARIO | {TIPO_MESA} for o in orgaos]
        efetivos = []
        for i, (t, o) in enumerate(zip(tramites, orgaos)):
            if legislativo[i]:
                efetivos.append((t, o))
                continue
            proximo = next((orgaos[j] for j in range(i + 1, len(orgaos)) if legislativo[j]), None)
            anterior = next((orgaos[j] for j in range(i - 1, -1, -1) if legislativo[j]), None)
            efetivos.append((t, proximo or anterior or o))
        return efetivos

    def montar(self, id_proposicao: int) -> dict[str, Any]:
        """Monta o dicionário completo do relatório de uma proposição."""
        api = self.api
        ficha = api.obter(f"/proposicoes/{id_proposicao}")
        st = ficha["statusProposicao"]
        tramites = sorted(api.obter(f"/proposicoes/{id_proposicao}/tramitacoes"), key=lambda t: t["sequencia"])
        efetivos = self._classificar_orgaos(tramites)
        autores = sorted(api.obter(f"/proposicoes/{id_proposicao}/autores"), key=lambda a: a.get("ordemAssinatura") or 99)
        temas = api.obter(f"/proposicoes/{id_proposicao}/temas")
        relacionadas = api.obter(f"/proposicoes/{id_proposicao}/relacionadas")

        tipo, numero, ano = ficha["siglaTipo"], ficha["numero"], ficha["ano"]
        sigla_ficha = f"{tipo} {numero}/{ano}"
        teor = codteor(ficha.get("urlInteiroTeor")) or next((codteor(t["url"]) for t in tramites if codteor(t["url"])), "")
        situacao_desc = st.get("descricaoSituacao") or st.get("descricaoTramitacao") or "Sem situação registrada"
        conclusiva = "Conclusiva" in (st.get("apreciacao") or "")

        # Proposição principal, quando tramita em conjunto.
        principal = None
        if ficha.get("uriPropPrincipal"):
            p = api.obter(f"/proposicoes/{id_da_uri(ficha['uriPropPrincipal'])}")
            principal = identificacao(p["siglaTipo"], p["numero"], p["ano"])

        # Autor: primeiro deputado signatário.
        dep_autor = next((a for a in autores if "/deputados/" in (a.get("uri") or "")), None)
        autor = self.parlamentar(id_da_uri(dep_autor["uri"]), "AUTOR · PROPONENTE") if dep_autor else None
        if autor is None:
            raise ValueError(f"Proposição {id_proposicao} sem deputado autor")
        if len(autores) > 1:
            autor["rotulo"] = f"AUTOR · {len(autores)} SIGNATÁRIOS"

        # Documentos acessórios (relacionadas), com codteor e órgão.
        orgaos_conhecidos = set(self.apelidos.values()) | {o["sigla"] for _, o in efetivos}
        def detalhar(item: dict[str, Any]) -> dict[str, Any]:
            f = api.obter(f"/proposicoes/{item['id']}")
            numerador = self.orgao(f.get("uriOrgaoNumerador"))["sigla"] if f.get("uriOrgaoNumerador") else None
            return {"item": item, "ficha": f, "sigla": sigla_acessoria(item, f, numerador, orgaos_conhecidos)}

        with ThreadPoolExecutor(8) as ex:
            docs = list(ex.map(detalhar, relacionadas))
        por_codteor = {}
        for d in docs:
            c = codteor(d["ficha"].get("urlInteiroTeor"))
            if c and c not in por_codteor:
                por_codteor[c] = d

        # Órgão atual: último órgão legislativo do histórico.
        atual_orgao = efetivos[-1][1] if efetivos else self.orgao(st.get("uriOrgao"))
        atual_sigla = atual_orgao["sigla"]
        # Início da situação: primeiro trâmite da última passagem pelo órgão atual.
        desde = (st.get("dataHora") or ficha["dataApresentacao"])[:10]
        for t, o in reversed(efetivos):
            if o["sigla"] != atual_sigla:
                break
            desde = self._dia(t)

        sem_relator = situacao_desc.startswith("Aguardando Designação de Relator")
        situacao = {
            "descricao": situacao_desc,
            "estado": ESTADOS_SITUACAO.get(situacao_desc, "EM ANDAMENTO"),
            "orgao_sigla": atual_sigla,
            "orgao_nome": atual_orgao["nome"],
            "desde": desde,
            "rotulo_tempo": "SEM RELATOR HÁ" if sem_relator else "NESTA SITUAÇÃO HÁ",
            "rotulo_indicador": f"DIAS SEM RELATOR NA {atual_sigla}" if sem_relator else "DIAS NA SITUAÇÃO ATUAL",
        }

        estagios = self._estagios(ficha, efetivos, atual_sigla, conclusiva, situacao_desc, docs)
        fases = self._fases(efetivos, ficha, teor, sigla_ficha, por_codteor)
        relatoria = self._relatoria(st, efetivos, docs)

        aut_desc = f"{autor['nome']} ({autor['descricao'].split(' · ')[1]})"
        explicacao = limpar(ficha.get("ementaDetalhada"))
        if principal:
            explicacao = (explicacao + " " if explicacao else "") + f"Tramita em conjunto com o {principal}, à qual está apensada."
        metadados = [
            {"rotulo": "APRESENTAÇÃO", "valor": data_br(ficha["dataApresentacao"])},
            {"rotulo": "REGIME", "valor": st.get("regime") or "Não definido"},
            {"rotulo": "APRECIAÇÃO", "valor": apreciacao_curta(st.get("apreciacao"))},
        ]
        if principal:
            metadados.append({"rotulo": "APENSADA A", "valor": principal})

        arvore, anexos = self._arvore_e_anexos(ficha, sigla_ficha, aut_desc, teor, situacao_desc, docs, tramites)
        emendas = sum(1 for d in docs if d["item"]["siglaTipo"] in GRUPOS_ACESSORIOS[1][2])

        return {
            "data_consulta": self.data_consulta.isoformat(),
            "proposicao": {
                "id": ficha["id"],
                "casa": "Câmara dos Deputados",
                "identificacao": identificacao(tipo, numero, ano),
                "ementa": limpar(ficha["ementa"]),
                "explicacao": explicacao,
                "codteor_inteiro_teor": teor,
                "metadados": metadados,
                "apresentacao": ficha["dataApresentacao"][:10],
                "rotulo_apreciacao": f"REGIME {(st.get('regime') or 'NÃO DEFINIDO').upper()} · APRECIAÇÃO {apreciacao_curta(st.get('apreciacao')).upper()}",
                "nota_apreciacao": NOTA_CONCLUSIVA if conclusiva else NOTA_PLENARIO,
                "emendas_apresentadas": emendas,
                "temas": [t["tema"] for t in temas],
                "keywords": limpar(ficha.get("keywords")),
            },
            "autor": autor,
            "situacao": situacao,
            "estagios": estagios,
            "relatoria": relatoria,
            "fases": fases,
            "proximos_marcos": self._proximos(estagios, situacao, conclusiva, principal),
            "arvore": arvore,
            "anexos": anexos,
        }

    def _estagios(self, ficha, efetivos, atual_sigla, conclusiva, situacao_desc, docs) -> list[dict[str, Any]]:
        """Etapas: Mesa, comissões (visitadas e previstas no despacho), Plenário e remessa ao Senado."""
        visitas: dict[str, dict[str, Any]] = {}
        ordem: list[str] = []
        for t, o in efetivos:
            sig = o["sigla"]
            if sig not in visitas:
                visitas[sig] = {"orgao": o, "inicio": self._dia(t), "fim": self._dia(t), "tramites": []}
                ordem.append(sig)
            visitas[sig]["fim"] = self._dia(t)
            visitas[sig]["tramites"].append(t)

        despacho = next((limpar(t["despacho"]) for t, _ in reversed(efetivos) if t["descricaoTramitacao"].startswith("Distribuição")), "")
        previstas = comissoes_do_despacho(despacho, self.apelidos)
        papeis = dict(previstas)

        def doc(sig: str, inicio: str, nome: str) -> dict[str, Any] | None:
            tramites_orgao = visitas.get(sig, {}).get("tramites", [])
            for t in reversed(tramites_orgao):
                if t["descricaoTramitacao"].startswith(inicio) and codteor(t["url"]):
                    return {"codteor": codteor(t["url"]), "nome": nome}
            # Sem PDF no trâmite de aprovação: usa o último parecer do relator na comissão.
            if inicio == "Aprovação do Parecer" and any(t["descricaoTramitacao"].startswith(inicio) for t in tramites_orgao):
                prls = sorted((d for d in docs if d["item"]["siglaTipo"].startswith("PRL") and d["sigla"].endswith(f" {sig}")
                               and codteor(d["ficha"].get("urlInteiroTeor"))), key=lambda d: d["ficha"]["dataApresentacao"])
                if prls:
                    return {"codteor": codteor(prls[-1]["ficha"]["urlInteiroTeor"]), "nome": nome, "id": prls[-1]["item"]["id"]}
            return None

        no_senado = situacao_desc == "Aguardando Apreciação pelo Senado Federal"
        estagios = []
        mesa = visitas.get("MESA")
        primeira_saida = next((self._dia(t) for t, o in efetivos if o["sigla"] != "MESA"), None)
        estagios.append({
            "sigla": "MESA", "nome": "Mesa Diretora", "papel": "Apresentação, despacho e publicação",
            "inicio": ficha["dataApresentacao"][:10], "fim": primeira_saida,
            "estado": "atual" if atual_sigla == "MESA" and not primeira_saida else "concluido",
            "documento": doc("MESA", "Distribuição", "DESPACHO") if mesa else None,
        })

        comissoes = [s for s in ordem if visitas[s]["orgao"]["codTipoOrgao"] in TIPOS_COMISSAO]
        # Comissões previstas no despacho e não visitadas só continuam pendentes enquanto a matéria
        # está nas comissões: uma comissão especial as substitui, e o Plenário ou o Senado as encerram.
        especial = any(visitas[s]["orgao"]["codTipoOrgao"] != 2 for s in comissoes)
        if not (especial or no_senado or atual_sigla == "PLEN"):
            comissoes += [s for s, _ in previstas if s not in comissoes]
        for sig in comissoes:
            v = visitas.get(sig)
            deliberou = bool(v) and any(t["descricaoTramitacao"].startswith("Aprovação do Parecer") for t in v["tramites"])
            papel = papeis.get(sig, "Mérito")
            if sig == atual_sigla and not no_senado:
                estado = "atual"
            elif v and not deliberou and atual_sigla == "PLEN" and not no_senado:
                # Em regime de urgência, o parecer da comissão é dado em Plenário.
                estado, papel = "pendente", f"{papel} · parecer em Plenário"
            elif v:
                estado = "concluido"
            else:
                estado = "pendente"
            nome = v["orgao"].get("apelido") or v["orgao"]["nome"] if v else next((a for a, s in self.apelidos.items() if s == sig), sig)
            estagios.append({
                "sigla": sig, "nome": nome, "papel": papel,
                "inicio": v["inicio"] if v else None, "fim": v["fim"] if v and estado == "concluido" else None,
                "estado": estado, "comissao": True,
                "documento": doc(sig, "Aprovação do Parecer", "PARECER APROVADO") if v else None,
            })

        # Em matéria conclusiva, o Plenário só entra como etapa se houver ato de mérito nele
        # (urgência, discussão, votação, relatoria); apresentação e publicação não contam.
        atos_plen = [t for t in visitas.get("PLEN", {}).get("tramites", [])
                     if not t["descricaoTramitacao"].startswith(("Apresentação", "Publicação", "Notificação"))]
        if not conclusiva or atos_plen:
            v = visitas.get("PLEN")
            em_comissao = any(e.get("comissao") and e["estado"] in ("atual", "pendente") for e in estagios)
            if atual_sigla == "PLEN" and not no_senado:
                estado = "atual"
            elif no_senado or (v and not em_comissao):
                estado = "concluido"
            else:
                estado = "pendente"
            estagios.append({
                "sigla": "PLEN", "nome": "Plenário", "papel": "Discussão e votação da matéria",
                "inicio": v["inicio"] if v else None, "fim": v["fim"] if v and estado == "concluido" else None,
                "estado": estado,
            })
        estagios.append({
            "sigla": "REMESSA", "nome": "Mesa Diretora",
            "papel": "Envio dos autógrafos ao Senado Federal, encerrando a fase na Câmara (CF, art. 65)",
            "inicio": desde_remessa(efetivos) if no_senado else None, "fim": desde_remessa(efetivos) if no_senado else None,
            "estado": "concluido" if no_senado else "pendente",
        })
        return [{k: v for k, v in e.items() if v is not None} for e in estagios]

    def _fases(self, efetivos, ficha, teor, sigla_ficha, por_codteor) -> list[dict[str, Any]]:
        """Histórico agrupado por órgão, na ordem dos trâmites."""
        fases: list[dict[str, Any]] = []
        retiradas = 0
        # A posição atual é o último trâmite de órgão legislativo (publicações da CCP não contam).
        indice_atual = max((i for i, (t, o) in enumerate(efetivos) if t["siglaOrgao"] == o["sigla"]), default=len(efetivos) - 1)
        for i, (t, o) in enumerate(efetivos):
            descricao = limpar(t["descricaoTramitacao"]) or "Trâmite"
            texto = limpar(t["despacho"])
            if t["siglaOrgao"] != o["sigla"]:
                texto = f"{texto} ({t['siglaOrgao']})" if texto else f"({t['siglaOrgao']})"
            tipo = tipo_evento(descricao)
            etiqueta = None
            if i == 0:
                etiqueta = "INÍCIO"
            if descricao.startswith("Retirada de Pauta"):
                retiradas += 1
                etiqueta = f"{retiradas}ª RETIRADA"
            elif descricao.startswith("Aprovação do Parecer"):
                etiqueta = "APROVADO"
            if i == indice_atual:
                tipo, etiqueta = "atual", "ESTÁGIO ATUAL"
            evento: dict[str, Any] = {
                "data_hora": t["dataHora"][:16], "titulo": descricao, "texto": texto or descricao, "tipo": tipo,
            }
            if etiqueta:
                evento["etiqueta"] = etiqueta
            c = codteor(t["url"])
            if c:
                if c == teor:
                    evento["documento"] = {"codteor": c, "nome": f"Inteiro teor · {sigla_ficha}", "id": ficha["id"]}
                elif c in por_codteor:
                    d = por_codteor[c]
                    evento["documento"] = {"codteor": c, "nome": d["sigla"], "id": d["item"]["id"]}
                else:
                    evento["documento"] = {"codteor": c, "nome": descricao}
            sigla = o["sigla"] or t["siglaOrgao"]
            if not fases or fases[-1]["sigla"] != sigla:
                fases.append({"sigla": sigla, "nome": o["nome"] or sigla, "eventos": []})
            fases[-1]["eventos"].append(evento)
        return fases

    def _relatoria(self, st, efetivos, docs) -> dict[str, Any] | None:
        """Relatoria do último relator informado pela API, com os pareceres que apresentou."""
        id_relator = id_da_uri(st.get("uriUltimoRelator"))
        if not id_relator:
            return None
        ultima = next(((t, o) for t, o in reversed(efetivos) if t["descricaoTramitacao"].startswith("Designação de Relator")), None)
        orgao = ultima[1]["sigla"] if ultima else st.get("siglaOrgao")
        # Data da primeira designação na comissão da última relatoria.
        designacao = next(((t, o) for t, o in efetivos if t["descricaoTramitacao"].startswith("Designação de Relator") and o["sigla"] == orgao), None)
        relator = self.parlamentar(id_relator, f"RELATOR(A) · {orgao}")
        if relator is None:
            return None
        aprovado = any(t["descricaoTramitacao"].startswith("Aprovação do Parecer") and o["sigla"] == orgao for t, o in efetivos)
        prls = sorted(
            (d for d in docs if d["item"]["siglaTipo"].startswith("PRL") and d["sigla"].endswith(f" {orgao}")
             and codteor(d["ficha"].get("urlInteiroTeor"))),
            key=lambda d: d["ficha"]["dataApresentacao"],
        )
        pareceres = []
        for i, d in enumerate(prls):
            ultimo = i == len(prls) - 1
            sigla_curta = d["sigla"].rsplit(" ", 1)[0]
            pareceres.append({
                "sigla": sigla_curta, "nome": f"Parecer do Relator · {d['sigla']}",
                "data": data_br(d["ficha"]["dataApresentacao"]) + (" · aprovado" if ultimo and aprovado else ""),
                "codteor": codteor(d["ficha"]["urlInteiroTeor"]), "aprovado": ultimo and aprovado, "id": d["item"]["id"],
            })
        inicio = f"Designação em {data_br(designacao[0]['dataHora'])}." if designacao else "Relatoria informada pela API."
        if pareceres:
            versoes = "uma versão" if len(pareceres) == 1 else f"{len(pareceres)} versões"
            inicio += f" Apresentou {versoes} de parecer:"
        return {
            "orgao_sigla": orgao,
            "relator": relator,
            "resumo_inicio": inicio,
            "resumo_fim": "O último parecer foi aprovado na comissão." if aprovado and pareceres else "",
            "pareceres": pareceres,
        }

    def _proximos(self, estagios, situacao, conclusiva, principal) -> list[dict[str, str]]:
        """Próximos passos previstos a partir das etapas pendentes."""
        marcos = []
        if principal:
            marcos.append({"titulo": f"Andamento do {principal}", "descricao": "Apensada, a proposição segue a tramitação da proposição principal."})
        if situacao["estado"] == "PARADA":
            marcos.append({"titulo": f"Designação de relator(a) na {situacao['orgao_sigla']}", "descricao": "Passo que destrava a tramitação na comissão."})
        for e in estagios:
            if e.get("comissao") and e["estado"] in ("atual", "pendente"):
                marcos.append({"titulo": f"Parecer da {e['sigla']}", "descricao": f"{e['papel']}."})
            elif e["sigla"] == "PLEN" and e["estado"] in ("atual", "pendente"):
                marcos.append({"titulo": "Votação em Plenário", "descricao": "Discussão e votação da matéria pelo Plenário da Câmara."})
        remessa = next(e for e in estagios if e["sigla"] == "REMESSA")
        if remessa["estado"] == "concluido":
            marcos.append({"titulo": "Apreciação pelo Senado Federal", "descricao": "A proposição está na Casa revisora."})
        else:
            no_plenario = any(e["sigla"] == "PLEN" and e["estado"] == "atual" for e in estagios)
            if conclusiva and not no_plenario:
                marcos.append({"titulo": "Prazo de recurso ao Plenário", "descricao": "5 sessões após a última comissão (Art. 132, § 2º, RICD)."})
            marcos.append({"titulo": "Remessa ao Senado Federal", "descricao": "Aprovado na Câmara, o projeto segue à Casa revisora."})
        return marcos

    def _arvore_e_anexos(self, ficha, sigla_ficha, aut_desc, teor, situacao_desc, docs, tramites):
        """Árvore de apensados e acessórios e as categorias de documentos anexos."""
        siglas: set[str] = set()

        def item(d: dict[str, Any]) -> dict[str, Any]:
            f = d["ficha"]
            sigla = d["sigla"] if d["sigla"] not in siglas else f"{d['sigla']} (id {d['item']['id']})"
            siglas.add(sigla)
            it: dict[str, Any] = {"sigla": sigla, "tipo": f.get("descricaoTipo") or d["item"]["siglaTipo"],
                                  "data": data_br(f.get("dataApresentacao")), "id": d["item"]["id"]}
            if limpar(f.get("ementa")):
                it["texto"] = limpar(f["ementa"])
            c = codteor(f.get("urlInteiroTeor"))
            if c:
                it["codteor"] = c
            if d["item"]["siglaTipo"] in TIPOS_PRINCIPAIS and (f.get("statusProposicao") or {}).get("descricaoSituacao"):
                it["situacao"] = f["statusProposicao"]["descricaoSituacao"].upper()
            return it

        ordenados = sorted(docs, key=lambda d: (d["ficha"].get("dataApresentacao") or "", d["item"]["id"]))
        apensados = [item(d) for d in ordenados if d["item"]["siglaTipo"] in TIPOS_PRINCIPAIS]
        grupos = []
        conhecidos = set().union(*(g[2] for g in GRUPOS_ACESSORIOS)) | TIPOS_PRINCIPAIS
        definicoes = GRUPOS_ACESSORIOS + [("OUTROS DOCUMENTOS", "outros documentos", None)]
        for rotulo, plural, tipos in definicoes:
            selec = [d for d in ordenados if (d["item"]["siglaTipo"] in tipos if tipos else d["item"]["siglaTipo"] not in conhecidos)]
            if selec:
                grupos.append({"rotulo": rotulo, "plural": plural, "itens": [item(d) for d in selec]})

        raiz = {"sigla": sigla_ficha, "tipo": ficha.get("descricaoTipo") or ficha["siglaTipo"],
                "data": f"Apresentado em {data_br(ficha['dataApresentacao'])}", "autor": aut_desc,
                "texto": limpar(f"{ficha['ementa']} {ficha.get('ementaDetalhada') or ''}"), "id": ficha["id"],
                "situacao": situacao_desc.upper()}
        if teor:
            raiz["codteor"] = teor
        arvore = {"raiz": raiz, "descricao_raiz": f"{raiz['tipo']} · {aut_desc}", "apensados": apensados, "grupos": grupos}

        def refs(rotulo: str) -> list[str]:
            return [i["sigla"] for g in grupos if g["rotulo"] == rotulo for i in g["itens"]]

        despachos = []
        for t in tramites:
            if t["descricaoTramitacao"].startswith(("Distribuição", "Despacho")):
                d: dict[str, Any] = {"sigla": f"{limpar(t['descricaoTramitacao'])} de {data_br(t['dataHora'])}",
                                     "tipo": "Despacho", "data": data_br(t["dataHora"]), "autor": t["siglaOrgao"],
                                     "texto": limpar(t["despacho"])}
                if codteor(t["url"]):
                    d["codteor"] = codteor(t["url"])
                despachos.append(d)
        anexos = [
            {"titulo": "Inteiro Teor", "subtitulo": "Texto original da proposição", "selo": "PDF" if teor else "N/D",
             "itens": [{"sigla": f"Inteiro teor · {sigla_ficha}", "tipo": "Texto original", "codteor": teor}] if teor else []},
            {"titulo": "Mensagens, Ofícios e Requerimentos", "subtitulo": "Requerimentos vinculados à proposição", "referencias": refs("REQUERIMENTOS")},
            {"titulo": "Histórico de Pareceres, Substitutivos e Votos", "subtitulo": "Pareceres, substitutivos e votos das comissões", "referencias": refs("PARECERES, SUBSTITUTIVOS E VOTOS")},
            {"titulo": "Emendas", "subtitulo": "Emendas ao projeto e ao substitutivo", "referencias": refs("EMENDAS"),
             "mensagem_vazio": "Nenhuma emenda apresentada até {data_consulta}."},
            {"titulo": "Destaques", "subtitulo": "Destaques para votação em separado", "referencias": refs("DESTAQUES")},
            {"titulo": "Histórico de Despachos", "subtitulo": "Despachos da Mesa Diretora", "itens": despachos},
            {"titulo": "Redação Final", "subtitulo": "Texto final aprovado", "referencias": refs("REDAÇÃO FINAL E AUTÓGRAFOS"),
             "mensagem_vazio": "Ainda não há redação final registrada até {data_consulta}."},
        ]
        return arvore, anexos


def desde_remessa(efetivos: list[tuple[dict[str, Any], dict[str, Any]]]) -> str | None:
    """Data do primeiro trâmite de remessa ao Senado Federal após a última passagem pelo Plenário."""
    ultimo_plen = max((i for i, (_, o) in enumerate(efetivos) if o["sigla"] == "PLEN"), default=-1)
    for t, _ in efetivos[ultimo_plen + 1:]:
        descricao, despacho = t["descricaoTramitacao"] or "", t["despacho"] or ""
        if descricao.startswith("Remessa") or (t["siglaOrgao"] == "MESA" and "Senado Federal" in despacho):
            return t["dataHora"][:10]
    return None


def nome_arquivo(dados: dict[str, Any]) -> str:
    """Nome-base dos arquivos de uma proposição, como ``pl-1680-2025``."""
    return nome_relatorio(dados.get("proposicao", dados)["identificacao"])


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None, cliente_fabrica: Callable[[], ClienteApi] = ClienteApi) -> None:
    """Coleta relatórios na API e grava um JSON por proposição."""
    parser = argparse.ArgumentParser(description="Gera os JSONs de relatório de tramitação a partir da API da Câmara.")
    parser.add_argument("ids", nargs="*", type=int, help="ids de proposições na API")
    parser.add_argument("--ids-de", type=Path, help="usa os ids dos registros de uma base de pesquisa (JSON)")
    parser.add_argument("-o", "--saida", type=Path, default=Path("dados/proposicoes"), help="pasta dos JSONs")
    parser.add_argument("--pesquisa", type=Path, help="base de pesquisa cujos 'detalhes' apontarão para os relatórios gerados")
    parser.add_argument("--manter", nargs="*", type=int, default=[], help="ids que não devem ser sobrescritos nos detalhes")
    parser.add_argument("--data", type=date.fromisoformat, default=date.today(), help="data da consulta (AAAA-MM-DD)")
    args = parser.parse_args(argv)

    ids = list(args.ids)
    if args.ids_de:
        ids += [r[0] for r in json.loads(args.ids_de.read_text(encoding="utf-8"))["L"]]
    ids = [i for i in dict.fromkeys(ids) if i not in args.manter]
    if not ids:
        parser.error("informe ids ou --ids-de")

    montador = MontadorRelatorio(cliente_fabrica(), args.data)
    args.saida.mkdir(parents=True, exist_ok=True)
    gerados: dict[str, str] = {}
    for i in ids:
        dados = montador.montar(i)
        nome = nome_arquivo(dados)
        destino = args.saida / f"{nome}.json"
        # Seções escritas à mão (análise estratégica, versão válida) sobrevivem à recoleta.
        if destino.exists():
            anterior = json.loads(destino.read_text(encoding="utf-8"))
            dados.update({k: anterior[k] for k in SECOES_MANUAIS if k in anterior})
        destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        gerados[str(i)] = nome
        print(f"{dados['proposicao']['identificacao']}: {args.saida / nome}.json")

    if args.pesquisa:
        base = json.loads(args.pesquisa.read_text(encoding="utf-8"))
        detalhes = base.get("detalhes", {})
        for i, nome in gerados.items():
            titulo = next(f"Tramitação {identificacao(r[1], r[2], r[3])}" for r in base["L"] if str(r[0]) == i)
            detalhes[i] = {"arquivo": f"{nome}.html", "titulo": titulo, "coleta": args.data.isoformat()}
        # Reescreve só a linha de "detalhes", preservando o formato compacto do restante da base.
        linhas = args.pesquisa.read_text(encoding="utf-8").split("\n")
        n = next(k for k, linha in enumerate(linhas) if linha.startswith('  "detalhes": '))
        linhas[n] = '  "detalhes": ' + json.dumps(detalhes, ensure_ascii=False) + ("," if linhas[n].rstrip().endswith(",") else "")
        texto = "\n".join(linhas)
        json.loads(texto)
        args.pesquisa.write_text(texto, encoding="utf-8")
        print(f"Detalhes atualizados em {args.pesquisa}")


if __name__ == "__main__":
    main()

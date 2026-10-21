"""Modelos de dados do relatório de tramitação e leitura a partir de JSON."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

URL_INTEIRO_TEOR = "https://www.camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor="
URL_FICHA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao="
URL_FOTO_DEPUTADO = "https://www.camara.leg.br/internet/deputado/bandep/{id}.jpg"

EstadoEstagio = Literal["concluido", "atual", "pendente"]
TipoEvento = Literal["marco", "rotina", "alerta", "atual"]


def valor_documento(id: int | None, codteor: str | None, reserva: str = "") -> str:
    """Chave que identifica o mesmo documento em todos os pontos da página.

    Componentes com a mesma chave acendem juntos no hover. Usa o id da
    proposição acessória quando existe (pareceres e substitutivos podem
    compartilhar o PDF), senão o ``codteor``, senão ``reserva``.
    """
    if id:
        return f"p{id}"
    if codteor:
        return f"c{codteor}"
    return f"x{reserva}"


@dataclass(frozen=True)
class Documento:
    """Documento oficial da Câmara identificado pelo código do inteiro teor."""

    codteor: str
    nome: str
    id: int | None = None

    @property
    def url(self) -> str:
        """URL pública do PDF do documento."""
        return URL_INTEIRO_TEOR + self.codteor

    @property
    def valor(self) -> str:
        """Chave compartilhada do documento (ver :func:`valor_documento`)."""
        return valor_documento(self.id, self.codteor)

    @classmethod
    def de_dict(cls, dados: dict[str, Any] | None) -> Documento | None:
        """Cria o documento a partir de um dicionário, ou ``None`` se ausente."""
        if not dados:
            return None
        return cls(codteor=str(dados["codteor"]), nome=dados["nome"], id=dados.get("id"))


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
    id: int | None = None
    status: str | None = None

    @property
    def rotulo_status(self) -> str:
        """Situação exibida no cartão: a informada nos dados, ou APROVADO/SUPERADO."""
        return self.status or ("APROVADO" if self.aprovado else "SUPERADO")

    @property
    def url(self) -> str:
        """URL pública do PDF do parecer."""
        return URL_INTEIRO_TEOR + self.codteor

    @property
    def valor(self) -> str:
        """Chave compartilhada do parecer (ver :func:`valor_documento`)."""
        return valor_documento(self.id, self.codteor)


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
    temas: list[str] = field(default_factory=list)
    keywords: str = ""

    @property
    def url_inteiro_teor(self) -> str:
        """URL pública do inteiro teor da proposição."""
        return URL_INTEIRO_TEOR + self.codteor_inteiro_teor

    @property
    def valor(self) -> str:
        """Chave compartilhada do texto original (ver :func:`valor_documento`)."""
        return valor_documento(self.id, self.codteor_inteiro_teor)

    @property
    def termos_indexacao(self) -> list[str]:
        """Termos do campo ``keywords``, separados por vírgulas fora de parênteses."""
        termos: list[str] = []
        atual, nivel = "", 0
        for caractere in re.sub(r"\.\s*$", "", self.keywords):
            nivel += {"(": 1, ")": -1}.get(caractere, 0)
            if caractere == "," and nivel == 0:
                termos.append(atual.strip())
                atual = ""
            else:
                atual += caractere
        if atual.strip():
            termos.append(atual.strip())
        return termos


@dataclass(frozen=True)
class MarcoFuturo:
    """Próximo passo previsto na tramitação."""

    titulo: str
    descricao: str


@dataclass(frozen=True)
class VersaoValida:
    """Texto de referência vigente (substitutivo adotado) e o parecer que o publicou."""

    sigla: str
    titulo: str
    selo: str
    rotulo_botao: str
    ementa: str
    descricao: str
    documento: Documento
    parecer: Documento

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> VersaoValida:
        """Cria a versão válida a partir de um dicionário."""
        return cls(
            **{k: v for k, v in dados.items() if k not in ("documento", "parecer")},
            documento=Documento.de_dict(dados["documento"]),
            parecer=Documento.de_dict(dados["parecer"]),
        )


@dataclass(frozen=True)
class ItemVinculado:
    """Documento ou proposição acessória exibido na árvore e nas janelas de detalhes."""

    sigla: str
    tipo: str
    data: str | None = None
    autor: str | None = None
    texto: str | None = None
    id: int | None = None
    codteor: str | None = None
    situacao: str | None = None
    destaque: str | None = None
    nota: str | None = None
    superado: bool = False
    vinculados: list[ItemVinculado] = field(default_factory=list)

    @property
    def meta(self) -> str:
        """Linha de metadados (data e autoria)."""
        return " · ".join(p for p in (self.data, self.autor) if p)

    @property
    def url_teor(self) -> str | None:
        """URL do inteiro teor em PDF, se houver."""
        return URL_INTEIRO_TEOR + self.codteor if self.codteor else None

    @property
    def url_ficha(self) -> str | None:
        """URL da ficha de tramitação, se o item tiver id de proposição."""
        return f"{URL_FICHA}{self.id}" if self.id else None

    @property
    def valor(self) -> str:
        """Chave compartilhada do item (ver :func:`valor_documento`)."""
        return valor_documento(self.id, self.codteor, self.sigla)

    @property
    def rotulo_acionador(self) -> str:
        """Texto que identifica o item como origem do popover da versão válida."""
        return f"{self.sigla} · {self.destaque}" if self.destaque else self.sigla

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> ItemVinculado:
        """Cria o item (e seus vinculados) a partir de um dicionário."""
        valores = dict(dados)
        if "codteor" in valores:
            valores["codteor"] = str(valores["codteor"])
        valores["vinculados"] = [cls.de_dict(v) for v in dados.get("vinculados", [])]
        return cls(**valores)


@dataclass(frozen=True)
class GrupoVinculado:
    """Ramo da árvore com documentos vinculados de um mesmo tipo."""

    rotulo: str
    plural: str
    itens: list[ItemVinculado]
    sigla_vinculados: str | None = None
    plural_vinculados: str | None = None

    @property
    def total_vinculados(self) -> int:
        """Quantidade de documentos de segundo nível (ex.: retiradas de pauta)."""
        return sum(len(i.vinculados) for i in self.itens)


@dataclass(frozen=True)
class Arvore:
    """Árvore de apensados e documentos acessórios da proposição."""

    raiz: ItemVinculado
    descricao_raiz: str
    apensados: list[ItemVinculado]
    grupos: list[GrupoVinculado]

    @property
    def resumo(self) -> str:
        """Frase que resume apensados e documentos acessórios vinculados."""
        if self.apensados:
            inicio = f"{len(self.apensados)} proposição(ões) apensada(s)."
        else:
            inicio = "Nenhuma proposição apensada."
        partes = [f"{len(g.itens)} {g.plural}" for g in self.grupos]
        partes += [f"{g.total_vinculados} {g.plural_vinculados}" for g in self.grupos if g.total_vinculados]
        total = sum(len(g.itens) + g.total_vinculados for g in self.grupos)
        if not partes:
            return inicio
        lista = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " e " + partes[-1]
        return f"{inicio} Ficam vinculados à matéria {total} documentos acessórios: {lista}."

    def localizar(self, sigla: str) -> ItemVinculado:
        """Busca um item pela sigla em todos os níveis da árvore."""
        pendentes = [self.raiz, *self.apensados, *(i for g in self.grupos for i in g.itens)]
        while pendentes:
            item = pendentes.pop(0)
            if item.sigla == sigla:
                return item
            pendentes.extend(item.vinculados)
        raise KeyError(f"Documento {sigla!r} não encontrado na árvore")

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Arvore:
        """Cria a árvore a partir de um dicionário."""
        return cls(
            raiz=ItemVinculado.de_dict(dados["raiz"]),
            descricao_raiz=dados["descricao_raiz"],
            apensados=[ItemVinculado.de_dict(a) for a in dados.get("apensados", [])],
            grupos=[
                GrupoVinculado(**{**g, "itens": [ItemVinculado.de_dict(i) for i in g["itens"]]})
                for g in dados["grupos"]
            ],
        )


@dataclass(frozen=True)
class CategoriaAnexo:
    """Categoria de documentos anexos e referenciados da ficha de tramitação."""

    titulo: str
    subtitulo: str
    itens: list[ItemVinculado]
    selo: str | None = None
    mensagem_vazio: str | None = None

    @property
    def contador(self) -> str:
        """Texto do selo: o informado nos dados ou a quantidade de itens."""
        return self.selo or str(len(self.itens))

    @property
    def vazia(self) -> bool:
        """Indica categoria sem documentos (selo ``0`` ou ``N/D``)."""
        return self.contador in ("0", "N/D")


@dataclass(frozen=True)
class Fonte:
    """Fonte oficial citada na análise estratégica."""

    titulo: str
    url: str


@dataclass(frozen=True)
class ItemDiagnostico:
    """Argumento do diagnóstico técnico, com as fontes que o sustentam."""

    texto: str
    fontes: list[Fonte]


@dataclass(frozen=True)
class BlocoDiagnostico:
    """Eixo do diagnóstico técnico (processo, constitucionalidade etc.)."""

    rotulo: str
    titulo: str
    itens: list[ItemDiagnostico]


@dataclass(frozen=True)
class Semaforo:
    """Avaliação sintética de um eixo, com nível BAIXO, MÉDIO ou ALTO."""

    eixo: str
    nivel: str
    texto: str


@dataclass(frozen=True)
class AchadoLegistica:
    """Problema de técnica legislativa (LC 95/1998) e a correção sugerida."""

    dispositivo: str
    problema: str
    fundamento: str
    correcao: str


@dataclass(frozen=True)
class Risco:
    """Linha da matriz de riscos."""

    id: str
    nivel: str
    titulo: str
    descricao: str
    instancia: str
    probabilidade: str
    impacto: str
    fundamento: str
    fontes: list[Fonte]
    mitigacao: str


@dataclass(frozen=True)
class Oportunidade:
    """Oportunidade identificada para a tramitação."""

    id: str
    tipo: str
    titulo: str
    descricao: str
    como: str
    fontes: list[Fonte]


@dataclass(frozen=True)
class Acao:
    """Ação do plano da assessoria legislativa."""

    numero: str
    prioridade: str
    titulo: str
    descricao: str
    prazo: str
    instrumento: str
    resultado: str
    riscos: str


@dataclass(frozen=True)
class FonteConsultada:
    """Fonte oficial listada ao fim da análise, com o que foi consultado nela."""

    fonte: Fonte
    nota: str


@dataclass(frozen=True)
class Analise:
    """Análise estratégica do gabinete: síntese, diagnóstico, riscos e plano de ação."""

    introducao: str
    sintese: list[str]
    semaforo: list[Semaforo]
    diagnostico: list[BlocoDiagnostico]
    rotulo_legistica: str
    legistica: list[AchadoLegistica]
    riscos: list[Risco]
    oportunidades: list[Oportunidade]
    plano: list[Acao]
    fontes: list[FonteConsultada]

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Analise:
        """Cria a análise, trocando as chaves de fonte pelos objetos :class:`Fonte`."""
        catalogo = {chave: Fonte(**f) for chave, f in dados["fontes"].items()}

        def fontes(chaves: list[str]) -> list[Fonte]:
            return [catalogo[c] for c in chaves]

        return cls(
            introducao=dados["introducao"],
            sintese=dados["sintese"],
            semaforo=[Semaforo(**s) for s in dados["semaforo"]],
            diagnostico=[
                BlocoDiagnostico(
                    rotulo=b["rotulo"],
                    titulo=b["titulo"],
                    itens=[ItemDiagnostico(texto=i["texto"], fontes=fontes(i["fontes"])) for i in b["itens"]],
                )
                for b in dados["diagnostico"]
            ],
            rotulo_legistica=dados["legistica"]["rotulo"],
            legistica=[AchadoLegistica(**a) for a in dados["legistica"]["achados"]],
            riscos=[Risco(**{**r, "fontes": fontes(r["fontes"])}) for r in dados["riscos"]],
            oportunidades=[Oportunidade(**{**o, "fontes": fontes(o["fontes"])}) for o in dados["oportunidades"]],
            plano=[Acao(**a) for a in dados["plano"]],
            fontes=[FonteConsultada(fonte=catalogo[f["fonte"]], nota=f["nota"]) for f in dados["fontes_consultadas"]],
        )


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
    versao_valida: VersaoValida | None = None
    arvore: Arvore | None = None
    anexos: list[CategoriaAnexo] = field(default_factory=list)
    analise: Analise | None = None

    @property
    def documentos_aprovados(self) -> dict[str, ItemVinculado]:
        """Itens com selo de aprovação, por chave compartilhada; acionam o popover da versão válida."""
        if not self.arvore:
            return {}
        itens = [i for g in self.arvore.grupos for i in g.itens if i.destaque]
        return {i.valor: i for i in itens}

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> Relatorio:
        """Cria o relatório completo a partir do dicionário lido do JSON."""
        data_consulta = date.fromisoformat(dados["data_consulta"])
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
        arvore = Arvore.de_dict(dados["arvore"]) if dados.get("arvore") else None
        return cls(
            data_consulta=data_consulta,
            proposicao=Proposicao(**prop),
            autor=Parlamentar.de_dict(dados["autor"]),
            situacao=Situacao(**situacao),
            estagios=[Estagio.de_dict(e) for e in dados["estagios"]],
            relatoria=relatoria,
            fases=[Fase.de_dict(f) for f in dados["fases"]],
            proximos_marcos=[MarcoFuturo(**m) for m in dados.get("proximos_marcos", [])],
            versao_valida=VersaoValida.de_dict(dados["versao_valida"]) if dados.get("versao_valida") else None,
            arvore=arvore,
            anexos=[_categoria_anexo(c, arvore, data_consulta) for c in dados.get("anexos", [])],
            analise=Analise.de_dict(dados["analise"]) if dados.get("analise") else None,
        )


def _categoria_anexo(dados: dict[str, Any], arvore: Arvore | None, data_consulta: date) -> CategoriaAnexo:
    """Cria a categoria de anexos, resolvendo ``referencias`` a itens da árvore."""
    itens = [ItemVinculado.de_dict(i) for i in dados.get("itens", [])]
    if dados.get("referencias"):
        if arvore is None:
            raise ValueError("Categoria de anexos com referências exige a árvore de documentos")
        itens += [arvore.localizar(sigla) for sigla in dados["referencias"]]
    mensagem = dados.get("mensagem_vazio")
    return CategoriaAnexo(
        titulo=dados["titulo"],
        subtitulo=dados["subtitulo"],
        itens=itens,
        selo=dados.get("selo"),
        mensagem_vazio=mensagem.format(data_consulta=data_consulta.strftime("%d/%m/%Y")) if mensagem else None,
    )


def carregar_relatorio(caminho: str | Path) -> Relatorio:
    """Lê um arquivo JSON de dados e devolve o :class:`Relatorio` correspondente."""
    with open(caminho, encoding="utf-8") as arquivo:
        return Relatorio.de_dict(json.load(arquivo))


def _data_opcional(valor: str | None) -> date | None:
    """Converte uma data ISO opcional."""
    return date.fromisoformat(valor) if valor else None

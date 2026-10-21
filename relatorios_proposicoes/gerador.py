"""Renderização das páginas (tramitação, capa e pesquisa) em HTML autocontido."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup, escape

from relatorios_proposicoes import indicadores
from relatorios_proposicoes.capa import Capa
from relatorios_proposicoes.modelos import Estagio, Relatorio
from relatorios_proposicoes.pesquisa import BasePesquisa

Tema = Literal["claro", "escuro"]
TEMAS: tuple[Tema, ...] = ("claro", "escuro")

ARQUIVOS_CSS = ("tokens.css", "relatorio.css")
ARQUIVOS_CSS_PESQUISA = ("tokens.css", "pesquisa.css")

CLASSES_NIVEL = {"ALTO": "alto", "CRÍTICA": "alto", "MÉDIO": "medio", "ALTA": "medio", "BAIXO": "baixo", "MÉDIA": "baixo"}


def data_br(valor: date | datetime | None, curta: bool = False) -> str:
    """Formata a data no padrão brasileiro (``dd/mm/aaaa`` ou ``dd/mm/aa``)."""
    if valor is None:
        return ""
    return valor.strftime("%d/%m/%y" if curta else "%d/%m/%Y")


def hora(valor: datetime) -> str:
    """Formata a hora como ``HH:MM``."""
    return valor.strftime("%H:%M")


def periodo_estagio(estagio: Estagio) -> str:
    """Texto do rodapé do cartão de estágio (intervalo, início ou pendência)."""
    if estagio.estado == "pendente" or estagio.inicio is None:
        return "A INICIAR"
    if estagio.fim is None:
        return f"DESDE {data_br(estagio.inicio, curta=True)}"
    return f"{data_br(estagio.inicio, curta=True)} → {data_br(estagio.fim, curta=True)}"


def negrito(texto: str) -> Markup:
    """Escapa o texto e converte trechos entre ``**`` em ``<strong>``."""
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", str(escape(texto))))


def classe_nivel(nivel: str) -> str:
    """Classe CSS da cor de um nível de risco ou de uma prioridade do plano de ação."""
    return CLASSES_NIVEL.get(nivel.upper(), "baixo")


def criar_ambiente() -> Environment:
    """Cria o ambiente Jinja2 com os templates e filtros do pacote."""
    ambiente = Environment(
        loader=PackageLoader("relatorios_proposicoes", "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ambiente.filters["data_br"] = data_br
    ambiente.filters["hora"] = hora
    ambiente.filters["periodo_estagio"] = periodo_estagio
    ambiente.filters["negrito"] = negrito
    ambiente.filters["classe_nivel"] = classe_nivel
    return ambiente


def _arquivo_do_pacote(*partes: str) -> Any:
    """Recurso empacotado em ``relatorios_proposicoes``."""
    caminho = resources.files("relatorios_proposicoes")
    for parte in partes:
        caminho = caminho / parte
    return caminho


def carregar_estilos(arquivos: tuple[str, ...] = ARQUIVOS_CSS) -> Markup:
    """Concatena as folhas de estilo do pacote para embuti-las no HTML."""
    return Markup("\n".join(_arquivo_do_pacote("estilos", nome).read_text(encoding="utf-8") for nome in arquivos))


def carregar_script(nome: str) -> Markup:
    """Lê um script do pacote para embuti-lo no HTML."""
    return Markup(_arquivo_do_pacote("scripts", nome).read_text(encoding="utf-8"))


def recurso_em_data_uri(*partes: str) -> str:
    """Lê um recurso binário (imagem ou fonte) e o devolve como URI ``data:``."""
    nome = partes[-1]
    tipo = "font/woff2" if nome.endswith(".woff2") else mimetypes.guess_type(nome)[0] or "application/octet-stream"
    conteudo = base64.b64encode(_arquivo_do_pacote("recursos", *partes).read_bytes()).decode("ascii")
    return f"data:{tipo};base64,{conteudo}"


def json_para_script(dados: Any) -> Markup:
    """Serializa dados para um ``<script type="application/json">`` sem permitir fechar a tag."""
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    return Markup(texto.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def _validar_tema(tema: str) -> Tema:
    if tema not in TEMAS:
        raise ValueError(f"Tema inválido: {tema!r} (use {' ou '.join(TEMAS)})")
    return tema  # type: ignore[return-value]


def renderizar_relatorio(relatorio: Relatorio, tema: Tema = "claro") -> str:
    """Renderiza o relatório de tramitação completo como uma página HTML."""
    template = criar_ambiente().get_template("tramitacao.html")
    return template.render(
        r=relatorio,
        tema=_validar_tema(tema),
        estilos=carregar_estilos(),
        script=carregar_script("tramitacao.js"),
        total_eventos=len(indicadores.todos_eventos(relatorio)),
        total_com_documento=indicadores.total_eventos_com_documento(relatorio),
        ultima_movimentacao=indicadores.ultima_movimentacao(relatorio),
        dias_na_situacao=indicadores.dias_na_situacao(relatorio),
        indicadores=indicadores.calcular_indicadores(relatorio),
        progresso=indicadores.progresso_comissoes(relatorio),
    )


def renderizar_capa(capa: Capa) -> str:
    """Renderiza a capa A4 do relatório, com imagens e fontes embutidas."""
    imagens = {
        nome: recurso_em_data_uri("capa", arquivo)
        for nome, arquivo in {
            "textura": "textura.png",
            "regua": "regua.png",
            "pontos": "pontos.png",
            "escritorio": "logo-escritorio.png",
            "faixa": "faixa.jpg",
            "atomo": "atomo.png",
            "partido": "logo-partido.png",
        }.items()
    }
    fontes = {
        nome: recurso_em_data_uri("fontes", f"{nome}.woff2")
        for nome in ("liberation-sans-400", "liberation-sans-700", "dejavu-sans-mono-400", "dejavu-sans-mono-700")
    }
    template = criar_ambiente().get_template("capa.html")
    return template.render(c=capa, imagens=imagens, fontes=fontes, estilos=carregar_estilos(("capa.css",)))


def renderizar_pesquisa(base: BasePesquisa, tema: Tema = "claro") -> str:
    """Renderiza a página de pesquisa facetada sobre a base local de proposições."""
    template = criar_ambiente().get_template("pesquisa.html")
    return template.render(
        base=base,
        tema=_validar_tema(tema),
        dados=json_para_script(base.para_pagina()),
        estilos=carregar_estilos(ARQUIVOS_CSS_PESQUISA),
        script=carregar_script("pesquisa.js"),
    )


def carregar_pagina(caminho: str | Path) -> Relatorio | Capa | BasePesquisa:
    """Lê um JSON de dados e devolve o modelo da página indicada pela chave ``pagina``.

    Sem a chave, o arquivo é tratado como relatório de tramitação.
    """
    with open(caminho, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    pagina = dados.get("pagina", "tramitacao")
    if pagina == "capa":
        return Capa.de_dict(dados)
    if pagina == "pesquisa":
        return BasePesquisa.de_dict(dados)
    if pagina == "tramitacao":
        return Relatorio.de_dict(dados)
    raise ValueError(f"Página desconhecida em {caminho}: {pagina!r}")


def renderizar(modelo: Relatorio | Capa | BasePesquisa, tema: Tema = "claro") -> str:
    """Renderiza qualquer página a partir do seu modelo (a capa é sempre clara, para impressão)."""
    if isinstance(modelo, Capa):
        return renderizar_capa(modelo)
    if isinstance(modelo, BasePesquisa):
        return renderizar_pesquisa(modelo, tema)
    return renderizar_relatorio(modelo, tema)


def gerar_arquivo(modelo: Relatorio | Capa | BasePesquisa, destino: str | Path, tema: Tema = "claro") -> Path:
    """Renderiza a página e grava o HTML em ``destino``, criando as pastas."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(renderizar(modelo, tema), encoding="utf-8")
    return destino

"""Renderização do relatório de tramitação em HTML autocontido."""

from __future__ import annotations

from datetime import date, datetime
from importlib import resources
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from relatorios_proposicoes import indicadores
from relatorios_proposicoes.modelos import Estagio, Relatorio

ARQUIVOS_CSS = ("tokens.css", "relatorio.css")


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
    return ambiente


def carregar_estilos() -> Markup:
    """Concatena as folhas de estilo do pacote para embuti-las no HTML."""
    pasta = resources.files("relatorios_proposicoes") / "estilos"
    return Markup("\n".join((pasta / nome).read_text(encoding="utf-8") for nome in ARQUIVOS_CSS))


def renderizar_relatorio(relatorio: Relatorio) -> str:
    """Renderiza o relatório de tramitação completo como uma página HTML."""
    template = criar_ambiente().get_template("tramitacao.html")
    return template.render(
        r=relatorio,
        estilos=carregar_estilos(),
        total_eventos=len(indicadores.todos_eventos(relatorio)),
        total_com_documento=indicadores.total_eventos_com_documento(relatorio),
        ultima_movimentacao=indicadores.ultima_movimentacao(relatorio),
        dias_na_situacao=indicadores.dias_na_situacao(relatorio),
        indicadores=indicadores.calcular_indicadores(relatorio),
        progresso=indicadores.progresso_comissoes(relatorio),
    )


def gerar_arquivo(relatorio: Relatorio, destino: str | Path) -> Path:
    """Renderiza o relatório e grava o HTML em ``destino``, criando as pastas."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(renderizar_relatorio(relatorio), encoding="utf-8")
    return destino

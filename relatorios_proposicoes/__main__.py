"""Linha de comando: gera a página HTML (tramitação, capa ou pesquisa) a partir de um JSON de dados."""

from __future__ import annotations

import argparse
from pathlib import Path

from relatorios_proposicoes.gerador import TEMAS, carregar_pagina, gerar_arquivo


def main(argv: list[str] | None = None) -> None:
    """Ponto de entrada da CLI ``relatorios-proposicoes``."""
    parser = argparse.ArgumentParser(
        description="Gera a página HTML de uma proposição (tramitação), da capa ou da pesquisa de proposições."
    )
    parser.add_argument(
        "dados",
        type=Path,
        nargs="+",
        help="arquivo(s) JSON de dados; a chave \"pagina\" indica capa ou pesquisa (padrão: tramitação)",
    )
    parser.add_argument(
        "-o", "--saida", type=Path, help="arquivo HTML de destino, com um único JSON (padrão: saida/<nome-do-json>.html)"
    )
    parser.add_argument("--tema", choices=TEMAS, default="claro", help="tema visual das páginas (padrão: claro)")
    args = parser.parse_args(argv)
    if args.saida and len(args.dados) > 1:
        parser.error("--saida só pode ser usado com um único arquivo de dados")

    for dados in args.dados:
        destino = args.saida or Path("saida") / f"{dados.stem}.html"
        caminho = gerar_arquivo(carregar_pagina(dados), destino, args.tema)
        print(f"Página gerada em {caminho}")


if __name__ == "__main__":
    main()

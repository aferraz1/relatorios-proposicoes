"""Linha de comando: gera o relatório HTML a partir de um arquivo JSON de dados."""

from __future__ import annotations

import argparse
from pathlib import Path

from relatorios_proposicoes.gerador import gerar_arquivo
from relatorios_proposicoes.modelos import carregar_relatorio


def main(argv: list[str] | None = None) -> None:
    """Ponto de entrada da CLI ``relatorios-proposicoes``."""
    parser = argparse.ArgumentParser(description="Gera o relatório de tramitação de uma proposição em HTML.")
    parser.add_argument("dados", type=Path, help="arquivo JSON com os dados da proposição")
    parser.add_argument(
        "-o", "--saida", type=Path, help="arquivo HTML de destino (padrão: saida/<nome-do-json>.html)"
    )
    args = parser.parse_args(argv)

    destino = args.saida or Path("saida") / f"{args.dados.stem}.html"
    caminho = gerar_arquivo(carregar_relatorio(args.dados), destino)
    print(f"Relatório gerado em {caminho}")


if __name__ == "__main__":
    main()

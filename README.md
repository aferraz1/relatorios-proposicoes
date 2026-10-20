# relatorios-proposicoes
Relatórios de Tramitação e Análise de Proposições Legislativas

Gera páginas HTML autocontidas com a linha do tempo de tramitação de uma
proposição, no visual do design system **Glass HUD Legislativo** (tema escuro,
vidro e acentos em cyan).

O relatório reúne:

- cabeçalho com ementa, autor, metadados e o botão para o inteiro teor;
- painel de situação atual, com os dias na situação calculados até a data da consulta;
- o caminho de tramitação (Mesa, comissões, Senado e sanção), com o estado de cada etapa;
- o histórico de tramitações agrupado por órgão, com marcadores por tipo de ato e links para os PDFs;
- a relatoria, os indicadores calculados, o progresso das comissões e os próximos marcos.

## Uso

```bash
pip install -e ".[dev]"
python -m relatorios_proposicoes dados/pl-1680-2025.json        # gera saida/pl-1680-2025.html
python -m relatorios_proposicoes dados/pl-1680-2025.json -o relatorio.html
pytest
```

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| `dados/*.json` | Dados de cada proposição (um arquivo por relatório) |
| `relatorios_proposicoes/modelos.py` | Modelos (`Relatorio`, `Estagio`, `Evento`…) e leitura do JSON |
| `relatorios_proposicoes/indicadores.py` | Contagens e durações derivadas dos dados |
| `relatorios_proposicoes/gerador.py` | Renderização Jinja2 e filtros de data |
| `relatorios_proposicoes/templates/` | `base.html`, `componentes.html` (macros) e `tramitacao.html` |
| `relatorios_proposicoes/estilos/` | `tokens.css` (tokens do design system) e `relatorio.css` (componentes) |

## Formato dos dados

Datas usam o formato ISO (`AAAA-MM-DD`, ou `AAAA-MM-DDTHH:MM` nos eventos).
Os documentos são referenciados pelo `codteor` da Câmara, e as fotos dos
deputados vêm do portal da Câmara a partir do `id`. Cada evento tem um `tipo`
que define seu marcador na linha do tempo:

| `tipo` | Marcador |
| --- | --- |
| `marco` | Círculo cheio: marco decisivo |
| `rotina` | Círculo vazado: ato de rotina |
| `alerta` | Losango rosa: atraso ou retirada |
| `atual` | Anel com brilho: posição atual |

Os estágios têm `estado` igual a `concluido`, `atual` ou `pendente`; os
marcados com `"comissao": true` entram no cálculo de progresso das comissões.

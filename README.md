# relatorios-proposicoes
Relatórios de Tramitação e Análise de Proposições Legislativas

Gera páginas HTML autocontidas no visual do design system **Glass HUD Legislativo**
(vidro, acentos em teal/cyan, tema claro por padrão e tema escuro opcional):

1. **Capa** A4 do relatório de gestão e acompanhamento de proposições, pronta para impressão.
2. **Tramitação** de uma proposição (relatório de detalhes), com:
   - cabeçalho com ementa, autor, metadados e botões para o texto original e o texto vigente;
   - painel de situação atual, com os dias na situação calculados até a data da consulta;
   - o caminho de tramitação na Câmara (Mesa, comissões e remessa), com o estado de cada etapa;
   - o histórico de tramitações agrupado por órgão, com marcadores por tipo de ato e links para os PDFs;
   - relatoria, temas e keywords, indicadores, progresso das comissões e próximos marcos;
   - árvore de apensados e documentos acessórios, e documentos anexos, cada item com uma janela de detalhes;
   - análise estratégica: síntese, diagnóstico técnico, legística, matriz de riscos, oportunidades,
     plano de ação e fontes oficiais.
3. **Pesquisa** facetada sobre uma base local de proposições: filtros interligados com contagens,
   autocompletar de tipos, ordenação, painel de detalhes e a consulta equivalente na API.

Na página de tramitação, passar o mouse (ou o foco) sobre um documento acende todos os componentes
que apontam para ele, e os documentos aprovados abrem o popover da **versão válida** (texto de
referência vigente), com atalho para os detalhes.

## Uso

```bash
pip install -e ".[dev]"
python -m relatorios_proposicoes dados/capa.json dados/pl-1680-2025.json dados/pesquisa-cti.json  # gera saida/*.html
python -m relatorios_proposicoes dados/pl-1680-2025.json -o relatorio.html --tema escuro
pytest
```

### Relatórios a partir da API da Câmara

`relatorios_proposicoes.coleta` monta o JSON de tramitação direto da API de Dados Abertos: ficha,
autor, situação, etapas (pelo despacho de distribuição), histórico agrupado por órgão, relatoria,
temas e keywords, árvore de documentos relacionados e anexos. Versão válida e análise estratégica
dependem de avaliação humana e não são geradas.

```bash
# um relatório por proposição da base de pesquisa, ligando-os à página de pesquisa
python -m relatorios_proposicoes.coleta --ids-de dados/pesquisa-pedro-lucas.json --manter 2497586 \
    -o dados/proposicoes --pesquisa dados/pesquisa-pedro-lucas.json
python -m relatorios_proposicoes dados/proposicoes/*.json dados/pl-1680-2025.json dados/pesquisa-pedro-lucas.json
```

`--manter` preserva relatórios curados à mão (como o do PL 1.680/2025, com a análise estratégica).

A chave `"pagina"` do JSON escolhe a página (`"capa"` ou `"pesquisa"`); sem ela, o arquivo é um
relatório de tramitação. A capa é sempre clara, para impressão. A pesquisa abre o relatório de
detalhes das proposições listadas em `detalhes` (gere os dois na mesma pasta).

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| `dados/*.json` | Dados de cada página (um arquivo por página) |
| `relatorios_proposicoes/modelos.py` | Modelos do relatório (`Relatorio`, `Estagio`, `Evento`, `Arvore`, `Analise`…) e leitura do JSON |
| `relatorios_proposicoes/capa.py`, `pesquisa.py` | Modelos da capa e da base de pesquisa |
| `relatorios_proposicoes/coleta.py` | Coleta na API de Dados Abertos e montagem do JSON de tramitação |
| `relatorios_proposicoes/indicadores.py` | Contagens e durações derivadas dos dados |
| `relatorios_proposicoes/gerador.py` | Renderização Jinja2, filtros e escolha da página |
| `relatorios_proposicoes/templates/` | `base.html`, `componentes.html` (macros), `tramitacao.html`, `capa.html` e `pesquisa.html` |
| `relatorios_proposicoes/estilos/` | `tokens.css` (tokens dos dois temas), `relatorio.css`, `capa.css` e `pesquisa.css` |
| `relatorios_proposicoes/scripts/` | `tramitacao.js` (realce, janelas e popover) e `pesquisa.js` (filtros e resultados) |
| `relatorios_proposicoes/recursos/` | Imagens da capa e fontes Liberation Sans e DejaVu Sans Mono (licenças livres), embutidas no HTML |

## Formato dos dados

### Tramitação

Datas usam o formato ISO (`AAAA-MM-DD`, ou `AAAA-MM-DDTHH:MM` nos eventos).
Os documentos são referenciados pelo `codteor` da Câmara (e, quando são proposições acessórias,
pelo `id`, que identifica o mesmo documento em todos os pontos da página). As fotos dos
deputados vêm do portal da Câmara a partir do `id`. Cada evento tem um `tipo` que define seu
marcador na linha do tempo:

| `tipo` | Marcador |
| --- | --- |
| `marco` | Círculo cheio: marco decisivo |
| `rotina` | Círculo vazado: ato de rotina |
| `alerta` | Losango rosa: atraso ou retirada |
| `atual` | Anel com brilho: posição atual |

Os estágios têm `estado` igual a `concluido`, `atual` ou `pendente`; os
marcados com `"comissao": true` entram no cálculo de progresso das comissões.

Seções opcionais:

- `versao_valida`: texto vigente e parecer que o publicou (popover e botão do cabeçalho);
- `arvore`: raiz, `apensados` e `grupos` de documentos vinculados; itens com `destaque` são os
  aprovados (acionam o popover) e itens com `superado` aparecem esmaecidos;
- `anexos`: categorias da ficha de tramitação, com `itens` próprios ou `referencias` (siglas de itens
  da árvore); `selo` substitui a contagem (`PDF`, `N/D`) e `mensagem_vazio` aceita `{data_consulta}`;
- `analise`: textos da análise estratégica; trechos entre `**` ficam em negrito e as fontes são
  citadas pela chave do catálogo `fontes`.

### Pesquisa

Formato compacto lido diretamente pela página: tabelas de referência (`TP` tipos, `S` situações,
`O` órgãos, `T` temas e `TC` seus códigos, `A` autores, `AP` apreciações, `RG` regimes) e os
registros em `L`, que apontam para elas por índice (detalhes em `relatorios_proposicoes/pesquisa.py`).

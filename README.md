# GeoSGB MCP

MCP connector para dados geológicos do Serviço Geológico do Brasil (SGB/CPRM).

## Tools Disponíveis

- `search_mineral_occurrences` - Busca ocorrências minerais
- `search_rare_earth_occurrences` - Busca ocorrências de Terras Raras
- `get_occurrence_details` - Detalhes de uma ocorrência por ID
- `list_mineral_substances` - Lista substâncias minerais cadastradas
- `get_geological_outcrops` - Afloramentos geológicos por UF + município ou
  bbox de até 1 grau quadrado (filtro obrigatório; desde 0.6.0)
- `get_lithology_by_area` - Unidades litoestratigráficas do mapa geológico
  1:1.000.000 (2004) que intersectam um bbox de até 25 graus quadrados ou um
  ponto (lon + lat), agregadas por unidade, sem geometria (desde 0.7.0)

## Instalação

```bash
pip install -e .
```

Usa o SDK oficial `mcp` na linha 2.x (`MCPServer`); Python 3.10 ou superior.

## Uso

```bash
python -m geosgb_mcp.server
```

Toda tool declara `outputSchema` (derivado dos modelos em `models.py`) e
responde com `structuredContent` validado pelo SDK. Toda resposta carrega um
bloco `provenance` (contrato de proveniência v1.0 do portfólio, montado em
`provenance.py`): URL da camada, cláusula WHERE efetiva, instante da extração
em UTC, atribuição "Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB" e o que a
fonte declara de licença (nada além do `copyrightText`), mais `attribution`
com a URL que reproduz a consulta. Argumento com nome
desconhecido é recusado (`additionalProperties: false`). Ocorrência inexistente
em `get_occurrence_details` é resposta de erro (`isError`), não um dict com
`error`.

## Custo da fonte

O geoportal do SGB não pagina: toda query devolve tudo o que casa com a
WHERE, e `limit`/`offset` cortam no cliente. Por isso (medido em 2026-09-17,
Sessão 2 do roadmap):

- As buscas pedem só os campos da resposta (`outFields` explícito) e fazem
  uma requisição só — `UF = 'MG'` (7.562 registros) passou de 8,0 MB / 13 s
  em duas idas para 2,2 MB / ~4 s em uma. `get_occurrence_details` pede `*`.
- `list_mineral_substances` precisa baixar a camada inteira (a fonte recusa
  agregar o campo `SUBSTANCIAS`): a primeira chamada leva ~20 s e as
  seguintes, por 24 h, saem de um cache em processo (`served_from_cache` no
  bloco `provenance`, `retrieved_at` da ida original).
- `search_rare_earth_occurrences` busca só por substância por default (74
  registros); `include_related_rocks=True` soma as rochas hospedeiras
  típicas e traz 2.383 registros, 96% deles pegmatitos.
- O bbox exige os quatro cantos (ou nenhum), `xmin < xmax`, `ymin < ymax`,
  em graus WGS84; incompleto ou invertido é recusado antes de ir à fonte.
- `get_geological_outcrops` (Sessão 3, 0.6.0) serve a camada "Afloramentos
  geológicos": 360.042 pontos em 3.540 municípios, e a fonte só corta sem
  filtro nenhum (`maxRecordCount` 300.000). Por isso o filtro é obrigatório
  e recusado na borda quando falta: `uf` + `municipality` juntos (município
  por igualdade exata, com a grafia da fonte — "Santa Bárbara" acha 1.333
  pontos, "Santa Barbara" acha zero; `LIKE` pegaria 1.571, com vizinhos) ou
  bbox de até 1 grau quadrado. Medido pela tool em 2026-09-17: Santa
  Bárbara/MG em 0,5 MB / ~0,8 s; o maior município (São Félix do Xingu/PA)
  tem 3.000 pontos, 1,2 MB / ~1,8 s; 1°×1° na região mais densa
  (Quadrilátero Ferrífero) traz 8.572 pontos em 3,0 MB / ~3,5 s, e 2°×2° já
  seriam 22.042 / 7,9 MB (recusado). A resposta
  pede 8 campos + coordenadas; `DESCRICAO` fica fora (quase dobra o
  tamanho). `DATA_CADASTRO` vem em epoch ms e sai como `registered_at` em
  `YYYY-MM-DD`.
- `get_lithology_by_area` (Sessão 3, 0.7.0) serve a camada "Unidades
  litoestratigráficas - 1:1.000.000 [2004]": 46.712 polígonos, geometria
  pesada (com ela um bbox de 1°×1° vem em 6,4 MB; sem, em 0,15 MB). Por
  isso a tool nunca pede geometria e exige recorte na borda: bbox de até 25
  graus quadrados OU um ponto (`lon` + `lat`), nunca os dois. A resposta é
  DERIVADA (`provenance.derived: true`, com `derivation_note`): a fonte
  devolve polígonos e a tool agrega no cliente por sigla da unidade
  (agregar na fonte não dá — `groupBy` com bbox responde em 140 s e
  `returnDistinctValues` dá 400), com `polygon_count` e `area_deg2` por
  unidade, ordenadas da maior para a menor. `area_deg2` é a soma da área dos
  polígonos INTEIROS que tocam o recorte, em graus quadrados (a fonte é
  WGS84), não a área dentro do recorte. Medido pela tool em 2026-09-17:
  1°×1° no Quadrilátero Ferrífero traz 311 polígonos em 60 unidades, 0,15
  MB / ~0,5 s; o teto de 25 graus quadrados (5°×5° no centro de MG) 4.180
  polígonos em 356 unidades, 2,1 MB / ~4 s; um ponto (centro de BH: A34bh,
  Complexo Belo Horizonte) ~0,4 s; ponto no mar é lista vazia, não erro. A
  primeira chamada do processo pode demorar bem mais (17 s medidos: o
  portal frio). Pede 17 campos (`LEGENDA` fica fora). `limit`/`offset`
  cortam UNIDADES.

## Testes

```bash
pip install -e .[dev]
pytest                      # offline: modelos + contrato de saída (gate do CI)
INTEGRATION_TESTS=1 pytest  # inclui as suítes que batem no geoportal vivo do SGB
```

`tests/test_output_contract.py` é o gate: sobe o servidor por uma sessão em
memória do SDK, substitui o `httpx.AsyncClient` por um `MockTransport` e, para
cada tool, valida um caso cheio e um magro contra o `outputSchema` publicado
em `tools/list` (validador independente, `jsonschema`). Roda em `ci.yml` a
cada push e PR; a vigília semanal dos endpoints vivos fica em `integration.yml`.

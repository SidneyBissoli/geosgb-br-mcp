# GeoSGB MCP

MCP connector para dados geológicos do Serviço Geológico do Brasil (SGB/CPRM).

## Tools Disponíveis

- `search_mineral_occurrences` - Busca ocorrências minerais
- `search_rare_earth_occurrences` - Busca ocorrências de Terras Raras
- `get_occurrence_details` - Detalhes de uma ocorrência por ID
- `list_mineral_substances` - Lista substâncias minerais cadastradas
- `get_geological_outcrops` - Afloramentos geológicos por UF + município ou
  bbox de até 1 grau quadrado (filtro obrigatório; desde 0.6.0)

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

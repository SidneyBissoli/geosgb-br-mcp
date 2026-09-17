# GeoSGB MCP

MCP connector para dados geológicos do Serviço Geológico do Brasil (SGB/CPRM).

## Tools Disponíveis

- `search_mineral_occurrences` - Busca ocorrências minerais
- `search_rare_earth_occurrences` - Busca ocorrências de Terras Raras
- `get_occurrence_details` - Detalhes de uma ocorrência por ID
- `list_mineral_substances` - Lista substâncias minerais cadastradas

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

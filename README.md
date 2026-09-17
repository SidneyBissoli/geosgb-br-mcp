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

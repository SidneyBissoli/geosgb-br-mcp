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

## Uso

```bash
python -m geosgb_mcp.server
```

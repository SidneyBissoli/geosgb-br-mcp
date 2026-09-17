# GeoSGB MCP Connector - Especificação Técnica

> **Nota (2026-09-17):** este documento faz parte do plano ORIGINAL de janeiro
> de 2026 e descreve o SDK 1.x (`from mcp.server.fastmcp import FastMCP`,
> retorno `-> dict`) e tools que não existem. O código vivo em `src/geosgb_mcp/`
> migrou para o SDK 2.x (`from mcp.server.mcpserver import MCPServer`), anota os
> retornos com modelos Pydantic (`outputSchema`) e recusa argumento
> desconhecido. Em caso de divergência, vale o código e
> `tests/test_output_contract.py`. A porta de entrada do repositório é o
> `README.md` da raiz.

## 1. Visão Geral do Projeto

### 1.1 Objetivo
Criar um MCP (Model Context Protocol) connector para acessar dados geológicos do Serviço Geológico do Brasil (SGB/CPRM), com foco em prospecção de minerais estratégicos, especialmente Elementos Terras Raras (ETRs).

### 1.2 Contexto
- O Brasil possui apenas ~35% do território com mapeamento geológico sistemático
- O país detém a 2ª maior reserva de terras raras do mundo (~21 milhões de toneladas)
- Os dados estão disponíveis via ArcGIS REST API e GeoServer WFS/WMS
- Este connector visa democratizar o acesso a esses dados para análises programáticas

### 1.3 Tecnologias Recomendadas
- **Linguagem:** Python 3.10+
- **Framework MCP:** mcp (oficial da Anthropic)
- **HTTP Client:** httpx (async)
- **Geoespacial:** shapely, geojson (opcional)

---

## 2. Arquitetura de Dados do SGB

### 2.1 Infraestrutura Principal: ArcGIS REST Services

**URL Base:** `https://geoportal.sgb.gov.br/server/rest/services`

O SGB utiliza ArcGIS Server 11.3, que expõe dados via REST API com suporte a:   
- Queries espaciais e por atributos  
- Formatos: JSON, geoJSON, PBF  
- Paginação via `resultOffset` e `resultRecordCount`  

### 2.2 Infraestrutura Secundária: GeoServer OGC

**URL Base:** `https://geoservicos.sgb.gov.br/geoserver`

Serviços WFS/WMS padrão OGC (pode ser implementado como fallback ou alternativa).

---

## 3. Endpoints e Camadas Disponíveis

### 3.1 Ocorrências Minerais ⭐ (PRIORIDADE MÁXIMA)

**Endpoint:** 
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/ocorrencias/MapServer/0
```

**Tipo:** Feature Layer (Point)

**Extensão Geográfica:**  
- XMin: -71, YMin: -34, XMax: -34, YMax: 5  
- EPSG: 4326 (WGS84)  

**Campos Disponíveis:**

| Campo | Tipo | Descrição | Valores Exemplo |
|-------|------|-----------|-----------------|
| `SUBSTANCIAS` | String | Substâncias minerais (186+ tipos) | "Terras raras", "Nióbio", "Lítio", "Ouro" |
| `STATUS_ECONOMICO` | String | Status econômico | "Garimpo", "Mina", "Indeterminado", "Ocorrência" |
| `TIPOLOGIA` | String | Tipo genético do depósito | Vários |
| `PROVINCIA` | String | Província mineral | Vários |
| `ROCHAS_HOSPEDEIRAS` | String | Rochas hospedeiras (426+ tipos) | "Carbonatito", "Granito alcalino" |
| `ROCHAS_ENCAIXANTES` | String | Rochas encaixantes (510+ tipos) | Vários |
| `CLASSES_UTILITARIAS` | String | Classe utilitária | "Gemas", "Metais base", "Água mineral" |
| `UF` | String | Unidade federativa | "MG", "GO", "BA", etc. |
| `MUNICIPIO` | String | Município | Vários |
| `PROJETO` | String | Projeto de mapeamento (187+ projetos) | Vários |
| `CODIGO_FOLHA` | String | Código da folha cartográfica | Ex: "SF.23-X-A-III-1-NO" |
| `FOLHA` | String | Nome da folha | Vários |
| `ID_OCORRENCIA` | Integer | ID único da ocorrência | Numérico |
| `METODO_GEOPOSICIONAMENTO` | String | Método de posicionamento | "GPS", "Carta topográfica" |

**Exemplo de Query:**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/ocorrencias/MapServer/0/query?where=SUBSTANCIAS+LIKE+'%25Terras+raras%25'&outFields=*&f=json
```

---

### 3.2 Afloramentos Geológicos

**Endpoint:**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/afloramentos/MapServer/0
```

**Tipo:** Feature Layer (Point)

**Campos Disponíveis:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ID_AFLORAMENTO` | Integer | ID único |
| `TIPO_AFLORAMENTO` | String | Tipo do afloramento |
| `DESCRICAO` | String | Descrição detalhada |
| `NUMERO_CAMPO` | String | Número de campo |
| `ROCHAS` | String | Rochas do afloramento |
| `TOPONIMIA` | String | Toponímia local |
| `MUNICIPIO` | String | Município |
| `UF` | String | Estado |
| `PROJETO` | String | Projeto de mapeamento |
| `METODO_GEOPOSICIONAMENTO` | String | Método de posicionamento |
| `SUREG` | String | Superintendência Regional |

---

### 3.3 Litoestratigrafia por Estados

**Endpoint:**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/litoestratigrafia_estados/FeatureServer
```

**Tipo:** Feature Layer (Polygon)

**Camadas por Estado (IDs):**  
- 0: Alagoas  
- 1: Amazonas  
- 2: Ceará  
- ... (27 estados)  
- 12: Rio de Janeiro  
- 16: Santa Catarina  
- 23: São Paulo  

**Campos Principais:**  
- `SIGLA` - Sigla da unidade  
- `ID_UNIDADE_ESTRATIGRAFICA` - ID único  
- `NOME_UNIDADE` - Nome completo  

---

### 3.4 Litoestratigrafia Brasil 1:1.000.000

**Endpoint:**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/litoestratigrafia_1000000/MapServer/0
```

**Tipo:** Feature Layer (Polygon)

**Descrição:** Carta Geológica do Brasil ao Milionésimo (2004)

---

### 3.5 Sedimento de Corrente (Geoquímica)

**Endpoint:**
```
https://geoportal.sgb.gov.br/server/rest/services/sedimento_corrente_query_all/FeatureServer
```

**Descrição:** Dados de prospecção geoquímica regional com análises químicas de amostras de sedimento.

---

### 3.6 Cartas de Anomalias Geofísicas

**Endpoint:**
```
https://geoportal.sgb.gov.br/server/rest/services/Cartas_de_Anomalia/MapServer
```

**Descrição:** Índice de cartas de anomalias geofísicas na escala 1:100.000.

---

### 3.7 Favorabilidade para Lítio

**Endpoint:**
```
https://geoportal.sgb.gov.br/server/rest/services/Favora_litio_borb_tif/MapServer
```

**Descrição:** Mapa de favorabilidade para lítio (metodologia aplicável a outros minerais estratégicos).

---

## 4. Padrões de Query da ArcGIS REST API

### 4.1 Estrutura Básica de Query

```
{base_url}/query?
  where={sql_where_clause}
  &outFields={fields}
  &returnGeometry={true|false}
  &f={json|geojson|pjson}
  &resultOffset={offset}
  &resultRecordCount={limit}
```

### 4.2 Parâmetros Comuns

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `where` | Cláusula SQL WHERE | `UF='MG'` ou `1=1` (todos) |
| `outFields` | Campos retornados | `*` ou `SUBSTANCIAS,UF,MUNICIPIO` |
| `returnGeometry` | Incluir geometria | `true` ou `false` |
| `f` | Formato de saída | `json`, `geojson`, `pjson` |
| `resultOffset` | Offset para paginação | `0`, `1000`, `2000` |
| `resultRecordCount` | Limite de registros | `1000` (máximo varia por camada) |
| `geometry` | Filtro espacial (bbox) | `-50,-20,-40,-10` |
| `geometryType` | Tipo de geometria | `esriGeometryEnvelope` |
| `spatialRel` | Relação espacial | `esriSpatialRelIntersects` |
| `inSR` | Sistema de referência entrada | `4326` |
| `outSR` | Sistema de referência saída | `4326` |

### 4.3 Operadores SQL Suportados no WHERE

- Comparação: `=`, `<>`, `<`, `>`, `<=`, `>=`
- Lógicos: `AND`, `OR`, `NOT`
- Pattern matching: `LIKE` com `%` (wildcard)
- Lista: `IN ('valor1', 'valor2')`
- Nulo: `IS NULL`, `IS NOT NULL`

### 4.4 Exemplos de Queries

**Buscar ocorrências de Terras Raras em Minas Gerais:**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/ocorrencias/MapServer/0/query?
  where=SUBSTANCIAS+LIKE+'%25Terras+raras%25'+AND+UF='MG'
  &outFields=*
  &returnGeometry=true
  &f=json
```

**Buscar por bounding box (região amazônica):**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/ocorrencias/MapServer/0/query?
  where=1=1
  &geometry=-70,-10,-50,5
  &geometryType=esriGeometryEnvelope
  &spatialRel=esriSpatialRelIntersects
  &inSR=4326
  &outFields=SUBSTANCIAS,UF,MUNICIPIO
  &f=json
```

**Contar total de registros:**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/ocorrencias/MapServer/0/query?
  where=1=1
  &returnCountOnly=true
  &f=json
```

**Obter valores únicos de um campo:**
```
https://geoportal.sgb.gov.br/server/rest/services/geologia/ocorrencias/MapServer/0/query?
  where=1=1
  &outFields=SUBSTANCIAS
  &returnDistinctValues=true
  &f=json
```

---

## 5. Especificação das Tools do MCP

### 5.1 `search_mineral_occurrences`

**Descrição:** Busca ocorrências minerais por substância, estado, município ou área geográfica.

**Parâmetros:**
```python
{
    "substance": str | None,      # Ex: "Terras raras", "Nióbio", "Lítio"
    "uf": str | None,             # Ex: "MG", "GO", "BA"
    "municipality": str | None,   # Nome do município
    "economic_status": str | None, # "Mina", "Garimpo", "Ocorrência"
    "bbox": tuple | None,         # (xmin, ymin, xmax, ymax) em WGS84
    "limit": int = 100,           # Máximo de resultados
    "offset": int = 0,            # Para paginação
    "include_geometry": bool = True
}
```

**Retorno:**
```python
{
    "count": int,
    "total_count": int,
    "features": [
        {
            "id": int,
            "substance": str,
            "economic_status": str,
            "host_rocks": str,
            "uf": str,
            "municipality": str,
            "project": str,
            "coordinates": {"lat": float, "lon": float} | None
        }
    ]
}
```

---

### 5.2 `search_rare_earth_occurrences`

**Descrição:** Busca específica para ocorrências de Elementos Terras Raras (ETRs).

**Parâmetros:**
```python
{
    "uf": str | None,             # Filtro por estado
    "bbox": tuple | None,         # Bounding box
    "include_related_rocks": bool = True,  # Incluir carbonatitos, alcalinas
    "limit": int = 100
}
```

**Lógica Interna:**  
- Busca `SUBSTANCIAS LIKE '%Terras raras%'`   
- Se `include_related_rocks=True`, também busca ocorrências em rochas hospedeiras típicas de ETRs (carbonatitos, rochas alcalinas, pegmatitos)  

---

### 5.3 `get_geological_outcrops`

**Descrição:** Retorna afloramentos geológicos em uma área.

**Parâmetros:**
```python
{
    "uf": str | None,
    "municipality": str | None,
    "bbox": tuple | None,
    "rock_type": str | None,      # Filtro por tipo de rocha
    "project": str | None,        # Filtro por projeto
    "limit": int = 100,
    "offset": int = 0
}
```

---

### 5.4 `get_lithology_by_area`

**Descrição:** Retorna unidades litoestratigráficas (polígonos) em uma área.

**Parâmetros:**
```python
{
    "uf": str,                    # Estado (obrigatório)
    "bbox": tuple | None,         # Bounding box opcional
    "unit_name": str | None       # Filtro por nome da unidade
}
```

---

### 5.5 `get_geochemical_samples`

**Descrição:** Retorna amostras geoquímicas de sedimento de corrente.

**Parâmetros:**
```python
{
    "bbox": tuple | None,
    "uf": str | None,
    "element": str | None,        # Elemento químico de interesse
    "limit": int = 100
}
```

---

### 5.6 `list_available_substances`

**Descrição:** Lista todas as substâncias minerais cadastradas no banco.

**Parâmetros:** Nenhum

**Retorno:** Lista de substâncias únicas

---

### 5.7 `list_mineral_provinces`

**Descrição:** Lista províncias minerais do Brasil.

**Parâmetros:** 
```python
{
    "uf": str | None  # Filtro opcional por estado
}
```

---

### 5.8 `get_mapping_coverage`

**Descrição:** Retorna informação sobre a cobertura de mapeamento geológico por estado/região.

**Parâmetros:**
```python
{
    "uf": str | None
}
```

---

## 6. Estrutura Sugerida do Projeto

```
geosgb-mcp/
├── pyproject.toml
├── README.md
├── src/
│   └── geosgb_mcp/
│       ├── __init__.py
│       ├── server.py           # MCP Server principal
│       ├── client.py           # Cliente HTTP para ArcGIS REST API
│       ├── models.py           # Pydantic models
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── occurrences.py  # Tools de ocorrências minerais
│       │   ├── outcrops.py     # Tools de afloramentos
│       │   ├── lithology.py    # Tools de litoestratigrafia
│       │   └── geochemistry.py # Tools de geoquímica
│       └── constants.py        # URLs, constantes
└── tests/
    └── ...
```

---

## 7. Considerações Técnicas

### 7.1 Rate Limiting
- A API do SGB não documenta rate limits explícitos
- Recomenda-se implementar throttling conservador (1-2 req/s)
- Usar cache para queries frequentes

### 7.2 Paginação
- MaxRecordCount varia por camada (geralmente 1000)
- Implementar paginação automática para queries grandes
- Usar `resultOffset` e `resultRecordCount`

### 7.3 Tratamento de Erros
- Timeout: serviço pode ser lento para queries grandes
- Geometrias inválidas: validar bbox antes de enviar
- Encoding: alguns campos podem ter caracteres especiais (UTF-8)

### 7.4 Cache
- Considerar cache para:
  - Lista de substâncias (muda raramente)
  - Lista de províncias minerais
  - Metadados de camadas

---

## 8. Substâncias Minerais Relevantes para ETRs

### 8.1 Termos de Busca Diretos
- "Terras raras"
- "Elementos terras raras"
- "ETR"
- Elementos individuais: "Cério", "Lantânio", "Neodímio", "Ítrio", etc.

### 8.2 Minerais Hospedeiros de ETRs
- Monazita
- Bastnasita
- Xenotima
- Apatita (pode conter ETRs)
- Pirocloro (associado a Nb, mas pode ter ETRs)

### 8.3 Rochas Hospedeiras Típicas
- Carbonatito
- Nefelina sienito
- Sienito alcalino
- Pegmatito
- Granito alcalino
- Fonolito

### 8.4 Províncias com Potencial para ETRs
- Alto Paranaíba (MG) - Araxá
- Província Estanífera de Goiás
- Complexo Jequié (BA)
- Bacia do Parnaíba (PI)
- Vale do Ribeira (PR/SP/SC)

---

## 9. Exemplos de Uso Esperados

### 9.1 Buscar ocorrências de terras raras em Goiás
```
User: Quais são as ocorrências de terras raras em Goiás?

Tool call: search_rare_earth_occurrences(uf="GO")
```

### 9.2 Listar ocorrências em um bounding box
```
User: Mostre ocorrências minerais na região de Araxá, MG

Tool call: search_mineral_occurrences(
    bbox=(-47.5, -20.0, -46.5, -19.0),
    limit=50
)
```

### 9.3 Buscar rochas alcalinas (potencial para ETRs)
```
User: Onde há ocorrências de carbonatitos no Brasil?

Tool call: search_mineral_occurrences(
    substance=None,
    host_rocks="Carbonatito"
)
```

---

## 10. Referências

- GeoPortal SGB: https://geoportal.sgb.gov.br/server/rest/services
- GeoSGB: https://geosgb.sgb.gov.br/
- OpenData SGB: https://opendata.sgb.gov.br/
- ArcGIS REST API Reference: https://developers.arcgis.com/rest/services-reference/
- MCP Specification: https://modelcontextprotocol.io/

---

## 11. Notas de Implementação

1. **Começar pelo endpoint de Ocorrências Minerais** - é o mais estruturado e útil
2. **Testar queries básicas antes de implementar** - verificar disponibilidade e formato
3. **Implementar logging detalhado** - ajuda na depuração
4. **Considerar modo offline** - cache de dados para uso sem conexão
5. **Documentar limitações conhecidas** - campos que podem estar vazios, etc.

---

*Documento gerado em: Janeiro/2026*
*Autor: Claude (Anthropic) em colaboração com Sidney*

# GeoSGB MCP Connector - Código de Referência

> **Nota (2026-09-17):** este documento é o plano ORIGINAL e seus snippets
> refletem o SDK 1.x (`from mcp.server.fastmcp import FastMCP`, retorno
> `-> dict`). O código vivo em `src/geosgb_mcp/` migrou para o SDK 2.x
> (`from mcp.server.mcpserver import MCPServer`), anota os retornos com
> modelos Pydantic (`outputSchema`) e recusa argumento desconhecido. Em caso
> de divergência, vale o código e `tests/test_output_contract.py`.

## Snippet 1: Cliente HTTP Base

```python
# client.py
import httpx
from typing import Any
from urllib.parse import urlencode

class GeoSGBClient:
    """Cliente para ArcGIS REST API do SGB."""
    
    BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"
    
    ENDPOINTS = {
        "ocorrencias": "/geologia/ocorrencias/MapServer/0",
        "afloramentos": "/geologia/afloramentos/MapServer/0",
        # raiz do serviço: uma camada POR ESTADO, resolver id via ?f=json
        "litoestratigrafia_estados": "/geologia/litoestratigrafia_estados/MapServer",
        "litoestratigrafia_1m": "/geologia/litoestratigrafia_1000000/MapServer/0",
        # 2026-08: sedimento_corrente_query_all morreu na fonte; camada 2 do
        # serviço integrado de geoquímica ("Sedimento de Corrente")
        "sedimento_corrente": "/geoquimica/geoquimica_integrada/MapServer/2",
    }
    
    def __init__(self, timeout: float = 30.0):
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def query(
        self,
        endpoint_key: str,
        where: str = "1=1",
        out_fields: str = "*",
        return_geometry: bool = True,
        geometry: tuple | None = None,  # (xmin, ymin, xmax, ymax)
        result_offset: int = 0,
        result_record_count: int = 100,
        return_count_only: bool = False,
        f: str = "json"
    ) -> dict[str, Any]:
        """Executa query na ArcGIS REST API."""
        
        endpoint = self.ENDPOINTS.get(endpoint_key)
        if not endpoint:
            raise ValueError(f"Endpoint desconhecido: {endpoint_key}")
        
        url = f"{self.BASE_URL}{endpoint}/query"
        
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": str(return_geometry).lower(),
            "resultOffset": result_offset,
            "resultRecordCount": result_record_count,
            "f": f,
        }
        
        if return_count_only:
            params["returnCountOnly"] = "true"
        
        if geometry:
            xmin, ymin, xmax, ymax = geometry
            params["geometry"] = f"{xmin},{ymin},{xmax},{ymax}"
            params["geometryType"] = "esriGeometryEnvelope"
            params["spatialRel"] = "esriSpatialRelIntersects"
            params["inSR"] = "4326"
        
        params["outSR"] = "4326"
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_count(self, endpoint_key: str, where: str = "1=1") -> int:
        """Retorna contagem total de registros."""
        result = await self.query(
            endpoint_key=endpoint_key,
            where=where,
            return_count_only=True
        )
        return result.get("count", 0)
    
    async def close(self):
        await self.client.aclose()
```

---

## Snippet 2: Models Pydantic

```python
# models.py
from pydantic import BaseModel, Field
from typing import Optional

class Coordinates(BaseModel):
    lat: float
    lon: float

class MineralOccurrence(BaseModel):
    id: int = Field(alias="ID_OCORRENCIA")
    substance: Optional[str] = Field(None, alias="SUBSTANCIAS")
    economic_status: Optional[str] = Field(None, alias="STATUS_ECONOMICO")
    host_rocks: Optional[str] = Field(None, alias="ROCHAS_HOSPEDEIRAS")
    enclosing_rocks: Optional[str] = Field(None, alias="ROCHAS_ENCAIXANTES")
    typology: Optional[str] = Field(None, alias="TIPOLOGIA")
    province: Optional[str] = Field(None, alias="PROVINCIA")
    uf: Optional[str] = Field(None, alias="UF")
    municipality: Optional[str] = Field(None, alias="MUNICIPIO")
    project: Optional[str] = Field(None, alias="PROJETO")
    coordinates: Optional[Coordinates] = None
    
    class Config:
        populate_by_name = True

class GeologicalOutcrop(BaseModel):
    id: int = Field(alias="ID_AFLORAMENTO")
    outcrop_type: Optional[str] = Field(None, alias="TIPO_AFLORAMENTO")
    description: Optional[str] = Field(None, alias="DESCRICAO")
    rocks: Optional[str] = Field(None, alias="ROCHAS")
    uf: Optional[str] = Field(None, alias="UF")
    municipality: Optional[str] = Field(None, alias="MUNICIPIO")
    toponymy: Optional[str] = Field(None, alias="TOPONIMIA")
    project: Optional[str] = Field(None, alias="PROJETO")
    coordinates: Optional[Coordinates] = None
    
    class Config:
        populate_by_name = True

class SearchResult(BaseModel):
    count: int
    total_count: int
    offset: int
    features: list
```

---

## Snippet 3: Tool de Ocorrências Minerais

```python
# tools/occurrences.py
from mcp.server.fastmcp import FastMCP
from ..client import GeoSGBClient
from ..models import MineralOccurrence, Coordinates

async def search_mineral_occurrences(
    substance: str | None = None,
    uf: str | None = None,
    municipality: str | None = None,
    economic_status: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 100,
    offset: int = 0,
    include_geometry: bool = True
) -> dict:
    """
    Busca ocorrências minerais no banco de dados do SGB.
    
    Args:
        substance: Substância mineral (ex: "Terras raras", "Ouro", "Lítio")
        uf: Sigla do estado (ex: "MG", "GO", "BA")
        municipality: Nome do município
        economic_status: Status econômico ("Mina", "Garimpo", "Ocorrência")
        bbox: Bounding box (xmin, ymin, xmax, ymax) em WGS84
        limit: Máximo de resultados (default: 100)
        offset: Offset para paginação
        include_geometry: Incluir coordenadas na resposta
    
    Returns:
        Dicionário com count, total_count e lista de ocorrências
    """
    
    # Construir cláusula WHERE
    conditions = []
    
    if substance:
        # Escape de aspas simples e uso de LIKE para busca parcial
        substance_escaped = substance.replace("'", "''")
        conditions.append(f"SUBSTANCIAS LIKE '%{substance_escaped}%'")
    
    if uf:
        conditions.append(f"UF = '{uf.upper()}'")
    
    if municipality:
        municipality_escaped = municipality.replace("'", "''")
        conditions.append(f"MUNICIPIO LIKE '%{municipality_escaped}%'")
    
    if economic_status:
        status_escaped = economic_status.replace("'", "''")
        conditions.append(f"STATUS_ECONOMICO = '{status_escaped}'")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    # Executar query
    client = GeoSGBClient()
    
    try:
        # Obter contagem total
        total_count = await client.get_count("ocorrencias", where_clause)
        
        # Obter registros
        result = await client.query(
            endpoint_key="ocorrencias",
            where=where_clause,
            return_geometry=include_geometry,
            geometry=bbox,
            result_offset=offset,
            result_record_count=min(limit, 1000)
        )
        
        features = result.get("features", [])
        
        # Processar resultados
        occurrences = []
        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})
            
            occurrence = {
                "id": attrs.get("ID_OCORRENCIA"),
                "substance": attrs.get("SUBSTANCIAS"),
                "economic_status": attrs.get("STATUS_ECONOMICO"),
                "host_rocks": attrs.get("ROCHAS_HOSPEDEIRAS"),
                "typology": attrs.get("TIPOLOGIA"),
                "province": attrs.get("PROVINCIA"),
                "uf": attrs.get("UF"),
                "municipality": attrs.get("MUNICIPIO"),
                "project": attrs.get("PROJETO"),
            }
            
            if include_geometry and geom:
                occurrence["coordinates"] = {
                    "lon": geom.get("x"),
                    "lat": geom.get("y")
                }
            
            occurrences.append(occurrence)
        
        return {
            "count": len(occurrences),
            "total_count": total_count,
            "offset": offset,
            "features": occurrences
        }
    
    finally:
        await client.close()


async def search_rare_earth_occurrences(
    uf: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    include_related_rocks: bool = True,
    limit: int = 100
) -> dict:
    """
    Busca específica para ocorrências de Elementos Terras Raras (ETRs).
    
    Args:
        uf: Sigla do estado
        bbox: Bounding box
        include_related_rocks: Se True, inclui ocorrências em rochas 
                               típicas de ETRs (carbonatitos, alcalinas)
        limit: Máximo de resultados
    
    Returns:
        Dicionário com ocorrências de ETRs
    """
    
    # Termos de busca para ETRs
    ree_terms = [
        "Terras raras",
        "Elementos terras raras",
        "ETR",
        "Monazita",
        "Bastnasita",
        "Xenotima",
        "Cério",
        "Lantânio",
        "Neodímio",
        "Ítrio",
    ]
    
    # Rochas hospedeiras típicas
    host_rocks = [
        "Carbonatito",
        "Nefelina sienito",
        "Sienito alcalino",
        "Granito alcalino",
        "Pegmatito",
    ]
    
    # Construir condição de substâncias
    substance_conditions = [f"SUBSTANCIAS LIKE '%{term}%'" for term in ree_terms]
    
    # Adicionar condição de rochas se solicitado
    if include_related_rocks:
        rock_conditions = [f"ROCHAS_HOSPEDEIRAS LIKE '%{rock}%'" for rock in host_rocks]
        all_conditions = substance_conditions + rock_conditions
    else:
        all_conditions = substance_conditions
    
    where_clause = "(" + " OR ".join(all_conditions) + ")"
    
    if uf:
        where_clause = f"{where_clause} AND UF = '{uf.upper()}'"
    
    client = GeoSGBClient()
    
    try:
        total_count = await client.get_count("ocorrencias", where_clause)
        
        result = await client.query(
            endpoint_key="ocorrencias",
            where=where_clause,
            geometry=bbox,
            result_record_count=min(limit, 1000)
        )
        
        features = result.get("features", [])
        
        occurrences = []
        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})
            
            occurrences.append({
                "id": attrs.get("ID_OCORRENCIA"),
                "substance": attrs.get("SUBSTANCIAS"),
                "economic_status": attrs.get("STATUS_ECONOMICO"),
                "host_rocks": attrs.get("ROCHAS_HOSPEDEIRAS"),
                "province": attrs.get("PROVINCIA"),
                "uf": attrs.get("UF"),
                "municipality": attrs.get("MUNICIPIO"),
                "coordinates": {
                    "lon": geom.get("x"),
                    "lat": geom.get("y")
                } if geom else None
            })
        
        return {
            "count": len(occurrences),
            "total_count": total_count,
            "features": occurrences,
            "search_terms_used": ree_terms + (host_rocks if include_related_rocks else [])
        }
    
    finally:
        await client.close()
```

---

## Snippet 4: MCP Server Principal

```python
# server.py
from mcp.server.fastmcp import FastMCP

# Criar instância do servidor MCP
mcp = FastMCP("geosgb")

@mcp.tool()
async def search_mineral_occurrences(
    substance: str | None = None,
    uf: str | None = None,
    municipality: str | None = None,
    economic_status: str | None = None,
    bbox_xmin: float | None = None,
    bbox_ymin: float | None = None,
    bbox_xmax: float | None = None,
    bbox_ymax: float | None = None,
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    Busca ocorrências minerais no banco de dados do Serviço Geológico do Brasil.
    
    Permite filtrar por substância mineral, estado (UF), município, status econômico
    e/ou área geográfica (bounding box).
    
    Args:
        substance: Nome da substância mineral (ex: "Ouro", "Terras raras", "Lítio", "Nióbio")
        uf: Sigla do estado brasileiro (ex: "MG", "GO", "BA", "AM")
        municipality: Nome do município
        economic_status: Status econômico da ocorrência ("Mina", "Garimpo", "Ocorrência", "Indeterminado")
        bbox_xmin: Longitude mínima do bounding box (WGS84)
        bbox_ymin: Latitude mínima do bounding box (WGS84)
        bbox_xmax: Longitude máxima do bounding box (WGS84)
        bbox_ymax: Latitude máxima do bounding box (WGS84)
        limit: Número máximo de resultados (default: 100, máximo: 1000)
        offset: Offset para paginação
    
    Returns:
        Dicionário contendo:
        - count: número de resultados retornados
        - total_count: total de registros que atendem aos critérios
        - features: lista de ocorrências minerais com detalhes
    """
    from .tools.occurrences import search_mineral_occurrences as _search
    
    bbox = None
    if all([bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax]):
        bbox = (bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)
    
    return await _search(
        substance=substance,
        uf=uf,
        municipality=municipality,
        economic_status=economic_status,
        bbox=bbox,
        limit=limit,
        offset=offset
    )


@mcp.tool()
async def search_rare_earth_occurrences(
    uf: str | None = None,
    bbox_xmin: float | None = None,
    bbox_ymin: float | None = None,
    bbox_xmax: float | None = None,
    bbox_ymax: float | None = None,
    include_related_rocks: bool = True,
    limit: int = 100
) -> dict:
    """
    Busca ocorrências de Elementos Terras Raras (ETRs) no Brasil.
    
    ETRs são 17 elementos químicos estratégicos para tecnologias de transição
    energética, incluindo lantanídeos, escândio e ítrio.
    
    Args:
        uf: Sigla do estado (ex: "MG", "GO", "BA")
        bbox_xmin: Longitude mínima
        bbox_ymin: Latitude mínima
        bbox_xmax: Longitude máxima
        bbox_ymax: Latitude máxima
        include_related_rocks: Se True, inclui ocorrências em carbonatitos e 
                               rochas alcalinas (hospedeiras típicas de ETRs)
        limit: Número máximo de resultados
    
    Returns:
        Dicionário com ocorrências de ETRs e termos de busca utilizados
    """
    from .tools.occurrences import search_rare_earth_occurrences as _search
    
    bbox = None
    if all([bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax]):
        bbox = (bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)
    
    return await _search(
        uf=uf,
        bbox=bbox,
        include_related_rocks=include_related_rocks,
        limit=limit
    )


@mcp.tool()
async def list_mineral_substances() -> dict:
    """
    Lista todas as substâncias minerais cadastradas no banco de dados do SGB.
    
    Útil para descobrir quais minerais estão disponíveis para consulta.
    
    Returns:
        Lista de substâncias minerais únicas
    """
    from .client import GeoSGBClient
    
    client = GeoSGBClient()
    try:
        result = await client.query(
            endpoint_key="ocorrencias",
            where="1=1",
            out_fields="SUBSTANCIAS",
            return_geometry=False,
            result_record_count=1000
        )
        
        substances = set()
        for feature in result.get("features", []):
            subst = feature.get("attributes", {}).get("SUBSTANCIAS")
            if subst:
                # Algumas substâncias são listas separadas por vírgula
                for s in subst.split(","):
                    substances.add(s.strip())
        
        return {
            "count": len(substances),
            "substances": sorted(list(substances))
        }
    finally:
        await client.close()


@mcp.tool()
async def get_occurrence_details(occurrence_id: int) -> dict:
    """
    Obtém detalhes completos de uma ocorrência mineral específica pelo ID.
    
    Args:
        occurrence_id: ID da ocorrência mineral
    
    Returns:
        Detalhes completos da ocorrência
    """
    from .client import GeoSGBClient
    
    client = GeoSGBClient()
    try:
        result = await client.query(
            endpoint_key="ocorrencias",
            where=f"ID_OCORRENCIA = {occurrence_id}",
            out_fields="*",
            return_geometry=True
        )
        
        features = result.get("features", [])
        if not features:
            return {"error": f"Ocorrência {occurrence_id} não encontrada"}
        
        feature = features[0]
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry", {})
        
        return {
            "id": attrs.get("ID_OCORRENCIA"),
            "substance": attrs.get("SUBSTANCIAS"),
            "economic_status": attrs.get("STATUS_ECONOMICO"),
            "host_rocks": attrs.get("ROCHAS_HOSPEDEIRAS"),
            "enclosing_rocks": attrs.get("ROCHAS_ENCAIXANTES"),
            "typology": attrs.get("TIPOLOGIA"),
            "province": attrs.get("PROVINCIA"),
            "utilitarian_class": attrs.get("CLASSES_UTILITARIAS"),
            "uf": attrs.get("UF"),
            "municipality": attrs.get("MUNICIPIO"),
            "project": attrs.get("PROJETO"),
            "sheet_code": attrs.get("CODIGO_FOLHA"),
            "sheet_name": attrs.get("FOLHA"),
            "positioning_method": attrs.get("METODO_GEOPOSICIONAMENTO"),
            "coordinates": {
                "lon": geom.get("x"),
                "lat": geom.get("y")
            } if geom else None
        }
    finally:
        await client.close()


# Ponto de entrada
if __name__ == "__main__":
    mcp.run()
```

---

## Snippet 5: pyproject.toml

```toml
[project]
name = "geosgb-mcp"
version = "0.1.0"
description = "MCP connector para dados geológicos do Serviço Geológico do Brasil"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}
authors = [
    {name = "Sidney", email = "your.email@example.com"}
]
keywords = ["mcp", "geology", "brazil", "rare-earth", "mining"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: GIS",
]

dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/geosgb_mcp"]

[project.scripts]
geosgb-mcp = "geosgb_mcp.server:mcp.run"
```

---

## Snippet 6: Teste Básico da API

```python
# test_api.py
"""
Script para testar a API do SGB antes de implementar o MCP.
Execute com: python test_api.py
"""

import httpx
import asyncio
import json

BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"

async def test_occurrences_api():
    """Testa endpoint de ocorrências minerais."""
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Teste 1: Buscar terras raras
        print("=" * 60)
        print("Teste 1: Buscar ocorrências de Terras Raras")
        print("=" * 60)
        
        url = f"{BASE_URL}/geologia/ocorrencias/MapServer/0/query"
        params = {
            "where": "SUBSTANCIAS LIKE '%Terras raras%'",
            "outFields": "ID_OCORRENCIA,SUBSTANCIAS,UF,MUNICIPIO,STATUS_ECONOMICO",
            "returnGeometry": "true",
            "f": "json",
            "resultRecordCount": "10"
        }
        
        response = await client.get(url, params=params)
        data = response.json()
        
        print(f"Status: {response.status_code}")
        print(f"Registros retornados: {len(data.get('features', []))}")
        
        for feature in data.get("features", [])[:3]:
            attrs = feature.get("attributes", {})
            print(f"\n  ID: {attrs.get('ID_OCORRENCIA')}")
            print(f"  Substância: {attrs.get('SUBSTANCIAS')}")
            print(f"  UF: {attrs.get('UF')}")
            print(f"  Município: {attrs.get('MUNICIPIO')}")
        
        # Teste 2: Contar total
        print("\n" + "=" * 60)
        print("Teste 2: Contar total de ocorrências de Terras Raras")
        print("=" * 60)
        
        params = {
            "where": "SUBSTANCIAS LIKE '%Terras raras%'",
            "returnCountOnly": "true",
            "f": "json"
        }
        
        response = await client.get(url, params=params)
        data = response.json()
        print(f"Total de ocorrências de Terras Raras: {data.get('count')}")
        
        # Teste 3: Buscar por UF
        print("\n" + "=" * 60)
        print("Teste 3: Buscar ocorrências em Minas Gerais")
        print("=" * 60)
        
        params = {
            "where": "UF = 'MG'",
            "returnCountOnly": "true",
            "f": "json"
        }
        
        response = await client.get(url, params=params)
        data = response.json()
        print(f"Total de ocorrências em MG: {data.get('count')}")
        
        # Teste 4: Buscar por bounding box (região de Araxá)
        print("\n" + "=" * 60)
        print("Teste 4: Buscar por bounding box (região de Araxá/MG)")
        print("=" * 60)
        
        params = {
            "where": "1=1",
            "geometry": "-47.5,-20.0,-46.0,-19.0",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outFields": "SUBSTANCIAS,MUNICIPIO",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": "5"
        }
        
        response = await client.get(url, params=params)
        data = response.json()
        print(f"Ocorrências na região: {len(data.get('features', []))}")
        
        for feature in data.get("features", []):
            attrs = feature.get("attributes", {})
            print(f"  - {attrs.get('MUNICIPIO')}: {attrs.get('SUBSTANCIAS')[:50]}...")


if __name__ == "__main__":
    asyncio.run(test_occurrences_api())
```

---

## Notas para o Claude Code

1. **Comece testando a API** - Execute `test_api.py` primeiro para validar conectividade

2. **Use FastMCP** - É a forma mais simples de criar um MCP server em Python

3. **Trate timeouts** - A API do SGB pode ser lenta; use timeout generoso (30s+)

4. **Implemente paginação** - `resultRecordCount` máximo é geralmente 1000

5. **Cache de metadados** - Lista de substâncias, províncias, etc. podem ser cacheados

6. **Logging** - Adicione logs para debug de queries

7. **URL Encoding** - Caracteres especiais em queries SQL precisam ser encoded

8. **Campos nulos** - Muitos campos podem estar vazios; trate como `None`

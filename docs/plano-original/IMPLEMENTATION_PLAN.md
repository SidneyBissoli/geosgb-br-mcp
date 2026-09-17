# GeoSGB MCP Connector - Plano de Implementação e Testes

> **Nota (2026-09-17):** este documento faz parte do plano ORIGINAL de janeiro
> de 2026 e descreve o SDK 1.x (`from mcp.server.fastmcp import FastMCP`,
> retorno `-> dict`) e tools que não existem. O código vivo em `src/geosgb_mcp/`
> migrou para o SDK 2.x (`from mcp.server.mcpserver import MCPServer`), anota os
> retornos com modelos Pydantic (`outputSchema`) e recusa argumento
> desconhecido. Em caso de divergência, vale o código e
> `tests/test_output_contract.py`. A porta de entrada do repositório é o
> `README.md` da raiz.

## 1. Visão Geral do Plano

### 1.1 Objetivo deste Documento
Especificar a sequência de implementação, critérios de aceitação e procedimentos de teste para cada componente do MCP connector do GeoSGB.

### 1.2 Princípios de Desenvolvimento
- **Incremental**: uma funcionalidade por vez
- **Testável**: cada etapa deve ser validada antes de prosseguir
- **Fail-fast**: identificar problemas cedo, antes de acumular complexidade

### 1.3 Dependências entre Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                    FASE 0: VALIDAÇÃO DA API                     │
│                      test_api.py                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASE 1: INFRAESTRUTURA                       │
│              client.py → models.py → constants.py               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASE 2: TOOLS PRINCIPAIS                     │
│    search_mineral_occurrences → search_rare_earth_occurrences   │
│              → list_mineral_substances → get_occurrence_details │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASE 3: TOOLS SECUNDÁRIAS                    │
│      get_geological_outcrops → get_lithology_by_area            │
│              → get_geochemical_samples                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASE 4: INTEGRAÇÃO MCP                       │
│                server.py → configuração → deploy                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. FASE 0: Validação da API Externa

### 2.1 Objetivo
Confirmar que a API do SGB está acessível e responde conforme esperado.

### 2.2 Arquivo a Criar
`test_api.py` (na raiz do projeto, temporário)

### 2.3 Script de Teste

```python
#!/usr/bin/env python3
"""
FASE 0: Validação da API do SGB
Execute: python test_api.py
"""

import httpx
import asyncio
import sys

BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"
TIMEOUT = 30.0

async def test_api():
    """Executa bateria de testes na API do SGB."""
    
    results = {"passed": 0, "failed": 0, "errors": []}
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        
        # ═══════════════════════════════════════════════════════════
        # TESTE 1: Conectividade básica
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 1] Conectividade básica")
        print("-" * 50)
        try:
            url = f"{BASE_URL}/geologia/ocorrencias/MapServer/0/query"
            params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if "count" in data:
                    print(f"  ✓ API acessível. Total de ocorrências: {data['count']}")
                    results["passed"] += 1
                else:
                    print(f"  ✗ Resposta inesperada: {data}")
                    results["failed"] += 1
                    results["errors"].append("Teste 1: resposta sem 'count'")
            else:
                print(f"  ✗ Status code: {response.status_code}")
                results["failed"] += 1
                results["errors"].append(f"Teste 1: status {response.status_code}")
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 1: {e}")
        
        # ═══════════════════════════════════════════════════════════
        # TESTE 2: Query com filtro WHERE
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 2] Query com filtro WHERE (UF='MG')")
        print("-" * 50)
        try:
            params = {
                "where": "UF = 'MG'",
                "outFields": "ID_OCORRENCIA,SUBSTANCIAS,MUNICIPIO",
                "returnGeometry": "false",
                "f": "json",
                "resultRecordCount": "5"
            }
            response = await client.get(url, params=params)
            data = response.json()
            
            features = data.get("features", [])
            if len(features) > 0:
                print(f"  ✓ Retornou {len(features)} registros")
                print(f"    Exemplo: {features[0].get('attributes', {}).get('MUNICIPIO')}")
                results["passed"] += 1
            else:
                print(f"  ✗ Nenhum registro retornado")
                results["failed"] += 1
                results["errors"].append("Teste 2: nenhum registro")
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 2: {e}")
        
        # ═══════════════════════════════════════════════════════════
        # TESTE 3: Query com LIKE (busca parcial)
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 3] Query com LIKE (Terras raras)")
        print("-" * 50)
        try:
            params = {
                "where": "SUBSTANCIAS LIKE '%Terras raras%'",
                "returnCountOnly": "true",
                "f": "json"
            }
            response = await client.get(url, params=params)
            data = response.json()
            
            count = data.get("count", 0)
            if count > 0:
                print(f"  ✓ Encontradas {count} ocorrências de Terras Raras")
                results["passed"] += 1
            else:
                print(f"  ⚠ Nenhuma ocorrência de Terras Raras (pode ser normal)")
                results["passed"] += 1  # Não é necessariamente erro
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 3: {e}")
        
        # ═══════════════════════════════════════════════════════════
        # TESTE 4: Query espacial (bounding box)
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 4] Query espacial (bbox região de Araxá)")
        print("-" * 50)
        try:
            params = {
                "where": "1=1",
                "geometry": "-47.5,-20.0,-46.0,-19.0",
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
                "inSR": "4326",
                "outSR": "4326",
                "outFields": "SUBSTANCIAS,MUNICIPIO",
                "returnGeometry": "true",
                "f": "json",
                "resultRecordCount": "5"
            }
            response = await client.get(url, params=params)
            data = response.json()
            
            features = data.get("features", [])
            if len(features) > 0:
                print(f"  ✓ Retornou {len(features)} registros na região")
                # Verificar se geometria está presente
                geom = features[0].get("geometry", {})
                if "x" in geom and "y" in geom:
                    print(f"    Coordenadas: ({geom['x']:.4f}, {geom['y']:.4f})")
                    results["passed"] += 1
                else:
                    print(f"  ⚠ Geometria ausente ou formato inesperado")
                    results["passed"] += 1
            else:
                print(f"  ⚠ Nenhum registro na região (pode ser normal)")
                results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 4: {e}")
        
        # ═══════════════════════════════════════════════════════════
        # TESTE 5: Paginação
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 5] Paginação (resultOffset)")
        print("-" * 50)
        try:
            # Primeira página
            params = {
                "where": "1=1",
                "outFields": "ID_OCORRENCIA",
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": "0",
                "resultRecordCount": "2"
            }
            response = await client.get(url, params=params)
            data1 = response.json()
            ids_page1 = [f["attributes"]["ID_OCORRENCIA"] for f in data1.get("features", [])]
            
            # Segunda página
            params["resultOffset"] = "2"
            response = await client.get(url, params=params)
            data2 = response.json()
            ids_page2 = [f["attributes"]["ID_OCORRENCIA"] for f in data2.get("features", [])]
            
            # Verificar se são diferentes
            if len(ids_page1) > 0 and len(ids_page2) > 0:
                if set(ids_page1) != set(ids_page2):
                    print(f"  ✓ Paginação funcionando")
                    print(f"    Página 1 IDs: {ids_page1}")
                    print(f"    Página 2 IDs: {ids_page2}")
                    results["passed"] += 1
                else:
                    print(f"  ✗ Paginação retornou mesmos IDs")
                    results["failed"] += 1
                    results["errors"].append("Teste 5: paginação não funcionou")
            else:
                print(f"  ⚠ Dados insuficientes para testar paginação")
                results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 5: {e}")
        
        # ═══════════════════════════════════════════════════════════
        # TESTE 6: Endpoint de afloramentos
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 6] Endpoint de afloramentos")
        print("-" * 50)
        try:
            url_aflor = f"{BASE_URL}/geologia/afloramentos/MapServer/0/query"
            params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
            response = await client.get(url_aflor, params=params)
            data = response.json()
            
            if "count" in data:
                print(f"  ✓ Endpoint acessível. Total de afloramentos: {data['count']}")
                results["passed"] += 1
            else:
                print(f"  ✗ Resposta inesperada")
                results["failed"] += 1
                results["errors"].append("Teste 6: resposta sem 'count'")
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 6: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # RESUMO
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 50)
    print("RESUMO DA VALIDAÇÃO")
    print("=" * 50)
    print(f"  Testes passados: {results['passed']}")
    print(f"  Testes falhados: {results['failed']}")
    
    if results["errors"]:
        print("\n  Erros encontrados:")
        for err in results["errors"]:
            print(f"    - {err}")
    
    if results["failed"] == 0:
        print("\n  ✓ API VALIDADA - Pode prosseguir para FASE 1")
        return 0
    else:
        print("\n  ✗ VALIDAÇÃO FALHOU - Corrigir antes de prosseguir")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_api())
    sys.exit(exit_code)
```

### 2.4 Critérios de Aceitação  
- [ ] Todos os 6 testes passam  
- [ ] Tempo de resposta < 30s para cada teste  
- [ ] Nenhum erro de conexão  

### 2.5 Ação se Falhar  
- Verificar conectividade de rede  
- Verificar se o domínio `geoportal.sgb.gov.br` está acessível  
- Verificar se a API não está em manutenção  

### 2.6 Próximo Passo
Se todos os testes passarem → **FASE 1**

---

## 3. FASE 1: Infraestrutura Base

### 3.1 Objetivo
Criar os componentes fundamentais: cliente HTTP, modelos de dados e constantes.

### 3.2 Sequência de Implementação

#### 3.2.1 Etapa 1.1: Estrutura de Diretórios

```bash
# Criar estrutura do projeto
mkdir -p geosgb-mcp/src/geosgb_mcp/tools
mkdir -p geosgb-mcp/tests

# Criar arquivos __init__.py
touch geosgb-mcp/src/geosgb_mcp/__init__.py
touch geosgb-mcp/src/geosgb_mcp/tools/__init__.py
```

**Critério de Aceitação:**  
- [ ] Estrutura de diretórios criada  
- [ ] Arquivos `__init__.py` presentes  

#### 3.2.2 Etapa 1.2: constants.py

```python
# src/geosgb_mcp/constants.py
"""Constantes e configurações do GeoSGB MCP."""

# URLs base
BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"

# Endpoints disponíveis
ENDPOINTS = {
    "ocorrencias": "/geologia/ocorrencias/MapServer/0",
    "afloramentos": "/geologia/afloramentos/MapServer/0",
    "litoestratigrafia_estados": "/geologia/litoestratigrafia_estados/FeatureServer",
    "litoestratigrafia_1m": "/geologia/litoestratigrafia_1000000/MapServer/0",
    "sedimento_corrente": "/sedimento_corrente_query_all/FeatureServer/0",
}

# Configurações de requisição
DEFAULT_TIMEOUT = 30.0
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

# Termos de busca para ETRs
REE_SEARCH_TERMS = [
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
    "Samário",
    "Európio",
    "Gadolínio",
]

# Rochas hospedeiras típicas de ETRs
REE_HOST_ROCKS = [
    "Carbonatito",
    "Nefelina sienito",
    "Sienito alcalino",
    "Granito alcalino",
    "Pegmatito",
    "Fonolito",
]

# Estados brasileiros (para validação)
UF_CODES = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"
]
```

**Critério de Aceitação:**    
- [ ] Arquivo criado sem erros de sintaxe    
- [ ] `python -c "from geosgb_mcp.constants import BASE_URL; print(BASE_URL)"` funciona  

#### 3.2.3 Etapa 1.3: client.py

Implementar conforme código de referência (`geosgb-mcp-code-reference.md`, Snippet 1).

**Teste de Validação:**

```python
# tests/test_client.py
import asyncio
import pytest
from geosgb_mcp.client import GeoSGBClient

@pytest.mark.asyncio
async def test_client_connectivity():
    """Testa conectividade básica do cliente."""
    client = GeoSGBClient()
    try:
        count = await client.get_count("ocorrencias")
        assert count > 0, "Deve haver ocorrências no banco"
    finally:
        await client.close()

@pytest.mark.asyncio
async def test_client_query_with_where():
    """Testa query com filtro WHERE."""
    client = GeoSGBClient()
    try:
        result = await client.query(
            endpoint_key="ocorrencias",
            where="UF = 'MG'",
            result_record_count=5
        )
        assert "features" in result
        assert len(result["features"]) <= 5
    finally:
        await client.close()

@pytest.mark.asyncio
async def test_client_query_with_bbox():
    """Testa query com bounding box."""
    client = GeoSGBClient()
    try:
        result = await client.query(
            endpoint_key="ocorrencias",
            geometry=(-47.5, -20.0, -46.0, -19.0),
            result_record_count=5
        )
        assert "features" in result
    finally:
        await client.close()

# Executar: pytest tests/test_client.py -v
```

**Critérios de Aceitação:**  
- [ ] `pytest tests/test_client.py -v` passa todos os testes  
- [ ] Nenhum timeout nos testes  

#### 3.2.4 Etapa 1.4: models.py

Implementar conforme código de referência (`geosgb-mcp-code-reference.md`, Snippet 2).

**Teste de Validação:**

```python
# tests/test_models.py
from geosgb_mcp.models import MineralOccurrence, Coordinates

def test_mineral_occurrence_from_api():
    """Testa criação de MineralOccurrence a partir de dados da API."""
    api_data = {
        "ID_OCORRENCIA": 12345,
        "SUBSTANCIAS": "Ouro, Prata",
        "UF": "MG",
        "MUNICIPIO": "Ouro Preto",
        "STATUS_ECONOMICO": "Mina"
    }
    
    occurrence = MineralOccurrence(**api_data)
    
    assert occurrence.id == 12345
    assert occurrence.substance == "Ouro, Prata"
    assert occurrence.uf == "MG"

def test_mineral_occurrence_with_none():
    """Testa campos opcionais como None."""
    api_data = {
        "ID_OCORRENCIA": 1,
        "SUBSTANCIAS": None,
        "UF": "GO"
    }
    
    occurrence = MineralOccurrence(**api_data)
    assert occurrence.substance is None

# Executar: pytest tests/test_models.py -v
```

**Critérios de Aceitação:**  
- [ ] `pytest tests/test_models.py -v` passa todos os testes  
- [ ] Models aceitam campos nulos corretamente  

### 3.3 Checkpoint FASE 1

Antes de prosseguir para FASE 2, verificar:

```bash
# Rodar todos os testes da FASE 1
pytest tests/ -v

# Verificar imports funcionam
python -c "
from geosgb_mcp.constants import BASE_URL, ENDPOINTS
from geosgb_mcp.client import GeoSGBClient
from geosgb_mcp.models import MineralOccurrence
print('✓ Todos os imports funcionam')
"
```

**Critérios para avançar:**  
- [ ] Todos os testes passam  
- [ ] Imports funcionam sem erro  
- [ ] Cliente consegue fazer queries básicas  

---

## 4. FASE 2: Tools Principais

### 4.1 Objetivo
Implementar as tools core do MCP: busca de ocorrências minerais.

### 4.2 Sequência de Implementação

#### 4.2.1 Etapa 2.1: search_mineral_occurrences

**Arquivo:** `src/geosgb_mcp/tools/occurrences.py`

Implementar conforme código de referência (`geosgb-mcp-code-reference.md`, Snippet 3, primeira função).

**Teste de Validação:**

```python
# tests/test_tools_occurrences.py
import asyncio
import pytest
from geosgb_mcp.tools.occurrences import search_mineral_occurrences

@pytest.mark.asyncio
async def test_search_by_uf():
    """Testa busca por estado."""
    result = await search_mineral_occurrences(uf="MG", limit=10)
    
    assert "count" in result
    assert "total_count" in result
    assert "features" in result
    assert result["count"] <= 10
    
    # Verificar que todos os resultados são de MG
    for feature in result["features"]:
        assert feature["uf"] == "MG"

@pytest.mark.asyncio
async def test_search_by_substance():
    """Testa busca por substância."""
    result = await search_mineral_occurrences(substance="Ouro", limit=5)
    
    assert result["count"] >= 0
    # Se houver resultados, verificar que contém "Ouro"
    for feature in result["features"]:
        assert "Ouro" in (feature["substance"] or "")

@pytest.mark.asyncio
async def test_search_by_bbox():
    """Testa busca por bounding box."""
    result = await search_mineral_occurrences(
        bbox=(-47.5, -20.0, -46.0, -19.0),
        limit=10
    )
    
    assert "features" in result
    # Verificar coordenadas dentro do bbox
    for feature in result["features"]:
        if feature.get("coordinates"):
            lon = feature["coordinates"]["lon"]
            lat = feature["coordinates"]["lat"]
            assert -47.5 <= lon <= -46.0
            assert -20.0 <= lat <= -19.0

@pytest.mark.asyncio
async def test_search_combined_filters():
    """Testa busca com múltiplos filtros."""
    result = await search_mineral_occurrences(
        uf="GO",
        substance="Nióbio",
        limit=5
    )
    
    assert "features" in result

@pytest.mark.asyncio
async def test_search_pagination():
    """Testa paginação."""
    # Primeira página
    result1 = await search_mineral_occurrences(uf="MG", limit=5, offset=0)
    # Segunda página
    result2 = await search_mineral_occurrences(uf="MG", limit=5, offset=5)
    
    # IDs devem ser diferentes
    ids1 = {f["id"] for f in result1["features"]}
    ids2 = {f["id"] for f in result2["features"]}
    
    assert ids1.isdisjoint(ids2), "Paginação deve retornar registros diferentes"

# Executar: pytest tests/test_tools_occurrences.py -v
```

**Critérios de Aceitação:**  
- [ ] Todos os 5 testes passam  
- [ ] Busca por UF filtra corretamente  
- [ ] Busca por substância funciona com LIKE  
- [ ] Busca espacial respeita o bbox  
- [ ] Paginação retorna registros diferentes  

#### 4.2.2 Etapa 2.2: search_rare_earth_occurrences

**Arquivo:** Adicionar a `src/geosgb_mcp/tools/occurrences.py`

Implementar conforme código de referência (`geosgb-mcp-code-reference.md`, Snippet 3, segunda função).

**Teste de Validação:**

```python
# Adicionar a tests/test_tools_occurrences.py

@pytest.mark.asyncio
async def test_search_ree_basic():
    """Testa busca básica de ETRs."""
    result = await search_rare_earth_occurrences(limit=20)
    
    assert "count" in result
    assert "features" in result
    assert "search_terms_used" in result
    
    # Deve ter usado os termos de busca
    assert len(result["search_terms_used"]) > 0

@pytest.mark.asyncio
async def test_search_ree_by_uf():
    """Testa busca de ETRs por estado."""
    result = await search_rare_earth_occurrences(uf="GO", limit=10)
    
    # Se houver resultados, todos devem ser de GO
    for feature in result["features"]:
        assert feature["uf"] == "GO"

@pytest.mark.asyncio
async def test_search_ree_with_related_rocks():
    """Testa busca de ETRs incluindo rochas relacionadas."""
    result_with = await search_rare_earth_occurrences(
        include_related_rocks=True, 
        limit=50
    )
    result_without = await search_rare_earth_occurrences(
        include_related_rocks=False, 
        limit=50
    )
    
    # Com rochas relacionadas deve retornar mais termos de busca
    assert len(result_with["search_terms_used"]) > len(result_without["search_terms_used"])
```

**Critérios de Aceitação:**  
- [ ] Busca retorna ocorrências de ETRs  
- [ ] Filtro por UF funciona  
- [ ] Flag `include_related_rocks` afeta os resultados  

#### 4.2.3 Etapa 2.3: list_mineral_substances

**Arquivo:** Adicionar a `src/geosgb_mcp/tools/occurrences.py`

```python
async def list_mineral_substances() -> dict:
    """
    Lista todas as substâncias minerais únicas no banco de dados.
    
    Returns:
        Dicionário com count e lista de substâncias
    """
    from ..client import GeoSGBClient
    
    client = GeoSGBClient()
    try:
        # Buscar amostra grande para capturar diversidade
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
                # Separar substâncias múltiplas (podem vir separadas por vírgula)
                for s in subst.split(","):
                    s = s.strip()
                    if s:
                        substances.add(s)
        
        return {
            "count": len(substances),
            "substances": sorted(list(substances))
        }
    finally:
        await client.close()
```

**Teste de Validação:**

```python
@pytest.mark.asyncio
async def test_list_substances():
    """Testa listagem de substâncias."""
    result = await list_mineral_substances()
    
    assert "count" in result
    assert "substances" in result
    assert result["count"] > 0
    assert isinstance(result["substances"], list)
    
    # Deve conter algumas substâncias conhecidas
    substances_lower = [s.lower() for s in result["substances"]]
    assert any("ouro" in s for s in substances_lower)
```

**Critérios de Aceitação:**  
- [ ] Retorna lista não vazia  
- [ ] Lista está ordenada alfabeticamente  
- [ ] Contém substâncias esperadas (Ouro, Ferro, etc.)  

#### 4.2.4 Etapa 2.4: get_occurrence_details

**Arquivo:** Adicionar a `src/geosgb_mcp/tools/occurrences.py`

```python
async def get_occurrence_details(occurrence_id: int) -> dict:
    """
    Obtém detalhes completos de uma ocorrência específica.
    
    Args:
        occurrence_id: ID da ocorrência
    
    Returns:
        Detalhes completos ou erro se não encontrada
    """
    from ..client import GeoSGBClient
    
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
```

**Teste de Validação:**

```python
@pytest.mark.asyncio
async def test_get_occurrence_details():
    """Testa obtenção de detalhes de uma ocorrência."""
    # Primeiro, buscar uma ocorrência válida
    search_result = await search_mineral_occurrences(limit=1)
    if search_result["count"] == 0:
        pytest.skip("Nenhuma ocorrência disponível para teste")
    
    occurrence_id = search_result["features"][0]["id"]
    
    # Buscar detalhes
    details = await get_occurrence_details(occurrence_id)
    
    assert "error" not in details
    assert details["id"] == occurrence_id
    assert "substance" in details
    assert "uf" in details

@pytest.mark.asyncio
async def test_get_occurrence_not_found():
    """Testa busca de ocorrência inexistente."""
    details = await get_occurrence_details(999999999)
    
    assert "error" in details
```

**Critérios de Aceitação:**  
- [ ] Retorna todos os campos disponíveis  
- [ ] Retorna erro apropriado para ID inexistente  
- [ ] Coordenadas estão presentes quando disponíveis  

### 4.3 Checkpoint FASE 2

```bash
# Rodar todos os testes das tools
pytest tests/test_tools_occurrences.py -v

# Teste manual rápido
python -c "
import asyncio
from geosgb_mcp.tools.occurrences import (
    search_mineral_occurrences,
    search_rare_earth_occurrences,
    list_mineral_substances,
    get_occurrence_details
)

async def test():
    # Teste rápido de cada função
    r1 = await search_mineral_occurrences(uf='MG', limit=2)
    print(f'search_mineral_occurrences: {r1[\"count\"]} resultados')
    
    r2 = await search_rare_earth_occurrences(limit=2)
    print(f'search_rare_earth_occurrences: {r2[\"count\"]} resultados')
    
    r3 = await list_mineral_substances()
    print(f'list_mineral_substances: {r3[\"count\"]} substâncias')
    
    if r1['features']:
        r4 = await get_occurrence_details(r1['features'][0]['id'])
        print(f'get_occurrence_details: {r4.get(\"municipality\", \"OK\")}')
    
    print('\\n✓ Todas as tools FASE 2 funcionando')

asyncio.run(test())
"
```

**Critérios para avançar:**  
- [ ] Todos os testes de tools passam  
- [ ] Teste manual executa sem erros  
- [ ] Cada tool retorna dados válidos  

---

## 5. FASE 3: Tools Secundárias (Opcional)

### 5.1 Objetivo
Implementar tools adicionais para afloramentos, litologia e geoquímica.

### 5.2 Priorização
Esta fase é **opcional** para o MVP. Pode ser implementada após validação no Claude Desktop.

### 5.3 Tools a Implementar

#### 5.3.1 get_geological_outcrops  
- Endpoint: `/geologia/afloramentos/MapServer/0`  
- Parâmetros: uf, municipality, bbox, rock_type, limit  

#### 5.3.2 get_lithology_by_area  
- Endpoint: `/geologia/litoestratigrafia_estados/FeatureServer/{state_id}`  
- Parâmetros: uf (obrigatório), bbox  

#### 5.3.3 get_geochemical_samples  
- Endpoint: `/sedimento_corrente_query_all/FeatureServer/0`  
- Parâmetros: bbox, uf, element  

### 5.4 Decisão  
- Se tempo disponível → Implementar  
- Se urgência → Pular para FASE 4  

---

## 6. FASE 4: Integração MCP e Deploy

### 6.1 Objetivo
Configurar o servidor MCP e integrar com Claude Desktop.

### 6.2 Etapa 4.1: server.py

Implementar conforme código de referência (`geosgb-mcp-code-reference.md`, Snippet 4).

**Teste de Validação:**

```bash
# Testar se o servidor inicia sem erro
python -c "from geosgb_mcp.server import mcp; print('✓ Server importado')"

# Testar execução do servidor (Ctrl+C para parar)
python -m geosgb_mcp.server
```

### 6.3 Etapa 4.2: Configuração pyproject.toml

Criar conforme código de referência (`geosgb-mcp-code-reference.md`, Snippet 5).

**Teste de Validação:**

```bash
# Instalar em modo desenvolvimento
pip install -e .

# Verificar que o comando está disponível
geosgb-mcp --help
```

### 6.4 Etapa 4.3: Configuração Claude Desktop

**Arquivo:** `~/.config/claude/claude_desktop_config.json` (Linux) ou equivalente

```json
{
  "mcpServers": {
    "geosgb": {
      "command": "python",
      "args": ["-m", "geosgb_mcp.server"],
      "cwd": "/caminho/absoluto/para/geosgb-mcp"
    }
  }
}
```

**Alternativa com ambiente virtual:**

```json
{
  "mcpServers": {
    "geosgb": {
      "command": "/caminho/para/venv/bin/python",
      "args": ["-m", "geosgb_mcp.server"]
    }
  }
}
```

### 6.5 Etapa 4.4: Teste no Claude Desktop

1. **Reiniciar Claude Desktop** (completamente, não apenas a janela)

2. **Verificar que o MCP foi carregado:**  
   - Deve aparecer ícone ou indicação de tools disponíveis  

3. **Testar com prompts:**

```
Prompt 1 (básico):
"Liste as substâncias minerais disponíveis no banco do SGB"

Prompt 2 (busca simples):
"Quais são as ocorrências de ouro em Minas Gerais?"

Prompt 3 (busca ETRs):
"Busque ocorrências de terras raras em Goiás"

Prompt 4 (busca espacial):
"Mostre ocorrências minerais na região de Araxá, MG (use bbox -47.5,-20,-46,-19)"

Prompt 5 (detalhes):
"Me dê detalhes da ocorrência mineral com ID [usar ID de resultado anterior]"
```

### 6.6 Critérios de Aceitação Final  

- [ ] Servidor MCP inicia sem erros  
- [ ] Claude Desktop reconhece as tools  
- [ ] Todos os 5 prompts de teste retornam resultados válidos  
- [ ] Não há timeouts ou erros de conexão  
- [ ] Resultados são formatados de forma legível  

---

## 7. Troubleshooting

### 7.1 Erros Comuns

| Erro | Causa Provável | Solução |
|------|----------------|---------|
| `Connection refused` | API do SGB indisponível | Aguardar e tentar novamente |
| `Timeout` | Query muito grande | Reduzir `limit` ou área do bbox |
| `JSONDecodeError` | Resposta HTML (erro) | Verificar URL e parâmetros |
| `ModuleNotFoundError` | Import incorreto | Verificar estrutura de diretórios |
| `Tool not found` (Claude) | MCP não carregado | Reiniciar Claude Desktop |

### 7.2 Debug de Queries

```python
# Adicionar logging ao client.py
import logging
logging.basicConfig(level=logging.DEBUG)

# Ou imprimir URL final
print(f"URL: {url}?{urlencode(params)}")
```

### 7.3 Verificar Resposta da API

```python
# Salvar resposta para análise
import json
with open("debug_response.json", "w") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
```

---

## 8. Checklist Final

### 8.1 Antes de Considerar Completo

- [ ] FASE 0: API validada  
- [ ] FASE 1: Infraestrutura funcionando  
- [ ] FASE 2: Tools principais testadas  
- [ ] FASE 4: Integração com Claude Desktop OK  
- [ ] README.md criado com instruções de uso  
- [ ] Código commitado em repositório Git  

### 8.2 Melhorias Futuras (Backlog)

- [ ] Cache de resultados frequentes  
- [ ] Rate limiting para proteger a API  
- [ ] Retry automático em caso de falha  
- [ ] Tools da FASE 3 (afloramentos, litologia, geoquímica)  
- [ ] Suporte a exportação GeoJSON  
- [ ] Integração com mapas (Leaflet/Folium)  

---

*Documento gerado em: Janeiro/2026*
*Autor: Claude (Anthropic) em colaboração com Sidney*

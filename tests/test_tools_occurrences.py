"""Testes das tools de ocorrências minerais."""

import pytest
from geosgb_mcp.tools.occurrences import (
    search_mineral_occurrences,
    search_rare_earth_occurrences,
    list_mineral_substances,
    get_occurrence_details,
)


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
        bbox=(-47.5, -20.0, -46.0, -19.0), limit=10
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
    result = await search_mineral_occurrences(uf="GO", substance="Niobio", limit=5)

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
    result_with = await search_rare_earth_occurrences(include_related_rocks=True, limit=50)
    result_without = await search_rare_earth_occurrences(
        include_related_rocks=False, limit=50
    )

    # Com rochas relacionadas deve retornar mais termos de busca
    assert len(result_with["search_terms_used"]) > len(result_without["search_terms_used"])


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

"""Testes vivos da tool de afloramentos (batem no geoportal do SGB).

Vigília, não gate: rodam só com INTEGRATION_TESTS=1 (conftest.py). Os
números esperados são os medidos em 2026-09-17 na decisão por camada da
Sessão 3; a fonte muda com o cadastro, por isso os pisos são folgados.
"""

import pytest
from geosgb_mcp.tools.outcrops import search_geological_outcrops


@pytest.mark.asyncio
async def test_search_by_municipality():
    """Santa Bárbara/MG por igualdade: 1.333 pontos em 2026-09-17 (LIKE
    pegaria 1.571, com os vizinhos)."""
    result = await search_geological_outcrops(uf="MG", municipality="Santa Bárbara", limit=10)

    assert result["count"] == 10
    assert 1000 <= result["total_count"] <= 1600
    assert result["total_count"] < 1571, "LIKE pegou vizinhos: a busca é por igualdade"
    for feature in result["features"]:
        assert feature["uf"] == "MG"
        assert feature["municipality"] == "Santa Bárbara"
        assert isinstance(feature["id"], int)
    # Data de cadastro em ISO quando vier.
    datas = [f["registered_at"] for f in result["features"] if f["registered_at"]]
    for data in datas:
        assert len(data) == 10 and data[4] == "-" and data[7] == "-", data


@pytest.mark.asyncio
async def test_search_by_bbox_1x1():
    """Bbox de 1°×1° sobre o Quadrilátero Ferrífero: 8.572 pontos em
    2026-09-17 (a região mais densa da camada)."""
    result = await search_geological_outcrops(bbox=(-44.5, -20.5, -43.5, -19.5), limit=20)

    assert result["count"] == 20
    assert 7000 <= result["total_count"] <= 12000
    for feature in result["features"]:
        coords = feature["coordinates"]
        assert coords is not None
        assert -44.5 <= coords["lon"] <= -43.5
        assert -20.5 <= coords["lat"] <= -19.5


@pytest.mark.asyncio
async def test_municipality_without_accent_finds_nothing():
    """A igualdade é sensível a acento: "Santa Barbara" é zero na fonte —
    a descrição da tool avisa; aqui se confere que a fonte segue assim."""
    result = await search_geological_outcrops(uf="MG", municipality="Santa Barbara", limit=5)

    assert result["total_count"] == 0
    assert result["features"] == []


@pytest.mark.asyncio
async def test_pagination_in_client():
    """Offset é aplicado no cliente sobre a mesma resposta: páginas disjuntas."""
    p1 = await search_geological_outcrops(uf="MG", municipality="Santa Bárbara", limit=5, offset=0)
    p2 = await search_geological_outcrops(uf="MG", municipality="Santa Bárbara", limit=5, offset=5)

    ids1 = {f["id"] for f in p1["features"]}
    ids2 = {f["id"] for f in p2["features"]}
    assert ids1.isdisjoint(ids2)
    assert p1["total_count"] == p2["total_count"]

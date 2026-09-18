"""Testes vivos da tool de litoestratigrafia (batem no geoportal do SGB).

Vigília, não gate: rodam só com INTEGRATION_TESTS=1 (conftest.py). Os
números esperados são os medidos em 2026-09-17 na decisão por camada da
Sessão 3 (o mapa é de 2004 e não muda; os pisos são folgados mesmo assim).
"""

import pytest
from geosgb_mcp.tools.lithology import search_lithology_by_area

# 1°×1° sobre o Quadrilátero Ferrífero: 311 polígonos / 60 unidades em 2026-09-17.
BBOX_1x1 = (-44.5, -20.5, -43.5, -19.5)


@pytest.mark.asyncio
async def test_bbox_1x1_agrega_por_unidade():
    """Bbox de 1°×1°: ~60 unidades a partir de ~311 polígonos, ordenadas por
    área somada decrescente; a soma dos polygon_count é o total lido."""
    result = await search_lithology_by_area(bbox=BBOX_1x1, limit=1000)

    assert 40 <= result["total_count"] <= 90, result["total_count"]
    assert 200 <= result["polygon_count"] <= 450, result["polygon_count"]
    assert result["count"] == result["total_count"]
    assert sum(u["polygon_count"] for u in result["units"]) == result["polygon_count"]
    areas = [u["area_deg2"] for u in result["units"] if u["area_deg2"] is not None]
    assert areas == sorted(areas, reverse=True)
    codes = [u["code"] for u in result["units"]]
    assert len(codes) == len(set(codes)), "sigla repetida: a agregação falhou"
    # A maior unidade do recorte em 2026-09-17: NP3bsh, 16 polígonos, 1,53 grau².
    maior = result["units"][0]
    assert maior["code"] == "NP3bsh"
    assert maior["polygon_count"] >= 10
    assert maior["area_deg2"] > 1.0
    assert result["provenance"]["derived"] is True
    assert "graus quadrados" in result["provenance"]["derivation_note"]


@pytest.mark.asyncio
async def test_ponto_em_belo_horizonte():
    """Ponto no centro de BH: uma unidade (A34bh, Complexo Belo Horizonte
    em 2026-09-17), um polígono."""
    result = await search_lithology_by_area(point=(-43.94, -19.92))

    assert result["total_count"] == 1 and result["polygon_count"] == 1
    unidade = result["units"][0]
    assert unidade["code"] == "A34bh"
    assert unidade["polygon_count"] == 1
    assert unidade["age_max_ma"] is not None and unidade["age_max_ma"] > 2000
    assert result["provenance"]["dimension_key"]["geometry_type"] == "point"


@pytest.mark.asyncio
async def test_ponto_no_mar_e_lista_vazia():
    """Ponto no Atlântico: nenhuma unidade, resposta vazia legítima."""
    result = await search_lithology_by_area(point=(-30.0, -20.0))

    assert result["total_count"] == 0 and result["polygon_count"] == 0
    assert result["units"] == []


@pytest.mark.asyncio
async def test_pagination_in_client():
    """Offset é aplicado no cliente sobre a mesma lista ordenada: páginas disjuntas."""
    p1 = await search_lithology_by_area(bbox=BBOX_1x1, limit=5, offset=0)
    p2 = await search_lithology_by_area(bbox=BBOX_1x1, limit=5, offset=5)

    codes1 = {u["code"] for u in p1["units"]}
    codes2 = {u["code"] for u in p2["units"]}
    assert codes1.isdisjoint(codes2)
    assert p1["total_count"] == p2["total_count"]

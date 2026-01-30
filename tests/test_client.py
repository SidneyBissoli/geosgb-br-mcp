"""Testes do cliente HTTP GeoSGB."""

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
        )
        assert "features" in result
        assert len(result["features"]) > 0
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
        )
        assert "features" in result
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_client_invalid_endpoint():
    """Testa erro com endpoint inválido."""
    client = GeoSGBClient()
    try:
        with pytest.raises(ValueError, match="Endpoint desconhecido"):
            await client.query(endpoint_key="endpoint_invalido")
    finally:
        await client.close()

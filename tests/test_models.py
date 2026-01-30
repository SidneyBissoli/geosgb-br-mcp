"""Testes dos modelos Pydantic."""

from geosgb_mcp.models import MineralOccurrence, GeologicalOutcrop, Coordinates


def test_mineral_occurrence_from_api():
    """Testa criação de MineralOccurrence a partir de dados da API."""
    api_data = {
        "ID_OCORRENCIA": 12345,
        "SUBSTANCIAS": "Ouro, Prata",
        "UF": "MG",
        "MUNICIPIO": "Ouro Preto",
        "STATUS_ECONOMICO": "Mina",
    }

    occurrence = MineralOccurrence(**api_data)

    assert occurrence.id == 12345
    assert occurrence.substance == "Ouro, Prata"
    assert occurrence.uf == "MG"
    assert occurrence.municipality == "Ouro Preto"
    assert occurrence.economic_status == "Mina"


def test_mineral_occurrence_with_none():
    """Testa campos opcionais como None."""
    api_data = {
        "ID_OCORRENCIA": 1,
        "SUBSTANCIAS": None,
        "UF": "GO",
    }

    occurrence = MineralOccurrence(**api_data)
    assert occurrence.substance is None
    assert occurrence.uf == "GO"


def test_coordinates():
    """Testa modelo de coordenadas."""
    coords = Coordinates(lat=-19.9167, lon=-43.9345)
    assert coords.lat == -19.9167
    assert coords.lon == -43.9345


def test_geological_outcrop():
    """Testa modelo de afloramento geológico."""
    api_data = {
        "ID_AFLORAMENTO": 999,
        "TIPO_AFLORAMENTO": "Natural",
        "UF": "BA",
        "MUNICIPIO": "Salvador",
    }

    outcrop = GeologicalOutcrop(**api_data)

    assert outcrop.id == 999
    assert outcrop.outcrop_type == "Natural"
    assert outcrop.uf == "BA"

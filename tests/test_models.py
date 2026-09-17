"""Modelos do contrato de saída: prendem a regra de models.py.

Regra: todo campo é obrigatório e anulável, sem default. Se alguém acrescentar
`campo: Optional[str] = None`, o `structuredContent` (do modelo) ganha a chave
e o texto (do dict cru) não — e o gate de contrato reprova. Este arquivo pega
o deslize antes, no modelo.
"""

import pytest
from pydantic import ValidationError

from geosgb_mcp.models import (
    Coordinates,
    OccurrenceDetails,
    OccurrenceSearchResult,
    OccurrenceSummary,
    RareEarthOccurrence,
    RareEarthSearchResult,
    SubstanceList,
)

MODELOS = [
    OccurrenceSummary,
    OccurrenceSearchResult,
    RareEarthOccurrence,
    RareEarthSearchResult,
    OccurrenceDetails,
    SubstanceList,
]


def _so_nulos(modelo, **fixos):
    """Registro magro: todo campo nulo, salvo os fixados."""
    return {nome: None for nome in modelo.model_fields} | fixos


@pytest.mark.parametrize("modelo", MODELOS, ids=[m.__name__ for m in MODELOS])
def test_nenhum_campo_tem_default(modelo):
    com_default = [n for n, f in modelo.model_fields.items() if not f.is_required()]
    assert com_default == [], f"{modelo.__name__}: campos com default {com_default}"


@pytest.mark.parametrize("modelo", MODELOS, ids=[m.__name__ for m in MODELOS])
def test_json_schema_exige_todos_os_campos(modelo):
    """O que o SDK publica como outputSchema: `required` cobre todo campo,
    inclusive os anuláveis — a chave tem de vir, mesmo com null."""
    esquema = modelo.model_json_schema()
    assert set(esquema["required"]) == set(modelo.model_fields)


def test_details_aceita_nulos_mas_nao_ausencia():
    magro = _so_nulos(OccurrenceDetails, id=99)
    detalhes = OccurrenceDetails(**magro)
    assert detalhes.coordinates is None and detalhes.substance is None

    sem_coordinates = dict(magro)
    del sem_coordinates["coordinates"]
    with pytest.raises(ValidationError, match="coordinates"):
        OccurrenceDetails(**sem_coordinates)


def test_id_nao_e_anulavel():
    with pytest.raises(ValidationError, match="id"):
        OccurrenceSummary(**_so_nulos(OccurrenceSummary))


def test_search_result_tipa_as_features():
    resultado = OccurrenceSearchResult(
        count=1, total_count=1, offset=0, features=[_so_nulos(OccurrenceSummary, id=1)]
    )
    assert isinstance(resultado.features[0], OccurrenceSummary)
    with pytest.raises(ValidationError, match="features"):
        OccurrenceSearchResult(count=1, total_count=1, offset=0, features=[{"bogus": 1}])


def test_rare_earth_result_exige_termos_de_busca():
    with pytest.raises(ValidationError, match="search_terms_used"):
        RareEarthSearchResult(count=0, total_count=0, features=[])


def test_substance_list_so_strings():
    assert SubstanceList(count=0, substances=[]).substances == []
    with pytest.raises(ValidationError, match="substances"):
        SubstanceList(count=1, substances=[None])


def test_coordinates():
    coords = Coordinates(lat=-19.9167, lon=-43.9345)
    assert (coords.lat, coords.lon) == (-19.9167, -43.9345)
    with pytest.raises(ValidationError):
        Coordinates(lat=None, lon=-43.9)

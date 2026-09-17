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
    Provenance,
    ProvenanceDataset,
    ProvenanceFieldSource,
    ProvenanceLicense,
    ProvenanceSource,
    RareEarthOccurrence,
    RareEarthSearchResult,
    SubstanceList,
)
from geosgb_mcp.provenance import build_provenance

MODELOS = [
    OccurrenceSummary,
    OccurrenceSearchResult,
    RareEarthOccurrence,
    RareEarthSearchResult,
    OccurrenceDetails,
    SubstanceList,
    Provenance,
    ProvenanceSource,
    ProvenanceDataset,
    ProvenanceLicense,
    ProvenanceFieldSource,
]

# Bloco válido para construir respostas nos testes (o gate cobre o conteúdo).
PROV = build_provenance("1=1")


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
    magro = _so_nulos(OccurrenceDetails, id=99, provenance=PROV, attribution=[])
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
        count=1, total_count=1, offset=0, features=[_so_nulos(OccurrenceSummary, id=1)],
        provenance=PROV, attribution=[],
    )
    assert isinstance(resultado.features[0], OccurrenceSummary)
    with pytest.raises(ValidationError, match="features"):
        OccurrenceSearchResult(
            count=1, total_count=1, offset=0, features=[{"bogus": 1}], provenance=PROV, attribution=[]
        )


def test_rare_earth_result_exige_termos_de_busca():
    with pytest.raises(ValidationError, match="search_terms_used"):
        RareEarthSearchResult(count=0, total_count=0, features=[], provenance=PROV, attribution=[])


def test_substance_list_so_strings():
    assert SubstanceList(count=0, substances=[], provenance=PROV, attribution=[]).substances == []
    with pytest.raises(ValidationError, match="substances"):
        SubstanceList(count=1, substances=[None], provenance=PROV, attribution=[])


def test_toda_resposta_exige_proveniencia():
    """Desde 0.4.0 os quatro modelos de saída carregam `provenance` e
    `attribution`; resposta sem o bloco não passa no próprio SDK."""
    for modelo in (OccurrenceSearchResult, RareEarthSearchResult, OccurrenceDetails, SubstanceList):
        assert modelo.model_fields["provenance"].annotation is Provenance, modelo.__name__
        assert modelo.model_fields["provenance"].is_required(), modelo.__name__
        assert modelo.model_fields["attribution"].is_required(), modelo.__name__
    with pytest.raises(ValidationError, match="provenance"):
        SubstanceList(count=0, substances=[], attribution=[])


def test_bloco_de_proveniencia_obedece_ao_contrato():
    """Ordem canônica das chaves, piso legal (license.name), instante ISO em
    UTC, URL que reproduz a consulta e determinismo fora do timestamp."""
    bloco = build_provenance("UF = 'MG'", (-47.5, -20.5, -46.0, -19.0), retrieved_at="2026-09-17T12:00:00Z")
    assert list(bloco) == [
        "contract_version", "source", "dataset", "dimension_key", "data_vintage",
        "retrieved_at", "source_url", "api_version", "license", "citation",
        "notices", "derived", "derivation_note", "served_from_cache", "field_sources",
    ]
    assert bloco["contract_version"] == "1.0"
    assert bloco["license"]["name"] and bloco["license"]["id"] is None
    assert bloco["dimension_key"] == {"where": "UF = 'MG'", "geometry": "-47.5,-20.5,-46.0,-19.0"}
    assert bloco["source_url"].startswith(
        "https://geoportal.sgb.gov.br/server/rest/services/geologia/ocorrencias/MapServer/0/query?"
    )
    assert "where=UF+%3D+%27MG%27" in bloco["source_url"]
    assert "geometry=-47.5%2C-20.5%2C-46.0%2C-19.0" in bloco["source_url"]
    assert "extraído em 2026-09-17." in bloco["citation"] and bloco["source_url"] in bloco["citation"]
    assert bloco["data_vintage"] is None and bloco["derived"] is False and bloco["field_sources"] is None
    assert Provenance(**bloco).model_dump() == bloco
    de_novo = build_provenance("UF = 'MG'", (-47.5, -20.5, -46.0, -19.0), retrieved_at="2026-09-17T12:00:00Z")
    assert de_novo == bloco
    assert build_provenance("1=1")["dimension_key"] == {"where": "1=1"}


def test_coordinates():
    coords = Coordinates(lat=-19.9167, lon=-43.9345)
    assert (coords.lat, coords.lon) == (-19.9167, -43.9345)
    with pytest.raises(ValidationError):
        Coordinates(lat=None, lon=-43.9)

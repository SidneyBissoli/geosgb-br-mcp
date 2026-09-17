"""Modelos Pydantic do contrato de saída das tools (o que o cliente MCP recebe).

Anotar o retorno da tool com um destes faz o SDK publicar `outputSchema` em
tools/list, preencher `structuredContent` em tools/call e VALIDAR a resposta
em runtime (resposta desobediente vira `isError`). Os nomes são os em inglês
que as tools já devolviam antes de existir contrato.

Regra: todo campo é obrigatório e anulável, sem default. O SDK serializa o
`structuredContent` a partir do modelo (`model_dump`) e o texto a partir do
dict cru: um default preencheria só o estruturado e os dois divergiriam —
tests/test_output_contract.py exige que sejam iguais, e tests/test_models.py
prende a regra nos próprios modelos.

Até 2026-09-17 este módulo também trazia modelos da FONTE (aliases ArcGIS em
português: `MineralOccurrence`, `GeologicalOutcrop`, `SearchResult`), que
nenhuma tool usava — as tools montam os dicts direto de `attributes`. Foram
removidos: modelo que só o teste dele usa é contrato com ninguém.
"""

from typing import Optional

from pydantic import BaseModel


class Coordinates(BaseModel):
    """Coordenadas geográficas em WGS84."""

    lat: float
    lon: float


class OccurrenceSummary(BaseModel):
    """Uma ocorrência na lista de `search_mineral_occurrences`."""

    id: int
    substance: Optional[str]
    economic_status: Optional[str]
    host_rocks: Optional[str]
    typology: Optional[str]
    province: Optional[str]
    uf: Optional[str]
    municipality: Optional[str]
    project: Optional[str]
    coordinates: Optional[Coordinates]


class OccurrenceSearchResult(BaseModel):
    """Resposta de `search_mineral_occurrences`."""

    count: int
    total_count: int
    offset: int
    features: list[OccurrenceSummary]


class RareEarthOccurrence(BaseModel):
    """Uma ocorrência na lista de `search_rare_earth_occurrences`."""

    id: int
    substance: Optional[str]
    economic_status: Optional[str]
    host_rocks: Optional[str]
    province: Optional[str]
    uf: Optional[str]
    municipality: Optional[str]
    coordinates: Optional[Coordinates]


class RareEarthSearchResult(BaseModel):
    """Resposta de `search_rare_earth_occurrences`."""

    count: int
    total_count: int
    features: list[RareEarthOccurrence]
    search_terms_used: list[str]


class OccurrenceDetails(BaseModel):
    """Resposta de `get_occurrence_details`."""

    id: int
    substance: Optional[str]
    economic_status: Optional[str]
    host_rocks: Optional[str]
    enclosing_rocks: Optional[str]
    typology: Optional[str]
    province: Optional[str]
    utilitarian_class: Optional[str]
    uf: Optional[str]
    municipality: Optional[str]
    project: Optional[str]
    sheet_code: Optional[str]
    sheet_name: Optional[str]
    positioning_method: Optional[str]
    coordinates: Optional[Coordinates]


class SubstanceList(BaseModel):
    """Resposta de `list_mineral_substances`."""

    count: int
    substances: list[str]

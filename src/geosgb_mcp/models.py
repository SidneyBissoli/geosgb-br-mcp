"""Modelos Pydantic para dados do Serviço Geológico do Brasil."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class Coordinates(BaseModel):
    """Coordenadas geográficas em WGS84."""

    lat: float
    lon: float


class MineralOccurrence(BaseModel):
    """Ocorrência mineral."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(alias="ID_OCORRENCIA")
    substance: Optional[str] = Field(None, alias="SUBSTANCIAS")
    economic_status: Optional[str] = Field(None, alias="STATUS_ECONOMICO")
    host_rocks: Optional[str] = Field(None, alias="ROCHAS_HOSPEDEIRAS")
    enclosing_rocks: Optional[str] = Field(None, alias="ROCHAS_ENCAIXANTES")
    typology: Optional[str] = Field(None, alias="TIPOLOGIA")
    province: Optional[str] = Field(None, alias="PROVINCIA")
    utilitarian_class: Optional[str] = Field(None, alias="CLASSES_UTILITARIAS")
    uf: Optional[str] = Field(None, alias="UF")
    municipality: Optional[str] = Field(None, alias="MUNICIPIO")
    project: Optional[str] = Field(None, alias="PROJETO")
    sheet_code: Optional[str] = Field(None, alias="CODIGO_FOLHA")
    sheet_name: Optional[str] = Field(None, alias="FOLHA")
    positioning_method: Optional[str] = Field(None, alias="METODO_GEOPOSICIONAMENTO")
    coordinates: Optional[Coordinates] = None


class GeologicalOutcrop(BaseModel):
    """Afloramento geológico."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(alias="ID_AFLORAMENTO")
    outcrop_type: Optional[str] = Field(None, alias="TIPO_AFLORAMENTO")
    description: Optional[str] = Field(None, alias="DESCRICAO")
    field_number: Optional[str] = Field(None, alias="NUMERO_CAMPO")
    rocks: Optional[str] = Field(None, alias="ROCHAS")
    uf: Optional[str] = Field(None, alias="UF")
    municipality: Optional[str] = Field(None, alias="MUNICIPIO")
    toponymy: Optional[str] = Field(None, alias="TOPONIMIA")
    project: Optional[str] = Field(None, alias="PROJETO")
    positioning_method: Optional[str] = Field(None, alias="METODO_GEOPOSICIONAMENTO")
    sureg: Optional[str] = Field(None, alias="SUREG")
    coordinates: Optional[Coordinates] = None


class SearchResult(BaseModel):
    """Resultado de busca paginado."""

    count: int
    total_count: int
    offset: int
    features: list


# ---------------------------------------------------------------------------
# Contrato de saída das tools (o que o cliente MCP recebe)
#
# Os modelos acima espelham a FONTE (aliases ArcGIS em português). Estes
# descrevem a RESPOSTA das tools, com os nomes em inglês que elas já devolviam
# antes de existir contrato. Anotar o retorno da tool com um destes faz o
# FastMCP publicar `outputSchema` em tools/list, preencher `structuredContent`
# em tools/call e VALIDAR a resposta em runtime (resposta desobediente vira
# `isError`).
#
# Regra: todo campo é obrigatório e anulável, sem default. O SDK serializa o
# `structuredContent` a partir do modelo (`model_dump`) e o texto a partir do
# dict cru: um default preencheria só o estruturado e os dois divergiriam —
# tests/test_output_contract.py exige que sejam iguais.
# ---------------------------------------------------------------------------


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

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

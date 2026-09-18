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


# --- Proveniência (contrato v1.0 do portfólio; montado em provenance.py) ---
# Desde 2026-09-17 (0.4.0) todo modelo de saída carrega `provenance` e
# `attribution`, obrigatórios como os demais campos. As chaves seguem a
# ordem canônica do contrato; ausência é null explícito.


class ProvenanceSource(BaseModel):
    name: str
    agency: Optional[str]
    database: Optional[str]
    endpoint: Optional[str]


class ProvenanceDataset(BaseModel):
    id: Optional[str]
    version: Optional[str]
    name: Optional[str]


class ProvenanceLicense(BaseModel):
    """Piso legal do contrato: ao menos `id` ou `name` (prende-se no gate)."""

    id: Optional[str]
    name: Optional[str]
    url: Optional[str]
    terms_url: Optional[str]
    verified_at: Optional[str]


class ProvenanceFieldSource(BaseModel):
    fields: list[str]
    source_url: str
    dataset_id: Optional[str]
    data_vintage: Optional[str]
    retrieved_at: Optional[str]


class Provenance(BaseModel):
    """Bloco canônico: de onde o dado veio, com que recorte, quando e sob que regime."""

    contract_version: str
    source: ProvenanceSource
    dataset: ProvenanceDataset
    dimension_key: Optional[dict[str, str]]
    data_vintage: Optional[str]
    retrieved_at: str
    source_url: str
    api_version: Optional[str]
    license: ProvenanceLicense
    citation: str
    notices: list[str]
    derived: bool
    derivation_note: Optional[str]
    served_from_cache: Optional[bool]
    field_sources: Optional[list[ProvenanceFieldSource]]


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
    # Até 2026-09-17 havia `typology` aqui: a camada não tem o campo
    # TIPOLOGIA (37 campos lidos na fonte), saía sempre nulo.
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
    provenance: Provenance
    # Lista canônica de `source_url` distintas (RFC attribution do MCP).
    attribution: list[str]


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
    provenance: Provenance
    # Lista canônica de `source_url` distintas (RFC attribution do MCP).
    attribution: list[str]


class OccurrenceDetails(BaseModel):
    """Resposta de `get_occurrence_details`."""

    id: int
    substance: Optional[str]
    economic_status: Optional[str]
    host_rocks: Optional[str]
    enclosing_rocks: Optional[str]
    province: Optional[str]
    utilitarian_class: Optional[str]
    uf: Optional[str]
    municipality: Optional[str]
    project: Optional[str]
    sheet_code: Optional[str]
    sheet_name: Optional[str]
    positioning_method: Optional[str]
    coordinates: Optional[Coordinates]
    provenance: Provenance
    # Lista canônica de `source_url` distintas (RFC attribution do MCP).
    attribution: list[str]


class SubstanceList(BaseModel):
    """Resposta de `list_mineral_substances`."""

    count: int
    substances: list[str]
    provenance: Provenance
    # Lista canônica de `source_url` distintas (RFC attribution do MCP).
    attribution: list[str]


class OutcropSummary(BaseModel):
    """Um afloramento na lista de `get_geological_outcrops` (desde 0.6.0).

    Campos da camada "Afloramentos geológicos" (constants.OUTCROP_FIELDS).
    `outcrop_type` é nulo em 35% da fonte (medido em 2026-09-17);
    `registered_at` é a data ISO (`YYYY-MM-DD`) convertida do epoch em
    milissegundos que a fonte grava em `DATA_CADASTRO`, ou nulo.
    """

    id: int
    toponymy: Optional[str]
    outcrop_type: Optional[str]
    rocks: Optional[str]
    uf: Optional[str]
    municipality: Optional[str]
    project: Optional[str]
    registered_at: Optional[str]
    coordinates: Optional[Coordinates]


class OutcropSearchResult(BaseModel):
    """Resposta de `get_geological_outcrops`."""

    count: int
    total_count: int
    offset: int
    features: list[OutcropSummary]
    provenance: Provenance
    # Lista canônica de `source_url` distintas (RFC attribution do MCP).
    attribution: list[str]


class LithologyUnit(BaseModel):
    """Uma unidade litoestratigráfica em `get_lithology_by_area` (desde 0.7.0).

    NÃO é um registro da fonte: é a agregação, no cliente, dos polígonos da
    camada "Unidades litoestratigráficas - 1:1.000.000 [2004]" que têm a
    mesma `SIGLA` (`code`) e intersectam o recorte (constants.LITHOLOGY_FIELDS).
    Os atributos descritivos vêm do primeiro polígono da unidade lido (são
    iguais entre polígonos da mesma sigla na fonte). `polygon_count` é
    quantos polígonos entraram; `area_deg2` é a soma de `SHAPE.AREA` desses
    polígonos INTEIROS, em graus quadrados (a fonte é WGS84), não a parte
    deles dentro do recorte — nulo quando nenhum trouxe área. `code` é nulo
    quando a fonte devolve `SIGLA` nula: esses polígonos agregam numa
    unidade sem sigla em vez de sumir, para `polygon_count` somar o total.
    Idades em milhões de anos (Ma); `system_*`/`epoch_*` são nulos em um
    terço a metade dos polígonos (medido em 2026-09-17).
    """

    code: Optional[str]
    name: Optional[str]
    hierarchy: Optional[str]
    parent_code: Optional[str]
    parent_name: Optional[str]
    lithotypes: Optional[str]
    age_min_ma: Optional[float]
    age_max_ma: Optional[float]
    eon_min: Optional[str]
    eon_max: Optional[str]
    era_min: Optional[str]
    era_max: Optional[str]
    system_min: Optional[str]
    system_max: Optional[str]
    epoch_min: Optional[str]
    epoch_max: Optional[str]
    polygon_count: int
    area_deg2: Optional[float]


class LithologySearchResult(BaseModel):
    """Resposta de `get_lithology_by_area`.

    `count`/`total_count`/`offset` contam UNIDADES (o que a lista traz);
    `polygon_count` é o total de polígonos lidos da fonte antes da agregação
    (a soma dos `polygon_count` das unidades, antes do corte de `limit`).
    `provenance.derived` é True: a resposta é derivada, não a fonte crua.
    """

    count: int
    total_count: int
    offset: int
    polygon_count: int
    units: list[LithologyUnit]
    provenance: Provenance
    # Lista canônica de `source_url` distintas (RFC attribution do MCP).
    attribution: list[str]

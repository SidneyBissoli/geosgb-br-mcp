"""Bloco de proveniência — contrato v1.0 do portfólio, escrito à mão.

A lib do portfólio (`@sbissoli/mcp-provenance`, em mcp-br-commons) é
TypeScript; este servidor é Python, então o mesmo bloco canônico é montado
aqui: chaves em ordem fixa, ausência como `null`, instante em UTC sem
milissegundos. A mesma consulta produz bloco idêntico exceto por
`retrieved_at` e pela data embutida em `citation`.

O que o geoportal declara (medido em 2026-09-17 por `?f=pjson`): serviço
`geologia/ocorrencias/MapServer`, `copyrightText` "Serviço Geológico do
Brasil - SGB - CPRM", `currentVersion` 11.3, sem `lastEditDate` (por isso
`data_vintage` é null: a fonte não expõe). Camada 0: "Ocorrências minerais".
Nenhuma licença declarada — nem no serviço, nem em geoportal.sgb.gov.br;
sgb.gov.br/dados-abertos diz que o SGB não possui Plano de Dados Abertos por
estar fora do escopo do Decreto nº 8.777/2016. O contrato exige ao menos
`license.name`: vai o que a fonte de fato diz (o copyrightText), sem inventar
regime.
"""

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from .constants import BASE_URL, ENDPOINTS

CONTRACT_VERSION = "1.0"

LAYER_URL = f"{BASE_URL}{ENDPOINTS['ocorrencias']}"

SOURCE = {
    "name": "Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB",
    "agency": "Serviço Geológico do Brasil (SGB/CPRM)",
    "database": "GeoSGB",
    "endpoint": LAYER_URL,
}

DATASET = {"id": "ocorrencias", "version": None, "name": "Ocorrências minerais"}

API_VERSION = "ArcGIS REST 11.3"

LICENSE = {
    "id": None,
    "name": "Serviço Geológico do Brasil - SGB - CPRM (copyrightText do serviço; "
    "a fonte não declara licença de uso)",
    "url": None,
    "terms_url": None,
    "verified_at": "2026-09-17",
}

NOTICES = [
    "A fonte não declara licença de uso: o serviço publica apenas o copyrightText "
    '"Serviço Geológico do Brasil - SGB - CPRM". O SGB informa em '
    "sgb.gov.br/dados-abertos (lido em 2026-09-17) não possuir Plano de Dados "
    "Abertos por estar fora do escopo do Decreto nº 8.777/2016.",
]

ATTRIBUTION = "Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB"


def now_utc_iso() -> str:
    """Instante em UTC, ISO-8601 sem milissegundos (`2026-09-17T18:04:05Z`)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def query_url(where: str, geometry: tuple[float, float, float, float] | None = None) -> str:
    """URL canônica que reproduz a consulta: o `/query` da camada com a WHERE
    efetiva e o envelope, quando houver, em `f=json`. Só o que muda o
    RESULTADO entra; `outFields`/`returnGeometry` são forma, não recorte."""
    params: dict[str, Any] = {"where": where, "f": "json"}
    if geometry:
        xmin, ymin, xmax, ymax = geometry
        params["geometry"] = f"{xmin},{ymin},{xmax},{ymax}"
        params["geometryType"] = "esriGeometryEnvelope"
        params["spatialRel"] = "esriSpatialRelIntersects"
        params["inSR"] = "4326"
    return f"{LAYER_URL}/query?{urlencode(params)}"


def build_provenance(
    where: str,
    geometry: tuple[float, float, float, float] | None = None,
    retrieved_at: str | None = None,
    served_from_cache: bool = False,
) -> dict[str, Any]:
    """Bloco canônico para UMA ida à camada de ocorrências.

    `where` é a cláusula EFETIVA que foi ao portal; `geometry` o envelope, se
    houve; `retrieved_at` o instante real da extração (default: agora — as
    buscas chamam logo após a resposta do portal). `served_from_cache` é True
    só quando a resposta saiu do cache em processo (desde 2026-09-17, apenas
    `list_mineral_substances`), e então `retrieved_at` é o instante da ida
    ORIGINAL ao portal, não o de agora — é o que o contrato manda. A ordem
    das chaves é a do contrato e é parte dele.
    """
    retrieved = retrieved_at or now_utc_iso()
    source_url = query_url(where, geometry)
    dimension_key: dict[str, str] = {"where": where}
    if geometry:
        xmin, ymin, xmax, ymax = geometry
        dimension_key["geometry"] = f"{xmin},{ymin},{xmax},{ymax}"
    return {
        "contract_version": CONTRACT_VERSION,
        "source": dict(SOURCE),
        "dataset": dict(DATASET),
        "dimension_key": dimension_key,
        "data_vintage": None,
        "retrieved_at": retrieved,
        "source_url": source_url,
        "api_version": API_VERSION,
        "license": dict(LICENSE),
        "citation": (
            f"Fonte: {ATTRIBUTION}, camada Ocorrências minerais, {source_url}, "
            f"extraído em {retrieved[:10]}."
        ),
        "notices": list(NOTICES),
        "derived": False,
        "derivation_note": None,
        "served_from_cache": served_from_cache,
        "field_sources": None,
    }

"""Bloco de proveniência — contrato v1.0 do portfólio, escrito à mão.

A lib do portfólio (`@sbissoli/mcp-provenance`, em mcp-br-commons) é
TypeScript; este servidor é Python, então o mesmo bloco canônico é montado
aqui: chaves em ordem fixa, ausência como `null`, instante em UTC sem
milissegundos. A mesma consulta produz bloco idêntico exceto por
`retrieved_at` e pela data embutida em `citation`.

O bloco é POR CAMADA: `build_provenance(endpoint_key, …)` lê de
`constants.LAYERS` o endpoint, o nome da camada e o `copyrightText` do
serviço — e recusa chave que não esteja lá. Até 2026-09-17 (Sessão 3,
pré-requisito) `LAYER_URL`, `SOURCE.endpoint`, `DATASET` e a `citation`
eram constantes fixas de `ocorrencias`, e a primeira tool sobre outra camada
citaria a camada errada; o bloco de ocorrências continua byte a byte igual
(tests/test_models.py prende o bloco inteiro).

O que o geoportal declara (medido em 2026-09-17 por `?f=pjson`, por
serviço): `currentVersion` 11.3, sem `lastEditDate` (por isso `data_vintage`
é null: a fonte não expõe). Nenhuma licença declarada — nem nos serviços,
nem em geoportal.sgb.gov.br; sgb.gov.br/dados-abertos diz que o SGB não
possui Plano de Dados Abertos por estar fora do escopo do Decreto nº
8.777/2016. O contrato exige ao menos `license.name`: vai o que a fonte de
fato diz (o copyrightText do serviço da camada), sem inventar regime.
"""

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from .constants import BASE_URL, LAYERS, Layer

CONTRACT_VERSION = "1.0"

SOURCE_NAME = "Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB"
AGENCY = "Serviço Geológico do Brasil (SGB/CPRM)"
DATABASE = "GeoSGB"

API_VERSION = "ArcGIS REST 11.3"

# Data em que sgb.gov.br/dados-abertos foi lido (é do SGB, não da camada).
OPEN_DATA_NOTICE_VERIFIED_AT = "2026-09-17"

ATTRIBUTION = SOURCE_NAME


def now_utc_iso() -> str:
    """Instante em UTC, ISO-8601 sem milissegundos (`2026-09-17T18:04:05Z`)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def layer(endpoint_key: str) -> Layer:
    """A camada servida registrada sob `endpoint_key` — ou erro de programação:
    tool nova sobre camada que não está em `constants.LAYERS` não tem como
    dizer de onde veio."""
    try:
        return LAYERS[endpoint_key]
    except KeyError:
        raise ValueError(
            f"camada {endpoint_key!r} não está em constants.LAYERS "
            f"(servidas: {', '.join(sorted(LAYERS))}) — registre-a antes de servi-la"
        ) from None


def layer_url(endpoint_key: str) -> str:
    """URL da camada (sem `/query`), como `source.endpoint` a publica."""
    return f"{BASE_URL}{layer(endpoint_key).path}"


def query_url(
    endpoint_key: str,
    where: str,
    geometry: tuple[float, float, float, float] | None = None,
) -> str:
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
    return f"{layer_url(endpoint_key)}/query?{urlencode(params)}"


def build_provenance(
    endpoint_key: str,
    where: str,
    geometry: tuple[float, float, float, float] | None = None,
    retrieved_at: str | None = None,
    served_from_cache: bool = False,
) -> dict[str, Any]:
    """Bloco canônico para UMA ida à camada `endpoint_key` (de `constants.LAYERS`).

    `where` é a cláusula EFETIVA que foi ao portal; `geometry` o envelope, se
    houve; `retrieved_at` o instante real da extração (default: agora — as
    buscas chamam logo após a resposta do portal). `served_from_cache` é True
    só quando a resposta saiu do cache em processo (desde 2026-09-17, apenas
    `list_mineral_substances`), e então `retrieved_at` é o instante da ida
    ORIGINAL ao portal, não o de agora — é o que o contrato manda. A ordem
    das chaves é a do contrato e é parte dele.
    """
    camada = layer(endpoint_key)
    retrieved = retrieved_at or now_utc_iso()
    source_url = query_url(endpoint_key, where, geometry)
    dimension_key: dict[str, str] = {"where": where}
    if geometry:
        xmin, ymin, xmax, ymax = geometry
        dimension_key["geometry"] = f"{xmin},{ymin},{xmax},{ymax}"
    return {
        "contract_version": CONTRACT_VERSION,
        "source": {
            "name": SOURCE_NAME,
            "agency": AGENCY,
            "database": DATABASE,
            "endpoint": layer_url(endpoint_key),
        },
        "dataset": {"id": endpoint_key, "version": None, "name": camada.name},
        "dimension_key": dimension_key,
        "data_vintage": None,
        "retrieved_at": retrieved,
        "source_url": source_url,
        "api_version": API_VERSION,
        "license": {
            "id": None,
            "name": (
                f"{camada.copyright_text} (copyrightText do serviço; "
                "a fonte não declara licença de uso)"
            ),
            "url": None,
            "terms_url": None,
            "verified_at": camada.verified_at,
        },
        "citation": (
            f"Fonte: {ATTRIBUTION}, camada {camada.name}, {source_url}, "
            f"extraído em {retrieved[:10]}."
        ),
        "notices": [
            "A fonte não declara licença de uso: o serviço publica apenas o "
            f'copyrightText "{camada.copyright_text}". O SGB informa em '
            f"sgb.gov.br/dados-abertos (lido em {OPEN_DATA_NOTICE_VERIFIED_AT}) não "
            "possuir Plano de Dados Abertos por estar fora do escopo do Decreto "
            "nº 8.777/2016.",
        ],
        "derived": False,
        "derivation_note": None,
        "served_from_cache": served_from_cache,
        "field_sources": None,
    }

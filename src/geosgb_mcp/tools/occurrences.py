"""Tools para busca de ocorrências minerais.

Custo da fonte (Sessão 2 do roadmap, 2026-09-17): o geoportal não pagina —
toda query traz TUDO que casa com a WHERE. Por isso (a) as buscas pedem só
os campos que devolvem (`outFields` explícito, constants.OCCURRENCE_FIELDS),
(b) não há requisição de contagem antes da query (`count == len(features)`,
medido em 4 de 4 WHERE na Sessão 1) e (c) a lista de substâncias, que só
existe baixando a camada inteira, fica num cache em processo com TTL.
"""

import asyncio
import time

from ..client import GeoSGBClient
from ..constants import (
    OCCURRENCE_FIELDS,
    RARE_EARTH_FIELDS,
    REE_HOST_ROCKS,
    REE_SEARCH_TERMS,
    SUBSTANCES_CACHE_TTL,
)
from ..provenance import build_provenance, now_utc_iso


async def search_mineral_occurrences(
    substance: str | None = None,
    uf: str | None = None,
    municipality: str | None = None,
    economic_status: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 100,
    offset: int = 0,
    include_geometry: bool = True,
) -> dict:
    """
    Busca ocorrências minerais no banco de dados do SGB.

    Args:
        substance: Substância mineral (ex: "Terras raras", "Ouro", "Lítio")
        uf: Sigla do estado (ex: "MG", "GO", "BA")
        municipality: Nome do município
        economic_status: Status econômico ("Mina", "Garimpo", "Indeterminado",
            "Não explotado" — os valores da fonte em 2026-09-17)
        bbox: Bounding box (xmin, ymin, xmax, ymax) em WGS84, já validado
            pela borda (server.py)
        limit: Máximo de resultados (default: 100)
        offset: Offset para paginação (aplicado no cliente)
        include_geometry: Incluir coordenadas na resposta

    Returns:
        Dicionário com count, total_count e lista de ocorrências
    """
    conditions = []

    if substance:
        substance_escaped = substance.replace("'", "''")
        conditions.append(f"SUBSTANCIAS LIKE '%{substance_escaped}%'")

    if uf:
        conditions.append(f"UF = '{uf.upper()}'")

    if municipality:
        municipality_escaped = municipality.replace("'", "''")
        conditions.append(f"MUNICIPIO LIKE '%{municipality_escaped}%'")

    if economic_status:
        status_escaped = economic_status.replace("'", "''")
        conditions.append(f"STATUS_ECONOMICO = '{status_escaped}'")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    client = GeoSGBClient()

    try:
        # Uma ida só: até 2026-09-17 havia um `returnCountOnly` antes desta
        # query, e a fonte, que não pagina, devolvia na query o mesmo total.
        result = await client.query(
            endpoint_key="ocorrencias",
            where=where_clause,
            out_fields=",".join(OCCURRENCE_FIELDS),
            return_geometry=include_geometry,
            geometry=bbox,
        )
        # Instante real da extração: logo após a resposta do portal.
        provenance = build_provenance(where_clause, bbox)

        features = result.get("features", [])
        total_count = len(features)

        # Aplicar offset e limit no cliente (API não suporta paginação)
        features = features[offset : offset + limit]

        occurrences = []
        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            occurrence = {
                "id": attrs.get("ID_OCORRENCIA"),
                "substance": attrs.get("SUBSTANCIAS"),
                "economic_status": attrs.get("STATUS_ECONOMICO"),
                "host_rocks": attrs.get("ROCHAS_HOSPEDEIRAS"),
                "province": attrs.get("PROVINCIA"),
                "uf": attrs.get("UF"),
                "municipality": attrs.get("MUNICIPIO"),
                "project": attrs.get("PROJETO"),
                # Chave sempre presente (None sem geometria): o contrato de
                # saída (models.OccurrenceSummary) a declara obrigatória e
                # anulável, como as outras duas buscas já faziam.
                "coordinates": {"lon": geom.get("x"), "lat": geom.get("y")}
                if include_geometry and geom
                else None,
            }

            occurrences.append(occurrence)

        return {
            "count": len(occurrences),
            "total_count": total_count,
            "offset": offset,
            "features": occurrences,
            "provenance": provenance,
            "attribution": [provenance["source_url"]],
        }

    finally:
        await client.close()


async def search_rare_earth_occurrences(
    uf: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    include_related_rocks: bool = False,
    limit: int = 100,
) -> dict:
    """
    Busca específica para ocorrências de Elementos Terras Raras (ETRs).

    Args:
        uf: Sigla do estado
        bbox: Bounding box, já validado pela borda (server.py)
        include_related_rocks: Se True, inclui ocorrências em rochas
            hospedeiras típicas de ETRs (constants.REE_HOST_ROCKS). Default
            False desde 2026-09-17: com True, 96% do resultado são pegmatitos
            (2.383 registros contra 74 só por substância).
        limit: Máximo de resultados

    Returns:
        Dicionário com ocorrências de ETRs
    """
    # Uma fonte só para os termos (constants.py, com a medição). Até 2026-09-17
    # havia aqui uma lista própria de 5 + 2, "reduzida para evitar queries
    # muito longas" — a WHERE completa responde em 5,5 s.
    ree_terms = REE_SEARCH_TERMS
    host_rocks = REE_HOST_ROCKS

    substance_conditions = [f"SUBSTANCIAS LIKE '%{term}%'" for term in ree_terms]

    if include_related_rocks:
        rock_conditions = [
            f"ROCHAS_HOSPEDEIRAS LIKE '%{rock}%'" for rock in host_rocks
        ]
        all_conditions = substance_conditions + rock_conditions
    else:
        all_conditions = substance_conditions

    where_clause = "(" + " OR ".join(all_conditions) + ")"

    if uf:
        where_clause = f"{where_clause} AND UF = '{uf.upper()}'"

    client = GeoSGBClient()

    try:
        result = await client.query(
            endpoint_key="ocorrencias",
            where=where_clause,
            out_fields=",".join(RARE_EARTH_FIELDS),
            geometry=bbox,
        )
        provenance = build_provenance(where_clause, bbox)

        features = result.get("features", [])
        total_count = len(features)

        # Aplicar limit no cliente
        features = features[:limit]

        occurrences = []
        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            occurrences.append(
                {
                    "id": attrs.get("ID_OCORRENCIA"),
                    "substance": attrs.get("SUBSTANCIAS"),
                    "economic_status": attrs.get("STATUS_ECONOMICO"),
                    "host_rocks": attrs.get("ROCHAS_HOSPEDEIRAS"),
                    "province": attrs.get("PROVINCIA"),
                    "uf": attrs.get("UF"),
                    "municipality": attrs.get("MUNICIPIO"),
                    "coordinates": {"lon": geom.get("x"), "lat": geom.get("y")}
                    if geom
                    else None,
                }
            )

        return {
            "count": len(occurrences),
            "total_count": total_count,
            "features": occurrences,
            # Fica ao lado do bloco de proveniência, não dentro dele: é a
            # lista legível dos termos; `provenance.dimension_key.where` é a
            # WHERE reproduzível que os contém (decisão de 2026-09-17).
            "search_terms_used": ree_terms + (host_rocks if include_related_rocks else []),
            "provenance": provenance,
            "attribution": [provenance["source_url"]],
        }

    finally:
        await client.close()


async def get_occurrence_details(occurrence_id: int) -> dict:
    """
    Obtém detalhes completos de uma ocorrência mineral específica pelo ID.

    Args:
        occurrence_id: ID da ocorrência mineral

    Returns:
        Detalhes completos da ocorrência

    Raises:
        LookupError: se não existe ocorrência com esse ID. Até 2026-09 a
            função devolvia `{"error": ...}` com status de sucesso; com o
            contrato de saída (models.OccurrenceDetails) esse dict seria
            reprovado pelo próprio SDK, então o erro é levantado — server.py
            o converte em `ToolError`, que chega ao cliente como `isError`
            com a mensagem (SDK 2.x: só `ToolError` preserva o texto).
    """
    client = GeoSGBClient()

    try:
        where_clause = f"ID_OCORRENCIA = {occurrence_id}"
        result = await client.query(
            endpoint_key="ocorrencias",
            where=where_clause,
            out_fields="*",
            return_geometry=True,
        )
        provenance = build_provenance(where_clause)

        features = result.get("features", [])
        if not features:
            raise LookupError(f"Ocorrência {occurrence_id} não encontrada")

        feature = features[0]
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry", {})

        return {
            "id": attrs.get("ID_OCORRENCIA"),
            "substance": attrs.get("SUBSTANCIAS"),
            "economic_status": attrs.get("STATUS_ECONOMICO"),
            "host_rocks": attrs.get("ROCHAS_HOSPEDEIRAS"),
            "enclosing_rocks": attrs.get("ROCHAS_ENCAIXANTES"),
            "province": attrs.get("PROVINCIA"),
            "utilitarian_class": attrs.get("CLASSES_UTILITARIAS"),
            "uf": attrs.get("UF"),
            "municipality": attrs.get("MUNICIPIO"),
            "project": attrs.get("PROJETO"),
            "sheet_code": attrs.get("CODIGO_FOLHA"),
            "sheet_name": attrs.get("FOLHA"),
            "positioning_method": attrs.get("METODO_GEOPOSICIONAMENTO"),
            "coordinates": {"lon": geom.get("x"), "lat": geom.get("y")}
            if geom
            else None,
            "provenance": provenance,
            "attribution": [provenance["source_url"]],
        }

    finally:
        await client.close()


class SubstancesCache:
    """Cache em processo da lista de substâncias (uma entrada, com validade).

    Guarda a lista deduplicada e o instante da ida ao portal que a produziu:
    a resposta servida do cache repete esse `retrieved_at` e marca
    `served_from_cache=True` no bloco de proveniência. `clock` é injetável
    (o gate vence o TTL sem esperar um dia).
    """

    def __init__(self, ttl: float):
        self.ttl = ttl
        self.clock = time.monotonic
        self.substances: list[str] | None = None
        self.retrieved_at: str | None = None
        self._expires_at = 0.0
        self.lock = asyncio.Lock()

    def valid(self) -> bool:
        return self.substances is not None and self.clock() < self._expires_at

    def store(self, substances: list[str], retrieved_at: str) -> None:
        self.substances = substances
        self.retrieved_at = retrieved_at
        self._expires_at = self.clock() + self.ttl

    def clear(self) -> None:
        self.substances = None
        self.retrieved_at = None
        self._expires_at = 0.0


_substances_cache = SubstancesCache(SUBSTANCES_CACHE_TTL)


async def _fetch_substances() -> tuple[list[str], str]:
    """Baixa a camada inteira (só SUBSTANCIAS, sem geometria) e deduplica."""
    client = GeoSGBClient()
    try:
        result = await client.query(
            endpoint_key="ocorrencias",
            where="1=1",
            out_fields="SUBSTANCIAS",
            return_geometry=False,
        )
        retrieved_at = now_utc_iso()
    finally:
        await client.close()

    substances: set[str] = set()
    for feature in result.get("features", []):
        subst = feature.get("attributes", {}).get("SUBSTANCIAS")
        if subst:
            for s in subst.split(","):
                if s.strip():
                    substances.add(s.strip())
    return sorted(substances), retrieved_at


async def list_mineral_substances() -> dict:
    """
    Lista todas as substâncias minerais cadastradas no banco de dados do SGB.

    A primeira chamada do processo baixa a camada inteira (~20 s em
    2026-09-17); as seguintes, dentro de constants.SUBSTANCES_CACHE_TTL,
    saem do cache em processo (< 50 ms) com `served_from_cache=True` e o
    `retrieved_at` da ida original. O lock evita duas chamadas simultâneas
    pagarem os 20 s em dobro.

    Returns:
        Lista de substâncias minerais únicas
    """
    cache = _substances_cache
    async with cache.lock:
        served_from_cache = cache.valid()
        if not served_from_cache:
            substances, retrieved_at = await _fetch_substances()
            cache.store(substances, retrieved_at)

    provenance = build_provenance(
        "1=1", retrieved_at=cache.retrieved_at, served_from_cache=served_from_cache
    )
    return {
        "count": len(cache.substances),
        "substances": list(cache.substances),
        "provenance": provenance,
        "attribution": [provenance["source_url"]],
    }

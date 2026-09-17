"""Tools para busca de ocorrências minerais."""

from ..client import GeoSGBClient
from ..constants import REE_HOST_ROCKS, REE_SEARCH_TERMS


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
        economic_status: Status econômico ("Mina", "Garimpo", "Ocorrência")
        bbox: Bounding box (xmin, ymin, xmax, ymax) em WGS84
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
        total_count = await client.get_count("ocorrencias", where_clause)

        result = await client.query(
            endpoint_key="ocorrencias",
            where=where_clause,
            return_geometry=include_geometry,
            geometry=bbox,
        )

        features = result.get("features", [])

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
                "typology": attrs.get("TIPOLOGIA"),
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
        }

    finally:
        await client.close()


async def search_rare_earth_occurrences(
    uf: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    include_related_rocks: bool = True,
    limit: int = 100,
) -> dict:
    """
    Busca específica para ocorrências de Elementos Terras Raras (ETRs).

    Args:
        uf: Sigla do estado
        bbox: Bounding box
        include_related_rocks: Se True, inclui ocorrências em rochas
                               típicas de ETRs (carbonatitos, alcalinas)
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
        total_count = await client.get_count("ocorrencias", where_clause)

        result = await client.query(
            endpoint_key="ocorrencias",
            where=where_clause,
            geometry=bbox,
        )

        features = result.get("features", [])

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
            "search_terms_used": ree_terms + (host_rocks if include_related_rocks else []),
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
        result = await client.query(
            endpoint_key="ocorrencias",
            where=f"ID_OCORRENCIA = {occurrence_id}",
            out_fields="*",
            return_geometry=True,
        )

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
            "typology": attrs.get("TIPOLOGIA"),
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
        }

    finally:
        await client.close()


async def list_mineral_substances() -> dict:
    """
    Lista todas as substâncias minerais cadastradas no banco de dados do SGB.

    Returns:
        Lista de substâncias minerais únicas
    """
    client = GeoSGBClient()

    try:
        result = await client.query(
            endpoint_key="ocorrencias",
            where="1=1",
            out_fields="SUBSTANCIAS",
            return_geometry=False,
        )

        substances = set()
        for feature in result.get("features", []):
            subst = feature.get("attributes", {}).get("SUBSTANCIAS")
            if subst:
                for s in subst.split(","):
                    substances.add(s.strip())

        return {"count": len(substances), "substances": sorted(list(substances))}

    finally:
        await client.close()

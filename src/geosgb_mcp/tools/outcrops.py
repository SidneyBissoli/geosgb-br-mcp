"""Tool de afloramentos geológicos (camada "Afloramentos geológicos").

Entrou em 0.6.0 (Sessão 3 do roadmap, 2026-09-17), depois da decisão por
camada medida ao vivo: 360.042 pontos em 3.540 municípios, fonte sem
paginação que só corta sem filtro nenhum (`maxRecordCount` 300.000). Por
isso o filtro é OBRIGATÓRIO e é a borda (server.py) que o impõe: UF +
município, ou bbox de até constants.OUTCROP_BBOX_MAX_DEG2 graus quadrados.

Município é IGUALDADE, com a grafia da fonte (acento incluído): `LIKE`
pegaria vizinhos por substring — Santa Bárbara/MG são 1.333 pontos por
igualdade e 1.571 por `LIKE` (medido em 2026-09-17); "Santa Barbara" sem
acento é zero — a descrição da tool e as `instructions` do servidor avisam.
Uma ida só, com `outFields` explícito (constants.OUTCROP_FIELDS): a fonte
não pagina, então `total_count == len(features)` e o corte é no cliente.
"""

from datetime import datetime, timezone

from ..client import GeoSGBClient
from ..constants import OUTCROP_FIELDS
from ..provenance import build_provenance


def registered_at_iso(epoch_ms: int | float | None) -> str | None:
    """`DATA_CADASTRO` vem em milissegundos de epoch (ArcGIS esriFieldTypeDate):
    867369600000 → "1997-06-27". Nulo fica nulo."""
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).date().isoformat()


async def search_geological_outcrops(
    uf: str | None = None,
    municipality: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    Busca afloramentos geológicos no geoportal do SGB.

    Args:
        uf: Sigla do estado (ex: "MG"), já validada pela borda
        municipality: Nome do município, exatamente como a fonte grava
            (igualdade, sensível a caixa e acento)
        bbox: Bounding box (xmin, ymin, xmax, ymax) em WGS84, já validado
            pela borda (server.py), inclusive o teto de área
        limit: Máximo de resultados (default: 100)
        offset: Offset para paginação (aplicado no cliente)

    Returns:
        Dicionário com count, total_count, offset e lista de afloramentos
    """
    conditions = []

    if uf:
        conditions.append(f"UF = '{uf.upper()}'")

    if municipality:
        municipality_escaped = municipality.replace("'", "''")
        conditions.append(f"MUNICIPIO = '{municipality_escaped}'")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    client = GeoSGBClient()

    try:
        # Uma ida só: `returnCountOnly` com geometria responde 400 nesta
        # camada (medido em 2026-09-17) e a query já traz o total.
        result = await client.query(
            endpoint_key="afloramentos",
            where=where_clause,
            out_fields=",".join(OUTCROP_FIELDS),
            return_geometry=True,
            geometry=bbox,
        )
        # Instante real da extração: logo após a resposta do portal.
        provenance = build_provenance("afloramentos", where_clause, bbox)

        features = result.get("features", [])
        total_count = len(features)

        # Aplicar offset e limit no cliente (API não suporta paginação)
        features = features[offset : offset + limit]

        outcrops = []
        for feature in features:
            attrs = feature.get("attributes", {})
            geom = feature.get("geometry", {})

            outcrops.append(
                {
                    "id": attrs.get("ID_AFLORAMENTO"),
                    "toponymy": attrs.get("TOPONIMIA"),
                    "outcrop_type": attrs.get("TIPO_AFLORAMENTO"),
                    "rocks": attrs.get("ROCHAS"),
                    "uf": attrs.get("UF"),
                    "municipality": attrs.get("MUNICIPIO"),
                    "project": attrs.get("PROJETO"),
                    "registered_at": registered_at_iso(attrs.get("DATA_CADASTRO")),
                    # Chave sempre presente (None sem geometria): o contrato
                    # de saída (models.OutcropSummary) a declara obrigatória
                    # e anulável.
                    "coordinates": {"lon": geom.get("x"), "lat": geom.get("y")}
                    if geom
                    else None,
                }
            )

        return {
            "count": len(outcrops),
            "total_count": total_count,
            "offset": offset,
            "features": outcrops,
            "provenance": provenance,
            "attribution": [provenance["source_url"]],
        }

    finally:
        await client.close()

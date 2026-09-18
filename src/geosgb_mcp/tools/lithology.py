"""Tool de litoestratigrafia (camada "Unidades litoestratigráficas - 1:1.000.000 [2004]").

Entrou em 0.7.0 (Sessão 3 do roadmap, 2026-09-17), depois da decisão por
camada medida ao vivo: 46.712 polígonos, `maxRecordCount` 100.000 (nenhum
recorte corta), geometria pesada — COM geometria um bbox de 1°×1° vem em
6,4 MB; sem, em 0,15 MB (35×). Por isso `returnGeometry=false` SEMPRE e o
recorte espacial é OBRIGATÓRIO e é a borda (server.py) que o impõe: bbox de
até constants.LITHOLOGY_BBOX_MAX_DEG2 graus quadrados, ou um ponto (lon,
lat) — "que unidade está sob este ponto" (1 polígono em 0,1 s; ponto no mar
é lista vazia, não erro).

A resposta é DERIVADA: a fonte devolve polígonos e a tool agrega, no
cliente, por `SIGLA` (a unidade) — nº de polígonos e soma de `SHAPE.AREA`.
Agregar na fonte não dá: `groupBy SIGLA` com bbox responde certo, mas em
140 s; `returnDistinctValues` com bbox responde 400 (medido em 2026-09-17).
`SHAPE.AREA` está em graus quadrados (a fonte é WGS84) e é a área do
polígono INTEIRO que intersecta o recorte, não a parte dentro dele — a
resposta chama o campo de `area_deg2` e o bloco de proveniência sai com
`derived: true` e a nota dizendo isso. Uma ida só, `outFields` explícito
(constants.LITHOLOGY_FIELDS); `total_count` conta unidades e o corte de
`limit`/`offset` é no cliente, sobre a lista ordenada por área.
"""

from ..client import GeoSGBClient
from ..constants import LITHOLOGY_FIELDS
from ..provenance import build_provenance

# Campo da fonte -> campo da resposta, para os atributos descritivos da
# unidade (iguais entre polígonos da mesma SIGLA; a agregação lê do primeiro).
_UNIT_ATTRIBUTES = (
    ("NOME", "name"),
    ("HIERARQUIA", "hierarchy"),
    ("SIGLA_PAI", "parent_code"),
    ("NOME_PAI", "parent_name"),
    ("LITOTIPOS", "lithotypes"),
    ("IDADE_MIN", "age_min_ma"),
    ("IDADE_MAX", "age_max_ma"),
    ("EON_MIN", "eon_min"),
    ("EON_MAX", "eon_max"),
    ("ERA_MIN", "era_min"),
    ("ERA_MAX", "era_max"),
    ("SISTEMA_MIN", "system_min"),
    ("SISTEMA_MAX", "system_max"),
    ("EPOCA_MIN", "epoch_min"),
    ("EPOCA_MAX", "epoch_max"),
)


def aggregate_units(features: list[dict]) -> list[dict]:
    """Agrega os polígonos da fonte em unidades, por `SIGLA`, ordenadas por
    `area_deg2` decrescente (unidade sem área nenhuma vai ao fim; empate
    desempata pela sigla, para a ordem ser determinística).

    `polygon_count` é quantos polígonos entraram; `area_deg2` é a soma de
    `SHAPE.AREA` dos que trouxeram área, ou nulo se nenhum trouxe. Polígono
    com `SIGLA` nula NÃO some: agrega numa unidade de `code` nulo — assim a
    soma dos `polygon_count` é sempre o total lido da fonte.
    """
    unidades: dict[str | None, dict] = {}
    for feature in features:
        attrs = feature.get("attributes", {})
        code = attrs.get("SIGLA")
        unidade = unidades.get(code)
        if unidade is None:
            unidade = {"code": code}
            for campo_fonte, campo_resposta in _UNIT_ATTRIBUTES:
                unidade[campo_resposta] = attrs.get(campo_fonte)
            unidade["polygon_count"] = 0
            unidade["area_deg2"] = None
            unidades[code] = unidade
        unidade["polygon_count"] += 1
        area = attrs.get("SHAPE.AREA")
        if area is not None:
            unidade["area_deg2"] = (unidade["area_deg2"] or 0.0) + area

    return sorted(
        unidades.values(),
        key=lambda u: (
            u["area_deg2"] is None,
            -(u["area_deg2"] or 0.0),
            u["code"] is None,
            u["code"] or "",
        ),
    )


def derivation_note(polygon_count: int, unit_count: int) -> str:
    """O que a resposta É, para `provenance.derivation_note`."""
    return (
        f"Agregação no cliente: {polygon_count} polígonos da fonte agrupados por "
        f"SIGLA em {unit_count} unidades (polygon_count e area_deg2 por unidade). "
        "area_deg2 é a soma de SHAPE.AREA dos polígonos INTEIROS que intersectam "
        "o recorte, em graus quadrados (fonte em WGS84) — não a área dentro do "
        "recorte. Sem geometria: a fonte foi consultada com returnGeometry=false."
    )


async def search_lithology_by_area(
    bbox: tuple[float, float, float, float] | None = None,
    point: tuple[float, float] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    Lista as unidades litoestratigráficas (mapa 1:1.000.000 de 2004) que
    intersectam um recorte do geoportal do SGB.

    Args:
        bbox: Bounding box (xmin, ymin, xmax, ymax) em WGS84, já validado
            pela borda (server.py), inclusive o teto de área
        point: Ponto (lon, lat) em WGS84, já validado pela borda. Um dos
            dois é obrigatório e a borda garante que não vêm juntos.
        limit: Máximo de unidades na resposta (default: 100)
        offset: Offset em unidades, para paginação (aplicado no cliente)

    Returns:
        Dicionário com count, total_count, offset, polygon_count e a lista
        de unidades agregadas
    """
    where_clause = "1=1"

    client = GeoSGBClient()

    try:
        # Uma ida só, SEM geometria (35× menor) — a agregação é no cliente.
        result = await client.query(
            endpoint_key="litoestratigrafia_1m",
            where=where_clause,
            out_fields=",".join(LITHOLOGY_FIELDS),
            return_geometry=False,
            geometry=bbox,
            point=point,
        )

        features = result.get("features", [])
        units = aggregate_units(features)
        polygon_count = len(features)
        total_count = len(units)

        # Instante real da extração: logo após a resposta do portal.
        provenance = build_provenance(
            "litoestratigrafia_1m",
            where_clause,
            bbox,
            point=point,
            derived=True,
            derivation_note=derivation_note(polygon_count, total_count),
        )

        # Aplicar offset e limit no cliente (API não suporta paginação)
        units = units[offset : offset + limit]

        return {
            "count": len(units),
            "total_count": total_count,
            "offset": offset,
            "polygon_count": polygon_count,
            "units": units,
            "provenance": provenance,
            "attribution": [provenance["source_url"]],
        }

    finally:
        await client.close()

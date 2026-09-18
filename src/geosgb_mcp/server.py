"""
MCP Server para dados geológicos do Serviço Geológico do Brasil (SGB).

Este servidor expõe tools para consultar:
- Ocorrências minerais
- Busca específica de Elementos Terras Raras (ETRs)
- Detalhes de ocorrências
- Lista de substâncias minerais
- Afloramentos geológicos (desde 0.6.0)
- Unidades litoestratigráficas do mapa 1:1.000.000, por recorte ou ponto,
  agregadas por unidade (desde 0.7.0)
"""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .constants import (
    DEFAULT_LIMIT,
    LITHOLOGY_BBOX_MAX_DEG2,
    MAX_LIMIT,
    OUTCROP_BBOX_MAX_DEG2,
    UF,
)
from .models import (
    LithologySearchResult,
    OccurrenceDetails,
    OccurrenceSearchResult,
    OutcropSearchResult,
    RareEarthSearchResult,
    SubstanceList,
)

# Texto de roteamento que o cliente recebe no `initialize` (SDK 2.x:
# `instructions=` no construtor). Até 2026-09-17 o servidor subia sem ele;
# os irmãos (uis, ilo, bcb) publicam um. O gate confere que cita cada tool.
INSTRUCTIONS = (
    "Ocorrências minerais, afloramentos geológicos e unidades litoestratigráficas "
    "do Brasil a partir do GeoSGB, o geoportal do Serviço Geológico do Brasil "
    "(SGB/CPRM): a camada \"Ocorrências minerais\" (36.484 registros em 2026-09-17), "
    "com substâncias, status econômico, rochas hospedeiras, província, UF, município "
    "e coordenadas; a camada \"Afloramentos geológicos\" (360.042 pontos em "
    "2026-09-17), com toponímia, tipo de afloramento, rochas, município, UF, projeto, "
    "data de cadastro e coordenadas; e a camada \"Unidades litoestratigráficas - "
    "1:1.000.000 [2004]\" (46.712 polígonos), com sigla, nome, hierarquia, unidade-pai, "
    "litotipos, idade mínima e máxima em milhões de anos e éon/era/sistema/época. "
    "Qual tool para qual pergunta: search_mineral_occurrences filtra por substância, "
    "UF, município, status econômico e/ou retângulo geográfico (bbox em WGS84); "
    "search_rare_earth_occurrences é a busca pronta de terras raras (ETR) por "
    "termos de substância (default; 74 registros em 2026-09-17) e, com "
    "include_related_rocks=True, também por rochas hospedeiras típicas — atenção: "
    "esse modo traz 2.383 registros e 96% deles são pegmatitos, não ETR; "
    "get_occurrence_details traz o registro completo de UMA ocorrência pelo id; "
    "list_mineral_substances lista os nomes de substância exatamente como a fonte "
    "os grava (a primeira chamada baixa a camada inteira, ~20 s; as seguintes "
    "saem de um cache válido por 24 h, e provenance.served_from_cache diz qual foi); "
    "get_geological_outcrops lista afloramentos (pontos de observação de rocha "
    "em campo, não ocorrências minerais) e EXIGE filtro: uf + municipality juntos, "
    "ou um bbox de até 1 grau quadrado — sem isso recusa antes de ir à fonte; "
    "get_lithology_by_area responde \"que unidades geológicas há neste recorte\" ou "
    "\"que unidade está sob este ponto\" com o mapa geológico 1:1.000.000 de 2004: "
    "EXIGE um bbox de até 25 graus quadrados OU um ponto (lon + lat), nunca os dois, "
    "e devolve UNIDADES (não polígonos, sem geometria), agregadas no cliente por sigla, "
    "cada uma com polygon_count e area_deg2 — atenção: area_deg2 é a soma da área dos "
    "polígonos INTEIROS que tocam o recorte, em graus quadrados, não a área dentro "
    "dele, e provenance.derived é true nessa tool. "
    "Como preencher: uf é a sigla em MAIÚSCULAS (\"MG\", não \"mg\" nem \"Minas\"); "
    "economic_status aceita exatamente \"Mina\", \"Garimpo\", \"Indeterminado\" ou "
    "\"Não explotado\" (valores medidos na fonte em 2026-09-17; não existe "
    "\"Ocorrência\"); em search_mineral_occurrences, substance e municipality "
    "casam por LIKE sensível a caixa e acento — use a grafia da fonte (\"Nióbio\", "
    "não \"Niobio\"; \"Terras raras\"), que list_mineral_substances devolve; em "
    "get_geological_outcrops, municipality é IGUALDADE exata com a grafia da fonte "
    "(\"Santa Bárbara\" acha 1.333 pontos; \"Santa Barbara\" acha zero). "
    "Custo: o portal não pagina, então toda busca baixa tudo o que casa e corta "
    "no cliente — uma UF inteira de ocorrências (MG, 7.562 registros) leva ~4 s; "
    "filtre por substância ou bbox quando puder. Em afloramentos o maior município "
    "(São Félix do Xingu/PA) tem 3.000 pontos e um bbox de 1 grau quadrado na região "
    "mais densa (Quadrilátero Ferrífero, MG) traz 8.572 pontos (3 MB) em ~3,5 s. Em "
    "litoestratigrafia um bbox de 1°×1° traz ~60 unidades (311 polígonos) em ~0,5 s "
    "e o teto de 25 graus quadrados ~350 unidades (4.180 polígonos, 2 MB) em ~4 s; "
    "um ponto responde em ~0,4 s (a primeira chamada do processo pode demorar bem "
    "mais: 17 s medidos, o portal frio). O bbox "
    "exige os quatro cantos (bbox_xmin < bbox_xmax, bbox_ymin < bbox_ymax, em graus "
    "WGS84) ou nenhum; incompleto ou invertido é recusado antes de ir à fonte. "
    "Toda resposta traz um bloco provenance (URL da camada, WHERE efetiva, "
    "instante da extração em UTC); ao citar, use \"Fonte: Serviço Geológico do "
    "Brasil (SGB/CPRM) — GeoSGB\". "
    "Não use este servidor para geoquímica (a camada de sedimento de corrente não "
    "publica resultados analíticos), nem para dados fora do Brasil."
)

# SDK 2.x (migrado em 2026-09-17): `FastMCP` virou `MCPServer`. O decorador
# `@mcp.tool()` e a conversão do retorno não mudaram.
mcp = MCPServer("geosgb", instructions=INSTRUCTIONS)

# Contrato de saída: cada tool anota o retorno com um modelo de models.py.
# Com isso o servidor publica `outputSchema` em tools/list, preenche
# `structuredContent` em tools/call e reprova em runtime resposta que não
# obedece (vira `isError`). Retorno `-> dict` não gera esquema nenhum — foi
# assim até 2026-09. Gate: tests/test_output_contract.py.


def _bbox(
    xmin: float | None, ymin: float | None, xmax: float | None, ymax: float | None
) -> tuple[float, float, float, float] | None:
    """Os quatro cantos viram um envelope — ou nenhum vira "sem bbox".

    Até 2026-09-17 os cantos eram aceitos soltos: três preenchidos e um
    vazio viravam "sem bbox" em silêncio (a busca ignorava a área e devolvia
    a UF inteira como se fosse resposta) e `xmin > xmax` ia ao portal. Agora
    a recusa é na borda, com o que faltou ou o que está invertido, antes de
    qualquer ida à fonte.
    """
    cantos = {"bbox_xmin": xmin, "bbox_ymin": ymin, "bbox_xmax": xmax, "bbox_ymax": ymax}
    faltam = [nome for nome, valor in cantos.items() if valor is None]
    if len(faltam) == 4:
        return None
    if faltam:
        raise ToolError(
            f"bbox incompleto: faltou {', '.join(faltam)} — informe os quatro cantos "
            "(bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax) ou nenhum"
        )
    assert xmin is not None and ymin is not None and xmax is not None and ymax is not None
    fora = [
        f"{nome}={valor}"
        for nome, valor, teto in (
            ("bbox_xmin", xmin, 180), ("bbox_xmax", xmax, 180),
            ("bbox_ymin", ymin, 90), ("bbox_ymax", ymax, 90),
        )
        if not -teto <= valor <= teto
    ]
    if fora:
        raise ToolError(
            f"bbox fora do globo: {', '.join(fora)} — longitude em [-180, 180] e "
            "latitude em [-90, 90], graus WGS84"
        )
    if xmin >= xmax or ymin >= ymax:
        raise ToolError(
            f"bbox invertido ou vazio: bbox_xmin ({xmin}) deve ser menor que bbox_xmax "
            f"({xmax}) e bbox_ymin ({ymin}) menor que bbox_ymax ({ymax})"
        )
    return (xmin, ymin, xmax, ymax)


def _bbox_area_max(
    bbox: tuple[float, float, float, float],
    teto: float,
    alternativa: str = "reduza o retângulo ou filtre por uf + municipality",
) -> None:
    """Recusa, na borda, bbox maior que `teto` graus quadrados — para camada
    em que a fonte não pagina e o recorte é o que segura a resposta
    (afloramentos: 360.042 pontos; 1°×1° na região mais densa são 8.572
    pontos / 3,0 MB / 2,4 s, 2°×2° já 22.042 / 7,9 MB, medido em 2026-09-17;
    litoestratigrafia: 46.712 polígonos agregados no cliente, 5°×5° são
    4.614 polígonos / 2,2 MB / 3,4 s, 10°×10° já 13.880 / 7,9 MB). A
    mensagem diz a área pedida, o teto e a `alternativa` da tool; o portal
    não é tocado."""
    xmin, ymin, xmax, ymax = bbox
    area = (xmax - xmin) * (ymax - ymin)
    if area > teto:
        raise ToolError(
            f"bbox grande demais: {area:g} graus quadrados "
            f"({xmax - xmin:g}° × {ymax - ymin:g}°); o teto é {teto:g} — "
            f"{alternativa}"
        )


def _point(lon: float | None, lat: float | None) -> tuple[float, float] | None:
    """`lon` e `lat` viram um ponto — ou nenhum vira "sem ponto". Um só é
    recusado nomeando o que faltou; fora do globo também (desde 0.7.0, para
    `get_lithology_by_area`)."""
    if lon is None and lat is None:
        return None
    if lon is None or lat is None:
        faltou = "lat" if lat is None else "lon"
        raise ToolError(
            f"ponto incompleto: faltou {faltou} — informe lon E lat (graus WGS84) ou nenhum"
        )
    fora = [
        f"{nome}={valor}"
        for nome, valor, teto in (("lon", lon, 180), ("lat", lat, 90))
        if not -teto <= valor <= teto
    ]
    if fora:
        raise ToolError(
            f"ponto fora do globo: {', '.join(fora)} — longitude em [-180, 180] e "
            "latitude em [-90, 90], graus WGS84"
        )
    return (lon, lat)


@mcp.tool()
async def search_mineral_occurrences(
    substance: str | None = None,
    # Sigla maiúscula, uma das 27 (constants.UF): o inputSchema publica o
    # enum e o SDK recusa "Minas" ou "mg" com a lista na mensagem. Até
    # 2026-09-17 era `str` e o valor errado virava zero achado em silêncio.
    uf: UF | None = None,
    municipality: str | None = None,
    economic_status: str | None = None,
    bbox_xmin: float | None = None,
    bbox_ymin: float | None = None,
    bbox_xmax: float | None = None,
    bbox_ymax: float | None = None,
    # Limites impostos no esquema (minimum/maximum) e na validação: até
    # 2026-09-17 a docstring prometia "máximo: 1000" e nada impunha —
    # limit=5000 passava e a API, que não pagina, devolvia tudo.
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> OccurrenceSearchResult:
    """
    Busca ocorrências minerais no banco de dados do Serviço Geológico do Brasil.

    Permite filtrar por substância mineral, estado (UF), município, status econômico
    e/ou área geográfica (bounding box).

    Args:
        substance: Nome da substância mineral (ex: "Ouro", "Terras raras", "Litio", "Niobio")
        uf: Sigla da unidade da federação, em maiúsculas (ex: "MG", "GO", "BA", "AM")
        municipality: Nome do município
        economic_status: Status econômico, exatamente como a fonte grava: "Mina",
            "Garimpo", "Indeterminado" ou "Não explotado" (medido em 2026-09-17;
            não existe "Ocorrência")
        bbox_xmin: Longitude mínima do bounding box (WGS84). Os quatro cantos
            vêm juntos ou nenhum; incompleto ou invertido é recusado.
        bbox_ymin: Latitude mínima do bounding box (WGS84)
        bbox_xmax: Longitude máxima do bounding box (WGS84)
        bbox_ymax: Latitude máxima do bounding box (WGS84)
        limit: Número máximo de resultados (default: 100, máximo: 1000)
        offset: Offset para paginação

    Returns:
        Dicionário contendo:
        - count: número de resultados retornados
        - total_count: total de registros que atendem aos critérios
        - features: lista de ocorrências minerais com detalhes

    Custo: a fonte não pagina — a busca baixa tudo que casa (só os campos da
    resposta, mais coordenadas) e corta no cliente; uma UF inteira leva ~4 s.
    """
    from .tools.occurrences import search_mineral_occurrences as _search

    bbox = _bbox(bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)

    return await _search(
        substance=substance,
        uf=uf,
        municipality=municipality,
        economic_status=economic_status,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
async def search_rare_earth_occurrences(
    uf: UF | None = None,
    bbox_xmin: float | None = None,
    bbox_ymin: float | None = None,
    bbox_xmax: float | None = None,
    bbox_ymax: float | None = None,
    # Default False desde 2026-09-17 (Sessão 2): com True, 96% do resultado
    # são pegmatitos (2.291 de 2.383), não ETR. Era True até então.
    include_related_rocks: bool = False,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> RareEarthSearchResult:
    """
    Busca ocorrências de Elementos Terras Raras (ETRs) no Brasil.

    ETRs são 17 elementos químicos estratégicos para tecnologias de transição
    energética, incluindo lantanídeos, escândio e ítrio.

    Dois modos, medidos na fonte em 2026-09-17 (Brasil inteiro):
    - include_related_rocks=False (default): só por substância (13 termos —
      "Terras raras", "Cério", "Lantânio", "Monazita"...): 74 registros,
      60 KB, ~1,5 s.
    - include_related_rocks=True: soma as ocorrências cuja rocha hospedeira é
      típica de ETR (carbonatito, nefelina sienito, pegmatito...): 2.383
      registros, 2,7 MB, ~5,5 s — e 2.291 deles (96%) são pegmatitos, que
      hospedam de tudo; use quando o alvo for a rocha, não o elemento.

    Args:
        uf: Sigla da unidade da federação, em maiúsculas (ex: "MG", "GO", "BA")
        bbox_xmin: Longitude mínima (os quatro cantos vêm juntos ou nenhum;
            incompleto ou invertido é recusado)
        bbox_ymin: Latitude mínima
        bbox_xmax: Longitude máxima
        bbox_ymax: Latitude máxima
        include_related_rocks: Se True, inclui ocorrências em rochas
            hospedeiras típicas de ETRs (ver os dois modos acima)
        limit: Número máximo de resultados

    Returns:
        Dicionário com ocorrências de ETRs e termos de busca utilizados
    """
    from .tools.occurrences import search_rare_earth_occurrences as _search

    bbox = _bbox(bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)

    return await _search(
        uf=uf,
        bbox=bbox,
        include_related_rocks=include_related_rocks,
        limit=limit,
    )


@mcp.tool()
async def get_occurrence_details(occurrence_id: int) -> OccurrenceDetails:
    """
    Obtém detalhes completos de uma ocorrência mineral específica pelo ID.

    Args:
        occurrence_id: ID da ocorrência mineral

    Returns:
        Detalhes completos da ocorrência incluindo:
        - Substâncias minerais
        - Status econômico
        - Rochas hospedeiras e encaixantes
        - Província mineral e classe utilitária
        - Localização (UF, município, coordenadas)
        - Projeto de mapeamento
    """
    from .tools.occurrences import get_occurrence_details as _get_details

    try:
        return await _get_details(occurrence_id)
    except LookupError as exc:
        # No SDK 2.x só `ToolError` leva a mensagem ao cliente; qualquer outra
        # exceção vira "Error executing tool …" genérico e o texto fica no log
        # do servidor. O não-achado é erro previsto: o cliente precisa do ID.
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def list_mineral_substances() -> SubstanceList:
    """
    Lista todas as substâncias minerais cadastradas no banco de dados do SGB.

    Útil para descobrir quais minerais estão disponíveis para consulta — e a
    grafia exata que `substance` em search_mineral_occurrences exige.

    Custo: a fonte não agrega este campo, então a primeira chamada do processo
    baixa a camada inteira (~20 s em 2026-09-17); as seguintes, por 24 h, saem
    de um cache em processo (< 50 ms). `provenance.served_from_cache` diz qual
    foi e `provenance.retrieved_at` é sempre o instante da ida real à fonte.

    Returns:
        Lista de substâncias minerais únicas ordenadas alfabeticamente
    """
    from .tools.occurrences import list_mineral_substances as _list_substances

    return await _list_substances()


@mcp.tool()
async def get_geological_outcrops(
    uf: UF | None = None,
    municipality: str | None = None,
    bbox_xmin: float | None = None,
    bbox_ymin: float | None = None,
    bbox_xmax: float | None = None,
    bbox_ymax: float | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> OutcropSearchResult:
    """
    Lista afloramentos geológicos (pontos de observação de rocha em campo) do
    banco de dados do Serviço Geológico do Brasil — camada "Afloramentos
    geológicos", 360.042 pontos em 3.540 municípios (2026-09-17). Não são
    ocorrências minerais: para essas, use search_mineral_occurrences.

    Filtro OBRIGATÓRIO, um dos dois:
    - uf + municipality juntos (município por igualdade exata, com a grafia
      da fonte: "Santa Bárbara" acha 1.333 pontos; "Santa Barbara" acha zero);
    - bbox de até 1 grau quadrado (os quatro cantos, em graus WGS84).
    Sem filtro, só uf, só municipality ou bbox acima do teto: recusado antes
    de ir à fonte. uf e municipality podem combinar com o bbox.

    Args:
        uf: Sigla da unidade da federação, em maiúsculas (ex: "MG", "PA")
        municipality: Nome do município exatamente como a fonte grava
            (sensível a caixa e acento)
        bbox_xmin: Longitude mínima do bounding box (WGS84). Os quatro cantos
            vêm juntos ou nenhum; incompleto, invertido ou maior que 1 grau
            quadrado é recusado.
        bbox_ymin: Latitude mínima do bounding box (WGS84)
        bbox_xmax: Longitude máxima do bounding box (WGS84)
        bbox_ymax: Latitude máxima do bounding box (WGS84)
        limit: Número máximo de resultados (default: 100, máximo: 1000)
        offset: Offset para paginação

    Returns:
        Dicionário contendo:
        - count: número de resultados retornados
        - total_count: total de afloramentos que atendem ao filtro
        - features: lista de afloramentos (id, toponímia, tipo, rochas, UF,
          município, projeto, data de cadastro em YYYY-MM-DD, coordenadas)

    Custo (medido pela tool em 2026-09-17): a fonte não pagina — a busca
    baixa tudo que casa (8 campos + coordenadas) e corta no cliente. Santa
    Bárbara/MG: 1.333 pontos, 0,5 MB, ~0,8 s; o maior município (São Félix
    do Xingu/PA): 3.000 pontos, 1,2 MB, ~1,8 s; bbox de 1°×1° na região mais
    densa (Quadrilátero Ferrífero, MG): 8.572 pontos, 3,0 MB, ~3,5 s.
    """
    from .tools.outcrops import search_geological_outcrops as _search

    bbox = _bbox(bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)
    if bbox is None:
        if not (uf and municipality):
            faltou = "municipality" if uf else "uf" if municipality else "uf e municipality"
            raise ToolError(
                "get_geological_outcrops exige filtro: a camada tem 360.042 pontos e a "
                f"fonte não pagina. Informe uf E municipality (faltou {faltou}) ou um "
                f"bbox de até {OUTCROP_BBOX_MAX_DEG2:g} grau quadrado"
            )
    else:
        _bbox_area_max(bbox, OUTCROP_BBOX_MAX_DEG2)

    return await _search(
        uf=uf,
        municipality=municipality,
        bbox=bbox,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
async def get_lithology_by_area(
    bbox_xmin: float | None = None,
    bbox_ymin: float | None = None,
    bbox_xmax: float | None = None,
    bbox_ymax: float | None = None,
    lon: float | None = None,
    lat: float | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> LithologySearchResult:
    """
    Lista as unidades litoestratigráficas que intersectam um recorte — "que
    unidades geológicas há nesta área" ou "que unidade está sob este ponto" —
    a partir do mapa geológico do Brasil 1:1.000.000 (2004) do Serviço
    Geológico do Brasil: camada "Unidades litoestratigráficas - 1:1.000.000
    [2004]", 46.712 polígonos. Escala de reconhecimento: unidades pequenas
    não aparecem e limites são aproximados.

    Recorte OBRIGATÓRIO, um dos dois (nunca os dois):
    - bbox de até 25 graus quadrados (os quatro cantos, em graus WGS84);
    - ponto: lon + lat (graus WGS84) — as unidades cujo polígono contém o
      ponto (normalmente uma; no mar ou fora do mapa, nenhuma — lista
      vazia, não erro).
    Sem recorte, só lon ou só lat, bbox acima do teto, ou bbox E ponto
    juntos: recusado antes de ir à fonte.

    A resposta é DERIVADA (provenance.derived = true): a fonte devolve
    polígonos e a tool os agrega, no cliente, por sigla da unidade. Cada
    unidade traz sigla (code), nome, hierarquia (Formação, Grupo, Suíte,
    Complexo...), sigla e nome da unidade-pai, litotipos, idade mínima e
    máxima em milhões de anos (Ma), éon/era/sistema/época mínimos e máximos,
    polygon_count (quantos polígonos da unidade tocam o recorte) e area_deg2.
    ATENÇÃO a area_deg2: é a soma da área dos polígonos INTEIROS que tocam o
    recorte, em graus quadrados (a fonte é WGS84), NÃO a área dentro do
    recorte — serve para ordenar (a lista vem da maior para a menor) e
    comparar unidades, não para medir o recorte. Sem geometria.

    Args:
        bbox_xmin: Longitude mínima do bounding box (WGS84). Os quatro cantos
            vêm juntos ou nenhum; incompleto, invertido ou maior que 25 graus
            quadrados é recusado.
        bbox_ymin: Latitude mínima do bounding box (WGS84)
        bbox_xmax: Longitude máxima do bounding box (WGS84)
        bbox_ymax: Latitude máxima do bounding box (WGS84)
        lon: Longitude do ponto (WGS84); vem junto com lat, ou nenhum
        lat: Latitude do ponto (WGS84); vem junto com lon, ou nenhum
        limit: Número máximo de unidades (default: 100, máximo: 1000)
        offset: Offset em unidades, para paginação

    Returns:
        Dicionário contendo:
        - count: número de unidades retornadas
        - total_count: total de unidades que intersectam o recorte
        - polygon_count: total de polígonos lidos da fonte (antes de agregar)
        - units: lista de unidades, da maior area_deg2 para a menor

    Custo (medido pela tool em 2026-09-17): uma ida, sem geometria, 17
    campos. Bbox de 1°×1° no Quadrilátero Ferrífero: 311 polígonos em 60
    unidades, 0,15 MB, ~0,5 s; o teto de 25 graus quadrados (5°×5°, centro
    de MG): 4.180 polígonos em 356 unidades, 2,1 MB, ~4 s; um ponto: ~0,4 s.
    A primeira chamada do processo pode demorar bem mais (17 s medidos no
    1°×1°: o portal frio), as seguintes não.
    """
    from .tools.lithology import search_lithology_by_area as _search

    bbox = _bbox(bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)
    point = _point(lon, lat)
    if bbox is not None and point is not None:
        raise ToolError(
            "get_lithology_by_area aceita um bbox OU um ponto (lon + lat), não os dois: "
            "para a unidade sob um ponto informe só lon e lat; para as unidades de uma "
            "área, só os quatro cantos do bbox"
        )
    if bbox is None and point is None:
        raise ToolError(
            "get_lithology_by_area exige recorte: a camada tem 46.712 polígonos e a "
            "fonte não pagina. Informe um bbox de até "
            f"{LITHOLOGY_BBOX_MAX_DEG2:g} graus quadrados (os quatro cantos) ou um ponto "
            "(lon E lat), em graus WGS84"
        )
    if bbox is not None:
        _bbox_area_max(
            bbox, LITHOLOGY_BBOX_MAX_DEG2, alternativa="reduza o retângulo ou consulte por ponto (lon + lat)"
        )

    return await _search(bbox=bbox, point=point, limit=limit, offset=offset)


def _forbid_unknown_arguments(server: MCPServer) -> None:
    """Faz cada tool recusar chave desconhecida nos argumentos.

    O SDK monta o modelo de argumentos sem `extra="forbid"`: uma chamada com
    `{"intruso": 1}` passava calada no 1.30 e, no 2.2, só gera um log
    ("rejected arguments") e SEGUE respondendo como sucesso (medido em
    2026-09-16 e 2026-09-17). Um argumento com o nome errado é a forma mais
    comum de um cliente achar que filtrou e não ter filtrado. Aqui o modelo é
    reconstruído com `extra="forbid"` e o `inputSchema` publicado ganha
    `additionalProperties: false`, para o cliente saber antes de chamar.
    Usa `_tool_manager` (privado; igual em 1.x e 2.x — o pin em pyproject).
    """
    for tool in server._tool_manager.list_tools():
        arg_model = tool.fn_metadata.arg_model
        arg_model.model_config["extra"] = "forbid"
        arg_model.model_rebuild(force=True)
        tool.parameters = arg_model.model_json_schema()


_forbid_unknown_arguments(mcp)


if __name__ == "__main__":
    mcp.run()

"""Contrato de saída: o `structuredContent` obedece ao `outputSchema` anunciado.

Por que este arquivo existe. A spec do MCP exige que toda resposta de sucesso
de uma tool com `outputSchema` traga `structuredContent` que OBEDEÇA ao
esquema, e cliente que valida (o MCP Inspector valida) rejeita a resposta
inteira quando não obedece. `tools/list` não pega nada: só `tools/call` expõe.

Aqui os esquemas nascem dos modelos Pydantic de `models.py`, então o caminho
feliz passa mesmo com um esquema desonesto. O defeito mora onde a fonte OMITE
um campo ou o devolve nulo — por isso cada tool tem um caso CHEIO (todos os
atributos e geometria) e um caso MAGRO (atributos nulos, sem geometria, lista
vazia). É o equivalente pytest do gate vitest dos irmãos (ilo, bcb, sih).

O teste roda o servidor de verdade (`geosgb_mcp.server.mcp`) pelo `Client` em
memória do SDK 2.x e valida contra o esquema que o `tools/list` publica, com um
validador INDEPENDENTE (jsonschema). A rede nunca é tocada: `httpx.AsyncClient`
é substituído por uma subclasse com `MockTransport`.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jsonschema
import pytest
from mcp import Client

from geosgb_mcp import server as server_module
from geosgb_mcp.constants import (
    BASE_URL,
    ENDPOINTS,
    LAYERS,
    LITHOLOGY_BBOX_MAX_DEG2,
    LITHOLOGY_FIELDS,
    OCCURRENCE_FIELDS,
    OUTCROP_BBOX_MAX_DEG2,
    OUTCROP_FIELDS,
    RARE_EARTH_FIELDS,
    REE_HOST_ROCKS,
    REE_SEARCH_TERMS,
    SUBSTANCES_CACHE_TTL,
    UF_CODES,
)
from geosgb_mcp.provenance import layer_url
from geosgb_mcp.tools import lithology as lithology_module
from geosgb_mcp.tools import occurrences as occurrences_module
from geosgb_mcp.tools import outcrops as outcrops_module

# ---------------------------------------------------------------------------
# Fonte falsa (geoportal do SGB)
# ---------------------------------------------------------------------------

FEATURE_CHEIA = {
    "attributes": {
        "ID_OCORRENCIA": 4101,
        "SUBSTANCIAS": "Terras raras, Monazita",
        "STATUS_ECONOMICO": "Ocorrência",
        "ROCHAS_HOSPEDEIRAS": "Carbonatito",
        "ROCHAS_ENCAIXANTES": "Gnaisse",
        "PROVINCIA": "Alto Paranaíba",
        "CLASSES_UTILITARIAS": "Metais raros",
        "UF": "MG",
        "MUNICIPIO": "Araxá",
        "PROJETO": "Projeto Terras Raras",
        "CODIGO_FOLHA": "SE-23-Y-C",
        "FOLHA": "Araxá",
        "METODO_GEOPOSICIONAMENTO": "GPS",
    },
    "geometry": {"x": -46.9439, "y": -19.5836},
}

FEATURE_CHEIA_2 = {
    "attributes": {**FEATURE_CHEIA["attributes"], "ID_OCORRENCIA": 4102, "MUNICIPIO": "Tapira"},
    "geometry": {"x": -46.8261, "y": -19.9153},
}

# Registro como o portal de fato devolve quando o cadastro está incompleto:
# só o ID preenchido, todo o resto nulo e SEM chave `geometry`.
FEATURE_MAGRA = {
    "attributes": {
        "ID_OCORRENCIA": 99,
        "SUBSTANCIAS": None,
        "STATUS_ECONOMICO": None,
        "ROCHAS_HOSPEDEIRAS": None,
        "ROCHAS_ENCAIXANTES": None,
        "PROVINCIA": None,
        "CLASSES_UTILITARIAS": None,
        "UF": None,
        "MUNICIPIO": None,
        "PROJETO": None,
        "CODIGO_FOLHA": None,
        "FOLHA": None,
        "METODO_GEOPOSICIONAMENTO": None,
    }
}


@dataclass
class Cenario:
    """O que o portal responde a uma query: as features. Não há mais `count`
    aqui — desde 2026-09-17 (Sessão 2) tool nenhuma pede `returnCountOnly`
    (a fonte não pagina: a query já traz tudo e `total_count` é
    `len(features)`), e o portal falso REPROVA quem voltar a pedir.

    `camada` é a chave de ENDPOINTS que o cenário serve: o portal só aceita
    requisição ao `/query` dessa camada (Sessão 3, 2026-09-17 — antes era
    sempre `ocorrencias`, e tool sobre outra camada não tinha como ser presa
    aqui). `exceeded_transfer_limit` faz a resposta trazer
    `exceededTransferLimit: true`, como a fonte faz quando corta em
    `maxRecordCount` (afloramentos: 300.000 para 360.042 pontos, medido em
    2026-09-17) — é o que uma tool precisa ler para declarar `truncated:
    true` em vez de esconder o corte."""

    features: list[dict[str, Any]] = field(default_factory=list)
    camada: str = "ocorrencias"
    exceeded_transfer_limit: bool = False

    @property
    def url_query(self) -> str:
        return f"{BASE_URL}{ENDPOINTS[self.camada]}/query"


CHEIO = Cenario(features=[FEATURE_CHEIA, FEATURE_CHEIA_2])
MAGRO = Cenario(features=[FEATURE_MAGRA])
VAZIO = Cenario(features=[])
SUBSTANCIAS_CHEIAS = Cenario(
    features=[
        {"attributes": {"SUBSTANCIAS": "Ouro, Prata"}},
        {"attributes": {"SUBSTANCIAS": "Ouro"}},
        {"attributes": {"SUBSTANCIAS": " Nióbio "}},
    ],
)
SUBSTANCIAS_MAGRAS = Cenario(
    features=[{"attributes": {"SUBSTANCIAS": None}}, {"attributes": {}}],
)

# Afloramentos (0.6.0, 2026-09-17): registro como a camada "Afloramentos
# geológicos" devolve com os 8 campos de OUTCROP_FIELDS. `DATA_CADASTRO` é
# epoch em milissegundos (867369600000 = 1997-06-27).
AFLORAMENTO_CHEIO = {
    "attributes": {
        "ID_AFLORAMENTO": 74194,
        "TOPONIMIA": "Estrada Santa Bárbara - Barão de Cocais, km 3",
        "TIPO_AFLORAMENTO": "Lajedo ou Lajeiro",
        "ROCHAS": "Quartzito micáceo",
        "MUNICIPIO": "Santa Bárbara",
        "UF": "MG",
        "PROJETO": "Jequitinhonha",
        "DATA_CADASTRO": 867369600000,
    },
    "geometry": {"x": -43.4153, "y": -19.9594},
}
AFLORAMENTO_CHEIO_2 = {
    "attributes": {**AFLORAMENTO_CHEIO["attributes"], "ID_AFLORAMENTO": 74195,
                   "TOPONIMIA": "Serra do Caraça, trilha da Cascatinha"},
    "geometry": {"x": -43.4901, "y": -20.0972},
}
# `TIPO_AFLORAMENTO` é nulo em 35% da fonte; aqui só o ID vem preenchido.
AFLORAMENTO_MAGRO = {
    "attributes": {
        "ID_AFLORAMENTO": 7,
        "TOPONIMIA": None,
        "TIPO_AFLORAMENTO": None,
        "ROCHAS": None,
        "MUNICIPIO": None,
        "UF": None,
        "PROJETO": None,
        "DATA_CADASTRO": None,
    }
}
OUTCROP_CHEIO = Cenario(features=[AFLORAMENTO_CHEIO, AFLORAMENTO_CHEIO_2], camada="afloramentos")
OUTCROP_MAGRO = Cenario(features=[AFLORAMENTO_MAGRO], camada="afloramentos")
OUTCROP_VAZIO = Cenario(features=[], camada="afloramentos")

# Bbox de 1°×1° (o teto da tool de afloramentos) sobre o Quadrilátero
# Ferrífero — o recorte medido em 2026-09-17 (8.572 pontos / 3,0 MB / 2,4 s).
BBOX_1x1 = {"bbox_xmin": -44.5, "bbox_ymin": -20.5, "bbox_xmax": -43.5, "bbox_ymax": -19.5}

# Litoestratigrafia 1:1.000.000 (0.7.0, 2026-09-17): polígonos como a camada
# devolve com os 17 campos de LITHOLOGY_FIELDS e SEM geometria. Dois
# polígonos da MESMA sigla (A4PP1mic, Formação Cauê) provam a agregação:
# polygon_count 2 e area_deg2 somada; o terceiro (NP3bsh) tem área maior e
# vem primeiro. Os valores são os do 1°×1° medido (SHAPE.AREA em graus²).
LITO_CAUE_1 = {
    "attributes": {
        "SIGLA": "A4PP1mic",
        "HIERARQUIA": "Formação",
        "NOME": "Formação Cauê",
        "SIGLA_PAI": "A4PP1mi",
        "NOME_PAI": "A4PP1mi - Grupo Itabira",
        "LITOTIPOS": "Dolomito, Filito, Itabirito, Marga",
        "IDADE_MIN": 2300.1,
        "IDADE_MAX": 2800.0,
        "EON_MIN": "Proterozóico",
        "EON_MAX": "Arqueano",
        "ERA_MIN": "Paleoproterozóico",
        "ERA_MAX": "Neoarqueano",
        "SISTEMA_MIN": "Sideriano",
        "SISTEMA_MAX": None,
        "EPOCA_MIN": None,
        "EPOCA_MAX": None,
        "SHAPE.AREA": 0.02,
    }
}
LITO_CAUE_2 = {"attributes": {**LITO_CAUE_1["attributes"], "SHAPE.AREA": 0.03}}
LITO_BAMBUI = {
    "attributes": {
        "SIGLA": "NP3bsh",
        "HIERARQUIA": "Formação",
        "NOME": "Formação Serra de Santa Helena",
        "SIGLA_PAI": "NP3b",
        "NOME_PAI": "NP3b - Grupo Bambuí",
        "LITOTIPOS": "Argilito, Siltito, Arcóseo",
        "IDADE_MIN": 541.0,
        "IDADE_MAX": 1000.0,
        "EON_MIN": "Proterozóico",
        "EON_MAX": "Proterozóico",
        "ERA_MIN": "Neoproterozóico",
        "ERA_MAX": "Neoproterozóico",
        "SISTEMA_MIN": "Ediacarano",
        "SISTEMA_MAX": "Toniano",
        "EPOCA_MIN": None,
        "EPOCA_MAX": None,
        "SHAPE.AREA": 1.5352569601235826,
    }
}
# Polígono como a fonte pode devolvê-lo com o cadastro incompleto: SIGLA e
# tudo o mais nulo, inclusive SHAPE.AREA — agrega numa unidade sem sigla.
LITO_MAGRO_POLIGONO = {
    "attributes": {campo: None for campo in LITHOLOGY_FIELDS}
}
LITO_CHEIO = Cenario(features=[LITO_CAUE_1, LITO_BAMBUI, LITO_CAUE_2], camada="litoestratigrafia_1m")
LITO_MAGRO = Cenario(features=[LITO_MAGRO_POLIGONO], camada="litoestratigrafia_1m")
LITO_VAZIO = Cenario(features=[], camada="litoestratigrafia_1m")

# Bbox de 5°×5° = 25 graus² (o teto da tool de litoestratigrafia), medido em
# 2026-09-17: 4.180 polígonos / 2,1 MB / 2,4 s sem geometria.
BBOX_5x5 = {"bbox_xmin": -48.0, "bbox_ymin": -23.0, "bbox_xmax": -43.0, "bbox_ymax": -18.0}
# Ponto no centro de Belo Horizonte: 1 polígono (A34bh) em 0,12 s.
PONTO_BH = {"lon": -43.94, "lat": -19.92}

class Portal:
    """Fonte falsa que responde pelo cenário e GRAVA cada requisição — é o
    que permite medir, sem rede, quantas idas cada tool faz e o que pede.
    Só responde ao `/query` da camada do cenário: a tool tem de ir aonde a
    proveniência diz que foi."""

    def __init__(self, cenario: Cenario) -> None:
        self.cenario = cenario
        self.requisicoes: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url_sem_query = str(request.url).split("?", 1)[0]
        if url_sem_query != self.cenario.url_query:
            raise AssertionError(
                f"requisição inesperada: {request.url} — o cenário serve a camada "
                f"{self.cenario.camada!r} ({self.cenario.url_query})"
            )
        self.requisicoes.append(request)
        if request.url.params.get("returnCountOnly") == "true":
            raise AssertionError(
                "returnCountOnly: a fonte não pagina e a query já traz o total — "
                "a requisição de contagem foi derrubada em 2026-09-17"
            )
        corpo: dict[str, Any] = {"features": self.cenario.features}
        if self.cenario.exceeded_transfer_limit:
            corpo["exceededTransferLimit"] = True
        return httpx.Response(200, json=corpo)


@pytest.fixture
def portal(monkeypatch):
    """Devolve `usar(cenario) -> Portal`: a partir daí todo `httpx.AsyncClient`
    novo responde pelo cenário, sem rede. O cliente lê `httpx.AsyncClient`
    como atributo do módulo em `_get_client`, então a troca pega. O cache de
    substâncias é limpo por teste — um teste não herda a ida do outro."""

    occurrences_module._substances_cache.clear()
    monkeypatch.setattr(occurrences_module._substances_cache, "clock", time.monotonic)
    # Sempre a classe ORIGINAL: `usar` pode ser chamado mais de uma vez no
    # mesmo teste, e herdar da falsa anterior duplicaria `transport`.
    AsyncClientReal = httpx.AsyncClient

    def usar(cenario: Cenario) -> Portal:
        fonte = Portal(cenario)
        transporte = httpx.MockTransport(fonte.handler)

        class AsyncClientFalso(AsyncClientReal):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(transport=transporte, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", AsyncClientFalso)
        return fonte

    return usar


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Caso:
    tool: str
    tipo: str  # "cheio" | "magro"
    cobre: str
    cenario: Cenario
    args: dict[str, Any]
    # Valores que o estruturado precisa carregar, por caminho pontuado
    # (`features.0.coordinates`). O esquema vê a FORMA; isto vê o que a fonte
    # falsa mandou chegar do outro lado — pega coordenada fabricada, lista
    # não deduplicada, offset perdido.
    espera: dict[str, Any] = field(default_factory=dict)
    # Camada que a proveniência da resposta tem de citar (chave de LAYERS).
    # O cenário diz aonde a tool FOI; isto diz o que ela DISSE — os dois
    # precisam bater, e o teste de proveniência confere.
    camada: str = "ocorrencias"


CASOS: list[Caso] = [
    Caso(
        "search_mineral_occurrences",
        "cheio",
        "dois achados com geometria, filtros de substância, UF e bbox, offset 1",
        CHEIO,
        {
            "substance": "Terras raras",
            "uf": "MG",
            "bbox_xmin": -47.5,
            "bbox_ymin": -20.5,
            "bbox_xmax": -46.0,
            "bbox_ymax": -19.0,
            "limit": 10,
            "offset": 1,
        },
        # offset é aplicado no cliente (a API não pagina): com dois achados e
        # offset 1, chega só o segundo — e total_count segue 2.
        # total_count é len(features) da própria query: não há mais contagem.
        {"count": 1, "total_count": 2, "offset": 1, "features.0.id": 4102,
         "features.0.coordinates": {"lon": -46.8261, "lat": -19.9153},
         "features.0.municipality": "Tapira",
         # Proveniência: a WHERE e o envelope que de fato foram ao portal.
         "provenance.dimension_key": {"where": "SUBSTANCIAS LIKE '%Terras raras%' AND UF = 'MG'",
                                      "geometry": "-47.5,-20.5,-46.0,-19.0"}},
    ),
    Caso(
        "search_mineral_occurrences",
        "magro",
        "registro com atributos nulos e sem geometria (coordinates nulo)",
        MAGRO,
        {"uf": "MG"},
        {"count": 1, "features.0.id": 99, "features.0.substance": None, "features.0.coordinates": None},
    ),
    Caso(
        "search_mineral_occurrences",
        "magro",
        "busca sem achado (features vazio, total_count zero)",
        VAZIO,
        {"municipality": "Lugar Nenhum", "offset": 5},
        {"count": 0, "total_count": 0, "offset": 5, "features": []},
    ),
    Caso(
        "search_rare_earth_occurrences",
        "cheio",
        "achados com geometria, rochas relacionadas incluídas",
        CHEIO,
        {"uf": "MG", "include_related_rocks": True, "limit": 5},
        {"count": 2, "features.0.coordinates": {"lon": -46.9439, "lat": -19.5836},
         # Uma fonte só: o que a tool diz ter buscado É a lista de constants.py
         # (até 2026-09-17 era uma lista própria de 5 + 2).
         "search_terms_used": list(REE_SEARCH_TERMS) + list(REE_HOST_ROCKS),
         "provenance.dimension_key.where": "("
         + " OR ".join([f"SUBSTANCIAS LIKE '%{t}%'" for t in REE_SEARCH_TERMS]
                       + [f"ROCHAS_HOSPEDEIRAS LIKE '%{r}%'" for r in REE_HOST_ROCKS])
         + ") AND UF = 'MG'"},
    ),
    Caso(
        "search_rare_earth_occurrences",
        "magro",
        "registro com atributos nulos, sem geometria; sem argumento = só substâncias",
        MAGRO,
        {},
        # Default False desde 2026-09-17: sem o argumento, a WHERE não tem
        # rocha nenhuma (com True, 96% do resultado eram pegmatitos).
        {"features.0.coordinates": None, "features.0.host_rocks": None,
         "search_terms_used": list(REE_SEARCH_TERMS),
         "provenance.dimension_key.where": "("
         + " OR ".join(f"SUBSTANCIAS LIKE '%{t}%'" for t in REE_SEARCH_TERMS) + ")"},
    ),
    Caso(
        "get_occurrence_details",
        "cheio",
        "ocorrência com todos os atributos e geometria",
        Cenario(features=[FEATURE_CHEIA]),
        {"occurrence_id": 4101},
        {"id": 4101, "enclosing_rocks": "Gnaisse", "sheet_code": "SE-23-Y-C",
         "coordinates": {"lon": -46.9439, "lat": -19.5836},
         "provenance.dimension_key": {"where": "ID_OCORRENCIA = 4101"}},
    ),
    Caso(
        "get_occurrence_details",
        "magro",
        "ocorrência só com ID: treze atributos nulos e coordinates nulo",
        MAGRO,
        {"occurrence_id": 99},
        {"id": 99, "substance": None, "positioning_method": None, "coordinates": None},
    ),
    Caso(
        "list_mineral_substances",
        "cheio",
        "substâncias repetidas e com espaços, deduplicadas e ordenadas",
        SUBSTANCIAS_CHEIAS,
        {},
        {"count": 3, "substances": ["Nióbio", "Ouro", "Prata"],
         "provenance.dimension_key": {"where": "1=1"}},
    ),
    Caso(
        "list_mineral_substances",
        "magro",
        "atributo nulo e atributo ausente (lista vazia, count zero)",
        SUBSTANCIAS_MAGRAS,
        {},
        {"count": 0, "substances": []},
    ),
    Caso(
        "get_geological_outcrops",
        "cheio",
        "dois achados com geometria por uf + municipio (igualdade), offset 1",
        OUTCROP_CHEIO,
        {"uf": "MG", "municipality": "Santa Bárbara", "limit": 10, "offset": 1},
        {"count": 1, "total_count": 2, "offset": 1, "features.0.id": 74195,
         "features.0.coordinates": {"lon": -43.4901, "lat": -20.0972},
         "features.0.outcrop_type": "Lajedo ou Lajeiro",
         "features.0.rocks": "Quartzito micáceo",
         # Epoch em ms convertido para data ISO.
         "features.0.registered_at": "1997-06-27",
         # Município por IGUALDADE (LIKE pega vizinhos: 1.571 ≠ 1.333).
         "provenance.dimension_key": {"where": "UF = 'MG' AND MUNICIPIO = 'Santa Bárbara'"}},
        camada="afloramentos",
    ),
    Caso(
        "get_geological_outcrops",
        "cheio",
        "achados por bbox de 1 grau quadrado, sem uf nem municipio",
        OUTCROP_CHEIO,
        {**BBOX_1x1, "limit": 5},
        {"count": 2, "total_count": 2, "offset": 0, "features.0.id": 74194,
         "features.0.coordinates": {"lon": -43.4153, "lat": -19.9594},
         "provenance.dimension_key": {"where": "1=1", "geometry": "-44.5,-20.5,-43.5,-19.5"}},
        camada="afloramentos",
    ),
    Caso(
        "get_geological_outcrops",
        "magro",
        "registro só com ID, sete atributos nulos e sem geometria",
        OUTCROP_MAGRO,
        {"uf": "PA", "municipality": "São Félix do Xingu"},
        {"count": 1, "features.0.id": 7, "features.0.outcrop_type": None,
         "features.0.registered_at": None, "features.0.coordinates": None},
        camada="afloramentos",
    ),
    Caso(
        "get_geological_outcrops",
        "magro",
        "municipio sem acento: zero achado (features vazio, total_count zero)",
        OUTCROP_VAZIO,
        {"uf": "MG", "municipality": "Santa Barbara", "offset": 3},
        {"count": 0, "total_count": 0, "offset": 3, "features": []},
        camada="afloramentos",
    ),
    Caso(
        "get_lithology_by_area",
        "cheio",
        "tres poligonos em duas unidades por bbox no teto (25 graus2), ordem por area",
        LITO_CHEIO,
        {**BBOX_5x5, "limit": 10},
        # Três polígonos, duas siglas: total_count conta UNIDADES; a de maior
        # área somada vem primeiro; os dois da Formação Cauê viram um só, com
        # polygon_count 2 e a área somada (0,02 + 0,03).
        {"count": 2, "total_count": 2, "offset": 0, "polygon_count": 3,
         "units.0.code": "NP3bsh", "units.0.polygon_count": 1,
         "units.0.area_deg2": 1.5352569601235826,
         "units.1.code": "A4PP1mic", "units.1.name": "Formação Cauê",
         "units.1.polygon_count": 2, "units.1.area_deg2": 0.05,
         "units.1.parent_code": "A4PP1mi", "units.1.age_max_ma": 2800.0,
         "units.1.system_max": None,
         "provenance.derived": True,
         "provenance.dimension_key": {"where": "1=1", "geometry": "-48.0,-23.0,-43.0,-18.0"}},
        camada="litoestratigrafia_1m",
    ),
    Caso(
        "get_lithology_by_area",
        "cheio",
        "por ponto (lon + lat), offset 1: a segunda unidade",
        LITO_CHEIO,
        {**PONTO_BH, "offset": 1},
        {"count": 1, "total_count": 2, "offset": 1, "polygon_count": 3,
         "units.0.code": "A4PP1mic", "units.0.polygon_count": 2,
         # Ponto na proveniência: geometry "lon,lat" + geometry_type.
         "provenance.dimension_key": {"where": "1=1", "geometry": "-43.94,-19.92",
                                      "geometry_type": "point"}},
        camada="litoestratigrafia_1m",
    ),
    Caso(
        "get_lithology_by_area",
        "magro",
        "poligono com SIGLA e tudo nulo, SHAPE.AREA nulo: uma unidade sem sigla",
        LITO_MAGRO,
        PONTO_BH,
        {"count": 1, "total_count": 1, "polygon_count": 1,
         "units.0.code": None, "units.0.name": None, "units.0.age_min_ma": None,
         "units.0.polygon_count": 1, "units.0.area_deg2": None,
         "provenance.derived": True},
        camada="litoestratigrafia_1m",
    ),
    Caso(
        "get_lithology_by_area",
        "magro",
        "ponto no mar: nenhuma unidade (units vazio, total_count zero)",
        LITO_VAZIO,
        {"lon": -30.0, "lat": -20.0, "offset": 2},
        {"count": 0, "total_count": 0, "offset": 2, "polygon_count": 0, "units": []},
        camada="litoestratigrafia_1m",
    ),
]


# ---------------------------------------------------------------------------
# Infra: sessão em memória e esquemas publicados
# ---------------------------------------------------------------------------


def conectar() -> Client:
    """Cliente MCP ligado ao servidor de verdade pelo transporte em memória —
    o equivalente Python do `InMemoryTransport.createLinkedPair()` do gate TS.
    SDK 2.x: `Client(servidor)`; no 1.x era
    `create_connected_server_and_client_session`. Uma sessão por `async with`."""
    return Client(server_module.mcp)


@pytest.fixture
async def esquemas() -> dict[str, dict[str, Any] | None]:
    async with conectar() as cliente:
        tools = (await cliente.list_tools()).tools
    return {t.name: t.output_schema for t in tools}


def _no_caminho(dado: Any, caminho: str) -> Any:
    for parte in caminho.split("."):
        dado = dado[int(parte)] if isinstance(dado, list) else dado[parte]
    return dado


def _validar(esquema: dict[str, Any], dado: Any) -> list[str]:
    validador = jsonschema.Draft202012Validator(esquema)
    return [e.message for e in validador.iter_errors(dado)]


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caso", CASOS, ids=[f"{c.tool}-{c.tipo}-{c.cobre}" for c in CASOS])
async def test_structured_content_obedece_ao_output_schema(caso: Caso, esquemas, portal):
    esquema = esquemas.get(caso.tool)
    assert esquema is not None, f"tool {caso.tool} sem outputSchema em tools/list"

    portal(caso.cenario)
    async with conectar() as cliente:
        resultado = await cliente.call_tool(caso.tool, caso.args)

    texto = resultado.content[0].text
    assert not resultado.is_error, f"{caso.tool} devolveu erro: {texto}"
    assert resultado.structured_content is not None, f"{caso.tool} sem structuredContent"

    # O que o CLIENTE vê: o estruturado atravessa como JSON. A sessão em
    # memória serializa de verdade, mas o round-trip aqui garante que nada
    # não-serializável (datetime, set) passou.
    no_fio = json.loads(json.dumps(resultado.structured_content))
    erros = _validar(esquema, no_fio)
    assert not erros, f"{caso.tool}: {erros}"

    # O texto (dict cru serializado pelo SDK) e o estruturado (modelo
    # serializado) precisam ser o MESMO documento: divergência significa chave
    # que a tool emite e o esquema não declara (ou o contrário, via default).
    assert json.loads(texto) == no_fio, f"{caso.tool}: content[0].text difere do structuredContent"

    for caminho, valor in caso.espera.items():
        assert _no_caminho(no_fio, caminho) == valor, f"{caso.tool}: {caminho}"


async def test_cobertura_derivada_do_tools_list(esquemas):
    """Toda tool publicada tem outputSchema e ao menos um caso CHEIO e um MAGRO.
    Tool nova sem caso reprova aqui, não some em silêncio."""
    publicadas = set(esquemas)
    assert publicadas, "tools/list vazio"
    sem_esquema = sorted(n for n, s in esquemas.items() if s is None)
    assert not sem_esquema, f"tools sem outputSchema: {sem_esquema}"

    for nome in sorted(publicadas):
        tipos = {c.tipo for c in CASOS if c.tool == nome}
        assert tipos == {"cheio", "magro"}, f"{nome}: casos cobertos = {sorted(tipos)}"
    orfaos = sorted({c.tool for c in CASOS} - publicadas)
    assert not orfaos, f"casos para tool que não existe: {orfaos}"


async def test_reprova_esquema_desonesto(esquemas, portal):
    """Um teste que não pode falhar não vale nada: a saída REAL do caso magro
    contra um esquema deliberadamente desonesto — a mentira exata que este
    arquivo existe para pegar."""
    portal(MAGRO)
    async with conectar() as cliente:
        resultado = await cliente.call_tool("get_occurrence_details", {"occurrence_id": 99})
    assert not resultado.is_error
    honesto = esquemas["get_occurrence_details"]
    assert _validar(honesto, resultado.structured_content) == []

    desonesto = json.loads(json.dumps(honesto))
    # `substance` é nulo no registro magro; anunciá-lo como string é a mentira.
    desonesto["properties"]["substance"] = {"type": "string"}
    erros = _validar(desonesto, resultado.structured_content)
    assert erros and any("None" in e or "null" in e for e in erros), erros


async def test_resposta_mutilada_vira_is_error(monkeypatch):
    """Prova de que o SDK fecha o portão em runtime: tool que devolve dict sem
    campo obrigatório não chega ao cliente como sucesso."""

    async def mutilada() -> dict:
        return {"count": 1}  # sem `substances`

    # server.py importa a função DENTRO da tool, então trocar no módulo basta.
    monkeypatch.setattr(occurrences_module, "list_mineral_substances", mutilada)
    async with conectar() as cliente:
        resultado = await cliente.call_tool("list_mineral_substances", {})
    assert resultado.is_error
    assert "substances" in resultado.content[0].text
    assert resultado.structured_content is None


async def test_ocorrencia_inexistente_e_erro_declarado(portal):
    """Até 2026-09 a tool devolvia `{"error": ...}` com status de sucesso
    (erro-mole). Com o contrato, o não-achado é `isError` com a mensagem."""
    portal(VAZIO)
    async with conectar() as cliente:
        resultado = await cliente.call_tool("get_occurrence_details", {"occurrence_id": 123456})
    assert resultado.is_error
    assert "123456" in resultado.content[0].text
    assert "não encontrada" in resultado.content[0].text


async def test_chave_desconhecida_nos_argumentos_e_recusada(portal):
    """Argumento com nome errado é a forma mais comum de o cliente achar que
    filtrou e não ter filtrado. O inputSchema anuncia a recusa e a chamada
    de fato reprova (medido em 2026-09-16: sem o ajuste, passava calado)."""
    portal(VAZIO)
    async with conectar() as cliente:
        tools = (await cliente.list_tools()).tools
        for tool in tools:
            assert tool.input_schema.get("additionalProperties") is False, tool.name
        resultado = await cliente.call_tool("search_mineral_occurrences", {"estado": "MG"})
    assert resultado.is_error
    assert "estado" in resultado.content[0].text
    assert "Extra inputs are not permitted" in resultado.content[0].text


async def test_limite_de_resultados_e_imposto(portal):
    """A docstring prometia "máximo: 1000" e nada impunha (até 2026-09-17):
    limit=5000 passava e a API, que não pagina, devolvia tudo. Agora o
    inputSchema anuncia o teto e a chamada acima dele reprova."""
    portal(CHEIO)
    async with conectar() as cliente:
        tools = {t.name: t for t in (await cliente.list_tools()).tools}
        for nome in ("search_mineral_occurrences", "search_rare_earth_occurrences",
                     "get_geological_outcrops", "get_lithology_by_area"):
            limite = tools[nome].input_schema["properties"]["limit"]
            assert (limite.get("minimum"), limite.get("maximum")) == (1, 1000), nome
        offset = tools["search_mineral_occurrences"].input_schema["properties"]["offset"]
        assert offset.get("minimum") == 0

        acima = await cliente.call_tool("search_mineral_occurrences", {"limit": 1001})
        assert acima.is_error and "1000" in acima.content[0].text
        zero = await cliente.call_tool("search_rare_earth_occurrences", {"limit": 0})
        assert zero.is_error and "greater than or equal to 1" in zero.content[0].text
        negativo = await cliente.call_tool("search_mineral_occurrences", {"offset": -1})
        assert negativo.is_error
        no_teto = await cliente.call_tool("search_mineral_occurrences", {"limit": 1000})
        assert not no_teto.is_error


async def test_uf_e_validada_no_esquema(portal):
    """`uf="Minas"` virava `UF = 'MINAS'` e devolvia zero achado como se fosse
    resposta (até 2026-09-17). Agora o inputSchema publica as 27 siglas e a
    chamada com valor fora delas reprova com a lista — inclusive minúscula,
    que antes passava por `upper()`: a sigla é como a fonte grava."""
    portal(CHEIO)
    async with conectar() as cliente:
        tools = {t.name: t for t in (await cliente.list_tools()).tools}
        for nome in ("search_mineral_occurrences", "search_rare_earth_occurrences",
                     "get_geological_outcrops"):
            uf = tools[nome].input_schema["properties"]["uf"]
            ramos = uf.get("anyOf", [uf])
            enums = [r["enum"] for r in ramos if "enum" in r]
            assert enums and set(enums[0]) == set(UF_CODES), nome

        errado = await cliente.call_tool("search_mineral_occurrences", {"uf": "Minas"})
        assert errado.is_error and "Minas" in errado.content[0].text
        assert "'MG'" in errado.content[0].text
        minuscula = await cliente.call_tool("search_rare_earth_occurrences", {"uf": "mg"})
        assert minuscula.is_error
        certo = await cliente.call_tool("search_mineral_occurrences", {"uf": "MG"})
        assert not certo.is_error


@pytest.mark.parametrize("caso", CASOS, ids=[f"{c.tool}-{c.tipo}" for c in CASOS])
async def test_toda_resposta_carrega_proveniencia(caso: Caso, portal):
    """Convenção do portfólio (contrato v1.0): todo dado diz de onde veio.
    Aqui o que o esquema não vê — o instante é ISO em UTC (forma, não valor),
    a URL reproduz a WHERE efetiva, a atribuição é a do SGB e `attribution`
    lista essa mesma URL."""
    portal(caso.cenario)
    async with conectar() as cliente:
        resultado = await cliente.call_tool(caso.tool, caso.args)
    assert not resultado.is_error, resultado.content[0].text
    bloco = resultado.structured_content["provenance"]

    # A camada que a resposta cita é a do caso — e é a mesma a que a tool
    # foi (o portal falso só responde pela camada do cenário).
    camada = LAYERS[caso.camada]
    assert caso.camada == caso.cenario.camada
    assert bloco["contract_version"] == "1.0"
    assert bloco["source"]["name"] == "Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB"
    assert bloco["source"]["endpoint"] == layer_url(caso.camada)
    assert bloco["dataset"] == {"id": caso.camada, "version": None, "name": camada.name}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", bloco["retrieved_at"]), bloco["retrieved_at"]
    assert bloco["license"]["name"].startswith(camada.copyright_text), "piso legal: license.name"
    assert bloco["notices"] and "não declara licença" in bloco["notices"][0]
    assert f"camada {camada.name}," in bloco["citation"]

    where = bloco["dimension_key"]["where"]
    assert bloco["source_url"].startswith(layer_url(caso.camada) + "/query?")
    assert httpx.URL(bloco["source_url"]).params["where"] == where
    assert bloco["source_url"] in bloco["citation"]
    assert resultado.structured_content["attribution"] == [bloco["source_url"]]

    # A WHERE reflete o argumento do caso — não é um bloco fixo colado.
    if "uf" in caso.args:
        assert f"UF = '{caso.args['uf']}'" in where
    if "occurrence_id" in caso.args:
        assert where == f"ID_OCORRENCIA = {caso.args['occurrence_id']}"
    if "bbox_xmin" in caso.args:
        a = caso.args
        esperada = f"{a['bbox_xmin']},{a['bbox_ymin']},{a['bbox_xmax']},{a['bbox_ymax']}"
        assert bloco["dimension_key"]["geometry"] == esperada
        assert "geometry_type" not in bloco["dimension_key"]
        assert httpx.URL(bloco["source_url"]).params["geometryType"] == "esriGeometryEnvelope"
    elif "lon" in caso.args:
        # Recorte por ponto (0.7.0): "lon,lat" + geometry_type, e a URL
        # reproduz o ponto com esriGeometryPoint.
        assert bloco["dimension_key"]["geometry"] == f"{caso.args['lon']},{caso.args['lat']}"
        assert bloco["dimension_key"]["geometry_type"] == "point"
        assert httpx.URL(bloco["source_url"]).params["geometryType"] == "esriGeometryPoint"
    else:
        assert "geometry" not in bloco["dimension_key"]

    # Só a agregação de litoestratigrafia é derivada; as demais devolvem a
    # fonte recortada e dizem isso (`derived: false`, sem nota).
    if caso.tool == "get_lithology_by_area":
        assert bloco["derived"] is True
        assert "graus quadrados" in bloco["derivation_note"]
        assert "não a área dentro do recorte" in bloco["derivation_note"]
    else:
        assert bloco["derived"] is False and bloco["derivation_note"] is None


async def test_instructions_citam_cada_tool_publicada():
    """O `initialize` devolve o texto de roteamento e ele cita cada tool de
    tools/list — tool nova sem menção reprova aqui. Também prende o que o
    texto promete sobre os argumentos: sigla maiúscula e os quatro valores
    de status econômico medidos na fonte em 2026-09-17."""
    async with conectar() as cliente:
        texto = cliente.instructions
        nomes = [t.name for t in (await cliente.list_tools()).tools]
    assert texto and len(texto) > 200
    for nome in nomes:
        assert nome in texto, f"instructions não cita {nome}"
    assert "MAIÚSCULAS" in texto
    for status in ("Mina", "Garimpo", "Indeterminado", "Não explotado"):
        assert f'"{status}"' in texto
    assert "Serviço Geológico do Brasil (SGB/CPRM) — GeoSGB" in texto


# ---------------------------------------------------------------------------
# Sessão 2 (2026-09-17): o custo da fonte sem paginação
# ---------------------------------------------------------------------------


async def test_busca_faz_uma_ida_so_e_pede_so_os_campos_da_resposta(portal):
    """Até 2026-09-17 cada busca fazia DUAS requisições (`returnCountOnly` e
    a query) e pedia `outFields=*` (37 campos, dos quais usava 8): `UF = 'MG'`
    vinha em 8,0 MB / 13 s. A fonte não pagina, então a query já traz o total
    (`count == len(features)` em 4 de 4 WHERE medidas) e só os campos da
    resposta bastam (2,2 MB / ~4 s). Aqui: uma ida, `outFields` explícito,
    `total_count` igual ao que a query devolveu. `get_occurrence_details`
    segue com `*` — é um registro."""
    esperado = {
        "search_mineral_occurrences": ({"uf": "MG", "limit": 1}, ",".join(OCCURRENCE_FIELDS)),
        "search_rare_earth_occurrences": ({"uf": "MG", "limit": 1}, ",".join(RARE_EARTH_FIELDS)),
        "get_occurrence_details": ({"occurrence_id": 4101}, "*"),
    }
    assert "TIPOLOGIA" not in OCCURRENCE_FIELDS  # a camada não tem o campo
    for nome, (args, out_fields) in esperado.items():
        fonte = portal(CHEIO)
        async with conectar() as cliente:
            resultado = await cliente.call_tool(nome, args)
        assert not resultado.is_error, resultado.content[0].text
        assert len(fonte.requisicoes) == 1, f"{nome}: {len(fonte.requisicoes)} idas ao portal"
        params = fonte.requisicoes[0].url.params
        assert params["outFields"] == out_fields, nome
        assert params["returnGeometry"] == "true" and "returnCountOnly" not in params
        if nome != "get_occurrence_details":
            assert resultado.structured_content["total_count"] == len(CHEIO.features)
            assert resultado.structured_content["count"] == 1


async def test_typology_saiu_do_contrato(esquemas):
    """`typology` lia TIPOLOGIA, campo que a camada não tem (37 campos lidos
    na fonte em 2026-09-17; pedi-lo dá 400): saía sempre nulo. Anunciar um
    campo que nunca vem é esquema desonesto — saiu dos dois modelos."""
    itens = esquemas["search_mineral_occurrences"]["$defs"]["OccurrenceSummary"]["properties"]
    assert "typology" not in itens
    assert "typology" not in esquemas["get_occurrence_details"]["properties"]


async def test_lista_de_substancias_vem_do_cache_dentro_da_validade(portal):
    """`list_mineral_substances` só existe baixando a camada inteira (36.484
    registros, 1,6 MB, ~20 s; a fonte recusa agregar SUBSTANCIAS com 400).
    Cache em processo: a segunda chamada não vai ao portal, responde em
    menos de 50 ms, diz `served_from_cache=True` e repete o `retrieved_at`
    da ida original. Vencida a validade, vai de novo."""
    fonte = portal(SUBSTANCIAS_CHEIAS)
    cache = occurrences_module._substances_cache
    agora = [1000.0]
    cache.clock = lambda: agora[0]

    async with conectar() as cliente:
        primeira = await cliente.call_tool("list_mineral_substances", {})
        t0 = time.perf_counter()
        segunda = await cliente.call_tool("list_mineral_substances", {})
        dt = time.perf_counter() - t0
    assert not primeira.is_error and not segunda.is_error
    assert len(fonte.requisicoes) == 1, "a segunda chamada foi ao portal"
    assert dt < 0.05, f"segunda chamada levou {dt * 1000:.0f} ms"

    p1, p2 = primeira.structured_content["provenance"], segunda.structured_content["provenance"]
    assert p1["served_from_cache"] is False and p2["served_from_cache"] is True
    assert p1["retrieved_at"] == p2["retrieved_at"]
    assert segunda.structured_content["substances"] == primeira.structured_content["substances"]
    assert segunda.structured_content["substances"] == ["Nióbio", "Ouro", "Prata"]

    # Validade vencida: nova ida, `retrieved_at` novo (a fonte falsa agora
    # devolve outra lista, para provar que não é o cache antigo).
    agora[0] += SUBSTANCES_CACHE_TTL + 1
    fonte.cenario = Cenario(features=[{"attributes": {"SUBSTANCIAS": "Lítio"}}])
    async with conectar() as cliente:
        terceira = await cliente.call_tool("list_mineral_substances", {})
    assert len(fonte.requisicoes) == 2
    assert terceira.structured_content["provenance"]["served_from_cache"] is False
    assert terceira.structured_content["substances"] == ["Lítio"]


async def test_lista_de_substancias_concorrente_paga_uma_ida_so(portal):
    """Duas chamadas simultâneas com o cache frio: o lock faz a segunda
    esperar a primeira e servir do cache, em vez de baixar 1,6 MB em dobro."""
    fonte = portal(SUBSTANCIAS_CHEIAS)
    async with conectar() as cliente:
        a, b = await asyncio.gather(
            cliente.call_tool("list_mineral_substances", {}),
            cliente.call_tool("list_mineral_substances", {}),
        )
    assert not a.is_error and not b.is_error
    assert len(fonte.requisicoes) == 1
    marcas = sorted(r.structured_content["provenance"]["served_from_cache"] for r in (a, b))
    assert marcas == [False, True]


@pytest.mark.parametrize(
    "tool, cenario, quatro",
    [
        ("search_mineral_occurrences", CHEIO,
         {"bbox_xmin": -47.5, "bbox_ymin": -20.5, "bbox_xmax": -46.0, "bbox_ymax": -19.0}),
        ("search_rare_earth_occurrences", CHEIO,
         {"bbox_xmin": -47.5, "bbox_ymin": -20.5, "bbox_xmax": -46.0, "bbox_ymax": -19.0}),
        # Afloramentos tem teto de 1 grau²: o bbox "certo" é o de 1°×1°.
        ("get_geological_outcrops", OUTCROP_CHEIO, BBOX_1x1),
        # Litoestratigrafia tem teto de 25 graus²: o bbox "certo" é o de 5°×5°.
        ("get_lithology_by_area", LITO_CHEIO, BBOX_5x5),
    ],
    ids=["search_mineral_occurrences", "search_rare_earth_occurrences",
         "get_geological_outcrops", "get_lithology_by_area"],
)
async def test_bbox_incompleto_ou_invertido_e_recusado_antes_da_fonte(portal, tool, cenario, quatro):
    """Até 2026-09-17 três cantos e um vazio viravam "sem bbox" em silêncio
    (a busca ignorava a área e devolvia a UF inteira como resposta) e
    `xmin > xmax` ia ao portal. Agora a recusa é na borda, nomeando o que
    faltou ou o que está invertido, e o portal não é tocado."""
    fonte = portal(cenario)
    geometria = ",".join(str(quatro[k]) for k in ("bbox_xmin", "bbox_ymin", "bbox_xmax", "bbox_ymax"))
    async with conectar() as cliente:
        tres = await cliente.call_tool(tool, {k: v for k, v in quatro.items() if k != "bbox_ymax"})
        assert tres.is_error and "bbox_ymax" in tres.content[0].text, tres.content[0].text
        um = await cliente.call_tool(tool, {"bbox_xmin": -47.5})
        assert um.is_error and "bbox_ymin, bbox_xmax, bbox_ymax" in um.content[0].text
        invertido = await cliente.call_tool(tool, {**quatro, "bbox_xmin": -46.0, "bbox_xmax": -47.5})
        assert invertido.is_error and "invertido" in invertido.content[0].text
        vazio = await cliente.call_tool(tool, {**quatro, "bbox_ymin": quatro["bbox_ymax"]})
        assert vazio.is_error and "invertido" in vazio.content[0].text
        fora = await cliente.call_tool(tool, {**quatro, "bbox_ymin": -95.0})
        assert fora.is_error and "bbox_ymin=-95.0" in fora.content[0].text
        assert fonte.requisicoes == [], "bbox inválido chegou ao portal"

        certo = await cliente.call_tool(tool, {**quatro, "limit": 1})
        assert not certo.is_error, certo.content[0].text
        assert fonte.requisicoes[-1].url.params["geometry"] == geometria
        # Sem bbox: afloramentos exige uf + municipality; litoestratigrafia
        # exige um ponto (e então `geometry` é o ponto); as outras aceitam só uf.
        if tool == "get_lithology_by_area":
            sem_bbox = {**PONTO_BH, "limit": 1}
        else:
            sem_bbox = {"uf": "MG", "limit": 1}
            if tool == "get_geological_outcrops":
                sem_bbox["municipality"] = "Santa Bárbara"
        nenhum = await cliente.call_tool(tool, sem_bbox)
        assert not nenhum.is_error, nenhum.content[0].text
        if tool == "get_lithology_by_area":
            assert fonte.requisicoes[-1].url.params["geometryType"] == "esriGeometryPoint"
        else:
            assert "geometry" not in fonte.requisicoes[-1].url.params


async def test_rochas_relacionadas_e_opt_in(portal):
    """Default de `include_related_rocks` é False desde 2026-09-17: com True
    a busca de ETR baixava 2.383 registros (2,7 MB, 5,5 s) e 2.291 deles
    (96%) eram pegmatitos, que hospedam de tudo; só por substância são 74
    (60 KB, 1,5 s). O inputSchema anuncia o default, a descrição diz o custo
    de cada modo e a chamada sem o argumento não põe rocha na WHERE."""
    fonte = portal(CHEIO)
    async with conectar() as cliente:
        tools = {t.name: t for t in (await cliente.list_tools()).tools}
        prop = tools["search_rare_earth_occurrences"].input_schema["properties"]["include_related_rocks"]
        assert prop.get("default") is False, prop
        assert "2.383" in tools["search_rare_earth_occurrences"].description
        assert "96%" in tools["search_rare_earth_occurrences"].description

        sem = await cliente.call_tool("search_rare_earth_occurrences", {"limit": 1})
        com = await cliente.call_tool(
            "search_rare_earth_occurrences", {"limit": 1, "include_related_rocks": True}
        )
    assert not sem.is_error and not com.is_error
    where_sem = fonte.requisicoes[0].url.params["where"]
    where_com = fonte.requisicoes[1].url.params["where"]
    assert "ROCHAS_HOSPEDEIRAS" not in where_sem
    assert all(f"ROCHAS_HOSPEDEIRAS LIKE '%{r}%'" in where_com for r in REE_HOST_ROCKS)
    assert sem.structured_content["search_terms_used"] == list(REE_SEARCH_TERMS)


# ---------------------------------------------------------------------------
# Sessão 3 (2026-09-17, 0.6.0): afloramentos — filtro obrigatório na borda
# ---------------------------------------------------------------------------


async def test_afloramentos_exigem_filtro_antes_da_fonte(portal):
    """A camada tem 360.042 pontos, a fonte não pagina e só corta sem filtro
    nenhum (300.000, `exceededTransferLimit`): sem filtro a tool baixaria a
    camada inteira cortada e a chamaria de resposta. A recusa é na borda —
    sem filtro, só uf, só municipality, ou bbox acima de 1 grau quadrado —
    nomeando o que faltou, e o portal não é tocado."""
    fonte = portal(OUTCROP_CHEIO)
    async with conectar() as cliente:
        nada = await cliente.call_tool("get_geological_outcrops", {})
        assert nada.is_error and "360.042" in nada.content[0].text
        assert "uf e municipality" in nada.content[0].text
        so_uf = await cliente.call_tool("get_geological_outcrops", {"uf": "MG"})
        assert so_uf.is_error and "faltou municipality" in so_uf.content[0].text
        so_mun = await cliente.call_tool("get_geological_outcrops", {"municipality": "Santa Bárbara"})
        assert so_mun.is_error and "faltou uf" in so_mun.content[0].text
        # 2°×2° = 4 graus² (22.042 pontos / 7,9 MB na região mais densa).
        grande = await cliente.call_tool(
            "get_geological_outcrops",
            {"bbox_xmin": -45.0, "bbox_ymin": -21.0, "bbox_xmax": -43.0, "bbox_ymax": -19.0},
        )
        assert grande.is_error, grande.content[0].text
        assert "grande demais" in grande.content[0].text
        assert "4 graus quadrados" in grande.content[0].text
        assert f"teto é {OUTCROP_BBOX_MAX_DEG2:g}" in grande.content[0].text
        # Um fio acima do teto também recusa; o teto exato passa.
        acima = await cliente.call_tool(
            "get_geological_outcrops", {**BBOX_1x1, "bbox_xmax": BBOX_1x1["bbox_xmax"] + 0.01}
        )
        assert acima.is_error and "grande demais" in acima.content[0].text
        assert fonte.requisicoes == [], "chamada sem filtro válido chegou ao portal"

        no_teto = await cliente.call_tool("get_geological_outcrops", BBOX_1x1)
        assert not no_teto.is_error, no_teto.content[0].text
        # uf + municipality podem combinar com o bbox.
        combinado = await cliente.call_tool(
            "get_geological_outcrops", {**BBOX_1x1, "uf": "MG", "municipality": "Santa Bárbara"}
        )
        assert not combinado.is_error
        params = fonte.requisicoes[-1].url.params
        assert params["where"] == "UF = 'MG' AND MUNICIPIO = 'Santa Bárbara'"
        assert params["geometry"] == "-44.5,-20.5,-43.5,-19.5"
        assert len(fonte.requisicoes) == 2


async def test_afloramentos_uma_ida_so_com_os_campos_da_resposta(portal):
    """Como as buscas de ocorrências: uma requisição, `outFields` explícito
    (constants.OUTCROP_FIELDS, sem `DESCRICAO`, que quase dobra a resposta),
    geometria pedida, sem `returnCountOnly` (dá 400 nesta camada com
    geometria) e `total_count` igual ao que a query devolveu. Município por
    igualdade, com aspas escapadas."""
    fonte = portal(OUTCROP_CHEIO)
    async with conectar() as cliente:
        resultado = await cliente.call_tool(
            "get_geological_outcrops", {"uf": "MG", "municipality": "Santana d'Água", "limit": 1}
        )
    assert not resultado.is_error, resultado.content[0].text
    assert len(fonte.requisicoes) == 1
    params = fonte.requisicoes[0].url.params
    assert params["outFields"] == ",".join(OUTCROP_FIELDS)
    assert "DESCRICAO" not in OUTCROP_FIELDS
    assert params["returnGeometry"] == "true" and "returnCountOnly" not in params
    assert params["where"] == "UF = 'MG' AND MUNICIPIO = 'Santana d''Água'"
    assert resultado.structured_content["total_count"] == len(OUTCROP_CHEIO.features)
    assert resultado.structured_content["count"] == 1


def test_data_de_cadastro_converte_epoch_em_ms():
    """`DATA_CADASTRO` chega como esriFieldTypeDate (epoch em milissegundos,
    UTC): 867369600000 é 1997-06-27; nulo fica nulo."""
    assert outcrops_module.registered_at_iso(867369600000) == "1997-06-27"
    assert outcrops_module.registered_at_iso(0) == "1970-01-01"
    assert outcrops_module.registered_at_iso(None) is None


# ---------------------------------------------------------------------------
# Sessão 3 (2026-09-17, 0.7.0): litoestratigrafia — recorte obrigatório,
# sem geometria, agregação no cliente
# ---------------------------------------------------------------------------


async def test_litoestratigrafia_exige_recorte_antes_da_fonte(portal):
    """A camada tem 46.712 polígonos e a fonte não pagina: sem recorte a tool
    baixaria o mapa inteiro. A recusa é na borda — sem nada, só lon, só lat,
    bbox acima de 25 graus², ponto fora do globo, ou bbox E ponto juntos —
    nomeando o que faltou, e o portal não é tocado."""
    fonte = portal(LITO_CHEIO)
    async with conectar() as cliente:
        nada = await cliente.call_tool("get_lithology_by_area", {})
        assert nada.is_error and "46.712" in nada.content[0].text
        assert f"{LITHOLOGY_BBOX_MAX_DEG2:g} graus quadrados" in nada.content[0].text
        so_lon = await cliente.call_tool("get_lithology_by_area", {"lon": -43.94})
        assert so_lon.is_error and "faltou lat" in so_lon.content[0].text
        so_lat = await cliente.call_tool("get_lithology_by_area", {"lat": -19.92})
        assert so_lat.is_error and "faltou lon" in so_lat.content[0].text
        fora = await cliente.call_tool("get_lithology_by_area", {"lon": -43.94, "lat": 95.0})
        assert fora.is_error and "lat=95.0" in fora.content[0].text
        # 6°×5° = 30 graus² (o teto é 25).
        grande = await cliente.call_tool(
            "get_lithology_by_area", {**BBOX_5x5, "bbox_xmin": -49.0},
        )
        assert grande.is_error, grande.content[0].text
        assert "grande demais" in grande.content[0].text
        assert "30 graus quadrados" in grande.content[0].text
        assert f"teto é {LITHOLOGY_BBOX_MAX_DEG2:g}" in grande.content[0].text
        assert "ponto" in grande.content[0].text
        # Um fio acima do teto também recusa.
        acima = await cliente.call_tool(
            "get_lithology_by_area", {**BBOX_5x5, "bbox_xmax": BBOX_5x5["bbox_xmax"] + 0.01}
        )
        assert acima.is_error and "grande demais" in acima.content[0].text
        juntos = await cliente.call_tool("get_lithology_by_area", {**BBOX_5x5, **PONTO_BH})
        assert juntos.is_error and "não os dois" in juntos.content[0].text
        assert fonte.requisicoes == [], "chamada sem recorte válido chegou ao portal"

        no_teto = await cliente.call_tool("get_lithology_by_area", BBOX_5x5)
        assert not no_teto.is_error, no_teto.content[0].text
        ponto = await cliente.call_tool("get_lithology_by_area", PONTO_BH)
        assert not ponto.is_error, ponto.content[0].text
        assert len(fonte.requisicoes) == 2


async def test_litoestratigrafia_uma_ida_sem_geometria_com_os_campos_da_resposta(portal):
    """Uma requisição, `outFields` explícito (constants.LITHOLOGY_FIELDS, com
    `SHAPE.AREA` e sem `LEGENDA`), `returnGeometry=false` SEMPRE (com
    geometria o 1°×1° é 35× maior), sem `returnCountOnly`; por bbox manda
    envelope, por ponto manda `esriGeometryPoint` com "lon,lat"."""
    fonte = portal(LITO_CHEIO)
    async with conectar() as cliente:
        por_bbox = await cliente.call_tool("get_lithology_by_area", {**BBOX_5x5, "limit": 1})
        por_ponto = await cliente.call_tool("get_lithology_by_area", PONTO_BH)
    assert not por_bbox.is_error and not por_ponto.is_error
    assert len(fonte.requisicoes) == 2
    assert "SHAPE.AREA" in LITHOLOGY_FIELDS and "LEGENDA" not in LITHOLOGY_FIELDS
    for requisicao in fonte.requisicoes:
        params = requisicao.url.params
        assert params["outFields"] == ",".join(LITHOLOGY_FIELDS)
        assert params["returnGeometry"] == "false" and "returnCountOnly" not in params
        assert params["where"] == "1=1"
        assert params["spatialRel"] == "esriSpatialRelIntersects" and params["inSR"] == "4326"
    envelope, ponto = (r.url.params for r in fonte.requisicoes)
    assert envelope["geometryType"] == "esriGeometryEnvelope"
    assert envelope["geometry"] == "-48.0,-23.0,-43.0,-18.0"
    assert ponto["geometryType"] == "esriGeometryPoint"
    assert ponto["geometry"] == "-43.94,-19.92"
    # `limit` corta unidades, não polígonos: polygon_count segue 3.
    assert por_bbox.structured_content["count"] == 1
    assert por_bbox.structured_content["total_count"] == 2
    assert por_bbox.structured_content["polygon_count"] == len(LITO_CHEIO.features)


def test_agregacao_por_sigla():
    """`aggregate_units` é a derivação que a proveniência declara: agrupa por
    SIGLA, conta polígonos, soma SHAPE.AREA (nulos não somam; unidade sem
    área nenhuma fica com area_deg2 nulo e vai ao fim), ordena por área
    decrescente com desempate pela sigla, e não descarta polígono nenhum —
    SIGLA nula agrega numa unidade de code nulo."""
    sem_area = {"attributes": {**LITO_BAMBUI["attributes"], "SIGLA": "ZZZ", "SHAPE.AREA": None}}
    unidades = lithology_module.aggregate_units(
        [LITO_CAUE_1, LITO_MAGRO_POLIGONO, sem_area, LITO_BAMBUI, LITO_CAUE_2, LITO_MAGRO_POLIGONO]
    )
    assert [u["code"] for u in unidades] == ["NP3bsh", "A4PP1mic", "ZZZ", None]
    assert [u["polygon_count"] for u in unidades] == [1, 2, 1, 2]
    assert unidades[1]["area_deg2"] == pytest.approx(0.05)
    assert unidades[2]["area_deg2"] is None and unidades[3]["area_deg2"] is None
    assert sum(u["polygon_count"] for u in unidades) == 6
    # Os atributos descritivos vêm do primeiro polígono da unidade.
    assert unidades[1]["name"] == "Formação Cauê" and unidades[1]["system_max"] is None
    assert set(unidades[0]) == {
        "code", "name", "hierarchy", "parent_code", "parent_name", "lithotypes",
        "age_min_ma", "age_max_ma", "eon_min", "eon_max", "era_min", "era_max",
        "system_min", "system_max", "epoch_min", "epoch_max", "polygon_count", "area_deg2",
    }
    # Área parcialmente nula: soma só o que veio.
    parcial = lithology_module.aggregate_units([LITO_CAUE_1, {"attributes": {**LITO_CAUE_1["attributes"], "SHAPE.AREA": None}}])
    assert parcial[0]["polygon_count"] == 2 and parcial[0]["area_deg2"] == pytest.approx(0.02)
    assert lithology_module.aggregate_units([]) == []

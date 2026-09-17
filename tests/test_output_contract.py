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

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import jsonschema
import pytest
from mcp import Client

from geosgb_mcp import server as server_module
from geosgb_mcp.constants import BASE_URL, ENDPOINTS
from geosgb_mcp.tools import occurrences as occurrences_module

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
        "TIPOLOGIA": "Carbonatítica",
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
        "TIPOLOGIA": None,
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
    """O que o portal responde: `returnCountOnly` -> count; query -> features."""

    count: int
    features: list[dict[str, Any]] = field(default_factory=list)


CHEIO = Cenario(count=2, features=[FEATURE_CHEIA, FEATURE_CHEIA_2])
MAGRO = Cenario(count=1, features=[FEATURE_MAGRA])
VAZIO = Cenario(count=0, features=[])
SUBSTANCIAS_CHEIAS = Cenario(
    count=3,
    features=[
        {"attributes": {"SUBSTANCIAS": "Ouro, Prata"}},
        {"attributes": {"SUBSTANCIAS": "Ouro"}},
        {"attributes": {"SUBSTANCIAS": " Nióbio "}},
    ],
)
SUBSTANCIAS_MAGRAS = Cenario(
    count=2,
    features=[{"attributes": {"SUBSTANCIAS": None}}, {"attributes": {}}],
)

URL_QUERY = f"{BASE_URL}{ENDPOINTS['ocorrencias']}/query"


def _handler_para(cenario: Cenario):
    def handler(request: httpx.Request) -> httpx.Response:
        url_sem_query = str(request.url).split("?", 1)[0]
        if url_sem_query != URL_QUERY:
            raise AssertionError(f"requisição inesperada: {request.url}")
        if request.url.params.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": cenario.count})
        return httpx.Response(200, json={"features": cenario.features})

    return handler


@pytest.fixture
def portal(monkeypatch):
    """Devolve `usar(cenario)`: a partir daí todo `httpx.AsyncClient` novo
    responde pelo cenário, sem rede. O cliente lê `httpx.AsyncClient` como
    atributo do módulo em `_get_client`, então a troca pega."""

    def usar(cenario: Cenario) -> None:
        transporte = httpx.MockTransport(_handler_para(cenario))

        class AsyncClientFalso(httpx.AsyncClient):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(transport=transporte, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", AsyncClientFalso)

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
        {"count": 1, "total_count": 2, "offset": 1, "features.0.id": 4102,
         "features.0.coordinates": {"lon": -46.8261, "lat": -19.9153},
         "features.0.municipality": "Tapira"},
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
         "search_terms_used": ["Terras raras", "ETR", "Monazita", "Bastnasita", "Xenotima", "Carbonatito", "Pegmatito"]},
    ),
    Caso(
        "search_rare_earth_occurrences",
        "magro",
        "registro com atributos nulos, sem geometria, sem rochas relacionadas",
        MAGRO,
        {"include_related_rocks": False},
        {"features.0.coordinates": None, "features.0.host_rocks": None,
         "search_terms_used": ["Terras raras", "ETR", "Monazita", "Bastnasita", "Xenotima"]},
    ),
    Caso(
        "get_occurrence_details",
        "cheio",
        "ocorrência com todos os atributos e geometria",
        Cenario(count=1, features=[FEATURE_CHEIA]),
        {"occurrence_id": 4101},
        {"id": 4101, "enclosing_rocks": "Gnaisse", "sheet_code": "SE-23-Y-C",
         "coordinates": {"lon": -46.9439, "lat": -19.5836}},
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
        {"count": 3, "substances": ["Nióbio", "Ouro", "Prata"]},
    ),
    Caso(
        "list_mineral_substances",
        "magro",
        "atributo nulo e atributo ausente (lista vazia, count zero)",
        SUBSTANCIAS_MAGRAS,
        {},
        {"count": 0, "substances": []},
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
        for nome in ("search_mineral_occurrences", "search_rare_earth_occurrences"):
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

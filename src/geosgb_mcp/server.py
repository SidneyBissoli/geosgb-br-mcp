"""
MCP Server para dados geológicos do Serviço Geológico do Brasil (SGB).

Este servidor expõe tools para consultar:
- Ocorrências minerais
- Busca específica de Elementos Terras Raras (ETRs)
- Detalhes de ocorrências
- Lista de substâncias minerais
"""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .constants import DEFAULT_LIMIT, MAX_LIMIT
from .models import (
    OccurrenceDetails,
    OccurrenceSearchResult,
    RareEarthSearchResult,
    SubstanceList,
)

# SDK 2.x (migrado em 2026-09-17): `FastMCP` virou `MCPServer`. O decorador
# `@mcp.tool()` e a conversão do retorno não mudaram.
mcp = MCPServer("geosgb")

# Contrato de saída: cada tool anota o retorno com um modelo de models.py.
# Com isso o servidor publica `outputSchema` em tools/list, preenche
# `structuredContent` em tools/call e reprova em runtime resposta que não
# obedece (vira `isError`). Retorno `-> dict` não gera esquema nenhum — foi
# assim até 2026-09. Gate: tests/test_output_contract.py.


@mcp.tool()
async def search_mineral_occurrences(
    substance: str | None = None,
    uf: str | None = None,
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
        uf: Sigla do estado brasileiro (ex: "MG", "GO", "BA", "AM")
        municipality: Nome do município
        economic_status: Status econômico da ocorrência ("Mina", "Garimpo", "Ocorrencia", "Indeterminado")
        bbox_xmin: Longitude mínima do bounding box (WGS84)
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
    """
    from .tools.occurrences import search_mineral_occurrences as _search

    bbox = None
    if all(v is not None for v in [bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax]):
        bbox = (bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)

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
    uf: str | None = None,
    bbox_xmin: float | None = None,
    bbox_ymin: float | None = None,
    bbox_xmax: float | None = None,
    bbox_ymax: float | None = None,
    include_related_rocks: bool = True,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> RareEarthSearchResult:
    """
    Busca ocorrências de Elementos Terras Raras (ETRs) no Brasil.

    ETRs são 17 elementos químicos estratégicos para tecnologias de transição
    energética, incluindo lantanídeos, escândio e ítrio.

    Args:
        uf: Sigla do estado (ex: "MG", "GO", "BA")
        bbox_xmin: Longitude mínima
        bbox_ymin: Latitude mínima
        bbox_xmax: Longitude máxima
        bbox_ymax: Latitude máxima
        include_related_rocks: Se True, inclui ocorrências em carbonatitos e
                               rochas alcalinas (hospedeiras típicas de ETRs)
        limit: Número máximo de resultados

    Returns:
        Dicionário com ocorrências de ETRs e termos de busca utilizados
    """
    from .tools.occurrences import search_rare_earth_occurrences as _search

    bbox = None
    if all(v is not None for v in [bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax]):
        bbox = (bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax)

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
        - Tipologia e província mineral
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

    Útil para descobrir quais minerais estão disponíveis para consulta.

    Returns:
        Lista de substâncias minerais únicas ordenadas alfabeticamente
    """
    from .tools.occurrences import list_mineral_substances as _list_substances

    return await _list_substances()


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

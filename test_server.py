"""Teste do servidor MCP GeoSGB."""

import asyncio
from geosgb_mcp.tools.occurrences import search_mineral_occurrences, search_rare_earth_occurrences


async def test():
    print("=" * 60)
    print("Teste 1: Buscar ocorrências em Minas Gerais")
    print("=" * 60)

    result = await search_mineral_occurrences(uf="MG", limit=5)
    print(f"Total em MG: {result['total_count']}")
    print(f"Retornados: {result['count']}")
    for f in result["features"]:
        subst = f["substance"][:50] if f["substance"] else "N/A"
        print(f"  - {f['municipality']}: {subst}...")

    print("\n" + "=" * 60)
    print("Teste 2: Buscar ocorrências de Terras Raras")
    print("=" * 60)

    result = await search_rare_earth_occurrences(limit=5)
    print(f"Total de ETRs: {result['total_count']}")
    print(f"Retornados: {result['count']}")
    for f in result["features"]:
        subst = f["substance"][:50] if f["substance"] else "N/A"
        print(f"  - {f['uf']}/{f['municipality']}: {subst}...")

    print("\n" + "=" * 60)
    print("Testes concluidos com sucesso!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test())

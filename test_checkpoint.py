#!/usr/bin/env python3
"""
Checkpoint FASE 2: Teste manual das tools principais.
Execute: python test_checkpoint.py
"""

import asyncio


async def test():
    from geosgb_mcp.tools.occurrences import (
        search_mineral_occurrences,
        search_rare_earth_occurrences,
        list_mineral_substances,
        get_occurrence_details,
    )

    print("=" * 60)
    print("CHECKPOINT FASE 2 - Teste Manual das Tools")
    print("=" * 60)

    # Teste 1: search_mineral_occurrences
    print("\n[1] search_mineral_occurrences(uf='MG', limit=2)")
    print("-" * 50)
    try:
        r1 = await search_mineral_occurrences(uf="MG", limit=2)
        print(f"  ✓ Retornou {r1['count']} resultados (total: {r1['total_count']})")
        if r1["features"]:
            f = r1["features"][0]
            print(f"    Exemplo: {f['municipality']} - {f['substance'][:40] if f['substance'] else 'N/A'}...")
    except Exception as e:
        print(f"  ✗ Erro: {e}")

    # Teste 2: search_rare_earth_occurrences
    print("\n[2] search_rare_earth_occurrences(limit=2)")
    print("-" * 50)
    try:
        r2 = await search_rare_earth_occurrences(limit=2)
        print(f"  ✓ Retornou {r2['count']} resultados (total: {r2['total_count']})")
        print(f"    Termos usados: {len(r2['search_terms_used'])} termos")
    except Exception as e:
        print(f"  ✗ Erro: {e}")

    # Teste 3: list_mineral_substances
    print("\n[3] list_mineral_substances()")
    print("-" * 50)
    try:
        r3 = await list_mineral_substances()
        print(f"  ✓ Encontradas {r3['count']} substâncias")
        print(f"    Exemplos: {r3['substances'][:5]}")
    except Exception as e:
        print(f"  ✗ Erro: {e}")

    # Teste 4: get_occurrence_details
    print("\n[4] get_occurrence_details()")
    print("-" * 50)
    try:
        if r1["features"]:
            occ_id = r1["features"][0]["id"]
            r4 = await get_occurrence_details(occ_id)
            print(f"  ✓ Detalhes da ocorrência {occ_id}:")
            print(f"    Município: {r4.get('municipality')}")
            print(f"    Substância: {r4.get('substance', 'N/A')[:40]}...")
        else:
            print("  ⚠ Sem ocorrências para testar detalhes")
    except Exception as e:
        print(f"  ✗ Erro: {e}")

    print("\n" + "=" * 60)
    print("✓ Checkpoint FASE 2 concluído")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test())

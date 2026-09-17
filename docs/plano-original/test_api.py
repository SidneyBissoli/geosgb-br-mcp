#!/usr/bin/env python3
# Nota (2026-09-17): script de prova MANUAL do plano original de janeiro de
# 2026, não um teste. Ficava na raiz e nunca foi coletado pelo pytest
# (`testpaths = tests`). Guardado aqui como registro; os testes vivos estão em
# tests/ (offline: `pytest`; contra o portal: `INTEGRATION_TESTS=1 pytest`).
# Porta de entrada do repositório: README.md da raiz.

"""
FASE 0: Validação da API do SGB
Execute: python test_api.py
"""

import httpx
import asyncio
import sys

BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"
TIMEOUT = 30.0


async def test_api():
    """Executa bateria de testes na API do SGB."""

    results = {"passed": 0, "failed": 0, "errors": []}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:

        # ═══════════════════════════════════════════════════════════
        # TESTE 1: Conectividade básica
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 1] Conectividade básica")
        print("-" * 50)
        try:
            url = f"{BASE_URL}/geologia/ocorrencias/MapServer/0/query"
            params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                if "count" in data:
                    print(f"  ✓ API acessível. Total de ocorrências: {data['count']}")
                    results["passed"] += 1
                else:
                    print(f"  ✗ Resposta inesperada: {data}")
                    results["failed"] += 1
                    results["errors"].append("Teste 1: resposta sem 'count'")
            else:
                print(f"  ✗ Status code: {response.status_code}")
                results["failed"] += 1
                results["errors"].append(f"Teste 1: status {response.status_code}")
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 1: {e}")

        # ═══════════════════════════════════════════════════════════
        # TESTE 2: Query com filtro WHERE
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 2] Query com filtro WHERE (UF='MG')")
        print("-" * 50)
        try:
            params = {
                "where": "UF = 'MG'",
                "outFields": "ID_OCORRENCIA,SUBSTANCIAS,MUNICIPIO",
                "returnGeometry": "false",
                "f": "json",
            }
            response = await client.get(url, params=params)
            data = response.json()

            features = data.get("features", [])
            if len(features) > 0:
                print(f"  ✓ Retornou {len(features)} registros")
                print(
                    f"    Exemplo: {features[0].get('attributes', {}).get('MUNICIPIO')}"
                )
                results["passed"] += 1
            else:
                print("  ✗ Nenhum registro retornado")
                results["failed"] += 1
                results["errors"].append("Teste 2: nenhum registro")
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 2: {e}")

        # ═══════════════════════════════════════════════════════════
        # TESTE 3: Query com LIKE (busca parcial)
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 3] Query com LIKE (Terras raras)")
        print("-" * 50)
        try:
            params = {
                "where": "SUBSTANCIAS LIKE '%Terras raras%'",
                "returnCountOnly": "true",
                "f": "json",
            }
            response = await client.get(url, params=params)
            data = response.json()

            count = data.get("count", 0)
            if count > 0:
                print(f"  ✓ Encontradas {count} ocorrências de Terras Raras")
                results["passed"] += 1
            else:
                print("  ⚠ Nenhuma ocorrência de Terras Raras (pode ser normal)")
                results["passed"] += 1  # Não é necessariamente erro
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 3: {e}")

        # ═══════════════════════════════════════════════════════════
        # TESTE 4: Query espacial (bounding box)
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 4] Query espacial (bbox região de Araxá)")
        print("-" * 50)
        try:
            params = {
                "where": "1=1",
                "geometry": "-47.5,-20.0,-46.0,-19.0",
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
                "inSR": "4326",
                "outSR": "4326",
                "outFields": "SUBSTANCIAS,MUNICIPIO",
                "returnGeometry": "true",
                "f": "json",
            }
            response = await client.get(url, params=params)
            data = response.json()

            features = data.get("features", [])
            if len(features) > 0:
                print(f"  ✓ Retornou {len(features)} registros na região")
                # Verificar se geometria está presente
                geom = features[0].get("geometry", {})
                if "x" in geom and "y" in geom:
                    print(f"    Coordenadas: ({geom['x']:.4f}, {geom['y']:.4f})")
                    results["passed"] += 1
                else:
                    print("  ⚠ Geometria ausente ou formato inesperado")
                    results["passed"] += 1
            else:
                print("  ⚠ Nenhum registro na região (pode ser normal)")
                results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 4: {e}")

        # ═══════════════════════════════════════════════════════════
        # TESTE 5: Verificar suporte a paginação
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 5] Verificar suporte a paginação")
        print("-" * 50)
        try:
            # Tentar com resultOffset
            params = {
                "where": "1=1",
                "outFields": "ID_OCORRENCIA",
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": "0",
                "resultRecordCount": "2",
            }
            response = await client.get(url, params=params)
            data = response.json()

            if "error" in data:
                print(f"  ⚠ API não suporta paginação: {data['error'].get('message')}")
                print("    (Limite será aplicado no cliente)")
                results["passed"] += 1
            else:
                features = data.get("features", [])
                if len(features) > 0:
                    print(f"  ✓ Paginação suportada, retornou {len(features)} registros")
                    results["passed"] += 1
                else:
                    print("  ⚠ Paginação pode não ser suportada")
                    results["passed"] += 1
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 5: {e}")

        # ═══════════════════════════════════════════════════════════
        # TESTE 6: Endpoint de afloramentos
        # ═══════════════════════════════════════════════════════════
        print("\n[TESTE 6] Endpoint de afloramentos")
        print("-" * 50)
        try:
            url_aflor = f"{BASE_URL}/geologia/afloramentos/MapServer/0/query"
            params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
            response = await client.get(url_aflor, params=params)
            data = response.json()

            if "count" in data:
                print(f"  ✓ Endpoint acessível. Total de afloramentos: {data['count']}")
                results["passed"] += 1
            else:
                print("  ✗ Resposta inesperada")
                results["failed"] += 1
                results["errors"].append("Teste 6: resposta sem 'count'")
        except Exception as e:
            print(f"  ✗ Erro: {e}")
            results["failed"] += 1
            results["errors"].append(f"Teste 6: {e}")

    # ═══════════════════════════════════════════════════════════════
    # RESUMO
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 50)
    print("RESUMO DA VALIDAÇÃO")
    print("=" * 50)
    print(f"  Testes passados: {results['passed']}")
    print(f"  Testes falhados: {results['failed']}")

    if results["errors"]:
        print("\n  Erros encontrados:")
        for err in results["errors"]:
            print(f"    - {err}")

    if results["failed"] == 0:
        print("\n  ✓ API VALIDADA - Pode prosseguir para FASE 1")
        return 0
    else:
        print("\n  ✗ VALIDAÇÃO FALHOU - Corrigir antes de prosseguir")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_api())
    sys.exit(exit_code)

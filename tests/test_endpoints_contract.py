"""Contrato dos endpoints ArcGIS — valida, contra o geoportal REAL do SGB,
que cada caminho de ENDPOINTS ainda existe e é a camada que o nome promete.

Regra de autoria do portfólio (caso ibge-br-mcp, 2026-08): referência externa
hardcoded envelhece em silêncio. Na ativação deste contrato (2026-08-23):
  - ocorrencias, afloramentos, litoestratigrafia_1m: OK (metadados com nome
    de camada coerente);
  - litoestratigrafia_estados: o SGB REMOVEU a extensão FeatureServer do
    serviço (erro 500 "extension 'featureserver' not found"); o MapServer
    homônimo segue no diretório — o cliente precisa migrar;
  - sedimento_corrente_query_all: respondendo página de erro HTML e
    pendurando conexões.
Enquanto os dois não forem corrigidos no cliente, este teste FALHA de
propósito — a falha do workflow vira pendência no painel do portfólio.

Roda só com INTEGRATION_TESTS=1 (o resto da suíte já é live, mas este é o
único com propósito de vigília; cron semanal em .github/workflows/integration.yml).
"""

import json
import os
import urllib.request

import pytest

from geosgb_mcp.constants import BASE_URL, ENDPOINTS

LIVE = os.environ.get("INTEGRATION_TESTS") in {"1", "true"}

# O que cada endpoint DEVE ser (termo do nome real da camada, minúsculo,
# independente do rótulo interno) — a segunda declaração do contrato.
EXPECTED_NAME_TERM = {
    "ocorrencias": "ocorrências minerais",
    "afloramentos": "afloramentos",
    "litoestratigrafia_estados": "litoestratigr",
    "litoestratigrafia_1m": "litoestratigr",
    "sedimento_corrente": "sedimento",
}


def _layer_metadata(path: str) -> dict:
    url = f"{BASE_URL}{path}?f=json"
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
        except Exception as exc:  # inclui HTML de erro (json inválido) e timeout
            last = exc
    raise AssertionError(f"{path}: sem metadados JSON após 3 tentativas — {last}")


@pytest.mark.skipif(not LIVE, reason="INTEGRATION_TESTS não definido")
def test_todo_endpoint_tem_expectativa():
    faltando = [k for k in ENDPOINTS if k not in EXPECTED_NAME_TERM]
    assert faltando == [], f"endpoints sem expectativa no contrato: {faltando}"


@pytest.mark.skipif(not LIVE, reason="INTEGRATION_TESTS não definido")
@pytest.mark.parametrize("key,path", sorted(ENDPOINTS.items()))
def test_endpoint_existe_e_e_o_que_promete(key: str, path: str):
    meta = _layer_metadata(path)
    assert "error" not in meta, f"{key} ({path}): o geoportal respondeu erro {meta['error']}"
    nome = str(meta.get("name", "")).lower()
    termo = EXPECTED_NAME_TERM.get(key, key)
    assert termo in nome, (
        f"{key}: a camada em {path} chama-se '{meta.get('name')}' — "
        f"não contém '{termo}'; endpoint trocado ou reorganizado?"
    )

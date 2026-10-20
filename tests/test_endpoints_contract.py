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
RESOLVIDO em 2026-08-23 (mesmo dia, à noite): litoestratigrafia_estados
migrado para a raiz do MapServer homônimo (uma camada POR ESTADO, ids
instáveis — o contrato valida a serviceDescription); sedimento_corrente
migrado para /geoquimica/geoquimica_integrada/MapServer/2 ("Sedimento de
Corrente", 151k pontos) — o serviço query_all morreu de vez (pendura em
todos os níveis, embora ainda listado na raiz do diretório).
2026-09-17 (Sessão 3): sedimento_corrente SAIU do contrato — a camada não
tem resultado analítico (só metadados de amostragem e URL do RIGeo), então
nenhuma tool a serve e vigiá-la é custo sem retorno (ver constants.py).
Ficam quatro: ocorrencias (servida), afloramentos e litoestratigrafia_1m
(decididas a entrar) e litoestratigrafia_estados (fora até haver resolvedor).

2026-10-19 (cron): 3 dos 4 endpoints reprovaram no MESMO segundo com a mesma
resposta do ArcGIS Server — HTTP 200 e corpo `{"error": {"code": 500,
"message": "json", "details": []}}`; no dia seguinte os três respondiam
normalmente. Soluço do portal, não deriva. O leitor só re-tentava quando a
requisição LEVANTAVA (HTML inválido, timeout) e aceitava esse JSON de erro
como resposta válida, reprovando na 1ª tentativa. Desde então um erro 5xx
no corpo conta como tentativa falha (pausa e nova tentativa, até 3×); erro
4xx (caminho inexistente) e nome trocado seguem reprovando na hora — é a
deriva que o contrato existe para pegar. Os testes `test_leitor_*` abaixo
rodam OFFLINE (portal falso) e prendem essa distinção.

Roda só com INTEGRATION_TESTS=1 (o resto da suíte já é live, mas este é o
único com propósito de vigília; cron semanal em .github/workflows/integration.yml).
"""

import json
import os
import time
import urllib.request

import pytest

from geosgb_mcp.constants import BASE_URL, ENDPOINTS

LIVE = os.environ.get("INTEGRATION_TESTS") in {"1", "true"}

# Tentativas contra o portal e pausa entre elas. Três tentativas com 5 s
# cobrem um soluço de segundos (o de 19/10 durou 3 s); indisponibilidade
# mais longa reprova igual — e aí o alarme é legítimo.
RETRIES = 3
RETRY_PAUSE_S = 5.0

# O que cada endpoint DEVE ser (termo do nome real da camada, minúsculo,
# independente do rótulo interno) — a segunda declaração do contrato.
EXPECTED_NAME_TERM = {
    "ocorrencias": "ocorrências minerais",
    "afloramentos": "afloramentos",
    "litoestratigrafia_estados": "litoestratigr",
    "litoestratigrafia_1m": "litoestratigr",
}


def _is_portal_hiccup(meta: dict) -> bool:
    """O ArcGIS Server devolve falha transitória como JSON bem-formado
    (HTTP 200): `{"error": {"code": 500, "message": "json", ...}}`.
    Código >= 500 ali é o portal tropeçando, não a camada mudando; 4xx
    (404 caminho inexistente, 400 pedido inválido) é quebra real do contrato."""
    err = meta.get("error") if isinstance(meta, dict) else None
    if not isinstance(err, dict):
        return False
    try:
        return int(err.get("code", 0)) >= 500
    except (TypeError, ValueError):
        return False


def _layer_metadata(path: str) -> dict:
    url = f"{BASE_URL}{path}?f=json"
    last = None
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(RETRY_PAUSE_S)
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            meta = json.loads(body)
        except Exception as exc:  # inclui HTML de erro (json inválido) e timeout
            last = exc
            continue
        if _is_portal_hiccup(meta):
            last = f"portal respondeu erro {meta['error']}"
            continue
        return meta
    raise AssertionError(
        f"{path}: sem metadados JSON após {RETRIES} tentativas — {last}"
    )


# --- Leitor com portal falso (OFFLINE; roda no gate de push) -----------------


def _portal_falso(monkeypatch, respostas):
    """Substitui urlopen por uma fila de corpos (str = JSON do portal,
    Exception = requisição que levanta) e sleep por um contador; devolve
    o registro de chamadas."""
    fila = list(respostas)
    registro = {"urlopen": 0, "sleep": []}

    class _Resp:
        def __init__(self, corpo: str):
            self._corpo = corpo

        def read(self) -> bytes:
            return self._corpo.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen_falso(url, timeout=None):
        registro["urlopen"] += 1
        proxima = fila.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return _Resp(proxima)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen_falso)
    monkeypatch.setattr(time, "sleep", lambda s: registro["sleep"].append(s))
    return registro


ERRO_500 = json.dumps({"error": {"code": 500, "message": "json", "details": []}})
ERRO_404 = json.dumps(
    {"error": {"code": 404, "message": "Unable to find layer", "details": []}}
)
CAMADA_OK = json.dumps({"name": "Afloramentos geológicos", "type": "Feature Layer"})


def test_leitor_retenta_soluco_5xx_e_devolve_a_camada(monkeypatch):
    reg = _portal_falso(monkeypatch, [ERRO_500, ERRO_500, CAMADA_OK])
    meta = _layer_metadata("/x/MapServer/0")
    assert meta["name"] == "Afloramentos geológicos"
    assert reg["urlopen"] == 3
    assert reg["sleep"] == [RETRY_PAUSE_S, RETRY_PAUSE_S]


def test_leitor_nao_retenta_erro_4xx(monkeypatch):
    # 404 é deriva (caminho sumiu): volta na 1ª tentativa para a asserção
    # do contrato reprovar na hora, sem gastar pausa.
    reg = _portal_falso(monkeypatch, [ERRO_404, CAMADA_OK])
    meta = _layer_metadata("/x/MapServer/0")
    assert meta["error"]["code"] == 404
    assert reg["urlopen"] == 1
    assert reg["sleep"] == []


def test_leitor_reprova_5xx_persistente(monkeypatch):
    reg = _portal_falso(monkeypatch, [ERRO_500] * RETRIES)
    with pytest.raises(AssertionError, match="3 tentativas.*500"):
        _layer_metadata("/x/MapServer/0")
    assert reg["urlopen"] == RETRIES


def test_leitor_retenta_requisicao_que_levanta(monkeypatch):
    # Comportamento anterior preservado: HTML de erro / timeout seguem
    # contando como tentativa falha.
    reg = _portal_falso(monkeypatch, [TimeoutError("timed out"), CAMADA_OK])
    meta = _layer_metadata("/x/MapServer/0")
    assert meta["name"] == "Afloramentos geológicos"
    assert reg["urlopen"] == 2


@pytest.mark.skipif(not LIVE, reason="INTEGRATION_TESTS não definido")
def test_todo_endpoint_tem_expectativa():
    faltando = [k for k in ENDPOINTS if k not in EXPECTED_NAME_TERM]
    assert faltando == [], f"endpoints sem expectativa no contrato: {faltando}"


@pytest.mark.skipif(not LIVE, reason="INTEGRATION_TESTS não definido")
@pytest.mark.parametrize("key,path", sorted(ENDPOINTS.items()))
def test_endpoint_existe_e_e_o_que_promete(key: str, path: str):
    meta = _layer_metadata(path)
    assert "error" not in meta, f"{key} ({path}): o geoportal respondeu erro {meta['error']}"
    # Camada tem "name"; raiz de serviço (caso litoestratigrafia_estados) não —
    # lá a identidade está na serviceDescription.
    nome = str(meta.get("name") or meta.get("serviceDescription") or "").lower()
    termo = EXPECTED_NAME_TERM.get(key, key)
    assert termo in nome, (
        f"{key}: o recurso em {path} identifica-se como "
        f"'{(meta.get('name') or meta.get('serviceDescription') or '')[:120]}' — "
        f"não contém '{termo}'; endpoint trocado ou reorganizado?"
    )

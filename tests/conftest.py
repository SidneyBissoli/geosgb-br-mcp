"""Separa a suíte OFFLINE (roda a cada push) da suíte VIVA (bate no geoportal).

`test_client.py` e `test_tools_occurrences.py` consultam o portal real do SGB:
servem como vigília, não como gate — um portal lento ou fora do ar não pode
derrubar um push. Ficam atrás do mesmo interruptor que
`test_endpoints_contract.py` já usa: `INTEGRATION_TESTS=1`.

Sem a variável, `pytest` roda só o que não toca a rede: modelos e o contrato
de saída (`test_output_contract.py`, que tem sua própria fonte falsa).
"""

import os

import pytest

LIVE_MODULES = {"test_client.py", "test_tools_occurrences.py"}


def pytest_collection_modifyitems(config, items):
    if os.environ.get("INTEGRATION_TESTS") == "1":
        return
    skip = pytest.mark.skip(
        reason="bate no geoportal vivo do SGB; rode com INTEGRATION_TESTS=1"
    )
    for item in items:
        if item.path.name in LIVE_MODULES:
            item.add_marker(skip)

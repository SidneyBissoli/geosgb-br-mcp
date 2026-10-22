"""Separa a suíte OFFLINE (roda a cada push) da suíte VIVA (bate no geoportal).

`test_client.py`, `test_tools_occurrences.py`, `test_tools_outcrops.py` e
`test_tools_lithology.py`
consultam o portal real do SGB: servem como vigília, não como gate — um
portal lento ou fora do ar não pode derrubar um push. Ficam atrás do mesmo
interruptor que `test_endpoints_contract.py` já usa: `INTEGRATION_TESTS=1`.

Sem a variável, `pytest` roda só o que não toca a rede: modelos e o contrato
de saída (`test_output_contract.py`, que tem sua própria fonte falsa).

A lista é EXPLÍCITA: módulo vivo novo que não entrar aqui roda no CI offline.

Fonte indisponível ≠ deriva (2026-10-22, item mcp:fonte-indisponivel-nao-e-
deriva): o contrato vivo registra no `stash` da sessão os endpoints em que o
portal não respondeu nada medível, e `pytest_terminal_summary` escreve a
anotação do GitHub Actions `::warning title=Fonte indisponível::a, b` — o
MESMO contrato que os servidores TypeScript do portfólio emitem pelo
@sbissoli/mcp-live-source, lido pelo painel em check-runs/{job}/annotations.
Escrita pelo repórter do terminal, não por `print`: o stdout dos testes é
capturado, e o runner só reconhece o comando no início de uma linha do
stdout do processo. Também vai ao `$GITHUB_STEP_SUMMARY` quando existe.
"""

import os

import pytest

LIVE_MODULES = {
    "test_client.py",
    "test_tools_occurrences.py",
    "test_tools_outcrops.py",
    "test_tools_lithology.py",
}

# Contrato com o painel do portfólio: título FIXO, mensagem "a, b".
TITULO_FONTE_INDISPONIVEL = "Fonte indisponível"
FONTE_INDISPONIVEL: pytest.StashKey[list[str]] = pytest.StashKey()


def anotacao_fonte_indisponivel(nomes: list[str]) -> str:
    """O comando de workflow, com o escape do runner na mensagem
    (`%`, CR e LF — os nomes de endpoint não os têm, mas o contrato é este)."""
    mensagem = ", ".join(nomes).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::warning title={TITULO_FONTE_INDISPONIVEL}::{mensagem}"


def pytest_configure(config):
    config.stash[FONTE_INDISPONIVEL] = []


def pytest_collection_modifyitems(config, items):
    if os.environ.get("INTEGRATION_TESTS") == "1":
        return
    skip = pytest.mark.skip(
        reason="bate no geoportal vivo do SGB; rode com INTEGRATION_TESTS=1"
    )
    for item in items:
        if item.path.name in LIVE_MODULES:
            item.add_marker(skip)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    nomes = config.stash.get(FONTE_INDISPONIVEL, [])
    if not nomes:
        return
    terminalreporter.write_line(
        f"Fonte indisponível — deriva NÃO medida ({len(nomes)}): {', '.join(nomes)}"
    )
    terminalreporter.write_line(anotacao_fonte_indisponivel(nomes))
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(
                "### Teste contra a fonte viva\n\n"
                f"**Deriva NÃO medida em {len(nomes)} endpoint(s)** (fonte indisponível): "
                f"{', '.join(f'`{n}`' for n in nomes)}\n\n"
            )

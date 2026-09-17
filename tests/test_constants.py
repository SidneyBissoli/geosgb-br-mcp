"""Constantes que as tools prometem obedecer — prende o que já foi letra morta.

Até 2026-09-17 `UF_CODES` existia e ninguém lia (`uf="Minas"` virava
`UF = 'MINAS'` e devolvia zero como resposta), `DEFAULT_TIMEOUT` valia 30 aqui
e 60 fixo no cliente, e a tool de terras raras usava listas próprias em vez de
`REE_SEARCH_TERMS`/`REE_HOST_ROCKS`. Este arquivo garante que cada constante
tem exatamente um consumidor de verdade.
"""

from typing import get_args

from geosgb_mcp.client import GeoSGBClient
from geosgb_mcp.constants import DEFAULT_TIMEOUT, UF, UF_CODES


def test_uf_codes_deriva_do_literal():
    """Uma fonte só: a lista É a tupla dos membros do Literal."""
    assert UF_CODES == get_args(UF)
    assert len(UF_CODES) == 27
    assert len(set(UF_CODES)) == 27
    assert all(len(sigla) == 2 and sigla.isupper() for sigla in UF_CODES)


def test_cliente_le_o_timeout_das_constantes():
    assert GeoSGBClient().timeout == DEFAULT_TIMEOUT == 60.0


def test_termos_de_etr_sao_a_grafia_da_fonte():
    """O LIKE do portal é sensível a caixa e acento (medido em 2026-09-17:
    "Cério" casa 25 registros, "Cerio" zero; "Nióbio" 564, "Niobio" zero).
    Termo sem o acento que a fonte usa é termo morto — e não pode haver
    repetição, porque cada termo vira um OR na WHERE."""
    from geosgb_mcp.constants import REE_HOST_ROCKS, REE_SEARCH_TERMS

    for elemento in ("Cério", "Lantânio", "Neodímio", "Ítrio", "Samário", "Európio", "Gadolínio"):
        assert elemento in REE_SEARCH_TERMS
    assert len(set(REE_SEARCH_TERMS)) == len(REE_SEARCH_TERMS) == 13
    assert len(set(REE_HOST_ROCKS)) == len(REE_HOST_ROCKS) == 6
    assert not any("'" in t for t in REE_SEARCH_TERMS + REE_HOST_ROCKS), "aspas quebrariam a WHERE"

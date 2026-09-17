"""Constantes e configurações do GeoSGB MCP."""

from typing import Literal, get_args

# URLs base
BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"

# Endpoints disponíveis — fonte única da verdade (client.py importa daqui).
# Contrato vivo: tests/test_endpoints_contract.py valida cada caminho contra
# o geoportal real (cron semanal em .github/workflows/integration.yml).
ENDPOINTS = {
    "ocorrencias": "/geologia/ocorrencias/MapServer/0",
    "afloramentos": "/geologia/afloramentos/MapServer/0",
    # 2026-08: o SGB removeu a extensão FeatureServer deste serviço (erro 500
    # "extension 'featureserver' not found"); migrado para o MapServer homônimo.
    # ATENÇÃO: aponta para a RAIZ do serviço porque há uma camada POR ESTADO
    # com ids instáveis (buracos na sequência; estados novos ganham ids novos —
    # ex.: Acre 2026 = 29). Quem consumir deve resolver a camada dinamicamente
    # via ?f=json (lista `layers`) e só então chamar /<id>/query — client.query()
    # NÃO funciona direto nesta chave.
    "litoestratigrafia_estados": "/geologia/litoestratigrafia_estados/MapServer",
    "litoestratigrafia_1m": "/geologia/litoestratigrafia_1000000/MapServer/0",
    # 2026-08: /sedimento_corrente_query_all (FeatureServer e MapServer) morreu
    # na fonte — segue listado na raiz do diretório, mas responde HTML de erro
    # e pendura conexões em todos os níveis. Substituído pela camada
    # "Sedimento de Corrente" do serviço integrado de geoquímica
    # (validada ao vivo em 2026-08-23: Query ok, 151.473 pontos).
    "sedimento_corrente": "/geoquimica/geoquimica_integrada/MapServer/2",
}

# Configurações de requisição. DEFAULT_TIMEOUT é o que o cliente usa de fato
# (client.py lê daqui); até 2026-09-17 valia 30 aqui e 60 fixo no cliente, e
# ninguém lia o 30. O valor é o que vinha valendo: uma busca larga (UF inteira,
# 7,8 MB) leva ~11 s e a lista de substâncias ~18 s — 30 seria curto.
DEFAULT_TIMEOUT = 60.0
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

# Termos de busca para ETRs
REE_SEARCH_TERMS = [
    "Terras raras",
    "Elementos terras raras",
    "ETR",
    "Monazita",
    "Bastnasita",
    "Xenotima",
    "Cerio",
    "Lantanio",
    "Neodimio",
    "Itrio",
    "Samario",
    "Europio",
    "Gadolinio",
]

# Rochas hospedeiras típicas de ETRs
REE_HOST_ROCKS = [
    "Carbonatito",
    "Nefelina sienito",
    "Sienito alcalino",
    "Granito alcalino",
    "Pegmatito",
    "Fonolito",
]

# Siglas das 27 unidades da federação, como a coluna UF da fonte as grava
# (maiúsculas). O tipo é o que as tools usam no parâmetro `uf`: o SDK publica
# as siglas como `enum` no inputSchema e recusa qualquer outra coisa com a
# lista na mensagem. Até 2026-09-17 UF_CODES existia e ninguém lia:
# `uf="Minas"` virava `UF = 'MINAS'` e devolvia zero como se fosse resposta.
# `Literal[tuple(...)]` não serve (o SDK não enxerga os membros), por isso o
# Literal é explícito e a lista deriva dele — uma fonte só.
UF = Literal[
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
UF_CODES: tuple[str, ...] = get_args(UF)

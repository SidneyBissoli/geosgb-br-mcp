"""Constantes e configurações do GeoSGB MCP."""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class Layer:
    """O que a proveniência precisa saber de uma camada SERVIDA por tool.

    `path` é o mesmo caminho de ENDPOINTS (o contrato semanal vigia por lá);
    `name` é o `name` da camada e `copyright_text` o `copyrightText` do
    SERVIÇO (raiz do MapServer) — no nível da camada ele vem vazio nas quatro
    camadas vigiadas (lido em 2026-09-17) e o texto muda de serviço para
    serviço, por isso não se copia de ocorrências. `verified_at` é o dia em
    que esses valores foram lidos do `?f=pjson`.
    """

    path: str
    name: str
    copyright_text: str
    verified_at: str


# Registro das camadas que TÊM tool — só essas entram aqui; ENDPOINTS lista
# também as vigiadas e não servidas. É deste registro que `provenance.py`
# deriva o endpoint, o `dataset`, a licença (o copyrightText) e a citação:
# até 2026-09-17 (Sessão 3, pré-requisito) tudo isso era constante fixa de
# ocorrências, e a primeira tool sobre outra camada citaria a camada errada.
#
# Medido em 2026-09-17 nas três camadas vigiadas e ainda sem tool, para
# quando entrarem (o valor vai aqui, não se deduz): `afloramentos` — camada
# "Afloramentos geológicos", serviço com copyrightText "Serviço Geológico do
# Brasil - CPRM", maxRecordCount 300.000 (abaixo dos 360.042 pontos: consulta
# sem filtro CORTA), 21 campos; `litoestratigrafia_1m` — "Unidades
# litoestratigráficas - 1:1.000.000 [2004]", copyright "Serviço Geológico do
# Brasil - CPRM", maxRecordCount 100.000, 30 campos, polígonos;
# `sedimento_corrente` — "Sedimento de Corrente" (camada 2 de
# geoquimica_integrada), copyright "Serviço Geológico do Brasil - CPRM",
# maxRecordCount 1.000, 52 campos. Só ocorrências traz "SGB" no copyright.
LAYERS: dict[str, Layer] = {
    "ocorrencias": Layer(
        path=ENDPOINTS["ocorrencias"],
        name="Ocorrências minerais",
        copyright_text="Serviço Geológico do Brasil - SGB - CPRM",
        # Serviço geologia/ocorrencias/MapServer, currentVersion 11.3,
        # maxRecordCount 100.000 (a camada tem 36.484: nenhuma WHERE corta).
        verified_at="2026-09-17",
    ),
}

# Configurações de requisição. DEFAULT_TIMEOUT é o que o cliente usa de fato
# (client.py lê daqui); até 2026-09-17 valia 30 aqui e 60 fixo no cliente, e
# ninguém lia o 30. O valor é o que vinha valendo: uma busca larga (UF inteira,
# 7,8 MB) leva ~11 s e a lista de substâncias ~18 s — 30 seria curto.
DEFAULT_TIMEOUT = 60.0
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

# Campos que as buscas pedem à fonte (`outFields`) — só os que a resposta
# usa. Até 2026-09-17 as duas buscas pediam `*` (37 campos) e a resposta
# aproveitava 8: `UF = 'MG'` (7.562 registros) vinha em 8,0 MB / 10,6 s com
# `*` + geometria e em 2,2 MB / 3,8 s com estes 8 + geometria (medido em
# 2026-09-17; a geometria pesa pouco, os 29 campos sobrando é que pesavam).
# A camada NÃO tem `TIPOLOGIA` (lista real de 37 campos lida em 2026-09-17):
# pedi-lo dá 400 "Failed to execute query", e o campo `typology` que as tools
# devolviam era sempre nulo — saiu do contrato. `get_occurrence_details`
# segue com `*`: é um registro.
OCCURRENCE_FIELDS = (
    "ID_OCORRENCIA",
    "SUBSTANCIAS",
    "STATUS_ECONOMICO",
    "ROCHAS_HOSPEDEIRAS",
    "PROVINCIA",
    "UF",
    "MUNICIPIO",
    "PROJETO",
)
# A busca de ETR não devolve `project`.
RARE_EARTH_FIELDS = tuple(f for f in OCCURRENCE_FIELDS if f != "PROJETO")

# Validade do cache em processo de `list_mineral_substances`, em segundos.
# A lista nasce de baixar a camada inteira (36.484 registros só com
# SUBSTANCIAS: 1,6 MB / ~20 s em 2026-09-17) porque a fonte recusa agregar
# esse campo: `outStatistics` + `groupByFieldsForStatistics=SUBSTANCIAS`
# responde 400 "Unable to complete operation" mesmo com `UF = 'AC'`, e
# `returnDistinctValues` também 400 — o mesmo groupBy por `UF` ou
# `STATUS_ECONOMICO` responde 200 em 0,1 s; é o campo multivalor ("Ouro,
# Prata", texto 255) que o servidor não agrupa. A lista muda raramente
# (cadastro do SGB, sem `lastEditDate` no serviço); um dia de validade
# amortiza os 20 s em uma ida por processo por dia.
SUBSTANCES_CACHE_TTL = 24 * 60 * 60

# Termos de busca para ETRs — a ÚNICA lista que search_rare_earth_occurrences
# usa (`SUBSTANCIAS LIKE '%termo%'`, um OR por termo). Até 2026-09-17 a tool
# tinha uma lista própria de 5 termos "para evitar queries muito longas", sem
# medição; e os elementos aqui estavam sem acento, que o LIKE da fonte não
# perdoa (sensível a caixa e acento: "Cério" casa 25, "Cerio" zero).
#
# Medido contra o portal em 2026-09-17 (36.484 registros), achados por termo:
# "Terras raras" 44, "Cério" 25, "Lantânio" 24, "Ítrio" 4, "Neodímio" 1; os
# demais zero na fonte de hoje (ficam: são grafias legítimas que o cadastro
# pode passar a usar e custam só comprimento de WHERE). A WHERE completa
# (13 termos + 6 rochas, 703 caracteres) responde: count 1,7 s, query 5,5 s,
# 2.383 registros — contra 1,1 s / 4,7 s / 2.352 da lista curta de 5 + 2.
REE_SEARCH_TERMS = [
    "Terras raras",
    "Elementos terras raras",
    "ETR",
    "Monazita",
    "Bastnasita",
    "Xenotima",
    "Cério",
    "Lantânio",
    "Neodímio",
    "Ítrio",
    "Samário",
    "Európio",
    "Gadolínio",
]

# Rochas hospedeiras típicas de ETRs (`ROCHAS_HOSPEDEIRAS LIKE`), entram com
# include_related_rocks=True. Achados por rocha em 2026-09-17: "Pegmatito"
# 2.291, "Carbonatito" 20, "Nefelina sienito" 4, "Granito alcalino" 1,
# "Sienito alcalino" e "Fonolito" zero. "Pegmatito" sozinho é 96% do
# resultado com as rochas (2.383 registros, 2,7 MB, 5,5 s, contra 74
# registros, 60 KB, 1,5 s só por substância) — por isso, desde 2026-09-17
# (Sessão 2), o default da tool é include_related_rocks=False: a busca por
# rochas é opt-in e a descrição da tool diz o que cada modo traz.
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

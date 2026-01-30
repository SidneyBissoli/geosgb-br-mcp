"""Constantes e configurações do GeoSGB MCP."""

# URLs base
BASE_URL = "https://geoportal.sgb.gov.br/server/rest/services"

# Endpoints disponíveis
ENDPOINTS = {
    "ocorrencias": "/geologia/ocorrencias/MapServer/0",
    "afloramentos": "/geologia/afloramentos/MapServer/0",
    "litoestratigrafia_estados": "/geologia/litoestratigrafia_estados/FeatureServer",
    "litoestratigrafia_1m": "/geologia/litoestratigrafia_1000000/MapServer/0",
    "sedimento_corrente": "/sedimento_corrente_query_all/FeatureServer/0",
}

# Configurações de requisição
DEFAULT_TIMEOUT = 30.0
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

# Estados brasileiros (para validação)
UF_CODES = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"
]

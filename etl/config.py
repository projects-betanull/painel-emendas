"""Configuração das fontes de dados. Ajuste aqui se alguma URL mudar."""

import os
from pathlib import Path

# Portal da Transparência (CGU): arquivo único com todas as emendas, em ZIP com CSV.
# Página: https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares
EMENDAS_ZIP_URL = os.environ.get(
    "EMENDAS_ZIP_URL",
    "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO",
)

# IBGE: lista de municípios com UF (código de 7 dígitos).
IBGE_MUNICIPIOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
# Cópia pública da mesma lista, usada quando a API do IBGE não responde.
MUNICIPIOS_ESPELHO_URL = (
    "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"
)

# Primeiro ano carregado.
ANO_INICIAL = int(os.environ.get("ANO_INICIAL", "2020"))

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "out"

# Encoding e separador usados pelo Portal da Transparência.
CSV_ENCODING = "latin-1"
CSV_SEP = ";"

# Endereço Lightning (coinos) para contribuições, mostrado na página Apoie.
LIGHTNING_ADDRESS = os.environ.get("LIGHTNING_ADDRESS", "lizard43@coinos.io")

# Endereço público do site (links de compartilhamento) e do repositório (correções).
SITE_URL = os.environ.get("SITE_URL", "https://painel-emendas.pages.dev")
REPO_URL = "https://github.com/projects-betanull/painel-emendas"

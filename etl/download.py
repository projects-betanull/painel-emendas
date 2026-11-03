"""Baixa os arquivos brutos: emendas (Portal da Transparência) e municípios (IBGE)."""

import io
import json
import zipfile
from pathlib import Path

import requests

from . import config

HEADERS = {"User-Agent": "painel-emendas/0.1 (dados abertos; +https://github.com/)"}


def baixar_emendas(destino: Path = config.RAW_DIR) -> Path:
    """Baixa o ZIP de emendas e extrai o CSV principal. Devolve o caminho do CSV."""
    destino.mkdir(parents=True, exist_ok=True)
    resp = requests.get(config.EMENDAS_ZIP_URL, headers=HEADERS, timeout=300)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            raise RuntimeError(f"ZIP sem CSV: {zf.namelist()}")
        # Se houver mais de um CSV, o maior é a tabela principal de emendas.
        principal = max(csvs, key=lambda n: zf.getinfo(n).file_size)
        caminho = destino / "emendas.csv"
        caminho.write_bytes(zf.read(principal))
    print(f"emendas: {principal} -> {caminho} ({caminho.stat().st_size / 1e6:.1f} MB)")
    return caminho


def baixar_municipios(destino: Path = config.RAW_DIR) -> Path:
    """Baixa a lista de municípios do IBGE e grava um JSON simplificado."""
    destino.mkdir(parents=True, exist_ok=True)
    resp = requests.get(config.IBGE_MUNICIPIOS_URL, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    municipios = []
    for m in resp.json():
        uf = _uf_do_municipio(m)
        municipios.append({"codigo_ibge": str(m["id"]), "nome": m["nome"], "uf": uf})
    caminho = destino / "municipios.json"
    caminho.write_text(json.dumps(municipios, ensure_ascii=False), encoding="utf-8")
    print(f"municipios: {len(municipios)} -> {caminho}")
    return caminho


def _uf_do_municipio(m: dict) -> str:
    # A API do IBGE às vezes traz microrregiao nula; regiao-imediata é o caminho alternativo.
    try:
        return m["microrregiao"]["mesorregiao"]["UF"]["sigla"]
    except (KeyError, TypeError):
        return m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]


if __name__ == "__main__":
    baixar_municipios()
    baixar_emendas()

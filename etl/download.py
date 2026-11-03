"""Baixa os arquivos brutos: emendas (Portal da Transparência) e municípios (IBGE)."""

import csv
import io
import json
import zipfile
from pathlib import Path

import requests

from . import config
from .normalize import UF_POR_CODIGO

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
        # O ZIP traz vários CSVs (emendas, por favorecido, convênios...). Guarda todos
        # com o nome original e escolhe como principal o que tem valores empenhados.
        principal = None
        for nome in csvs:
            dados = zf.read(nome)
            (destino / Path(nome).name).write_bytes(dados)
            cabecalho = dados.split(b"\n", 1)[0].decode(config.CSV_ENCODING, errors="replace")
            print(f"zip: {nome} ({len(dados) / 1e6:.1f} MB) colunas: {cabecalho.strip()[:300]}")
            if principal is None and "Valor Empenhado" in cabecalho:
                principal = nome
        if principal is None:
            raise RuntimeError(f"nenhum CSV com 'Valor Empenhado' no ZIP: {csvs}")
        caminho = destino / "emendas.csv"
        caminho.write_bytes(zf.read(principal))
    print(f"emendas: {principal} -> {caminho} ({caminho.stat().st_size / 1e6:.1f} MB)")
    return caminho


def baixar_municipios(destino: Path = config.RAW_DIR) -> Path:
    """Grava a lista de municípios (código IBGE, nome, UF) em JSON.

    Tenta a API do IBGE; se ela não responder (o servidor costuma bloquear acesso
    de fora do Brasil, como os runners do GitHub), usa uma cópia pública no GitHub.
    """
    destino.mkdir(parents=True, exist_ok=True)
    try:
        municipios = _municipios_ibge()
        fonte = "IBGE"
    except requests.RequestException as erro:
        print(f"aviso: API do IBGE indisponível ({type(erro).__name__}); usando cópia no GitHub")
        municipios = _municipios_espelho()
        fonte = "espelho GitHub"
    if len(municipios) < 5500:
        raise RuntimeError(f"lista de municípios incompleta: {len(municipios)}")
    caminho = destino / "municipios.json"
    caminho.write_text(json.dumps(municipios, ensure_ascii=False), encoding="utf-8")
    print(f"municipios ({fonte}): {len(municipios)} -> {caminho}")
    return caminho


def _municipios_ibge() -> list[dict]:
    resp = requests.get(config.IBGE_MUNICIPIOS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return [
        {"codigo_ibge": str(m["id"]), "nome": m["nome"], "uf": _uf_do_municipio(m)}
        for m in resp.json()
    ]




def _municipios_espelho() -> list[dict]:
    """CSV público com os municípios do IBGE (kelvins/municipios-brasileiros)."""
    resp = requests.get(config.MUNICIPIOS_ESPELHO_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    leitor = csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")))
    return [
        {
            "codigo_ibge": linha["codigo_ibge"],
            "nome": linha["nome"],
            "uf": UF_POR_CODIGO[linha["codigo_ibge"][:2]],
            "siafi": linha.get("siafi_id") or None,
        }
        for linha in leitor
    ]


def _uf_do_municipio(m: dict) -> str:
    # A API do IBGE às vezes traz microrregiao nula; regiao-imediata é o caminho alternativo.
    try:
        return m["microrregiao"]["mesorregiao"]["UF"]["sigla"]
    except (KeyError, TypeError):
        return m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]


if __name__ == "__main__":
    baixar_municipios()
    baixar_emendas()

"""Cubo compacto para o explorador: valores recebidos agregados por dimensões.

Formato colunar com dicionário (cada dimensão vira lista de rótulos + índices),
para o navegador pivotar sem servidor nem banco de dados.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DIMS = ["ano", "uf", "municipio", "autor", "tipo", "natureza", "area"]


def montar_cubo(fav: pd.DataFrame, fato: pd.DataFrame, municipios: list[dict]) -> dict:
    nomes = {str(m["codigo_ibge"]): f'{m["nome"]} ({m["uf"]})' for m in municipios}
    # Área (função orçamentária) de cada emenda, vinda do arquivo principal.
    area = (
        fato.dropna(subset=["funcao"]).groupby("codigo_emenda")["funcao"].agg(lambda s: s.mode().iat[0])
        if "funcao" in fato.columns else pd.Series(dtype=str)
    )
    df = pd.DataFrame({
        "ano": fav["ano"].astype("Int64").astype(str),
        "uf": fav["uf"].fillna("?"),
        "municipio": fav["municipio_ibge"].astype("string").map(nomes).fillna("Sem município"),
        "autor": fav["nome_autor"].fillna("Sem autor"),
        "tipo": fav["tipo_emenda"].fillna("?"),
        "natureza": fav["natureza_juridica"].fillna("?") if "natureza_juridica" in fav else "?",
        "area": fav["codigo_emenda"].map(area).fillna("Não informada"),
        "valor": fav["valor_recebido"],
    })
    g = df.groupby(DIMS, dropna=False)["valor"].agg(["sum", "count"]).reset_index()
    cubo = {"dims": {}, "cols": {}, "valor": g["sum"].round(0).astype("int64").tolist(), "n": g["count"].tolist()}
    for d in DIMS:
        cat = pd.Categorical(g[d].astype(str))
        cubo["dims"][d] = list(cat.categories)
        cubo["cols"][d] = cat.codes.tolist()
    return cubo


def gravar_cubo(cubo: dict, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / "cubo.json"
    caminho.write_text(json.dumps(cubo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"cubo: {len(cubo['valor']):,} linhas, {caminho.stat().st_size / 1e6:.1f} MB")
    return caminho

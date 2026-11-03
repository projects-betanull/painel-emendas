"""Monta as tabelas do painel a partir dos arquivos brutos.

Uso:
    python -m etl.build              # baixa tudo e gera data/out/
    python -m etl.build --sem-baixar # usa o que já está em data/raw/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import config
from .normalize import IndiceMunicipios, normalizar_emendas, relatorio_qualidade


def ler_csv_portal(caminho: Path) -> pd.DataFrame:
    return pd.read_csv(caminho, sep=config.CSV_SEP, encoding=config.CSV_ENCODING, dtype=str, keep_default_na=False)


def agregar(fato: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Tabelas derivadas usadas pelas páginas estáticas."""
    mun = fato[fato["escopo"] == "municipal"]
    metricas_municipio = (
        mun.groupby(["municipio_ibge", "uf", "ano"], dropna=False)
        .agg(
            valor_empenhado=("valor_empenhado", "sum"),
            valor_pago=("valor_pago", "sum"),
            emendas=("codigo_emenda", "nunique"),
            autores=("nome_autor", "nunique"),
        )
        .reset_index()
    )
    metricas_municipio["rank_uf"] = (
        metricas_municipio.groupby(["uf", "ano"])["valor_pago"].rank(ascending=False, method="min").astype("Int64")
    )

    chave_autor = ["codigo_autor", "nome_autor"] if "codigo_autor" in fato.columns else ["nome_autor"]
    autores = (
        fato.groupby(chave_autor + ["ano"], dropna=False)
        .agg(
            valor_empenhado=("valor_empenhado", "sum"),
            valor_pago=("valor_pago", "sum"),
            emendas=("codigo_emenda", "nunique"),
            municipios=("municipio_ibge", "nunique"),
        )
        .reset_index()
    )
    return {"metricas_municipio": metricas_municipio, "autores": autores}


def gravar(tabelas: dict[str, pd.DataFrame], destino: Path) -> list[Path]:
    """Grava Parquet com DuckDB (produção). Sem DuckDB instalado, cai para CSV."""
    destino.mkdir(parents=True, exist_ok=True)
    arquivos = []
    try:
        import duckdb
    except ImportError:
        duckdb = None
        print("aviso: duckdb não instalado; gravando CSV em vez de Parquet")
    for nome, df in tabelas.items():
        if duckdb is not None:
            caminho = destino / f"{nome}.parquet"
            con = duckdb.connect()
            con.register("t", df)
            con.execute(f"COPY t TO '{caminho.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            con.close()
        else:
            caminho = destino / f"{nome}.csv"
            df.to_csv(caminho, index=False)
        arquivos.append(caminho)
        print(f"{nome}: {len(df):,} linhas -> {caminho.name}")
    return arquivos


def main(argv=None) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--sem-baixar", action="store_true", help="usar arquivos já existentes em data/raw")
    p.add_argument("--raw", type=Path, default=config.RAW_DIR)
    p.add_argument("--out", type=Path, default=config.OUT_DIR)
    p.add_argument("--ano-inicial", type=int, default=config.ANO_INICIAL)
    args = p.parse_args(argv)

    if not args.sem_baixar:
        from .download import baixar_emendas, baixar_municipios

        baixar_municipios(args.raw)
        baixar_emendas(args.raw)

    municipios = json.loads((args.raw / "municipios.json").read_text(encoding="utf-8"))
    indice = IndiceMunicipios(municipios)
    bruto = ler_csv_portal(args.raw / "emendas.csv")
    fato = normalizar_emendas(bruto, indice, args.ano_inicial)

    tabelas = {"fato_emenda": fato, **agregar(fato)}
    gravar(tabelas, args.out)

    qualidade = relatorio_qualidade(fato)
    (args.out / "qualidade.json").write_text(json.dumps(qualidade, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"qualidade: {qualidade['linhas']:,} linhas, "
        f"{qualidade['pct_valor_pago_com_municipio']}% do valor pago atribuído a um município"
    )
    return qualidade


if __name__ == "__main__":
    main()

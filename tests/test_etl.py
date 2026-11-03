import json
from pathlib import Path

import pytest

from etl import build
from etl.normalize import IndiceMunicipios, classificar_localidade, slug, valor_br

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def indice():
    return IndiceMunicipios(json.loads((FIX / "municipios.json").read_text(encoding="utf-8")))


def test_slug():
    assert slug("São Paulo - SP") == "sao paulo sp"
    assert slug(None) == ""


@pytest.mark.parametrize(
    "entrada,esperado",
    [("1.234.567,89", 1234567.89), ("0,00", 0.0), ("", 0.0), ("(10,50)", -10.5), (None, 0.0), ("R$ 5,00", 5.0)],
)
def test_valor_br(entrada, esperado):
    assert valor_br(entrada) == pytest.approx(esperado)


@pytest.mark.parametrize(
    "texto,escopo,ibge,uf",
    [
        ("CAMPINAS - SP", "municipal", "3509502", "SP"),
        ("Campinas/SP", "municipal", "3509502", "SP"),
        ("MOJI MIRIM - SP", "municipal", "3530805", "SP"),  # grafia antiga
        ("SÃO PAULO - SP", "municipal", "3550308", "SP"),
        ("SÃO PAULO (UF)", "estadual", None, "SP"),
        ("CEARÁ (UF)", "estadual", None, "CE"),
        ("NACIONAL", "nacional", None, None),
        ("NORDESTE (REGIÃO)", "regional", None, None),
        ("CIDADE INEXISTENTE - MG", "outro", None, "MG"),
        ("", "outro", None, None),
    ],
)
def test_classificar_localidade(indice, texto, escopo, ibge, uf):
    loc = classificar_localidade(texto, indice)
    assert (loc.escopo, loc.municipio_ibge, loc.uf) == (escopo, ibge, uf)


def test_codigo_ibge_da_coluna_tem_prioridade(indice):
    loc = classificar_localidade("texto qualquer", indice, codigo_ibge="2304400", uf_col="CE")
    assert (loc.escopo, loc.municipio_ibge) == ("municipal", "2304400")


def test_nome_sem_uf_usa_coluna_uf(indice):
    loc = classificar_localidade("Cataguases", indice, uf_col="MG")
    assert loc.municipio_ibge == "3115300"


def test_build_ponta_a_ponta(tmp_path):
    q = build.main(["--sem-baixar", "--raw", str(FIX), "--out", str(tmp_path), "--ano-inicial", "2020"])
    # A linha de 2019 fica de fora.
    assert q["linhas"] == 7
    assert q["anos"] == [2023, 2024, 2025]
    assert q["valor_pago_total"] == pytest.approx(13_400_000.50)
    # Pago com município: Campinas 750.000,50 + Fortaleza 500.000 = 1.250.000,50
    assert q["pct_valor_pago_com_municipio"] == pytest.approx(9.3, abs=0.1)
    assert "CIDADE INEXISTENTE - MG" in q["localidades_nao_resolvidas_top20"]
    assert (tmp_path / "qualidade.json").exists()
    saidas = {p.stem for p in tmp_path.iterdir()}
    assert {"fato_emenda", "metricas_municipio", "autores"} <= saidas


def test_modalidade_pix(tmp_path):
    import pandas as pd

    build.main(["--sem-baixar", "--raw", str(FIX), "--out", str(tmp_path)])
    arq = next(tmp_path.glob("fato_emenda.*"))
    if arq.suffix == ".parquet":
        # Lê com DuckDB para não depender de pyarrow.
        import duckdb

        df = duckdb.sql(f"SELECT * FROM '{arq.as_posix()}'").df()
    else:
        df = pd.read_csv(arq, dtype=str)
    pix = df[df["modalidade"] == "pix"]["codigo_emenda"].astype(str).tolist()
    assert sorted(pix) == ["202312340003", "202312340004", "202412340001"]


def test_municipios_espelho(monkeypatch):
    from etl import download

    class Resp:
        content = "codigo_ibge,nome,latitude,longitude,capital,codigo_uf,siafi_id,ddd,fuso_horario\n3509502,Campinas,-22.9,-47.0,0,35,6291,19,America/Sao_Paulo\n".encode()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(download.requests, "get", lambda *a, **k: Resp())
    assert download._municipios_espelho() == [
        {"codigo_ibge": "3509502", "nome": "Campinas", "uf": "SP", "siafi": "6291"}
    ]

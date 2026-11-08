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


def test_uf_vem_do_codigo_ibge(indice):
    # A coluna UF do Portal pode vir por extenso; a sigla sai do código IBGE.
    loc = classificar_localidade("FORTALEZA", indice, codigo_ibge="2304400", uf_col="CEARÁ")
    assert (loc.municipio_ibge, loc.uf) == ("2304400", "CE")


def test_favorecidos(tmp_path):
    q = build.main(["--sem-baixar", "--raw", str(FIX), "--out", str(tmp_path), "--ano-inicial", "2020"])
    f = q["favorecidos"]
    assert f["linhas"] == 4  # a linha de 2019 sai
    assert f["valor_recebido_total"] == pytest.approx(4_250_000.50)
    # Campinas 750.000,50 + Fortaleza 3.000.000 = 3.750.000,50 de 4.250.000,50
    assert f["pct_valor_recebido_com_municipio"] == pytest.approx(88.2, abs=0.1)
    assert f["municipios_distintos"] == 2
    assert "CIDADE INEXISTENTE / MG" in f["nao_resolvidos_top20"]
    assert (tmp_path / "fato_favorecido.csv").exists() or (tmp_path / "fato_favorecido.parquet").exists()


@pytest.mark.parametrize("v,esperado", [("202403", (2024, 3)), ("05/2025", (2025, 5)), ("2023-11", (2023, 11)), ("", (None, None))])
def test_ano_mes(v, esperado):
    from etl.normalize import _ano_mes

    assert _ano_mes(v) == esperado


def test_multiplo(indice):
    assert classificar_localidade("MÚLTIPLO", indice).escopo == "multiplo"


def test_codigo_com_uf_nula(indice):
    assert indice.codigo("Campinas", float("nan")) is None
    assert indice.codigo("Campinas", None) is None


def test_site(tmp_path):
    site = tmp_path / "site"
    build.main(["--sem-baixar", "--raw", str(FIX), "--out", str(tmp_path / "out"), "--site", str(site)])
    inicio = (site / "index.html").read_text(encoding="utf-8")
    assert "Fortaleza" in inicio and "Campinas" in inicio
    campinas = (site / "municipio" / "campinas-sp" / "index.html").read_text(encoding="utf-8")
    assert "R$ 750.000" in campinas and "FULANO DE TAL" in campinas
    busca = json.loads((site / "busca.json").read_text(encoding="utf-8"))
    assert {m["n"] for m in busca} == {"Campinas", "Fortaleza"}
    assert (site / "estilo.css").exists() and (site / "apoie" / "index.html").exists()


def test_explorador(tmp_path):
    import subprocess

    site = tmp_path / "site"
    build.main(["--sem-baixar", "--raw", str(FIX), "--out", str(tmp_path / "out"), "--site", str(site), "--ano-inicial", "2020"])
    cubo = json.loads((site / "explorar" / "cubo.json").read_text(encoding="utf-8"))
    assert sum(cubo["valor"]) == 4_250_000  # 4 pagamentos desde 2020, inclusive sem município
    js = Path(__file__).parent.parent / "etl" / "site_static" / "motor.js"
    script = f"""
const m = require({json.dumps(str(js))}); const c = require({json.dumps(str(site / 'explorar' / 'cubo.json'))});
let e = m.deHash('l=uf&m=valor'); let r = m.pivotar(c, e);
const top = c.dims.uf[r.linhas[0][0]];
e = m.descer(e, 'CE'); const r2 = m.pivotar(c, e);
const ok = top === 'CE' && e.lin === 'municipio' && r2.linhas.length === 1 && m.subir(e, 'uf').lin === 'uf' && m.deHash(m.paraHash(e)).f.uf[0] === 'CE';
console.log(JSON.stringify({{top, lin: e.lin, total: r.total, ok}}));
"""
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert json.loads(out)["ok"], out


def test_bancada_js():
    import subprocess

    js = Path(__file__).parent.parent / "etl" / "site_static" / "motor.js"
    out = subprocess.run(["node", "-e", f"const m=require({json.dumps(str(js))});console.log(JSON.stringify([m.ufDaBancada('BANCADA DO CEARÁ'),m.ufDaBancada('Bancada de São Paulo'),m.ufDaBancada('FULANO'),m.legDoExercicio(2024),m.legDoExercicio(2019),m.legDoExercicio(2016)]))"],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == ["CE", "SP", None, 57, 55, 55]


def test_legislatura():
    from etl.bancadas import legislatura_do_exercicio as leg

    assert [leg(2016), leg(2019), leg(2020), leg(2023), leg(2024), leg(2027)] == [55, 55, 56, 56, 57, 57]


def test_mcp(tmp_path):
    import subprocess

    site = tmp_path / "site"
    build.main(["--sem-baixar", "--raw", str(FIX), "--out", str(tmp_path / "out"), "--site", str(site), "--ano-inicial", "2020"])
    raiz = Path(__file__).parent.parent
    r = subprocess.run(["node", str(raiz / "tests" / "test_mcp.mjs"), str(site)], capture_output=True, text=True)
    assert r.returncode == 0 and "mcp ok" in r.stdout, r.stdout + r.stderr


def _contrato(orgao, seq, ni, valor, pub, esfera="M", tipo="PJ", ass=None):
    return {"numeroControlePNCP": f"{orgao}-{seq}", "orgaoEntidade": {"cnpj": orgao, "esferaId": esfera}, "anoContrato": 2026,
            "sequencialContrato": seq, "niFornecedor": ni, "nomeRazaoSocialFornecedor": f"FORN {ni}", "tipoPessoa": tipo,
            "valorGlobal": valor, "dataAssinatura": ass or pub, "dataPublicacaoPncp": pub + "T10:00:00", "objetoContrato": "obra " * 100}


def test_pncp_base_e_resumo():
    from datetime import date

    from etl import pncp

    hoje = date(2026, 11, 8)
    brutos = [_contrato("46068425000133", 1, "11222333000181", 100, "2026-10-01"),
              _contrato("46068425000133", 2, "11222333000181", 50, "2026-11-01"),
              _contrato("46068425000133", 3, "12345678901", 9, "2026-11-02", tipo="PF"),
              _contrato("46068425000133", 4, "99888777000166", 80, "2025-10-01"),   # mais de 12 meses
              _contrato("00394460000141", 5, "11222333000181", 70, "2026-11-01", esfera="F")]  # federal
    linhas = [x for x in map(pncp.compactar, brutos) if x]
    assert len(linhas) == 4 and len(linhas[0]["objeto"]) == 240
    df = pncp.juntar(pncp.pd.DataFrame(columns=pncp.COLUNAS), linhas, hoje)
    assert len(df) == 3
    # atualização do contrato 1 substitui a linha antiga
    df = pncp.juntar(df, [pncp.compactar(_contrato("46068425000133", 1, "11222333000181", 120, "2026-10-01"))], hoje)
    r = pncp.resumos(df, {"46068425000133"}, "08/11/2026")["46068425000133"]
    assert r["total_contratos"] == 2 and r["valor_total"] == 170 and r["omitidos_pessoa_fisica"] == 1
    assert r["fornecedores"][0] == {"fornecedor": "FORN 11222333000181", "cnpj": "11222333000181", "valor": 170, "contratos": 2}
    assert r["recentes"][0]["data"] == "2026-11-01" and r["recentes"][0]["link"].endswith("/46068425000133/2026/2")


def test_site_com_contratos_prontos(tmp_path, monkeypatch):
    from datetime import date, timedelta

    from etl import pncp

    hoje = date.today()
    linhas = [pncp.compactar(_contrato("46068425000133", i, "11222333000181", 1000 * i, (hoje - timedelta(days=d)).isoformat()))
              for i, d in [(1, 360), (2, 1)]]
    arq = tmp_path / "pncp" / "contratos.parquet"
    pncp.gravar(pncp.pd.DataFrame(linhas, columns=pncp.COLUNAS), arq)
    monkeypatch.setattr(pncp, "ARQUIVO", arq)
    site = tmp_path / "site"
    build.main(["--sem-baixar", "--raw", str(FIX), "--out", str(tmp_path / "out"), "--site", str(site)])
    campinas = (site / "municipio" / "campinas-sp" / "index.html").read_text(encoding="utf-8")
    assert "FORN 11222333000181" in campinas and "R$ 3.000" in campinas and "contratos.js" not in campinas
    api = json.loads((site / "api" / "m" / "3509502.json").read_text(encoding="utf-8"))
    assert api["contratos"]["total_contratos"] == 2

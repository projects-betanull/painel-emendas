"""Contratos municipais do PNCP dos últimos 12 meses, guardados entre execuções.

Consultar o PNCP por órgão leva 15–40 s por pedido; consultar o país inteiro por data de
publicação leva ~3–9 s por página de 500. Então este módulo baixa tudo por data, guarda só a
esfera municipal num Parquet (data/pncp/contratos.parquet) e, a cada dia, busca apenas o que foi
publicado ou atualizado desde a última vez. O ETL lê esse arquivo e põe os contratos da prefeitura
direto na página do município.

Uso:
    python -m etl.pncp atualizar [--arquivo data/pncp/contratos.parquet]
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import config

API = "https://pncp.gov.br/api/consulta/v1"
TAM = 500
TRABALHADORES = 4
JANELA_DIAS = 364
ARQUIVO = config.ROOT / "data" / "pncp" / "contratos.parquet"
COLUNAS = ["id", "orgao", "ano", "seq", "ni", "fornecedor", "tipo_pessoa", "valor", "data_assinatura", "data_publicacao", "objeto"]
FONTE = "Portal Nacional de Contratações Públicas (PNCP), contratos publicados pelo órgão."
AVISO = "Contratos da prefeitura em geral; os dados públicos não indicam quais foram pagos com recursos de emendas."

_sessao = requests.Session()
_sessao.headers.update({"accept": "application/json", "user-agent": "painel-emendas (dados abertos)"})


def _dia(d: date) -> str:
    return d.strftime("%Y%m%d")


_pausa = {"ate": 0.0}
_trava = threading.Lock()


def _esperar_pausa() -> None:
    while (resta := _pausa["ate"] - time.time()) > 0:
        time.sleep(resta)


def _pausar(segundos: float) -> None:
    """HTTP 429 vale para todas as threads: ninguém pede nada até a pausa acabar."""
    with _trava:
        _pausa["ate"] = max(_pausa["ate"], time.time() + segundos)


def _pagina(caminho: str, d1: date, d2: date, p: int) -> dict:
    url = f"{API}/{caminho}?dataInicial={_dia(d1)}&dataFinal={_dia(d2)}&pagina={p}&tamanhoPagina={TAM}"
    erro = ""
    for tentativa in range(12):
        _esperar_pausa()
        try:
            r = _sessao.get(url, timeout=120)
            if r.status_code == 204:
                return {"data": [], "totalPaginas": 0}
            if r.status_code == 200:
                return r.json()
            erro = f"HTTP {r.status_code}"
            if r.status_code == 429:
                espera = r.headers.get("retry-after", "")
                _pausar(float(espera) if espera.isdigit() else min(15 * 2 ** tentativa, 300))
                continue
        except (requests.RequestException, ValueError) as e:
            erro = str(e)[:120]
        time.sleep(min(5 * 2 ** tentativa, 120))
    raise RuntimeError(f"PNCP falhou em {caminho} {_dia(d1)}-{_dia(d2)} pág. {p}: {erro}")


def compactar(c: dict) -> dict | None:
    """Só a esfera municipal e só os campos usados no site."""
    org = c.get("orgaoEntidade") or {}
    if str(org.get("esferaId") or "").upper() != "M":
        return None
    cnpj, ano, seq = str(org.get("cnpj") or ""), c.get("anoContrato"), c.get("sequencialContrato")
    ni, tipo = str(c.get("niFornecedor") or ""), str(c.get("tipoPessoa") or "").upper()
    if tipo == "PF" or len("".join(ch for ch in ni if ch.isdigit())) == 11:
        # Pessoa física: a base fica num arquivo público, então só a contagem é guardada (LGPD).
        return {"id": c.get("numeroControlePNCP") or f"{cnpj}-{ano}-{seq}", "orgao": cnpj, "ano": int(ano or 0), "seq": int(seq or 0),
                "ni": "", "fornecedor": "", "tipo_pessoa": "PF", "valor": 0.0, "data_assinatura": "",
                "data_publicacao": str(c.get("dataPublicacaoPncp") or "")[:10], "objeto": ""}
    return {
        "id": c.get("numeroControlePNCP") or f"{cnpj}-{ano}-{seq}",
        "orgao": cnpj, "ano": int(ano or 0), "seq": int(seq or 0),
        "ni": ni, "fornecedor": str(c.get("nomeRazaoSocialFornecedor") or ""), "tipo_pessoa": tipo,
        "valor": float(c.get("valorGlobal") or c.get("valorInicial") or 0),
        "data_assinatura": str(c.get("dataAssinatura") or "")[:10],
        "data_publicacao": str(c.get("dataPublicacaoPncp") or "")[:10],
        "objeto": str(c.get("objetoContrato") or "")[:240],
    }


def baixar_janela(caminho: str, d1: date, d2: date) -> list[dict]:
    """Todas as páginas de uma janela de datas (página 1 primeiro, as demais em paralelo)."""
    primeira = _pagina(caminho, d1, d2, 1)
    brutos = list(primeira.get("data") or [])
    total = int(primeira.get("totalPaginas") or 1)
    if total > 1:
        with ThreadPoolExecutor(TRABALHADORES) as ex:
            for j in ex.map(lambda p: _pagina(caminho, d1, d2, p), range(2, total + 1)):
                brutos.extend(j.get("data") or [])
    return [x for x in map(compactar, brutos) if x]


def baixar_periodo(caminho: str, d1: date, d2: date, passo: int = 7) -> list[dict]:
    """Período em janelas curtas: páginas profundas do PNCP ficam lentas."""
    linhas, ini = [], d1
    while ini <= d2:
        fim = min(ini + timedelta(days=passo - 1), d2)
        t = time.time()
        novas = baixar_janela(caminho, ini, fim)
        linhas.extend(novas)
        print(f"  {caminho} {ini}..{fim}: {len(novas):,} municipais ({time.time() - t:.0f} s)", flush=True)
        ini = fim + timedelta(days=1)
    return linhas


def ler(arquivo: Path) -> pd.DataFrame:
    if not arquivo.exists():
        return pd.DataFrame(columns=COLUNAS)
    import duckdb

    return duckdb.sql(f"SELECT * FROM read_parquet('{arquivo.as_posix()}')").df()


def gravar(df: pd.DataFrame, arquivo: Path) -> None:
    import duckdb

    arquivo.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("t", df[COLUNAS])
    con.execute(f"COPY t TO '{arquivo.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()


def juntar(base: pd.DataFrame, novas: list[dict], hoje: date) -> pd.DataFrame:
    """Novas linhas substituem as antigas de mesmo id; sai o que tem mais de 12 meses."""
    df = pd.concat([base, pd.DataFrame(novas, columns=COLUNAS)], ignore_index=True)
    df = df.drop_duplicates("id", keep="last")
    return df[df["data_publicacao"] >= (hoje - timedelta(days=JANELA_DIAS)).isoformat()].reset_index(drop=True)


def atualizar(arquivo: Path = ARQUIVO, hoje: date | None = None) -> pd.DataFrame:
    hoje = hoje or date.today()
    base = ler(arquivo)
    if base.empty:
        ini = hoje - timedelta(days=JANELA_DIAS)
        print(f"carga inicial do PNCP desde {ini}", flush=True)
    else:
        ini = date.fromisoformat(str(base["data_publicacao"].max())) - timedelta(days=3)
        print(f"base com {len(base):,} contratos; buscando publicados desde {ini}", flush=True)
    df, ini_j, n = base, ini, 0
    try:
        # Grava a cada 4 semanas: se o PNCP cair no meio da carga inicial, a próxima execução continua dali.
        while ini_j <= hoje:
            fim = min(ini_j + timedelta(days=6), hoje)
            novas = baixar_periodo("contratos", ini_j, fim)
            df = juntar(df, novas, hoje)
            ini_j, n = fim + timedelta(days=1), n + 1
            if n % 4 == 0:
                gravar(df, arquivo)
        # Contratos antigos que mudaram (aditivos, correções). Só na rotina diária: numa retomada
        # de carga, o período inteiro já veio novo e baixar as atualizações dobraria o tempo.
        if not base.empty and (hoje - ini).days <= 14:
            try:
                df = juntar(df, baixar_periodo("contratos/atualizacao", ini, hoje), hoje)
            except RuntimeError as e:
                print(f"aviso: atualizações não baixadas ({e})")
    finally:
        gravar(df, arquivo)
    print(f"PNCP: {len(df):,} contratos municipais, {df['orgao'].nunique():,} órgãos -> {arquivo}")
    return df


def resumos(df: pd.DataFrame, cnpjs: set[str], atualizado_em: str = "") -> dict[str, dict]:
    """Mesmo formato de lib/pncp.js (resumir) para cada CNPJ de prefeitura."""
    so_digitos = df["ni"].str.replace(r"\D", "", regex=True)
    pf = (df["tipo_pessoa"].str.upper() == "PF") | (so_digitos.str.len() == 11)
    df = df.assign(pf=pf)[df["orgao"].isin(cnpjs)]
    saida = {}
    for cnpj, parte in df.groupby("orgao"):
        pj = parte[~parte["pf"]]
        chave = pj["ni"].where(pj["ni"] != "", pj["fornecedor"])
        forn = (pj.assign(chave=chave).groupby("chave")
                .agg(fornecedor=("fornecedor", "first"), cnpj=("ni", "first"), valor=("valor", "sum"), contratos=("id", "size"))
                .sort_values("valor", ascending=False).head(15))
        rec = pj.sort_values("data_assinatura", ascending=False).head(10)
        saida[cnpj] = {
            "orgao_cnpj": cnpj, "periodo": "últimos 12 meses",
            "total_contratos": int(len(pj)), "valor_total": int(round(pj["valor"].sum())),
            "omitidos_pessoa_fisica": int(parte["pf"].sum()),
            "fornecedores": [{"fornecedor": f.fornecedor, "cnpj": f.cnpj, "valor": int(round(f.valor)), "contratos": int(f.contratos)}
                             for f in forn.itertuples()],
            "recentes": [{"data": r.data_assinatura, "fornecedor": r.fornecedor, "cnpj": r.ni, "valor": int(round(r.valor)),
                          "objeto": r.objeto, "link": f"https://pncp.gov.br/app/contratos/{r.orgao}/{r.ano}/{r.seq}" if r.ano and r.seq else None}
                         for r in rec.itertuples()],
            "fonte": FONTE, "aviso": AVISO, "atualizado_em": atualizado_em,
        }
    return saida


def vazio(cnpj: str, atualizado_em: str = "") -> dict:
    return {"orgao_cnpj": cnpj, "periodo": "últimos 12 meses", "total_contratos": 0, "valor_total": 0, "omitidos_pessoa_fisica": 0,
            "fornecedores": [], "recentes": [], "fonte": FONTE, "aviso": AVISO, "atualizado_em": atualizado_em}


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("comando", choices=["atualizar"])
    p.add_argument("--arquivo", type=Path, default=ARQUIVO)
    a = p.parse_args(argv)
    try:
        atualizar(a.arquivo)
    except RuntimeError as e:
        print(f"erro: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

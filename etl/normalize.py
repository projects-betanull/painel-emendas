"""Normalização das emendas: nomes de colunas, valores em reais e localidade -> código IBGE.

Tudo aqui é Python puro + pandas, sem rede, para poder ser testado com amostras.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

# --------------------------------------------------------------------------- texto


def slug(texto) -> str:
    """'São Paulo - SP' -> 'sao paulo sp'. Sem acentos, minúsculo, só letras/dígitos."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip().lower()
    return s


# --------------------------------------------------------------------------- colunas

# Nome canônico -> nomes possíveis no CSV do Portal (comparados via slug).
# O Portal já mudou rótulos antes; por isso aceitamos variações.
COLUNAS = {
    "codigo_emenda": ["codigo da emenda", "codigo emenda"],
    "ano": ["ano da emenda", "ano"],
    "tipo_emenda": ["tipo de emenda", "tipo da emenda"],
    "codigo_autor": ["codigo do autor da emenda", "codigo autor"],
    "nome_autor": ["nome do autor da emenda", "autor da emenda", "nome autor"],
    "numero_emenda": ["numero da emenda", "numero emenda"],
    "localidade": ["localidade de aplicacao do recurso", "localidade do gasto", "localidade"],
    "codigo_municipio_ibge": ["codigo municipio ibge", "codigo ibge municipio"],
    "municipio": ["municipio", "nome municipio"],
    "codigo_uf_ibge": ["codigo uf ibge"],
    "uf": ["uf", "sigla uf"],
    "regiao": ["regiao"],
    "codigo_funcao": ["codigo funcao"],
    "funcao": ["nome funcao", "funcao"],
    "codigo_subfuncao": ["codigo subfuncao"],
    "subfuncao": ["nome subfuncao", "subfuncao"],
    "codigo_programa": ["codigo programa"],
    "programa": ["nome programa", "programa"],
    "codigo_acao": ["codigo acao"],
    "acao": ["nome acao", "acao"],
    "valor_empenhado": ["valor empenhado"],
    "valor_liquidado": ["valor liquidado"],
    "valor_pago": ["valor pago"],
    "valor_rp_inscrito": ["valor restos a pagar inscritos"],
    "valor_rp_cancelado": ["valor restos a pagar cancelados"],
    "valor_rp_pago": ["valor restos a pagar pagos"],
}

OBRIGATORIAS = ["codigo_emenda", "ano", "nome_autor", "localidade", "valor_empenhado", "valor_pago"]
COLUNAS_VALOR = [c for c in COLUNAS if c.startswith("valor_")]


def renomear_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia as colunas do CSV para os nomes canônicos. Falha se faltar obrigatória."""
    por_slug = {slug(c): c for c in df.columns}
    mapa = {}
    for canonico, opcoes in COLUNAS.items():
        for op in opcoes:
            if op in por_slug:
                mapa[por_slug[op]] = canonico
                break
    faltando = [c for c in OBRIGATORIAS if c not in mapa.values()]
    if faltando:
        raise ValueError(
            f"Colunas obrigatórias não encontradas: {faltando}. Colunas do arquivo: {list(df.columns)}"
        )
    return df.rename(columns=mapa)[list(mapa.values())]


# --------------------------------------------------------------------------- valores


def valor_br(v) -> float:
    """'1.234.567,89' -> 1234567.89. Vazio -> 0.0."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if not s or s == "-":
        return 0.0
    negativo = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(".", "").replace(",", ".")
    try:
        x = float(s)
    except ValueError:
        return 0.0
    return -x if negativo else x


# --------------------------------------------------------------------------- localidade

UFS = {
    "AC": "acre", "AL": "alagoas", "AP": "amapa", "AM": "amazonas", "BA": "bahia",
    "CE": "ceara", "DF": "distrito federal", "ES": "espirito santo", "GO": "goias",
    "MA": "maranhao", "MT": "mato grosso", "MS": "mato grosso do sul", "MG": "minas gerais",
    "PA": "para", "PB": "paraiba", "PR": "parana", "PE": "pernambuco", "PI": "piaui",
    "RJ": "rio de janeiro", "RN": "rio grande do norte", "RS": "rio grande do sul",
    "RO": "rondonia", "RR": "roraima", "SC": "santa catarina", "SP": "sao paulo",
    "SE": "sergipe", "TO": "tocantins",
}
UF_POR_NOME = {v: k for k, v in UFS.items()}
# Código IBGE da UF (2 primeiros dígitos do código do município) -> sigla.
UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
REGIOES = {"norte", "nordeste", "centro oeste", "sudeste", "sul"}

# Grafias antigas ou alternativas comuns em bases federais -> grafia do IBGE (slug).
ALIASES_MUNICIPIO = {
    ("moji mirim", "SP"): "mogi mirim",
    ("embu", "SP"): "embu das artes",
    ("parati", "RJ"): "paraty",
    ("santana do livramento", "RS"): "sant ana do livramento",
    ("eldorado dos carajas", "PA"): "eldorado do carajas",
    ("sao luis do paraitinga", "SP"): "sao luiz do paraitinga",
    ("brasilia", "DF"): "brasilia",
}


@dataclass
class Localidade:
    escopo: str  # municipal | estadual | regional | nacional | multiplo | outro
    municipio_ibge: str | None = None
    uf: str | None = None


class IndiceMunicipios:
    """Procura código IBGE por (nome, UF) tolerando acento, caixa e pontuação."""

    def __init__(self, municipios: list[dict]):
        self._por_nome_uf: dict[tuple[str, str], str] = {}
        self._codigos: set[str] = set()
        for m in municipios:
            codigo = str(m["codigo_ibge"])
            self._por_nome_uf[(slug(m["nome"]), m["uf"].upper())] = codigo
            self._codigos.add(codigo)

    def codigo(self, nome: str, uf: str) -> str | None:
        uf = (uf or "").upper()
        chave = slug(nome)
        chave = ALIASES_MUNICIPIO.get((chave, uf), chave)
        return self._por_nome_uf.get((chave, uf))

    def existe(self, codigo) -> bool:
        return str(codigo) in self._codigos


# "CAMPINAS - SP", "Campinas/SP", "CAMPINAS (SP)"
_RE_MUN_UF = re.compile(r"^(?P<nome>.+?)\s*(?:-|/|\()\s*(?P<uf>[A-Za-z]{2})\s*\)?$")


def classificar_localidade(texto, indice: IndiceMunicipios, codigo_ibge=None, uf_col=None) -> Localidade:
    """Converte o texto de localidade do Portal em (escopo, código IBGE, UF)."""
    # 1) Se o arquivo já traz o código IBGE do município, ele vale mais que o texto.
    if codigo_ibge is not None and not (isinstance(codigo_ibge, float) and pd.isna(codigo_ibge)):
        cod = re.sub(r"\D", "", str(codigo_ibge))
        if cod and indice.existe(cod):
            # A UF sai do próprio código IBGE; a coluna UF do arquivo pode vir por extenso.
            return Localidade("municipal", cod, UF_POR_CODIGO.get(cod[:2]))

    bruto = "" if texto is None or (isinstance(texto, float) and pd.isna(texto)) else str(texto).strip()
    s = slug(bruto)
    if not s:
        return Localidade("outro", None, _uf_valida(uf_col))
    if s in {"nacional", "brasil"}:
        return Localidade("nacional")
    if s in {"multiplo", "multiplos", "multipla"}:
        return Localidade("multiplo")

    # Região: "NORDESTE (REGIÃO)", "REGIÃO NORDESTE"
    sem_regiao = s.replace("regiao", "").strip()
    if sem_regiao in REGIOES and ("regiao" in s or s in REGIOES):
        return Localidade("regional")

    # Estado: "SÃO PAULO (UF)", "SP", "ESTADO DE SÃO PAULO"
    sem_uf = re.sub(r"\buf\b|\bestado d[eoa]s?\b", "", s).strip()
    if sem_uf.upper() in UFS and len(sem_uf) == 2:
        return Localidade("estadual", None, sem_uf.upper())
    if sem_uf in UF_POR_NOME and ("uf" in s.split() or "estado" in s or s == sem_uf):
        # "sao paulo" sozinho é ambíguo (estado ou capital); o Portal marca estado com "(UF)".
        if "uf" in s.split() or "estado" in s:
            return Localidade("estadual", None, UF_POR_NOME[sem_uf])

    # Município com UF: "CAMPINAS - SP"
    m = _RE_MUN_UF.match(bruto)
    if m and m.group("uf").upper() in UFS:
        uf = m.group("uf").upper()
        nome = re.sub(r"^(munic[ií]pio|prefeitura municipal)\s+de\s+", "", m.group("nome"), flags=re.I)
        cod = indice.codigo(nome, uf)
        if cod:
            return Localidade("municipal", cod, uf)
        return Localidade("outro", None, uf)

    # Só o nome do município, com UF vinda de outra coluna.
    uf = _uf_valida(uf_col)
    if uf:
        cod = indice.codigo(bruto, uf)
        if cod:
            return Localidade("municipal", cod, uf)

    if sem_uf in UF_POR_NOME:
        return Localidade("estadual", None, UF_POR_NOME[sem_uf])
    return Localidade("outro", None, uf)


def _uf_valida(uf) -> str | None:
    if uf is None or (isinstance(uf, float) and pd.isna(uf)):
        return None
    u = str(uf).strip().upper()
    return u if u in UFS else None


# --------------------------------------------------------------------------- tabela


def modalidade(acao) -> str:
    """Emendas Pix são transferências especiais; o resto fica como 'outras'."""
    return "pix" if "transferencia especial" in slug(acao) or "transferencias especiais" in slug(acao) else "outras"


def normalizar_emendas(df_bruto: pd.DataFrame, indice: IndiceMunicipios, ano_inicial: int) -> pd.DataFrame:
    """CSV bruto do Portal -> tabela fato com colunas canônicas, valores numéricos e IBGE."""
    df = renomear_colunas(df_bruto)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df = df[df["ano"] >= ano_inicial].copy()

    for c in COLUNAS_VALOR:
        if c in df.columns:
            df[c] = df[c].map(valor_br)

    locs = [
        classificar_localidade(
            row.get("localidade"), indice, row.get("codigo_municipio_ibge"), row.get("uf")
        )
        for row in df.to_dict("records")
    ]
    df["escopo"] = [l.escopo for l in locs]
    df["municipio_ibge"] = [l.municipio_ibge for l in locs]
    df["uf"] = [l.uf for l in locs]
    df["modalidade"] = df["acao"].map(modalidade) if "acao" in df.columns else "outras"
    for c in ["codigo_emenda", "codigo_autor", "numero_emenda", "tipo_emenda", "nome_autor", "funcao"]:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()
    return df.reset_index(drop=True)


def relatorio_qualidade(df: pd.DataFrame) -> dict:
    """Quanto do dinheiro conseguimos atribuir a um município."""
    total = float(df["valor_pago"].sum()) or 1.0
    por_escopo = (
        df.groupby("escopo")["valor_pago"].agg(["count", "sum"]).rename(columns={"count": "linhas", "sum": "valor_pago"})
    )
    return {
        "linhas": int(len(df)),
        "anos": sorted(int(a) for a in df["ano"].dropna().unique()),
        "valor_pago_total": round(float(df["valor_pago"].sum()), 2),
        "pct_valor_pago_com_municipio": round(
            100 * float(df.loc[df["escopo"] == "municipal", "valor_pago"].sum()) / total, 1
        ),
        "por_escopo": {
            k: {"linhas": int(v["linhas"]), "valor_pago": round(float(v["valor_pago"]), 2)}
            for k, v in por_escopo.iterrows()
        },
        "linhas_com_codigo_ibge_no_arquivo": int(
            df["codigo_municipio_ibge"].astype(str).str.strip().replace({"": None, "nan": None, "<NA>": None}).notna().sum()
        ) if "codigo_municipio_ibge" in df.columns else None,
        "localidades_top15_por_valor_pago": (
            df.groupby(["escopo", "localidade"], dropna=False)["valor_pago"].sum()
            .sort_values(ascending=False).head(15).round(2)
            .rename(index=lambda x: str(x)).reset_index()
            .apply(lambda r: f"{r['escopo']} | {r['localidade']} | {r['valor_pago']:,.0f}", axis=1).tolist()
        ),
        "localidades_nao_resolvidas_top20": (
            df.loc[df["escopo"] == "outro"]
            .groupby("localidade", dropna=False)["valor_pago"].sum()
            .sort_values(ascending=False).head(20).round(2)
            .rename(index=lambda x: str(x)).to_dict()
        ),
    }


# --------------------------------------------------------------------------- favorecidos
# EmendasParlamentares_PorFavorecido.csv: quem recebeu o dinheiro de cada emenda,
# com município e UF do favorecido. É aqui que está o destino municipal, já que no
# arquivo principal a maior parte do valor vem com localidade "MÚLTIPLO".

COLUNAS_FAVORECIDO = {
    "codigo_emenda": ["codigo da emenda"],
    "codigo_autor": ["codigo do autor da emenda"],
    "nome_autor": ["nome do autor da emenda"],
    "numero_emenda": ["numero da emenda"],
    "tipo_emenda": ["tipo de emenda"],
    "ano_mes": ["ano mes", "mes ano"],
    "codigo_favorecido": ["codigo do favorecido"],
    "favorecido": ["favorecido", "nome do favorecido"],
    "natureza_juridica": ["natureza juridica"],
    "tipo_favorecido": ["tipo favorecido"],
    "uf_favorecido": ["uf favorecido"],
    "municipio_favorecido": ["municipio favorecido"],
    "valor_recebido": ["valor recebido"],
}
OBRIGATORIAS_FAVORECIDO = ["codigo_emenda", "ano_mes", "municipio_favorecido", "uf_favorecido", "valor_recebido"]


def _ano_mes(v) -> tuple[int | None, int | None]:
    """'202403', '2024/03', '03/2024', '2024-03' -> (2024, 3)."""
    digitos = re.findall(r"\d+", str(v or ""))
    if len(digitos) == 1 and len(digitos[0]) == 6:
        return int(digitos[0][:4]), int(digitos[0][4:])
    ano = next((int(d) for d in digitos if len(d) == 4), None)
    mes = next((int(d) for d in digitos if len(d) <= 2), None)
    return ano, mes


def _sigla_uf(v) -> str | None:
    s = slug(v)
    if s.upper() in UFS:
        return s.upper()
    return UF_POR_NOME.get(s)


def normalizar_favorecidos(df_bruto: pd.DataFrame, indice: IndiceMunicipios, ano_inicial: int) -> pd.DataFrame:
    por_slug = {slug(c): c for c in df_bruto.columns}
    mapa = {}
    for canonico, opcoes in COLUNAS_FAVORECIDO.items():
        for op in opcoes:
            if op in por_slug:
                mapa[por_slug[op]] = canonico
                break
    faltando = [c for c in OBRIGATORIAS_FAVORECIDO if c not in mapa.values()]
    if faltando:
        raise ValueError(f"Favorecidos: colunas não encontradas {faltando}. Arquivo: {list(df_bruto.columns)}")
    df = df_bruto.rename(columns=mapa)[list(mapa.values())].copy()

    am = df["ano_mes"].map(_ano_mes)
    df["ano"] = pd.array([a for a, _ in am], dtype="Int64")
    df["mes"] = pd.array([m for _, m in am], dtype="Int64")
    df = df[df["ano"] >= ano_inicial].copy()
    df["valor_recebido"] = df["valor_recebido"].map(valor_br)

    # Muitos favorecidos se repetem: resolve cada par (município, UF) uma vez só.
    df["uf"] = df["uf_favorecido"].map(_sigla_uf)
    pares = df[["municipio_favorecido", "uf"]].drop_duplicates()
    codigos = {
        (m, u): (indice.codigo(m, u) if u else None)
        for m, u in pares.itertuples(index=False)
    }
    df["municipio_ibge"] = [codigos[(m, u)] for m, u in zip(df["municipio_favorecido"], df["uf"])]
    for c in ["codigo_emenda", "codigo_autor", "nome_autor", "tipo_emenda", "favorecido", "tipo_favorecido"]:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()
    return df.reset_index(drop=True)


def relatorio_favorecidos(df: pd.DataFrame) -> dict:
    total = float(df["valor_recebido"].sum()) or 1.0
    com = df["municipio_ibge"].notna()
    return {
        "linhas": int(len(df)),
        "valor_recebido_total": round(float(df["valor_recebido"].sum()), 2),
        "pct_valor_recebido_com_municipio": round(100 * float(df.loc[com, "valor_recebido"].sum()) / total, 1),
        "municipios_distintos": int(df["municipio_ibge"].nunique()),
        "nao_resolvidos_top20": (
            df.loc[~com]
            .assign(chave=lambda d: d["municipio_favorecido"].astype(str) + " / " + d["uf_favorecido"].astype(str))
            .groupby("chave")["valor_recebido"].sum()
            .sort_values(ascending=False).head(20).round(2).to_dict()
        ),
    }

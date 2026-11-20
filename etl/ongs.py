"""Transparência das ONGs (organizações da sociedade civil, OSCs).

Junta, pelo CNPJ, o cadastro de todas as OSCs do país (Mapa das OSCs, IPEA) com o
dinheiro público federal que elas receberam (emendas parlamentares por favorecido e
convênios/termos do Transferegov) e com o financiamento internacional que doadores
estrangeiros declaram no padrão IATI. Gera a seção /ongs/ do site.

Tudo é reproduzido como publicado nas fontes. Não há juízo sobre legalidade.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from . import config

# --------------------------------------------------------------------------- fontes

MOSC_PAGINA = "https://mapaosc.ipea.gov.br/base-dados"
MOSC_BASE = "https://mapaosc.ipea.gov.br"
MOSC_INTERNACIONAIS = MOSC_BASE + "/arquivos/subitems/1754-20250718analiseoscinternacionais3204.xlsx"
PORTAL_DOWNLOAD = "https://portaldatransparencia.gov.br/download-de-dados"
DPORTAL = "https://d-portal.org"
IATI_PAGINA = "https://d-portal.org/ctrack.html?country=BR"
PORTAL_EMENDAS = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares"

RAW = config.RAW_DIR / "ongs"

# Naturezas jurídicas (tabela da Receita) usadas nos rótulos.
NATUREZAS = {
    "3069": "Fundação privada",
    "3204": "Estabelecimento no Brasil de fundação ou associação estrangeira",
    "3212": "Fundação ou associação domiciliada no exterior",
    "3220": "Organização religiosa",
    "3239": "Comunidade indígena",
    "3301": "Organização social (OS)",
    "3999": "Associação privada",
}
NATUREZAS_ESTRANGEIRAS = {"3204", "3212"}

AREAS = {
    "Area_Assistencia_social": "Assistência social",
    "Area_Associacoes_patronais_e_profissionais": "Associações patronais e profissionais",
    "Area_Cultura_e_recreacao": "Cultura e recreação",
    "Area_Desenvolvimento_e_defesa_de_direitos_e_interesses": "Desenvolvimento e defesa de direitos",
    "Area_Educacao_e_pesquisa": "Educação e pesquisa",
    "Area_Outras_atividades_associativas": "Outras atividades associativas",
    "Area_Religiao": "Religião",
    "Area_Saude": "Saúde",
}


# Linha de fonte oficial do rodapé das páginas de ONGs (o resto do rodapé vem de layout.rodape).
FONTE_ONGS = ('<p><strong>Fontes oficiais:</strong> <a href="https://mapaosc.ipea.gov.br/base-dados">Mapa das OSCs (IPEA)</a> e '
              '<a href="https://portaldatransparencia.gov.br/download-de-dados">Portal da Transparência (CGU)</a>, ligados pelo CNPJ. '
              'Valores reproduzidos como publicados; não constituem juízo sobre a legalidade de nenhum repasse. '
              '<a href="{raiz}ongs/#fontes">Fontes e limites</a>.</p>')
FONTE_IATI = ('<p><strong>Fonte:</strong> dados publicados pelos próprios doadores no padrão IATI '
              '(<a href="https://d-portal.org/">d-portal</a>), com os nomes como o doador escreveu e <strong>sem vínculo com CNPJ</strong>. '
              '<a href="{raiz}ongs/#fontes">Fontes e limites</a>.</p>')


def digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def cnpj8(v) -> str:
    """Raiz do CNPJ (8 dígitos): junta matriz e filiais da mesma organização."""
    d = digitos(v)
    return d.zfill(14)[:8] if 9 <= len(d) <= 14 else ""


def formatar_cnpj(d: str) -> str:
    d = digitos(d).zfill(14)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def consertar(texto):
    """Desfaz texto UTF-8 lido como Latin-1 ('SÃ£o' -> 'São'), comum na base do IPEA."""
    if not isinstance(texto, str) or ("Ã" not in texto and "Â" not in texto):
        return texto
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def chave_nome(texto) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


def valor_br(v) -> float:
    s = str(v or "").strip().replace("R$", "").strip()
    if not s:
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------- download


def _get(url: str, timeout: int = 600):
    import requests

    from .download import HEADERS

    r = requests.get(url, headers={**HEADERS, "User-Agent": "Mozilla/5.0 (painel-emendas; dados abertos)"}, timeout=timeout, stream=True)
    r.raise_for_status()
    return r


def _salvar(url: str, caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with _get(url) as r, open(caminho, "wb") as f:
        for bloco in r.iter_content(1 << 20):
            f.write(bloco)
    print(f"ongs: {url} -> {caminho.name} ({caminho.stat().st_size / 1e6:.1f} MB)")
    return caminho


def url_base_mosc() -> str:
    """O nome do arquivo muda a cada atualização (AAAAMMDD_MOSC_baseDivulgacao.csv): lê da página."""
    html = _get(MOSC_PAGINA, 60).text
    achados = sorted(set(re.findall(r'href="(/download/\d{8}_MOSC_baseDivulgacao\.csv)"', html)))
    if not achados:
        raise RuntimeError("Mapa das OSCs: link da base não encontrado na página")
    return MOSC_BASE + achados[-1]


def url_portal(origem: str) -> str:
    """Arquivo mais recente de um conjunto do Portal (a página lista as datas em arquivos.push({...}))."""
    html = _get(f"{PORTAL_DOWNLOAD}/{origem}", 60).text
    datas = re.findall(r'"ano"\s*:\s*"(\d{4})",\s*"mes"\s*:\s*"(\d{2})"(?:,\s*"dia"\s*:\s*"(\d{2})")?', html)
    if not datas:
        raise RuntimeError(f"Portal: datas de {origem} não encontradas na página")
    ano, mes, dia = max(datas)
    return f"{PORTAL_DOWNLOAD}/{origem}/{ano}{mes}{dia}"


def _data_url(url: str) -> str:
    m = re.search(r"(\d{4})(\d{2})(\d{2})", url.rsplit("/", 1)[-1])
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""


def baixar(raw: Path = RAW) -> dict:
    """Baixa as fontes. Só o Mapa das OSCs é obrigatório; as outras faltam sem derrubar o ETL."""
    raw.mkdir(parents=True, exist_ok=True)
    url = url_base_mosc()
    out: dict = {"mosc": _salvar(url, raw / "mosc.csv"), "mosc_data": _data_url(url)}
    tarefas = {
        "internacionais": (MOSC_INTERNACIONAIS, raw / "internacionais.xlsx"),
    }
    for chave, (url, caminho) in tarefas.items():
        try:
            out[chave] = _salvar(url, caminho)
        except Exception as erro:  # noqa: BLE001 - fonte opcional
            print(f"aviso: ongs: {chave} indisponível ({type(erro).__name__}: {erro})")
            out[chave] = None
    for chave in ("convenios", "cepim"):
        try:
            url = url_portal(chave)
            out[chave] = _salvar(url, raw / f"{chave}.zip")
            out[f"{chave}_data"] = _data_url(url)
        except Exception as erro:  # noqa: BLE001
            print(f"aviso: ongs: {chave} indisponível ({type(erro).__name__}: {erro})")
            out[chave] = None
    try:
        out["iati"] = _salvar(f"{DPORTAL}/q.xml?from=act,country&country_code=BR&limit=50000", raw / "iati_br.xml")
    except Exception as erro:  # noqa: BLE001
        print(f"aviso: ongs: IATI indisponível ({type(erro).__name__}: {erro})")
        out["iati"] = None
    return out


# --------------------------------------------------------------------------- leitura


def ler_mosc(fonte) -> pd.DataFrame:
    """Uma linha por estabelecimento (CNPJ de 14 dígitos), com nomes corrigidos e áreas em texto."""
    df = pd.read_csv(fonte, sep=";", encoding="latin-1", dtype=str, keep_default_na=False)
    for c in ["tx_razao_social_osc", "tx_nome_fantasia_osc", "matriz_filial", "situacao_cadastral", "removida_do_mosc"]:
        if c in df:
            uniq = df[c].unique()
            df[c] = df[c].map(dict(zip(uniq, (consertar(u) for u in uniq))))
    areas = [c for c in AREAS if c in df.columns]
    flags = df[areas].eq("1") if areas else pd.DataFrame(index=df.index)
    rotulos = [AREAS[c] for c in areas]
    out = pd.DataFrame({
        "cnpj": df["cnpj"].map(digitos).str.zfill(14),
        "nome": df["tx_razao_social_osc"].str.strip(),
        "fantasia": df.get("tx_nome_fantasia_osc", "").str.strip() if "tx_nome_fantasia_osc" in df else "",
        "natureza": df.get("natureza_juridica", "").map(digitos) if "natureza_juridica" in df else "",
        "matriz": df.get("matriz_filial", "").str.lower().str.startswith("matriz") if "matriz_filial" in df else True,
        "situacao": df.get("situacao_cadastral", ""),
        "fundacao": df.get("dt_fundacao_osc", "").str[:10] if "dt_fundacao_osc" in df else "",
        "removida": df.get("removida_do_mosc", "").str.lower().eq("sim") if "removida_do_mosc" in df else False,
        "municipio_ibge": df.get("cd_municipio", "").map(digitos) if "cd_municipio" in df else "",
        "municipio": df.get("municipio_nome", "").str.strip(),
        "uf": df.get("UF_Sigla", "").str.strip().str.upper(),
        "areas": ["; ".join(r for r, v in zip(rotulos, linha) if v) for linha in flags.itertuples(index=False)] if areas else "",
    })
    out = out[out["cnpj"].str.len().eq(14) & ~out["cnpj"].eq("0" * 14)]
    out["cnpj8"] = out["cnpj"].str[:8]
    return out.reset_index(drop=True)


def organizacoes(est: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por organização (raiz do CNPJ). Dados de cadastro vêm da matriz."""
    est = est.sort_values(["cnpj8", "matriz", "cnpj"], ascending=[True, False, True])
    base = est.drop_duplicates("cnpj8").set_index("cnpj8")
    g = est.groupby("cnpj8")
    org = base[["cnpj", "nome", "fantasia", "natureza", "situacao", "fundacao", "municipio_ibge", "municipio", "uf", "areas"]].copy()
    org["estabelecimentos"] = g.size()
    org["ufs_atuacao"] = g["uf"].agg(lambda s: sorted({u for u in s if u}))
    org["ativa"] = org["situacao"].str.lower().eq("ativa") & ~g["removida"].all()
    return org


def ler_internacionais(fonte) -> dict[str, str]:
    """Raiz do CNPJ -> país, para OSCs que o IPEA confirmou como estrangeiras (natureza 320-4)."""
    try:
        df = pd.read_excel(fonte, sheet_name="OSCs_Microdados", dtype=str)
    except Exception as erro:  # noqa: BLE001
        print(f"aviso: ongs: lista de OSCs internacionais ilegível ({erro})")
        return {}
    ok = df[pd.to_numeric(df.get("ChecadoEstrangeiroIPEA"), errors="coerce").eq(1)]
    # cnpj_basico já é a raiz (8 dígitos), às vezes sem os zeros à esquerda.
    return {digitos(r["cnpj_basico"]).zfill(8): str(r.get("PaisChecagemIPEA") or "").strip()
            for _, r in ok.iterrows() if digitos(r["cnpj_basico"])}


def _ler_portal(fonte, nome_contem: str) -> pd.DataFrame:
    with zipfile.ZipFile(fonte) as zf:
        nome = next(n for n in zf.namelist() if nome_contem.lower() in n.lower() and "ordens" not in n.lower())
        with zf.open(nome) as f:
            return pd.read_csv(f, sep=";", encoding=config.CSV_ENCODING, dtype=str, keep_default_na=False)


def _colunas(df: pd.DataFrame, mapa: dict[str, str]) -> pd.DataFrame:
    por_chave = {chave_nome(c): c for c in df.columns}
    out = {}
    for novo, original in mapa.items():
        c = por_chave.get(chave_nome(original))
        out[novo] = df[c] if c else ""
    return pd.DataFrame(out, index=df.index)


def ler_convenios(fonte) -> pd.DataFrame:
    """Convênios, termos de fomento/colaboração e congêneres do Portal da Transparência, por convenente (CNPJ)."""
    df = _colunas(_ler_portal(fonte, "convenios"), {
        "numero": "NÚMERO CONVÊNIO", "uf": "UF", "municipio": "NOME MUNICÍPIO", "situacao": "SITUAÇÃO CONVÊNIO",
        "objeto": "OBJETO DO CONVÊNIO", "orgao": "NOME ÓRGÃO SUPERIOR", "concedente": "NOME ÓRGÃO CONCEDENTE",
        "cnpj": "CÓDIGO CONVENENTE", "tipo_convenente": "TIPO CONVENENTE", "nome": "NOME CONVENENTE",
        "instrumento": "TIPO INSTRUMENTO", "valor": "VALOR CONVÊNIO", "liberado": "VALOR LIBERADO",
        "inicio": "DATA INÍCIO VIGÊNCIA", "fim": "DATA FINAL VIGÊNCIA",
    })
    df["cnpj8"] = df["cnpj"].map(cnpj8)
    df = df[df["cnpj8"].ne("") & df["cnpj"].map(digitos).str.len().ge(14)].copy()
    for c in ("valor", "liberado"):
        df[c] = df[c].map(valor_br)
    df["ano"] = pd.to_numeric(df["inicio"].str[-4:], errors="coerce").astype("Int64")
    for c in ("objeto", "orgao", "concedente", "situacao", "instrumento", "municipio"):
        df[c] = df[c].str.strip()
    return df.reset_index(drop=True)


def ler_cepim(fonte) -> pd.DataFrame:
    """Entidades impedidas de receber recursos federais (CEPIM, CGU), com o motivo publicado."""
    df = _colunas(_ler_portal(fonte, "cepim"), {
        "cnpj": "CNPJ ENTIDADE", "nome": "NOME ENTIDADE", "convenio": "NÚMERO CONVÊNIO",
        "orgao": "ÓRGÃO CONCEDENTE", "motivo": "MOTIVO DO IMPEDIMENTO",
    })
    df["cnpj8"] = df["cnpj"].map(cnpj8)
    return df[df["cnpj8"].ne("")].reset_index(drop=True)


IATI_PAPEIS = {"2": "responsável", "3": "extensão", "4": "executora"}
# Tipos de organização IATI que são ONGs: internacional, nacional, regional, sediada no país parceiro.
IATI_TIPOS_ONG = {"21", "22", "23", "24"}


def _texto(el) -> str:
    return " ".join((el.findtext("narrative") or el.text or "").split()) if el is not None else ""


def ler_iati(fonte) -> pd.DataFrame:
    """Organizações citadas em atividades IATI com destino ao Brasil, como executoras ou recebedoras.

    Uma linha por (atividade, organização), com o doador (quem publicou), título, anos e o valor que o
    doador declara ter desembolsado ou gasto para aquela organização, na moeda declarada.
    """
    linhas = []
    for _, el in ET.iterparse(fonte, events=("end",)):
        if el.tag != "iati-activity":
            continue
        aid = (el.findtext("iati-identifier") or "").strip()
        doador = _texto(el.find("reporting-org"))
        titulo = _texto(el.find("title"))[:200]
        anos = sorted({d.get("iso-date", "")[:4] for d in el.findall("activity-date") if d.get("iso-date")})
        moeda_padrao = el.get("default-currency", "")
        orgs: dict[tuple[str, str], dict] = {}

        def org(ref, nome, tipo, papel):
            o = orgs.setdefault((ref, nome), {"tipo": tipo, "papel": papel, "valor": 0.0, "moeda": ""})
            o["tipo"] = o["tipo"] or tipo
            return o

        for po in el.findall("participating-org"):
            if po.get("role") in IATI_PAPEIS:
                org((po.get("ref") or "").strip(), _texto(po), po.get("type", ""), IATI_PAPEIS[po.get("role")])
        for tr in el.findall("transaction"):
            tipo_tr = tr.find("transaction-type")
            ro = tr.find("receiver-org")
            if ro is None or tipo_tr is None or tipo_tr.get("code") not in ("3", "4"):
                continue
            o = org((ro.get("ref") or "").strip(), _texto(ro), ro.get("type", ""), "recebedora")
            v = tr.find("value")
            try:
                valor = float((v.text or "0").strip()) if v is not None else 0.0
            except ValueError:
                valor = 0.0
            moeda = (v.get("currency") if v is not None else "") or moeda_padrao
            if o["moeda"] in ("", moeda):
                o["moeda"] = moeda
                o["valor"] += valor
        for (ref, nome), o in orgs.items():
            if not (ref or nome):
                continue
            linhas.append({"aid": aid, "doador": doador, "titulo": titulo, "ano_inicio": anos[0] if anos else "",
                           "ano_fim": anos[-1] if anos else "", "ref": ref, "nome": nome, "tipo": o["tipo"],
                           "papel": o["papel"], "valor": round(o["valor"], 2), "moeda": o["moeda"] or moeda_padrao})
        el.clear()
    cols = ["aid", "doador", "titulo", "ano_inicio", "ano_fim", "ref", "nome", "tipo", "papel", "valor", "moeda"]
    df = pd.DataFrame(linhas, columns=cols)
    return df


# --------------------------------------------------------------------------- junção

def _registros(df: pd.DataFrame, colunas: list[str], n: int, ordem: str) -> list[list]:
    if df.empty:
        return []
    t = df.sort_values(ordem, ascending=False).head(n)[colunas]
    return [[(None if pd.isna(v) else (round(float(v), 2) if isinstance(v, float) else (int(v) if hasattr(v, "item") and not isinstance(v, str) else v))) for v in linha]
            for linha in t.itertuples(index=False)]


def montar(org: pd.DataFrame, fav: pd.DataFrame | None, conv: pd.DataFrame | None,
           cepim: pd.DataFrame | None, internacionais: dict[str, str]) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Resumo por organização (para listas e rankings) e ficha completa de cada uma (para a página).

    Só entram vínculos por CNPJ vindos de fonte oficial (CGU, IPEA/Receita). Projetos de doadores
    estrangeiros (IATI) NÃO são ligados a nenhuma OSC: ficam numa lista à parte (ver gravar_internacional).
    """
    org = org.copy()
    idx = org.index
    vazio = pd.Series(0.0, index=idx)

    # Emendas parlamentares: favorecido cujo CNPJ é de uma OSC.
    em = pd.DataFrame()
    if fav is not None and "codigo_favorecido" in fav:
        em = fav.assign(cnpj8=fav["codigo_favorecido"].map(cnpj8))
        em = em[em["cnpj8"].isin(idx)]
    org["emendas"] = em.groupby("cnpj8")["valor_recebido"].sum().reindex(idx).fillna(0.0) if len(em) else vazio

    cv = conv[conv["cnpj8"].isin(idx)] if conv is not None and len(conv) else pd.DataFrame()
    org["convenios"] = cv.groupby("cnpj8")["valor"].sum().reindex(idx).fillna(0.0) if len(cv) else vazio
    org["convenios_liberado"] = cv.groupby("cnpj8")["liberado"].sum().reindex(idx).fillna(0.0) if len(cv) else vazio
    org["n_convenios"] = cv.groupby("cnpj8").size().reindex(idx).fillna(0).astype(int) if len(cv) else 0

    ce = cepim[cepim["cnpj8"].isin(idx)] if cepim is not None and len(cepim) else pd.DataFrame()
    org["cepim"] = ce.groupby("cnpj8").size().reindex(idx).fillna(0).astype(int) if len(ce) else 0
    org["pais_estrangeiro"] = [internacionais.get(c) or ("exterior" if n in NATUREZAS_ESTRANGEIRAS else "")
                               for c, n in zip(idx, org["natureza"])]
    org["federal"] = org[["emendas", "convenios_liberado"]].max(axis=1)

    fichas: dict[str, dict] = {}
    em_g = dict(tuple(em.groupby("cnpj8"))) if len(em) else {}
    cv_g = dict(tuple(cv.groupby("cnpj8"))) if len(cv) else {}
    ce_g = dict(tuple(ce.groupby("cnpj8"))) if len(ce) else {}
    for c8, o in org.iterrows():
        f = {
            "cnpj": formatar_cnpj(o["cnpj"]), "nome": o["nome"], "fantasia": o["fantasia"] or None,
            "natureza": NATUREZAS.get(o["natureza"], o["natureza"]), "situacao": o["situacao"], "fundacao": o["fundacao"] or None,
            "municipio": o["municipio"], "uf": o["uf"], "ibge": o["municipio_ibge"] or None, "areas": o["areas"] or None,
            "estabelecimentos": int(o["estabelecimentos"]), "ufs": o["ufs_atuacao"],
            "estrangeira": o["pais_estrangeiro"] or None,
        }
        if c8 in em_g:
            e = em_g[c8]
            f["emendas"] = {
                "total": round(float(e["valor_recebido"].sum()), 2),
                "por_ano": {str(int(a)): round(float(v), 2) for a, v in e.groupby("ano")["valor_recebido"].sum().items() if pd.notna(a)},
                "autores": _registros(e.groupby("nome_autor", as_index=False)["valor_recebido"].sum(), ["nome_autor", "valor_recebido"], 15, "valor_recebido"),
                "explorar": [[uf, sorted({f"{n} · {c}" for n, c in zip(g["favorecido"], g["codigo_favorecido"])})]
                             for uf, g in e.groupby("uf") if isinstance(uf, str)],
            }
        if c8 in cv_g:
            c = cv_g[c8]
            f["convenios"] = {
                "n": int(len(c)), "valor": round(float(c["valor"].sum()), 2), "liberado": round(float(c["liberado"].sum()), 2),
                "por_orgao": _registros(c.groupby("orgao", as_index=False)[["liberado"]].sum(), ["orgao", "liberado"], 10, "liberado"),
                "lista": _registros(c, ["numero", "ano", "instrumento", "concedente", "objeto", "municipio", "uf", "situacao", "valor", "liberado"], 40, "valor"),
                "municipios": sorted({f"{m} ({u})" for m, u in zip(c["municipio"], c["uf"]) if m}),
            }
            for l in f["convenios"]["lista"]:
                l[4] = (l[4] or "")[:220]
        if c8 in ce_g:
            f["cepim"] = _registros(ce_g[c8].assign(o=0), ["convenio", "orgao", "motivo"], 20, "o")
        fichas[c8] = f
    return org, fichas


# --------------------------------------------------------------------------- site


def _json(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def bandeiras(o) -> int:
    """Bits para filtros no navegador: 1 emendas, 2 convênios, 8 CEPIM, 16 estrangeira, 32 inativa (4 não é usado)."""
    return ((o.emendas > 0) * 1 | (o.n_convenios > 0) * 2 | (o.cepim > 0) * 8
            | bool(o.pais_estrangeiro) * 16 | (not o.ativa) * 32)


def gravar(org: pd.DataFrame, fichas: dict[str, dict], destino: Path, atualizado: str, fontes: dict[str, str],
           iati: pd.DataFrame | None = None) -> dict:
    """Grava /ongs/: fichas em 1.000 arquivos (pelos 3 primeiros dígitos do CNPJ), lista por UF e destaques."""
    from .site import UFS, brl, e, inteiro, json_ld, pagina, tabela

    pasta = destino / "ongs"
    pasta.mkdir(parents=True, exist_ok=True)
    # Fichas: só organizações ativas ou que tenham algum dado de dinheiro/impedimento.
    relevantes = org[org["ativa"] | (org["federal"] > 0) | (org["cepim"] > 0) | (org["pais_estrangeiro"] != "")]
    lotes: dict[str, dict] = {}
    for c8 in relevantes.index:
        lotes.setdefault(c8[:3], {})[c8] = fichas[c8]
    for p, lote in lotes.items():
        _json(pasta / "d" / f"{p}.json", lote)
    # Lista por UF (busca de todas as OSCs do estado): [cnpj8, nome, município, bits, valor federal].
    rel = relevantes.assign(bits=[bandeiras(o) for o in relevantes.itertuples()])
    for uf, g in rel.groupby("uf"):
        if uf in UFS:
            g = g.sort_values("federal", ascending=False)
            _json(pasta / "l" / f"{uf}.json", [[c, n, m, int(b), round(float(v))] for c, n, m, b, v
                                              in zip(g.index, g["nome"], g["municipio"], g["bits"], g["federal"])])
    # Destaques nacionais: quem tem dinheiro federal, impedimento ou é estrangeira (busca rápida, sem escolher UF).
    dest = rel[(rel["bits"] & 27) > 0].sort_values("federal", ascending=False)
    _json(pasta / "destaques.json", [[c, n, u, m, int(b), round(float(v))] for c, n, u, m, b, v
                                     in zip(dest.index, dest["nome"], dest["uf"], dest["municipio"], dest["bits"], dest["federal"])])

    ativas = org[org["ativa"]]
    resumo = {
        "atualizado": atualizado, "oscs": int(len(org)), "ativas": int(len(ativas)),
        "com_emendas": int((org["emendas"] > 0).sum()), "emendas": round(float(org["emendas"].sum()), 2),
        "com_convenios": int((org["n_convenios"] > 0).sum()), "convenios_liberado": round(float(org["convenios_liberado"].sum()), 2),
        "estrangeiras": int((org["pais_estrangeiro"] != "").sum()),
        "cepim": int((org["cepim"] > 0).sum()), "fichas": int(len(relevantes)), "arquivos_fichas": len(lotes),
    }
    _json(pasta / "resumo.json", resumo)

    def link(c8, nome):
        return f'<a href="o/?c={c8}">{e(nome)}</a>'

    def top(col, n=25):
        t = org[org[col] > 0].sort_values(col, ascending=False).head(n)
        return tabela(["Organização", "UF", "Valor"], [[link(c, o["nome"]), e(o["uf"]), brl(o[col])] for c, o in t.iterrows()], {2})

    resumo.update(gravar_internacional(iati, pasta, atualizado))
    por_uf = ativas.groupby("uf").agg(oscs=("nome", "size"), emendas=("emendas", "sum"), conv=("convenios_liberado", "sum"))
    tab_uf = tabela(["UF", "OSCs ativas", "Emendas recebidas", "Convênios (liberado)"],
                    [[f'<a href="#uf={u}" data-uf="{u}">{e(UFS.get(u, u))}</a>', inteiro(r.oscs), brl(r.emendas), brl(r.conv)]
                     for u, r in por_uf.sort_values("oscs", ascending=False).iterrows() if u in UFS], {1, 2, 3})
    areas = ativas["areas"].str.split("; ").explode()
    tab_area = tabela(["Área de atuação", "OSCs ativas"], [[e(a or "Não informada"), inteiro(n)] for a, n in areas.value_counts().items()], {1})

    corpo = f"""
<p class="migalha"><a href="../">Início</a> › ONGs</p>
<h1>Transparência das ONGs</h1>
<p class="destaque">O Brasil tem <strong>{inteiro(resumo["ativas"])}</strong> organizações da sociedade civil ativas.
Aqui você vê, para cada uma, quanto recebeu do governo federal (emendas parlamentares e convênios), onde ela atua
e se está impedida de receber recursos. O dinheiro que doadores estrangeiros declaram enviar ao Brasil está numa
<a href="internacional/">lista à parte</a>.</p>
<section class="busca-ongs">
<label for="q">Buscar por nome, CNPJ ou cidade</label>
<input id="q" type="search" autocomplete="off" placeholder="Ex.: APAE, Instituto Socioambiental, 12.345.678">
<div class="controles">
<label>Estado<select id="uf"><option value="">Só as que receberam dinheiro (Brasil)</option>{"".join(f'<option value="{u}">{e(n)} (todas)</option>' for u, n in sorted(UFS.items(), key=lambda x: x[1]))}</select></label>
<label>Mostrar<select id="filtro"><option value="0">Todas</option><option value="1">Com emendas</option><option value="2">Com convênios</option>
<option value="16">Estrangeiras</option><option value="8">Impedidas (CEPIM)</option></select></label>
</div>
<p id="contagem" class="dica"></p>
<ul id="res" class="resultados"></ul>
</section>

<section class="kpis">
<div class="kpi"><strong>{inteiro(resumo["com_emendas"])}</strong><span>OSCs receberam emendas · {brl(resumo["emendas"])}</span></div>
<div class="kpi"><strong>{inteiro(resumo["com_convenios"])}</strong><span>têm convênios federais · {brl(resumo["convenios_liberado"])} liberados</span></div>
<div class="kpi"><strong>{inteiro(resumo["iati_projetos"])}</strong><span>projetos de doadores estrangeiros no Brasil (<a href="internacional/">lista à parte</a>)</span></div>
<div class="kpi"><strong>{inteiro(resumo["estrangeiras"])}</strong><span>são filiais de organizações estrangeiras</span></div>
<div class="kpi"><strong>{inteiro(resumo["cepim"])}</strong><span>estão impedidas de receber recursos (CEPIM)</span></div>
</section>

<section><h2>Quem mais recebeu em convênios federais (valor liberado)</h2>{top("convenios_liberado")}</section>
<section><h2>Quem mais recebeu em emendas parlamentares</h2>{top("emendas")}
<p class="dica">Parte das emendas é paga por meio de convênio. Por isso os dois valores não devem ser somados.</p></section>
<section><h2>Financiamento internacional declarado pelos doadores</h2>
<p>Governos e fundações estrangeiras publicam no padrão internacional IATI os projetos que financiam no Brasil e o nome de
quem executa ou recebe. Esses dados <strong>não têm confirmação oficial brasileira</strong>, por isso não são ligados a
nenhuma ONG deste cadastro: ficam numa <a href="internacional/">lista à parte</a>, com o nome escrito exatamente como o doador publicou.</p></section>
<section><h2>Por estado</h2>{tab_uf}</section>
<section><h2>Por área de atuação</h2>{tab_area}
<p class="dica">Uma OSC pode atuar em mais de uma área, por isso a soma passa do total.</p></section>

<section id="fontes"><h2>Fontes e limites</h2>
<ul>
<li><strong>Cadastro de todas as OSCs</strong>: <a href="{MOSC_PAGINA}">Mapa das Organizações da Sociedade Civil (IPEA)</a>, que reúne dados da Receita Federal. Base de {e(fontes.get("mosc", ""))}.</li>
<li><strong>Emendas parlamentares</strong>: <a href="{PORTAL_EMENDAS}">Portal da Transparência (CGU)</a>, arquivo de favorecidos, ligado pelo CNPJ.</li>
<li><strong>Convênios, termos de fomento e de colaboração</strong>: <a href="{PORTAL_DOWNLOAD}/convenios">Portal da Transparência (CGU)</a>, pelo CNPJ do convenente. Arquivo de {e(fontes.get("convenios", ""))}.</li>
<li><strong>Impedimentos</strong>: <a href="{PORTAL_DOWNLOAD}/cepim">CEPIM (CGU)</a>, entidades impedidas de receber transferências federais. Arquivo de {e(fontes.get("cepim", ""))}.</li>
<li><strong>Financiamento internacional</strong>: projetos com destino ao Brasil publicados pelos próprios doadores no padrão
<a href="https://iatistandard.org/pt/">IATI</a>, lidos pelo <a href="{IATI_PAGINA}">d-portal</a>. Mostrados à parte, sem ligação com o cadastro.</li>
<li><strong>Organizações estrangeiras</strong>: natureza jurídica 320-4/321-2 da Receita e a <a href="{MOSC_PAGINA}">checagem do IPEA</a>.</li>
</ul>
<p><strong>O que não está aqui.</strong> Não existe no Brasil um registro oficial único do dinheiro que vem do exterior para ONGs.
O IATI só mostra o que cada doador escolhe publicar; muitas fundações privadas e governos não publicam, e quase nenhum
doador informa o CNPJ de quem recebe. Como não há confirmação oficial, este site <strong>não liga</strong> esses projetos a
nenhuma ONG: as fichas só trazem vínculos por CNPJ vindos de fontes do governo (CGU, Receita Federal e IPEA). Dinheiro de estados e municípios, isenções fiscais e
doações de empresas e pessoas também não estão aqui.</p>
<p>Os valores são reproduzidos como publicados pelas fontes e não constituem juízo sobre a legalidade de nenhum repasse
ou sobre a atuação de nenhuma organização. Encontrou um erro? <a href="https://github.com/projects-betanull/painel-emendas/issues">Avise aqui</a>.</p>
</section>
<script src="ongs.js" defer></script>
"""
    (pasta / "index.html").write_text(
        pagina("Transparência das ONGs: dinheiro público e estrangeiro de cada organização",
               "Quanto cada ONG do Brasil recebeu em emendas parlamentares e convênios federais, onde atua e se está impedida. "
               "Projetos de doadores estrangeiros no Brasil, como declarados. Todas as OSCs do país, com fonte oficial.", corpo, "../", atualizado,
               url="ongs/", fonte=FONTE_ONGS.format(raiz="../"), sub="transparência das ONGs", extra_head=json_ld({"@context": "https://schema.org", "@type": "Dataset",
                   "name": "Transparência das organizações da sociedade civil do Brasil",
                   "description": "Cadastro das OSCs (IPEA) ligado pelo CNPJ a emendas, convênios federais e CEPIM; projetos de doadores estrangeiros (IATI) à parte.",
                   "url": "https://painel-emendas.pages.dev/ongs/", "inLanguage": "pt-BR", "isAccessibleForFree": True})),
        encoding="utf-8")
    mapa = destino / "sitemap.xml"
    if mapa.exists() and "/ongs/<" not in mapa.read_text(encoding="utf-8"):
        loc = f"<url><loc>{config.SITE_URL}/ongs/</loc><lastmod>{date.today().isoformat()}</lastmod></url>"
        mapa.write_text(mapa.read_text(encoding="utf-8").replace("</urlset>", loc + "</urlset>"), encoding="utf-8")
    print(f"ongs: {resumo}")
    return resumo


def gravar_internacional(iati: pd.DataFrame | None, pasta: Path, atualizado: str) -> dict:
    """Página /ongs/internacional/: projetos IATI no Brasil e organizações citadas, com o nome como o doador escreveu.

    Nenhuma linha é ligada a CNPJ ou a ficha do cadastro: a fonte é a declaração do doador, sem confirmação oficial.
    """
    from .site import e, inteiro, pagina

    if iati is None or iati.empty:
        return {"iati_projetos": 0, "iati_linhas": 0}
    # Só organizações que o doador classifica como ONG (tipos IATI 21–24), executoras ou recebedoras.
    df = iati[iati["tipo"].isin(IATI_TIPOS_ONG) & iati["nome"].ne("")].copy()
    df = df.sort_values("valor", ascending=False).drop_duplicates(["aid", "nome"])
    linhas = [[r.doador, r.titulo, r.ano_inicio, r.ano_fim, r.nome, r.papel, round(float(r.valor)), r.moeda, r.aid]
              for r in df.itertuples()]
    _json(pasta / "internacional" / "projetos.json", linhas)
    n_proj = int(iati["aid"].nunique())
    corpo = f"""
<p class="migalha"><a href="../../">Início</a> › <a href="../">ONGs</a> › Internacional</p>
<h1>Projetos de doadores estrangeiros no Brasil</h1>
<p class="destaque">{inteiro(n_proj)} projetos com destino ao Brasil publicados pelos próprios doadores no padrão internacional
<a href="https://iatistandard.org/pt/">IATI</a>. Abaixo, as organizações que eles classificam como ONG e citam como executoras
ou recebedoras: {inteiro(len(linhas))} citações.</p>
<aside class="origem"><strong>Por que estes nomes não são ligados a nenhuma ONG do cadastro.</strong> Os nomes aparecem exatamente como
o doador os escreveu, e quase nenhum doador informa o CNPJ. Não há registro oficial brasileiro que confirme esses repasses,
então este site <strong>não vincula</strong> nenhuma linha desta lista a um CNPJ ou a uma ficha de ONG. Nomes parecidos ou iguais
podem ser de organizações diferentes. Para conferir, abra o projeto no d-portal e a documentação publicada pelo doador.</aside>
<section class="busca-ongs">
<label for="q">Filtrar por doador, projeto ou organização</label>
<input id="q" type="search" autocomplete="off" placeholder="Ex.: Norad, Amazônia, saúde">
<p id="contagem" class="dica"></p>
<div id="res"></div>
</section>
<p class="origem">Fonte: dados publicados pelos doadores no padrão IATI, lidos pelo <a href="{IATI_PAGINA}">d-portal</a>, consulta em
{e(atualizado)}. Valores na moeda declarada pelo doador; zero quando ele não informa quanto repassou à organização.
Reproduzidos como publicados, sem juízo sobre legalidade.</p>
<script src="internacional.js" defer></script>
"""
    (pasta / "internacional" / "index.html").write_text(
        pagina("Projetos de doadores estrangeiros no Brasil (IATI): organizações citadas",
               "Projetos que governos e fundações estrangeiras declaram financiar no Brasil, com o nome das organizações "
               "como o doador publicou. Sem vínculo com CNPJ.", corpo, "../../", atualizado, url="ongs/internacional/",
               fonte=FONTE_IATI.format(raiz="../../"), sub="transparência das ONGs"),
        encoding="utf-8")
    return {"iati_projetos": n_proj, "iati_linhas": len(linhas)}


def gerar(fav: pd.DataFrame | None, destino: Path, raw: Path = RAW, baixar_fontes: bool = True) -> dict | None:
    """Ponto de entrada usado por etl.build. Sem a base do Mapa das OSCs, a seção não é gerada."""
    try:
        arqs = baixar(raw) if baixar_fontes else {k: (raw / n if (raw / n).exists() else None) for k, n in {
            "mosc": "mosc.csv", "internacionais": "internacionais.xlsx", "convenios": "convenios.zip",
            "cepim": "cepim.zip", "iati": "iati_br.xml"}.items()}
        if not arqs.get("mosc"):
            print("aviso: ongs: base do Mapa das OSCs ausente; seção não gerada")
            return None
        org = organizacoes(ler_mosc(arqs["mosc"]))

        def opcional(chave, leitor, *extra):
            if not arqs.get(chave):
                return None
            try:
                return leitor(arqs[chave], *extra)
            except Exception as erro:  # noqa: BLE001 - fonte opcional não derruba o site
                print(f"aviso: ongs: {chave} ilegível ({type(erro).__name__}: {erro})")
                return None

        conv = opcional("convenios", ler_convenios)
        cepim = opcional("cepim", ler_cepim)
        iati = opcional("iati", ler_iati)
        inter = opcional("internacionais", ler_internacionais) or {}
        org, fichas = montar(org, fav, conv, cepim, inter)
        hoje = date.today().strftime("%d/%m/%Y")
        fontes = {"mosc": arqs.get("mosc_data") or "",
                  "convenios": arqs.get("convenios_data") or "", "cepim": arqs.get("cepim_data") or ""}
        return gravar(org, fichas, destino, hoje, fontes, iati)
    except Exception as erro:  # noqa: BLE001 - a seção nova não pode derrubar o ETL de emendas
        import traceback

        traceback.print_exc()
        print(f"aviso: ongs: seção não gerada ({type(erro).__name__}: {erro})")
        return None

"""Acompanhamento parlamentar: sessões, presença, votações nominais e discursos do Plenário.

Fontes (dados abertos oficiais):
- Câmara: arquivos anuais em https://dadosabertos.camara.leg.br/arquivos (eventos, presença em
  eventos, votações, votos, proposições votadas) e a API v2 (deputados, blocos, discursos).
- Senado: https://legis.senado.leg.br/dadosabertos (agenda do Plenário, votações nominais,
  discursos, senadores, blocos).

O Senado não publica lista de presença por sessão; a presença do dia vem das votações nominais
(quem registrou voto ou "presente sem voto" estava lá; "NCom" = não compareceu; licenças e missões
contam como ausência justificada). Em dia de sessão sem votação nominal, a presença fica "não divulgada".

Saída em site/parlamento/dados/ (poucos arquivos, um por casa e mês):
- indice.json: dias com sessão, meses disponíveis, data de atualização
- membros.json: cadastro (nome, partido atual, UF, foto, perfil, autor no Portal da Transparência)
- blocos.json: blocos parlamentares atuais (partido -> bloco) por casa
- camara-AAAA-MM.json e senado-AAAA-MM.json: sessões, presença, votações e discursos do mês

Meses fechados já publicados são reaproveitados do próprio site (sem baixar tudo de novo).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests

from . import config

VERSAO = 1
INICIO = date(2023, 2, 1)  # 57ª legislatura
CAMARA_ARQ = "https://dadosabertos.camara.leg.br/arquivos/{nome}/csv/{nome}-{ano}.csv"
CAMARA_API = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
H = {"User-Agent": "painel-emendas (dados abertos; github.com/projects-betanull/painel-emendas)", "Accept": "application/json"}

# Voto -> código curto. S sim, N não, A abstenção, O obstrução, P presente sem voto (inclui presidente),
# F não compareceu, J ausência justificada (licença, missão, atividade parlamentar).
VOTOS = {"sim": "S", "nao": "N", "não": "N", "abstencao": "A", "abstenção": "A", "obstrucao": "O", "obstrução": "O",
         "artigo 17": "P", "p-nrv": "P", "presidente (art. 51 risf)": "P", "presidente": "P", "ncom": "F"}


def codigo_voto(texto: str) -> str:
    t = (texto or "").strip().lower()
    if t in VOTOS:
        return VOTOS[t]
    if t.startswith("presidente"):
        return "P"
    return "J" if t else ""


def normalizar_nome(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z ]", "", re.sub(r"\s+", " ", s.upper())).strip()


def meses(inicio: date, fim: date) -> list[str]:
    out, a, m = [], inicio.year, inicio.month
    while (a, m) <= (fim.year, fim.month):
        out.append(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def ultimo_dia(mes: str) -> date:
    a, m = map(int, mes.split("-"))
    return (date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


# ---------------------------------------------------------------- rede

_sessao = requests.Session()
_sessao.headers.update(H)


def _get(url: str, **kw) -> requests.Response:
    ultimo = None
    for _ in range(3):
        try:
            r = _sessao.get(url, timeout=kw.pop("timeout", 120), **kw)
            if r.status_code < 500:
                r.raise_for_status()
                return r
            ultimo = requests.HTTPError(f"HTTP {r.status_code}")
        except requests.RequestException as e:
            ultimo = e
    raise ultimo


def _lista(x) -> list:
    return x if isinstance(x, list) else ([] if x in (None, "") else [x])


def camara_csv(nome: str, ano: int) -> list[dict]:
    r = _get(CAMARA_ARQ.format(nome=nome, ano=ano), timeout=600)
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


# ---------------------------------------------------------------- Câmara


def montar_camara(eventos: list[dict], presencas: list[dict], votacoes: list[dict], votos: list[dict],
                  proposicoes: list[dict]) -> dict[str, dict]:
    """Agrupa por mês: sessões do Plenário, presença por dia e votações nominais."""
    out: dict[str, dict] = defaultdict(lambda: {"sessoes": {}, "presenca": {}, "votacoes": [], "partidos": {}})
    sessao_dia: dict[str, str] = {}
    for e in eventos:
        tipo = e.get("descricaoTipo") or ""
        if not tipo.startswith("Sessão") or "Cancelada" in (e.get("situacao") or ""):
            continue
        d = (e.get("dataHoraInicio") or "")[:10]
        if not d:
            continue
        deliberativa = tipo == "Sessão Deliberativa"
        out[d[:7]]["sessoes"].setdefault(d, []).append({"t": tipo, "h": (e.get("dataHoraInicio") or "")[11:16]})
        if deliberativa:
            sessao_dia[e["id"]] = d
    pres = defaultdict(set)
    for p in presencas:
        d = sessao_dia.get(p.get("idEvento"))
        if d and p.get("idDeputado"):
            pres[d].add(int(p["idDeputado"]))
    for d, ids in pres.items():
        out[d[:7]]["presenca"][d] = sorted(ids)
    props = defaultdict(list)
    for p in proposicoes:
        props[p["idVotacao"]].append(p)
    por_votacao = defaultdict(dict)
    partido = {}
    for v in votos:
        if v.get("idVotacao") and v.get("deputado_id"):
            i = int(v["deputado_id"])
            por_votacao[v["idVotacao"]][i] = codigo_voto(v.get("voto"))
            partido[(v["idVotacao"], i)] = v.get("deputado_siglaPartido") or ""
    for v in sorted(votacoes, key=lambda x: x.get("dataHoraRegistro") or ""):
        if v.get("siglaOrgao") != "PLEN" or v["id"] not in por_votacao:
            continue
        d = v["data"][:10]
        p = props.get(v["id"], [])
        titulo = p[0].get("proposicao_titulo", "") if p else ""
        ementa = p[0].get("proposicao_ementa", "") if p else ""
        m = out[d[:7]]
        m["votacoes"].append({
            "id": v["id"], "d": d, "h": (v.get("dataHoraRegistro") or "")[11:16], "titulo": titulo,
            "ementa": ementa[:400], "desc": (v.get("descricao") or "")[:400],
            "res": "Aprovada" if v.get("aprovacao") == "1" else ("Rejeitada" if v.get("aprovacao") == "0" else ""),
            "url": f"https://www.camara.leg.br/evento-legislativo/{v['idEvento']}" if v.get("idEvento") not in (None, "", "0") else "",
            "prop": f"https://www.camara.leg.br/propostas-legislativas/{p[0]['proposicao_id']}" if p else "",
            "v": {str(k): c for k, c in por_votacao[v["id"]].items()},
        })
        for k in por_votacao[v["id"]]:
            m["partidos"][str(k)] = partido[(v["id"], k)]
    return dict(out)


def camara_deputados() -> list[dict]:
    out, pagina = [], 1
    while True:
        r = _get(f"{CAMARA_API}/deputados", params={"idLegislatura": 57, "itens": 100, "pagina": pagina, "ordem": "ASC", "ordenarPor": "nome"})
        dados = r.json().get("dados", [])
        out += dados
        if len(dados) < 100:
            break
        pagina += 1
    atuais = {d["id"] for d in _get(f"{CAMARA_API}/deputados", params={"itens": 1000}).json().get("dados", [])}
    vistos, res = set(), []
    for d in out:
        if d["id"] in vistos:
            continue
        vistos.add(d["id"])
        res.append({"id": d["id"], "n": d["nome"], "p": d.get("siglaPartido") or "", "uf": d.get("siglaUf") or "",
                    "atual": d["id"] in atuais})
    return res


def camara_blocos() -> dict[str, str]:
    r = _get(f"{CAMARA_API}/blocos", params={"idLegislatura": 57, "itens": 100})
    out = {}
    for b in r.json().get("dados", []):
        for p in _get(f"{CAMARA_API}/blocos/{b['id']}/partidos").json().get("dados", []):
            out[p.get("sigla", "")] = b.get("nome", "")
    return out


def camara_discursos(ids: list[int], desde: date, ate: date) -> dict[str, dict]:
    """Discursos por deputado (API v2), agrupados por mês e dia."""
    def um(i):
        res, pagina = [], 1
        while True:
            try:
                r = _get(f"{CAMARA_API}/deputados/{i}/discursos", params={
                    "dataInicio": desde.isoformat(), "dataFim": ate.isoformat(), "itens": 100, "pagina": pagina,
                    "ordenarPor": "dataHoraInicio", "ordem": "ASC"})
            except requests.RequestException:
                return res
            dados = r.json().get("dados", [])
            for x in dados:
                res.append({"id": i, "d": (x.get("dataHoraInicio") or "")[:10], "t": (x.get("tipoDiscurso") or "").title(),
                            "r": re.sub(r"<[^>]+>|&nbsp;", " ", x.get("sumario") or "")[:220].strip(),
                            "u": x.get("urlVideo") or x.get("urlTexto") or x.get("urlAudio") or ""})
            if len(dados) < 100:
                return res
            pagina += 1

    out: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    with ThreadPoolExecutor(6) as ex:
        for lista in ex.map(um, ids):
            for x in lista:
                if x["d"]:
                    out[x["d"][:7]][x["d"]].append({k: x[k] for k in ("id", "t", "r", "u")})
    return {m: dict(v) for m, v in out.items()}


# ---------------------------------------------------------------- Senado


def senado_sessoes(mes: str) -> dict[str, list]:
    r = _get(f"{SENADO}/plenario/agenda/mes/{mes.replace('-', '')}01.json")
    out = {}
    for s in _lista((r.json().get("AgendaPlenario", {}).get("Sessoes") or {}).get("Sessao")):
        if s.get("Casa") != "SF" or (s.get("Realizada") or {}).get("Status") != "Sim":
            continue
        d = s.get("Data", "")
        if d[:7] == mes:
            out.setdefault(d, []).append({"t": (s.get("TipoSessao") or "").strip().capitalize(), "h": s.get("Hora", "")})
    return out


def montar_senado_votacoes(lista: list[dict]) -> tuple[list[dict], dict[str, dict], dict[str, str]]:
    """Votações nominais (endpoint /votacao) -> votações, presença do dia derivada e partido na data."""
    votacoes, presenca, partidos = [], defaultdict(dict), {}
    ordem = {"P": 3, "J": 2, "F": 1}
    for v in sorted(lista, key=lambda x: (x.get("dataSessao") or "", x.get("sequencialSessao") or 0)):
        if v.get("votacaoSecreta") == "S":
            continue
        d = (v.get("dataSessao") or "")[:10]
        votos = {}
        for p in _lista(v.get("votos")):
            c = codigo_voto(p.get("siglaVotoParlamentar"))
            k = str(p.get("codigoParlamentar"))
            votos[k] = c
            partidos[k] = p.get("siglaPartidoParlamentar") or ""
            st = "P" if c in "SNAOP" else c
            if ordem.get(st, 0) > ordem.get(presenca[d].get(k), 0):
                presenca[d][k] = st
        if not votos:
            continue
        info = (v.get("informeLegislativo") or {}).get("texto") or ""
        votacoes.append({
            "id": str(v.get("codigoSessaoVotacao") or ""), "d": d, "titulo": v.get("identificacao") or "",
            "ementa": (v.get("ementa") or "")[:400], "desc": (v.get("descricaoVotacao") or "")[:400],
            "res": {"A": "Aprovada", "R": "Rejeitada"}.get(v.get("resultadoVotacao") or "", ""),
            "prop": f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{v['codigoMateria']}" if v.get("codigoMateria") else "",
            "url": "", "info": info[:300], "v": votos,
        })
    return votacoes, {d: dict(p) for d, p in presenca.items()}, partidos


def senado_discursos(mes: str) -> dict[str, list]:
    fim = ultimo_dia(mes)
    r = _get(f"{SENADO}/plenario/lista/discursos/{mes.replace('-', '')}01/{fim.strftime('%Y%m%d')}.json")
    out = defaultdict(list)
    for s in _lista((r.json().get("DiscursosSessao", {}).get("Sessoes") or {}).get("Sessao")):
        for p in _lista((s.get("Pronunciamentos") or {}).get("Pronunciamento")):
            if not p.get("CodigoParlamentar"):
                continue
            d = (p.get("Data") or s.get("DataSessao") or "")[:10]
            out[d].append({"id": str(p["CodigoParlamentar"]), "t": (p.get("TipoUsoPalavra") or {}).get("Descricao", ""),
                           "r": (p.get("Resumo") or "")[:220], "u": p.get("TextoIntegral") or ""})
    return dict(out)


def senado_senadores() -> list[dict]:
    out = {}
    for url, chave in ((f"{SENADO}/senador/lista/legislatura/57.json", "ListaParlamentarLegislatura"),
                       (f"{SENADO}/senador/lista/atual.json", "ListaParlamentarEmExercicio")):
        atual = chave == "ListaParlamentarEmExercicio"
        try:
            lista = _get(url).json().get(chave, {}).get("Parlamentares", {}).get("Parlamentar", [])
        except (requests.RequestException, ValueError) as e:
            print(f"aviso: senadores ({url}) indisponível: {e}")
            continue
        for p in _lista(lista):
            i = p.get("IdentificacaoParlamentar", {})
            cod = str(i.get("CodigoParlamentar") or "")
            if not cod:
                continue
            uf = i.get("UfParlamentar") or ""
            if not uf:
                m = _lista((p.get("Mandatos") or {}).get("Mandato") or p.get("Mandato"))
                uf = (m[0] if m else {}).get("UfParlamentar", "")
            item = out.setdefault(cod, {"id": cod, "n": i.get("NomeParlamentar", ""), "p": "", "uf": uf, "atual": False})
            item["p"] = i.get("SiglaPartidoParlamentar") or item["p"]
            item["uf"] = uf or item["uf"]
            item["atual"] = item["atual"] or atual
    return list(out.values())


def senado_blocos() -> dict[str, str]:
    r = _get(f"{SENADO}/composicao/lista/blocos.json")
    out = {}

    def andar(x, bloco=None):
        if isinstance(x, dict):
            nome = x.get("NomeBloco") or x.get("NomeApelido") or bloco
            if x.get("SiglaPartido") and nome:
                out[x["SiglaPartido"]] = nome
            for v in x.values():
                andar(v, nome)
        elif isinstance(x, list):
            for v in x:
                andar(v, bloco)
    andar(r.json())
    return out


# ---------------------------------------------------------------- montagem


def janela_membros(ativos: dict[str, dict[str, list[str]]], atuais: set[str]) -> dict[str, dict[str, list]]:
    """Para cada mês, {id: [de, ate]}: de/ate = primeiro/último dia de atividade quando o parlamentar
    entra ou sai naquele mês (None = já estava / continua). Evita marcar ausente quem ainda não tomou
    posse ou já saiu."""
    ordem = sorted(m for m, v in ativos.items() if v)  # mês sem registro (recesso) não conta
    out = {}
    for i, m in enumerate(ordem):
        ant = ativos.get(ordem[i - 1], {}) if i else {}
        prox = ativos.get(ordem[i + 1], {}) if i + 1 < len(ordem) else None
        res = {}
        for k, dias in ativos[m].items():
            de = None if (k in ant or i == 0) else min(dias)
            fica = (k in prox) if prox is not None else (k in atuais)
            res[k] = [de, None if fica else max(dias)]
        out[m] = res
    return out


def ligar_emendas(nome: str, autores: dict[str, str]) -> str:
    return autores.get(normalizar_nome(nome), "")


def cache_site(caminho: str):
    """Arquivo já publicado no site (meses fechados não mudam)."""
    try:
        r = _sessao.get(f"{config.SITE_URL}/parlamento/dados/{caminho}", timeout=60)
        if r.ok and r.headers.get("content-type", "").startswith("application/json"):
            j = r.json()
            return j if j.get("versao") == VERSAO else None
    except (requests.RequestException, ValueError):
        pass
    return None


def gerar(destino: Path, autores_portal: list[str] | None = None, hoje: date | None = None) -> None:
    hoje = hoje or date.today()
    pasta = destino / "parlamento" / "dados"
    pasta.mkdir(parents=True, exist_ok=True)
    todos = meses(INICIO, hoje)
    # Meses com mais de 45 dias encerrados vêm do site publicado, se lá estiverem.
    limite = (hoje - timedelta(days=45)).isoformat()[:7]
    usar_cache = os.environ.get("PARLAMENTO_SEM_CACHE") != "1"
    cache = {}
    if usar_cache:
        for casa in ("camara", "senado"):
            for m in todos:
                if m < limite:
                    j = cache_site(f"{casa}-{m}.json")
                    if j:
                        cache[(casa, m)] = j
    print(f"parlamento: {len(cache)} meses reaproveitados do site")
    autores = {normalizar_nome(a): a for a in (autores_portal or []) if a}

    # Câmara
    deputados = camara_deputados()
    novos_c = [m for m in todos if ("camara", m) not in cache]
    camara: dict[str, dict] = {}
    if novos_c:
        anos = sorted({int(m[:4]) for m in novos_c})
        ev, pr, vt, vo, pp = [], [], [], [], []
        for a in anos:
            ev += camara_csv("eventos", a)
            pr += camara_csv("eventosPresencaDeputados", a)
            vt += camara_csv("votacoes", a)
            vo += camara_csv("votacoesVotos", a)
            pp += camara_csv("votacoesProposicoes", a)
        camara = {m: v for m, v in montar_camara(ev, pr, vt, vo, pp).items() if m in novos_c}
        for m in novos_c:
            camara.setdefault(m, {"sessoes": {}, "presenca": {}, "votacoes": [], "partidos": {}})
        desde = max(INICIO, date.fromisoformat(min(novos_c) + "-01"))
        disc = camara_discursos([d["id"] for d in deputados], desde, hoje)
        for m, dias in disc.items():
            if m in camara or m in novos_c:
                camara.setdefault(m, {"sessoes": {}, "presenca": {}, "votacoes": [], "partidos": {}})["discursos"] = dias
    # Senado
    senadores = senado_senadores()
    senado: dict[str, dict] = {}
    for m in todos:
        if ("senado", m) in cache:
            continue
        fim = min(ultimo_dia(m), hoje)
        r = _get(f"{SENADO}/votacao", params={"dataInicio": f"{m}-01", "dataFim": fim.isoformat()})
        votacoes, presenca, partidos = montar_senado_votacoes(r.json())
        try:
            disc = senado_discursos(m)
        except (requests.RequestException, ValueError):
            disc = {}
        senado[m] = {"sessoes": senado_sessoes(m), "presenca": presenca, "votacoes": votacoes, "partidos": partidos, "discursos": disc}

    blocos = {}
    for casa, fn in (("camara", camara_blocos), ("senado", senado_blocos)):
        try:
            blocos[casa] = fn()
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"aviso: blocos {casa} indisponíveis ({type(e).__name__})")
            blocos[casa] = {}

    indice = {"versao": VERSAO, "atualizado": hoje.isoformat(), "meses": todos, "dias": {}}
    cadastro = {"camara": {}, "senado": {}}
    for casa, novos, lista in (("camara", camara, deputados), ("senado", senado, senadores)):
        # Atividade por mês: quem votou ou teve presença registrada.
        ativos: dict[str, dict[str, list[str]]] = {}
        for m in todos:
            dados = cache.get((casa, m)) or novos.get(m)
            if not dados:
                continue
            if (casa, m) in cache:
                ativos[m] = {k: [v[0] or f"{m}-01", v[1] or f"{m}-28"] for k, v in dados["membros"].items()}
                continue
            dias = defaultdict(set)
            for d, ids in dados["presenca"].items():
                for k in ids:
                    dias[str(k)].add(d)
            for v in dados["votacoes"]:
                for k in v["v"]:
                    dias[str(k)].add(v["d"])
            ativos[m] = {k: sorted(s) for k, s in dias.items()}
        atuais = {str(x["id"]) for x in lista if x.get("atual")}
        janelas = janela_membros(ativos, atuais)
        atual_partido = {str(x["id"]): x["p"] for x in lista}
        dias_casa = {}
        for m in todos:
            if (casa, m) in cache:
                dados = cache[(casa, m)]
            elif m in novos:
                n = novos[m]
                membros = {}
                for k, jan in janelas.get(m, {}).items():
                    membros[k] = [jan[0], jan[1], n["partidos"].get(k) or atual_partido.get(k, "")]
                dados = {"versao": VERSAO, "casa": casa, "mes": m, "sessoes": n["sessoes"], "presenca": n["presenca"],
                         "votacoes": n["votacoes"], "discursos": n.get("discursos", {}), "membros": membros}
            else:
                continue
            (pasta / f"{casa}-{m}.json").write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            for d, s in dados["sessoes"].items():
                dias_casa[d] = [x["t"] for x in s]
            for d in dados["presenca"]:
                dias_casa.setdefault(d, ["Sessão"])
        indice["dias"][casa] = dict(sorted(dias_casa.items()))
        for x in lista:
            k = str(x["id"])
            foto = (f"https://www.camara.leg.br/internet/deputado/bandep/{k}.jpg" if casa == "camara"
                    else f"https://www.senado.leg.br/senadores/img/fotos-oficiais/senador{k}.jpg")
            perfil = (f"https://www.camara.leg.br/deputados/{k}" if casa == "camara"
                      else f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{k}")
            cadastro[casa][k] = {"n": x["n"], "p": x["p"], "uf": x["uf"], "f": foto, "u": perfil,
                                 "e": ligar_emendas(x["n"], autores), "a": 1 if x.get("atual") else 0}
    (pasta / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (pasta / "membros.json").write_text(json.dumps({"versao": VERSAO, **cadastro}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (pasta / "blocos.json").write_text(json.dumps(blocos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ligados = sum(1 for c in cadastro.values() for x in c.values() if x["e"])
    print(f"parlamento: {len(todos)} meses; dias com sessão: Câmara {len(indice['dias']['camara'])}, Senado {len(indice['dias']['senado'])}; "
          f"{ligados} de {sum(len(c) for c in cadastro.values())} parlamentares ligados às emendas")


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else config.ROOT / "site"
    autores = []
    arq = config.OUT_DIR / "autores.parquet"
    if arq.exists():
        import pandas as pd
        autores = pd.read_parquet(arq)["nome_autor"].dropna().unique().tolist()
    gerar(destino, autores)

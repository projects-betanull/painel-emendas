"""Sonda as APIs da Câmara e do Senado (presença, votações, discursos). Só imprime."""
import json, sys, re
import requests
H = {"User-Agent": "Mozilla/5.0 painel-emendas", "Accept": "application/json"}

def get(u, n=1500, **kw):
    try:
        r = requests.get(u, headers=H, timeout=90, **kw)
        t = r.text
        print(f"\n=== {u} {kw.get('params','')}\nHTTP {r.status_code} {r.headers.get('content-type')} {len(r.content)} bytes")
        print(t[:n])
        return r
    except Exception as e:
        print(f"\n=== {u}\nERRO {e}")

def head(u):
    try:
        r = requests.head(u, headers=H, timeout=60, allow_redirects=True)
        print(f"HEAD {u} -> {r.status_code} {r.headers.get('content-length')} {r.headers.get('last-modified')}")
    except Exception as e:
        print(f"HEAD {u} ERRO {e}")

C = "https://dadosabertos.camara.leg.br/api/v2"
S = "https://legis.senado.leg.br/dadosabertos"
D1, D2 = "2026-11-10", "2026-11-12"
for ano in (2025, 2026):
    for a in ("votacoes", "votacoesVotos", "votacoesOrientacoes", "eventos", "eventosPresencaDeputados", "votacoesObjetos"):
        head(f"https://dadosabertos.camara.leg.br/arquivos/{a}/json/{a}-{ano}.json")
        head(f"https://dadosabertos.camara.leg.br/arquivos/{a}/csv/{a}-{ano}.csv")
r = get(f"{C}/eventos", params={"dataInicio": D1, "dataFim": D2, "idOrgao": 180, "itens": 50}, n=2500)
ev = []
try: ev = r.json()["dados"]
except Exception: pass
for e in ev[:2]:
    get(f"{C}/eventos/{e['id']}/deputados", n=800)
    get(f"{C}/eventos/{e['id']}/votacoes", n=800)
r = get(f"{C}/votacoes", params={"dataInicio": D1, "dataFim": D2, "idOrgao": 180, "itens": 50}, n=2000)
try:
    vs = r.json()["dados"]
    for v in vs[:3]:
        get(f"{C}/votacoes/{v['id']}/votos", n=600)
        get(f"{C}/votacoes/{v['id']}", n=1200)
except Exception: pass
get(f"{C}/deputados/204554/discursos", params={"dataInicio": "2026-01-01", "dataFim": D2, "itens": 3}, n=1500)
get("https://www.camara.leg.br/SitCamaraWS/sessoesreunioes.asmx/ListarPresencasDia", params={"data": "11/11/2026", "numLegislatura": "", "numMatriculaParlamentar": "", "siglaPartido": "", "siglaUF": ""}, n=1500)
get("https://dadosabertos.camara.leg.br/arquivos/eventosPresencaDeputados/csv/eventosPresencaDeputados-2026.csv", n=800, stream=True)
# Senado
for path in ("/v3/api-docs", "/api-docs", "/v3/api-docs/swagger-config"):
    r = get(S + path, n=300)
    if r is not None and r.ok and "paths" in r.text:
        paths = list(r.json().get("paths", {}))
        print(len(paths), "caminhos")
        for p in paths:
            if re.search(r"presen|sessao|discurs|votac|plenario|comparec", p, re.I): print("  ", p)
        break
get(f"{S}/plenario/lista/votacao/20261110/20261112.json", n=2500)
get(f"{S}/votacao", params={"dataInicio": D1, "dataFim": D2}, n=2500)
get(f"{S}/plenario/lista/discursos/20261110/20261112.json", n=2000)
get(f"{S}/plenario/agenda/mes/20261101.json", n=1500)
get(f"{S}/plenario/lista/sessao/20261110/20261112.json", n=1500)
get(f"{S}/plenario/agenda/dia/20261111.json", n=2000)
get(f"{S}/senador/lista/atual.json", n=1200)
get(f"{S}/senador/5012/discursos.json", params={"dataInicio": "20260101", "dataFim": "20261112"}, n=1200)

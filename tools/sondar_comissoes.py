import csv, io, json, re
import requests
H = {"User-Agent": "painel-emendas", "Accept": "application/json"}
A = "https://dadosabertos.camara.leg.br/arquivos"
C = "https://dadosabertos.camara.leg.br/api/v2"
S = "https://legis.senado.leg.br/dadosabertos"
SITE = "https://painel-emendas.pages.dev/parlamento/dados"
def get(u, n=1500, **kw):
    try:
        r = requests.get(u, headers=H, timeout=180, **kw)
        print(f"\n=== {u} {kw.get('params','')}\nHTTP {r.status_code} {len(r.content)} bytes {r.headers.get('content-type')}"); print(r.text[:n]); return r
    except Exception as e: print(f"\n=== {u}\nERRO {e}")
def csvf(url, n=3):
    r = requests.get(url, headers=H, timeout=300)
    print(f"\n### {url} HTTP {r.status_code} {len(r.content)}")
    if not r.ok: return []
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    print(len(rows), "linhas; colunas:", list(rows[0]) if rows else None)
    for x in rows[:n]: print(json.dumps(x, ensure_ascii=False)[:700])
    return rows
# 1. Site publicado: discursos do Senado por mês
for m in ("2026-10", "2026-11", "2025-09"):
    for casa in ("senado", "camara"):
        try:
            d = requests.get(f"{SITE}/{casa}-{m}.json", timeout=60).json()
            print("SITE", casa, m, "dias com discurso:", len(d.get("discursos", {})), "total:", sum(len(v) for v in d.get("discursos", {}).values()))
        except Exception as e: print("SITE", casa, m, "ERRO", e)
get(f"{S}/plenario/lista/discursos/20261101/20261119.json", n=600)
get(f"{S}/plenario/lista/discursos/20261103/20261103.json", n=600)
# 2. Câmara: arquivos de órgãos
orgs = csvf(f"{A}/orgaos/csv/orgaos.csv")
od = csvf(f"{A}/orgaosDeputados/csv/orgaosDeputados-L57.csv")
eo = csvf(f"{A}/eventosOrgaos/csv/eventosOrgaos-2026.csv")
from collections import Counter
if orgs: print(Counter(o.get("tipoOrgao") for o in orgs).most_common(20))
if od: print(Counter(o.get("titulo") or o.get("cargo") for o in od).most_common(15))
get(f"{C}/orgaos", params={"codTipoOrgao": 2, "itens": 5}, n=800)
get(f"{C}/orgaos/2003/membros", params={"itens": 3}, n=800)
get(f"{C}/deputados/204379/orgaos", params={"itens": 5}, n=1200)
# 3. Senado
r = requests.get(S + "/v3/api-docs", headers=H, timeout=120)
for p in r.json().get("paths", {}):
    if re.search(r"comiss|colegiad|reuni|composic", p, re.I): print("  ", p)
for p in ("/comissao/lista/colegiados.json", "/composicao/lista/comissoes.json", "/senador/5012/comissoes.json",
          "/comissao/agenda/20261110/20261112.json", "/composicao/comissao/38.json", "/comissao/reuniao/CAE/20261110/20261112.json"):
    get(S + p, n=1500)

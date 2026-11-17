"""Sonda as APIs da Câmara e do Senado (presença, votações, discursos). Só imprime."""
import csv, io, json
import requests
H = {"User-Agent": "Mozilla/5.0 painel-emendas", "Accept": "application/json"}
A = "https://dadosabertos.camara.leg.br/arquivos"
C = "https://dadosabertos.camara.leg.br/api/v2"
S = "https://legis.senado.leg.br/dadosabertos"

def get(u, n=1500, **kw):
    try:
        r = requests.get(u, headers=H, timeout=120, **kw)
        print(f"\n=== {u} {kw.get('params','')}\nHTTP {r.status_code} {len(r.content)} bytes")
        print(r.text[:n]); return r
    except Exception as e:
        print(f"\n=== {u}\nERRO {e}")

def csvf(nome, ano=2026):
    r = requests.get(f"{A}/{nome}/csv/{nome}-{ano}.csv", headers=H, timeout=300)
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    print(f"\n### {nome}-{ano}: {len(rows)} linhas; colunas: {list(rows[0]) if rows else None}")
    return rows

for nome in ("votacoesProposicoes", "votacoesVotos", "votacoes"):
    rows = csvf(nome)
    for x in rows[:2]: print(json.dumps(x, ensure_ascii=False)[:1200])
ev = csvf("eventos")
from collections import Counter
print(Counter(e.get("descricaoTipo") for e in ev).most_common(30))
plen = [e for e in ev if "180" in (e.get("idOrgao") or e.get("orgaos") or "") or "PLEN" in json.dumps(e)]
print("plenario?", len(plen)); [print(json.dumps(x, ensure_ascii=False)[:600]) for x in ev[:2]]
pres = csvf("eventosPresencaDeputados")
cont = Counter(p["idEvento"] for p in pres)
delib = [e for e in ev if "Deliberativa" in (e.get("descricaoTipo") or "") and "Não" not in (e.get("descricaoTipo") or "")]
print("sessões deliberativas:", len(delib))
for e in delib[-8:]:
    print(e.get("id"), e.get("dataHoraInicio"), e.get("descricaoTipo"), e.get("situacao"), "presentes:", cont.get(e.get("id"), 0))
dep = requests.get(f"{C}/deputados", params={"itens": 5}, headers=H).json()["dados"]
print(dep[0])
for d in dep[:3]:
    get(f"{C}/deputados/{d['id']}/discursos", params={"dataInicio": "2026-09-01", "dataFim": "2026-11-16", "itens": 2}, n=1500)
for p in ("/plenario/lista/tiposComparecimento.json", "/plenario/encontro/594175/resumo", "/plenario/encontro/594175", "/plenario/resultado/20261111.json",
          "/plenario/lista/discursos/20261103/20261105.json", "/plenario/lista/discursos/20261001/20261031.json"):
    get(S + p, n=2500)
r = get(f"{S}/plenario/agenda/mes/20261101.json", n=10)
txt = r.text
i = txt.find("Comparec"); print("Comparec em agenda:", i, txt[i-200:i+600] if i > 0 else "")

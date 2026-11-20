import json
import requests
H = {"User-Agent": "painel-emendas", "Accept": "application/json"}
S = "https://legis.senado.leg.br/dadosabertos"
def j(u, **kw):
    r = requests.get(u, headers=H, timeout=180, **kw); print(f"\n=== {u} {kw.get('params','')} HTTP {r.status_code} {len(r.content)}"); return r.json() if r.ok else None
def forma(x, d=0, n=0):
    # mostra a estrutura (chaves e um exemplo) até 4 níveis
    pad = "  " * d
    if isinstance(x, dict):
        for k, v in list(x.items())[:25]:
            if isinstance(v, (dict, list)) and d < 5: print(f"{pad}{k}:"); forma(v, d + 1)
            else: print(f"{pad}{k}: {str(v)[:100]}")
    elif isinstance(x, list):
        print(f"{pad}[lista de {len(x)}]")
        if x: forma(x[0], d + 1)
a = j(f"{S}/comissao/agenda/20261110/20261112.json"); forma(a)
for cod in ("5012", "5008"):
    d = j(f"{S}/senador/{cod}/discursos.json", params={"dataInicio": "20261101", "dataFim": "20261120"})
    p = (((d or {}).get("DiscursosParlamentar") or {}).get("Parlamentar") or {}).get("Pronunciamentos")
    print("pronunciamentos nov:", json.dumps(p, ensure_ascii=False)[:800])
for ini, fim in (("20261020", "20261031"), ("20261027", "20261031")):
    d = j(f"{S}/plenario/lista/discursos/{ini}/{fim}.json")
    ss = ((d or {}).get("DiscursosSessao") or {}).get("Sessoes") or {}
    ss = ss.get("Sessao", []) if isinstance(ss, dict) else []
    ss = ss if isinstance(ss, list) else [ss]
    print("sessões com discurso:", [s.get("DataSessao") for s in ss])
e = j(f"{S}/plenario/encontro/594175")
enc = e["ServicoPlenario"]["encontros"]["encontro"][0]
print("linkVideo", enc.get("linkVideo"))
ors = (enc.get("oradores") or {}).get("orador") or []
print(len(ors), "oradores")
for o in ors[:3]: print(json.dumps({k: o.get(k) for k in ("codigo", "status", "codTipoOrador", "codUsoPalavra", "dthInclusao", "codParlamentarInscricao", "cancelado")}, ensure_ascii=False))
print([k for k in enc.keys()])
t = j(f"{S}/taquigrafia/notas/sessao/594175")
print(json.dumps(t, ensure_ascii=False)[:1500] if t else None)
c = j(f"{S}/senador/5012/comissoes.json")
cs = c["MembroComissaoParlamentar"]["Parlamentar"]["MembroComissoes"]["Comissao"]
print(len(cs), [x for x in cs if not x.get("DataFim")][:3])

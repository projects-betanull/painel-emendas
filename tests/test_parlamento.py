"""Acompanhamento parlamentar: montagem dos dados (sem rede) e geometria dos semicírculos (Node)."""

import json
import subprocess
from datetime import date
from pathlib import Path

from etl import parlamento as P

RAIZ = Path(__file__).resolve().parent.parent
JS = RAIZ / "etl" / "site_static" / "parlamento" / "parlamento.js"


def test_codigo_voto():
    assert [P.codigo_voto(x) for x in ["Sim", "Não", "Abstenção", "Obstrução", "Artigo 17", "P-NRV", "NCom", "LS", "MIS", ""]] == \
        ["S", "N", "A", "O", "P", "P", "F", "J", "J", ""]
    assert P.codigo_voto("Presidente (art. 51 RISF)") == "P"


def test_normalizar_nome_e_ligar_emendas():
    autores = {P.normalizar_nome(a): a for a in ["ACÁCIO FAVACHO", "Bancada do Amapá"]}
    assert P.ligar_emendas("Acácio Favacho", autores) == "ACÁCIO FAVACHO"
    assert P.ligar_emendas("Fulano", autores) == ""


def test_montar_camara():
    eventos = [
        {"id": "1", "dataHoraInicio": "2026-11-11T14:00:00", "situacao": "Encerrada", "descricaoTipo": "Sessão Deliberativa"},
        {"id": "2", "dataHoraInicio": "2026-11-10T09:00:00", "situacao": "Encerrada", "descricaoTipo": "Sessão Não Deliberativa Solene"},
        {"id": "3", "dataHoraInicio": "2026-11-11T10:00:00", "situacao": "Encerrada", "descricaoTipo": "Reunião Deliberativa"},
        {"id": "4", "dataHoraInicio": "2026-11-12T14:00:00", "situacao": "Cancelada", "descricaoTipo": "Sessão Deliberativa"},
    ]
    presencas = [{"idEvento": "1", "idDeputado": "10"}, {"idEvento": "1", "idDeputado": "20"}, {"idEvento": "3", "idDeputado": "30"}]
    votacoes = [
        {"id": "99-1", "data": "2026-11-11", "dataHoraRegistro": "2026-11-11T19:00:00", "siglaOrgao": "PLEN", "idEvento": "1",
         "aprovacao": "1", "descricao": "Aprovado o projeto."},
        {"id": "99-2", "data": "2026-11-11", "dataHoraRegistro": "2026-11-11T19:10:00", "siglaOrgao": "PLEN", "idEvento": "1",
         "aprovacao": "1", "descricao": "Simbólica (sem votos)."},
        {"id": "77-1", "data": "2026-11-11", "dataHoraRegistro": "2026-11-11T11:00:00", "siglaOrgao": "CCJC", "idEvento": "3",
         "aprovacao": "1", "descricao": "Comissão."},
    ]
    votos = [
        {"idVotacao": "99-1", "deputado_id": "10", "voto": "Sim", "deputado_siglaPartido": "PT"},
        {"idVotacao": "99-1", "deputado_id": "20", "voto": "Não", "deputado_siglaPartido": "PL"},
        {"idVotacao": "77-1", "deputado_id": "30", "voto": "Sim", "deputado_siglaPartido": "PP"},
    ]
    props = [{"idVotacao": "99-1", "proposicao_id": "555", "proposicao_titulo": "PL 1/2026", "proposicao_ementa": "Ementa."}]
    out = P.montar_camara(eventos, presencas, votacoes, votos, props)
    m = out["2026-11"]
    assert set(m["sessoes"]) == {"2026-11-10", "2026-11-11"}  # reunião de comissão e sessão cancelada ficam de fora
    assert m["presenca"] == {"2026-11-11": [10, 20]}  # só sessão deliberativa do Plenário
    assert len(m["votacoes"]) == 1
    v = m["votacoes"][0]
    assert v["titulo"] == "PL 1/2026" and v["v"] == {"10": "S", "20": "N"} and v["res"] == "Aprovada"
    assert v["prop"].endswith("/555") and v["url"].endswith("/1")
    assert m["partidos"] == {"10": "PT", "20": "PL"}


def test_montar_senado_votacoes():
    lista = [
        {"dataSessao": "2026-11-10", "sequencialSessao": 1, "codigoSessaoVotacao": 7113, "identificacao": "PLP 109/2025",
         "votacaoSecreta": "N", "resultadoVotacao": "A", "codigoMateria": 173581, "descricaoVotacao": "Votação nominal",
         "votos": [
             {"codigoParlamentar": 1, "siglaVotoParlamentar": "Sim", "siglaPartidoParlamentar": "PT"},
             {"codigoParlamentar": 2, "siglaVotoParlamentar": "P-NRV", "siglaPartidoParlamentar": "PL"},
             {"codigoParlamentar": 3, "siglaVotoParlamentar": "NCom", "siglaPartidoParlamentar": "MDB"},
             {"codigoParlamentar": 4, "siglaVotoParlamentar": "LS", "siglaPartidoParlamentar": "PP"},
         ]},
        {"dataSessao": "2026-11-10", "sequencialSessao": 2, "codigoSessaoVotacao": 7114, "votacaoSecreta": "N",
         "votos": [{"codigoParlamentar": 3, "siglaVotoParlamentar": "Não", "siglaPartidoParlamentar": "MDB"}]},
        {"dataSessao": "2026-11-10", "sequencialSessao": 3, "codigoSessaoVotacao": 7115, "votacaoSecreta": "S",
         "votos": [{"codigoParlamentar": 9, "siglaVotoParlamentar": "Votou", "siglaPartidoParlamentar": "X"}]},
    ]
    vots, pres, partidos = P.montar_senado_votacoes(lista)
    assert [v["id"] for v in vots] == ["7113", "7114"]  # secreta fica de fora
    assert vots[0]["v"] == {"1": "S", "2": "P", "3": "F", "4": "J"} and vots[0]["res"] == "Aprovada"
    # Quem faltou numa votação e votou noutra conta como presente no dia.
    assert pres == {"2026-11-10": {"1": "P", "2": "P", "3": "P", "4": "J"}}
    assert partidos["3"] == "MDB" and "9" not in partidos


def test_janela_membros():
    ativos = {
        "2026-09": {"a": ["2026-09-02"], "b": ["2026-09-03", "2026-09-20"]},
        "2026-10": {"a": ["2026-10-05"], "c": ["2026-10-14", "2026-10-28"]},
        "2026-11": {"a": ["2026-11-04"], "c": ["2026-11-11"]},
    }
    j = P.janela_membros(ativos, atuais={"a", "c"})
    assert j["2026-09"] == {"a": [None, None], "b": [None, "2026-09-20"]}  # b sai em setembro
    assert j["2026-10"] == {"a": [None, None], "c": ["2026-10-14", None]}  # c entra em outubro
    assert j["2026-11"] == {"a": [None, None], "c": [None, None]}


def test_gerar_sem_rede(tmp_path, monkeypatch):
    hoje = date(2026, 11, 17)
    monkeypatch.setattr(P, "INICIO", date(2026, 10, 1))
    monkeypatch.setattr(P, "cache_site", lambda caminho: None)
    monkeypatch.setattr(P, "camara_deputados", lambda: [{"id": 10, "n": "Acácio Favacho", "p": "MDB", "uf": "AP", "atual": True},
                                                       {"id": 20, "n": "Beltrana", "p": "PL", "uf": "SP", "atual": True}])
    linhas = {
        "eventos": [{"id": "1", "dataHoraInicio": "2026-11-11T14:00:00", "situacao": "Encerrada", "descricaoTipo": "Sessão Deliberativa"}],
        "eventosPresencaDeputados": [{"idEvento": "1", "idDeputado": "10"}],
        "votacoes": [], "votacoesVotos": [], "votacoesProposicoes": [],
    }
    monkeypatch.setattr(P, "camara_csv", lambda nome, ano: linhas[nome] if ano == 2026 else [])
    monkeypatch.setattr(P, "camara_discursos", lambda ids, desde, ate: {"2026-11": {"2026-11-11": [{"id": 10, "t": "Breves", "r": "Resumo", "u": ""}]}})
    monkeypatch.setattr(P, "camara_blocos", lambda: {"MDB": "Bloco A"})
    monkeypatch.setattr(P, "senado_senadores", lambda: [{"id": "5", "n": "Senadora X", "p": "PT", "uf": "DF", "atual": True}])
    monkeypatch.setattr(P, "senado_sessoes", lambda m: {"2026-11-10": [{"t": "Sessão deliberativa ordinária", "h": "14:00"}]} if m == "2026-11" else {})
    monkeypatch.setattr(P, "senado_discursos", lambda m: {})
    monkeypatch.setattr(P, "senado_blocos", lambda: {})

    class R:
        def __init__(self, dados): self.dados = dados
        def json(self): return self.dados
    votos = [{"dataSessao": "2026-11-10", "codigoSessaoVotacao": 1, "votacaoSecreta": "N",
              "votos": [{"codigoParlamentar": 5, "siglaVotoParlamentar": "Sim", "siglaPartidoParlamentar": "PT"}]}]
    monkeypatch.setattr(P, "_get", lambda url, **kw: R(votos if kw.get("params", {}).get("dataInicio", "").startswith("2026-11") else []))
    P.gerar(tmp_path, ["ACÁCIO FAVACHO"], hoje=hoje)
    pasta = tmp_path / "parlamento" / "dados"
    assert sorted(p.name for p in pasta.iterdir()) == ["blocos.json", "camara-2026-10.json", "camara-2026-11.json", "indice.json",
                                                         "membros.json", "senado-2026-10.json", "senado-2026-11.json"]
    ind = json.loads((pasta / "indice.json").read_text())
    assert ind["dias"]["camara"] == {"2026-11-11": ["Sessão Deliberativa"]} and "2026-11-10" in ind["dias"]["senado"]
    cad = json.loads((pasta / "membros.json").read_text())
    assert cad["camara"]["10"]["e"] == "ACÁCIO FAVACHO" and cad["camara"]["20"]["e"] == ""
    cam = json.loads((pasta / "camara-2026-11.json").read_text())
    assert cam["presenca"] == {"2026-11-11": [10]} and cam["discursos"]["2026-11-11"][0]["r"] == "Resumo"
    assert cam["membros"]["10"][2] == "MDB"
    sen = json.loads((pasta / "senado-2026-11.json").read_text())
    assert sen["presenca"] == {"2026-11-10": {"5": "P"}} and sen["membros"]["5"] == [None, None, "PT"]


def test_geometria_semicirculos():
    script = f"""
const m = require({json.dumps(str(JS))});
const out = {{}};
for (const n of [81, 513, 1, 7]) {{
  const a = m.assentos(n, false), b = m.assentos(n, true);
  out[n] = {{ len: a.pontos.length, raio: a.raio, ymaxCupula: Math.max(...a.pontos.map(p => p.y)), yminTigela: Math.min(...b.pontos.map(p => p.y)),
    esqDir: a.pontos[0].x <= a.pontos[a.pontos.length - 1].x }};
}}
const ord = m.ordenar([{{id:"1",p:"A",n:"z"}},{{id:"2",p:"B",n:"y"}},{{id:"4",p:"C",n:"w"}}], p => p === "C" ? "Bloco" : p === "A" ? "Bloco" : "");
out.ordem = ord.map(x => x.id);
out.dia = m.membrosDoDia({{membros: {{a: [null, null, "PT"], b: ["2026-11-10", null, "PL"], c: [null, "2026-11-05", "PP"]}}}}, "2026-11-08").map(x => x.id);
console.log(JSON.stringify(out));
"""
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    for n in ("81", "513", "1", "7"):
        assert out[n]["len"] == int(n) and out[n]["raio"] > 0 and out[n]["esqDir"]
        assert out[n]["ymaxCupula"] <= 1e-9  # Senado: cúpula (y para cima, negativo no SVG)
        assert out[n]["yminTigela"] >= -1e-9  # Câmara: tigela
    assert out["ordem"] == ["1", "4", "2"]  # bloco (2 partidos) antes do partido avulso menor
    assert out["dia"] == ["a"]

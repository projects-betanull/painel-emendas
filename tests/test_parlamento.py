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
        "votacoes": [], "votacoesVotos": [], "votacoesProposicoes": [], "eventosOrgaos": [],
    }
    monkeypatch.setattr(P, "camara_csv", lambda nome, ano: linhas[nome] if ano == 2026 else [])
    monkeypatch.setattr(P, "camara_discursos", lambda ids, desde, ate: {"2026-11": {"2026-11-11": [{"id": 10, "t": "Breves", "r": "Resumo", "u": ""}]}})
    monkeypatch.setattr(P, "camara_blocos", lambda: {"MDB": "Bloco A"})
    monkeypatch.setattr(P, "senado_senadores", lambda: [{"id": "5", "n": "Senadora X", "p": "PT", "uf": "DF", "atual": True}])
    monkeypatch.setattr(P, "senado_sessoes", lambda m: {"2026-11-10": [{"t": "Sessão deliberativa ordinária", "h": "14:00", "c": "594172"}]} if m == "2026-11" else {})
    monkeypatch.setattr(P, "senado_discursos", lambda m: {})
    monkeypatch.setattr(P, "senado_blocos", lambda: {})
    monkeypatch.setattr(P, "camara_comissoes", lambda: {"2003": {"s": "CCJC", "n": "CCJ", "t": "Comissão Permanente", "m": [["10", "Titular", "2023-03-01", None]]}})
    monkeypatch.setattr(P, "senado_comissoes", lambda cods: {"38": {"s": "CAE", "n": "Assuntos Econômicos", "t": "", "m": [[c, "Titular", None, None] for c in cods]}})
    monkeypatch.setattr(P, "senado_reunioes", lambda m, hoje: {"2026-11-11": [["38", "Reunião deliberativa", "10:00", "Realizada", "", "1"]]} if m == "2026-11" else {})
    monkeypatch.setattr(P, "senado_oradores", lambda c: [{"id": "5", "t": "Usou a palavra", "r": "", "u": "https://video"}])

    class R:
        def __init__(self, dados): self.dados = dados
        def json(self): return self.dados
    votos = [{"dataSessao": "2026-11-10", "codigoSessaoVotacao": 1, "votacaoSecreta": "N",
              "votos": [{"codigoParlamentar": 5, "siglaVotoParlamentar": "Sim", "siglaPartidoParlamentar": "PT"}]}]
    monkeypatch.setattr(P, "_get", lambda url, **kw: R(votos if kw.get("params", {}).get("dataInicio", "").startswith("2026-11") else []))
    P.gerar(tmp_path, ["ACÁCIO FAVACHO"], hoje=hoje)
    pasta = tmp_path / "parlamento" / "dados"
    assert sorted(p.name for p in pasta.iterdir()) == ["blocos.json", "camara-2026-10.json", "camara-2026-11.json", "comissoes.json", "indice.json",
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
    # Sem discurso publicado: quem usou a palavra, com o vídeo da sessão.
    assert sen["discursos"] == {"2026-11-10": [{"id": "5", "t": "Usou a palavra", "r": "", "u": "https://video"}]}
    assert sen["reunioes"]["2026-11-11"][0][0] == "38"
    com = json.loads((pasta / "comissoes.json").read_text())
    assert com["camara"]["2003"]["s"] == "CCJC" and com["senado"]["38"]["m"] == [["5", "Titular", None, None]]


def test_reunioes_de_comissao_na_camara():
    eventos = [
        {"id": "1", "dataHoraInicio": "2026-11-11T14:00:00", "situacao": "Encerrada", "descricaoTipo": "Sessão Deliberativa"},
        {"id": "3", "dataHoraInicio": "2026-11-11T10:00:00", "situacao": "Encerrada (Final)", "descricaoTipo": "Reunião Deliberativa"},
        {"id": "4", "dataHoraInicio": "2026-11-12T10:00:00", "situacao": "Cancelada", "descricaoTipo": "Audiência Pública"},
    ]
    eo = [{"idEvento": "1", "idOrgao": "180"}, {"idEvento": "3", "idOrgao": "2003"}, {"idEvento": "4", "idOrgao": "2001"}]
    pres = [{"idEvento": "1", "idDeputado": "10"}, {"idEvento": "3", "idDeputado": "10"}, {"idEvento": "3", "idDeputado": "20"}]
    m = P.montar_camara(eventos, pres, [], [], [], eo)["2026-11"]
    assert m["presenca"] == {"2026-11-11": [10]}  # reunião de comissão não conta como presença no Plenário
    assert m["reunioes"]["2026-11-11"] == [["2003", "Reunião Deliberativa", "10:00", "Encerrada (Final)",
                                            "https://www.camara.leg.br/evento-legislativo/3", "3"]]
    assert m["reunioes"]["2026-11-12"][0][3] == "Cancelada"
    assert m["presencaReuniao"] == {"3": [10, 20]}


def test_comissoes_e_oradores():
    linhas = [
        {"uriOrgao": "x/orgaos/2003", "siglaOrgao": "CCJC", "nomePublicacaoOrgao": "CCJ", "uriDeputado": "x/deputados/10",
         "cargo": "Titular", "dataInicio": "2025-03-01", "dataFim": ""},
        {"uriOrgao": "x/orgaos/2003", "siglaOrgao": "CCJC", "nomePublicacaoOrgao": "CCJ", "uriDeputado": "x/deputados/20",
         "cargo": "Presidente", "dataInicio": "2025-03-01T00:00", "dataFim": "2026-02-01"},
    ]
    c = P.montar_comissoes_camara(linhas, {"2003": "Comissão Permanente"})
    assert c == {"2003": {"s": "CCJC", "n": "CCJ", "t": "Comissão Permanente",
                          "m": [["10", "Titular", "2025-03-01", None], ["20", "Presidente", "2025-03-01", "2026-02-01"]]}}
    sen = P.montar_comissoes_senado({"5012": [
        {"IdentificacaoComissao": {"CodigoComissao": "38", "SiglaComissao": "CAE", "NomeComissao": "Assuntos Econômicos"},
         "DescricaoParticipacao": "Titular", "DataInicio": "2023-03-01"},
        {"IdentificacaoComissao": {"CodigoComissao": "2042", "SiglaComissao": "GPX", "NomeComissao": "Antiga"},
         "DescricaoParticipacao": "Titular", "DataInicio": "2014-08-06", "DataFim": "2018-12-28"},
    ]}, {"38": "Comissão Permanente"})
    assert list(sen) == ["38"] and sen["38"]["m"] == [["5012", "Titular", "2023-03-01", None]]
    enc = {"ServicoPlenario": {"encontros": {"encontro": [{"linkVideo": "https://yt", "oradores": {"orador": [
        {"codParlamentarInscricao": "5008", "codUsoPalavra": "1", "cancelado": "N"},
        {"codParlamentarInscricao": "22", "codUsoPalavra": None, "cancelado": "N"},
        {"codParlamentarInscricao": "70", "codUsoPalavra": "2", "cancelado": "S"},
        {"codParlamentarInscricao": "5008", "codUsoPalavra": "3", "cancelado": "N"},
    ]}}]}}}
    assert [o["id"] for o in P.montar_oradores(enc)] == ["5008"] and P.montar_oradores(enc)[0]["u"] == "https://yt"
    ag = {"AgendaReuniao": {"reunioes": {"reuniao": [{"codigo": 15031, "colegiadoCriador": {"codigo": 834, "sigla": "CDH"},
          "dataInicio": "2026-11-12T15:00:00.000", "situacao": "Realizada", "tipo": {"descricao": "Outros eventos"},
          "urlUltimoResultadoPublicado": "https://r"}]}}}
    assert P.montar_reunioes_senado(ag) == {"2026-11-12": [["834", "Outros eventos", "15:00", "Realizada", "https://r", "15031"]]}


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


def test_comissoes_no_navegador():
    script = f"""
const m = require({json.dumps(str(JS))});
const com = {{ s: "CCJC", n: "CCJ", m: [["1", "Titular", "2025-01-01", "2025-12-31"], ["1", "Presidente", "2026-01-01", null],
  ["2", "Suplente", null, null], ["3", "Titular", "2026-12-01", null]] }};
console.log(JSON.stringify({{
  ativos: m.membrosComissao(com, "2026-11-11").map(x => [x[0], x[1]]),
  antes: m.membrosComissao(com, "2025-06-01").map(x => x[0]),
  de: m.comissoesDe({{ "2003": com, "9": {{ s: "X", n: "Outra", m: [["2", "Titular", null, null]] }} }}, "2", "2026-11-11").map(c => [c.s, c.cargo]),
}}));
"""
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out["ativos"] == [["1", "Presidente"], ["2", "Suplente"]]  # 3 ainda não entrou; presidente antes do suplente
    assert out["antes"] == ["1", "2"]
    assert out["de"] == [["X", "Titular"], ["CCJC", "Suplente"]]

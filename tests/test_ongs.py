import io
import json
import zipfile

import pandas as pd
import pytest

from etl import ongs

CAB = ("cnpj;tx_razao_social_osc;tx_nome_fantasia_osc;natureza_juridica;matriz_filial;situacao_cadastral;dt_fundacao_osc;"
       "removida_do_mosc;data_fechamento;ano_fechamento;tx_endereco_completo;cd_municipio;municipio_nome;UF_Sigla;longitude;latitude;"
       "cnae;cnae_secundaria;Area_Assistencia_social;Area_Saude")
LINHAS = [
    "11222333000181;INSTITUTO AMIGOS DA FLORESTA AMAZONICA;AMIGOS DA FLORESTA;3999;Matriz;Ativa;2001-05-01;nÃ£o;;;Rua A, 1;1302603;MANAUS;AM;0;0;94308;;1;0",
    "11222333000262;INSTITUTO AMIGOS DA FLORESTA AMAZONICA;;3999;Filial;Ativa;2005-05-01;nÃ£o;;;Rua B, 2;1501402;BELÉM;PA;0;0;94308;;1;0",
    "44555666000110;ASSOCIACAO DE SAUDE SÃ£o JOSE;;3999;Matriz;Ativa;1990-01-01;nÃ£o;;;;3509502;CAMPINAS;SP;0;0;94308;;0;1",
    "77888999000155;FUNDACAO ESTRANGEIRA DO BRASIL;;3204;Matriz;Ativa;2010-01-01;nÃ£o;;;;3550308;SÃO PAULO;SP;0;0;94308;;0;0",
    "12121212000112;ASSOC EXTINTA;;3999;Matriz;Nula ou Baixada;1990-01-01;sim;;;;3550308;SÃO PAULO;SP;0;0;94308;;0;0",
]


def _zip(nome, texto):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(nome, texto.encode("latin-1"))
    buf.seek(0)
    return buf


@pytest.fixture
def org():
    mosc = io.BytesIO(("\r\n".join([CAB] + LINHAS) + "\r\n").encode("latin-1", errors="replace"))
    return ongs.organizacoes(ongs.ler_mosc(mosc))


def test_mosc_consertos_e_agrupamento(org):
    assert len(org) == 4  # 5 estabelecimentos, 4 organizações
    a = org.loc["11222333"]
    assert a["estabelecimentos"] == 2 and a["ufs_atuacao"] == ["AM", "PA"] and a["uf"] == "AM"
    assert org.loc["44555666", "nome"] == "ASSOCIACAO DE SAUDE São JOSE"
    assert a["areas"] == "Assistência social"
    assert not org.loc["12121212", "ativa"] and a["ativa"]


def _conv():
    cab = ('"NÚMERO CONVÊNIO";"UF";"CÓDIGO SIAFI MUNICÍPIO";"NOME MUNICÍPIO";"SITUAÇÃO CONVÊNIO";"NÚMERO ORIGINAL";"NÚMERO PROCESSO DO CONVÊNIO";'
           '"OBJETO DO CONVÊNIO";"CÓDIGO ÓRGÃO SUPERIOR";"NOME ÓRGÃO SUPERIOR";"CÓDIGO ÓRGÃO CONCEDENTE";"NOME ÓRGÃO CONCEDENTE";"CÓDIGO UG CONCEDENTE";'
           '"NOME UG CONCEDENTE";"CÓDIGO CONVENENTE";"TIPO CONVENENTE";"NOME CONVENENTE";"TIPO ENTE CONVENENTE";"TIPO INSTRUMENTO";"VALOR CONVÊNIO";'
           '"VALOR LIBERADO";"DATA PUBLICAÇÃO";"DATA INÍCIO VIGÊNCIA";"DATA FINAL VIGÊNCIA";"VALOR CONTRAPARTIDA";"DATA ÚLTIMA LIBERAÇÃO";"VALOR ÚLTIMA LIBERAÇÃO"')
    l1 = ('"900001";"PA";"0427";"BELEM";"EM EXECUÇÃO";"";"";"APOIO A COMUNIDADES";"44000";"Ministério do Meio Ambiente";"";"MMA";"";"";'
          '"11222333000181";"Entidades Sem Fins Lucrativos";"INSTITUTO AMIGOS";"";"TERMO DE FOMENTO";"1000000,00";"400000,50";"";"01/02/2023";"01/02/2025";"0,00";"";"0,00"')
    l2 = ('"900002";"SP";"6291";"CAMPINAS";"CONCLUÍDO";"";"";"OBRA";"36000";"Ministério da Saúde";"";"MS";"";"";'
          '"46068425000133";"Administração Pública Municipal";"MUNICIPIO DE CAMPINAS";"";"CONVENIO";"5000,00";"5000,00";"";"01/02/2020";"01/02/2021";"0,00";"";"0,00"')
    return ongs.ler_convenios(_zip("20261023_Convenios.csv", "\n".join([cab, l1, l2])))


def test_convenios_cepim(org):
    cv = _conv()
    assert list(cv["cnpj8"]) == ["11222333", "46068425"]
    assert cv.loc[0, "liberado"] == pytest.approx(400000.5) and cv.loc[0, "ano"] == 2023
    ce = ongs.ler_cepim(_zip("x_CEPIM.csv", '"CNPJ ENTIDADE";"NOME ENTIDADE";"NÚMERO CONVÊNIO";"ÓRGÃO CONCEDENTE";"MOTIVO DO IMPEDIMENTO"\n'
                                           '"44555666000110";"ASSOC";"123";"MS";"INSTAURACAO DE TOMADA DE CONTAS ESPECIAL"'))
    assert ce.loc[0, "cnpj8"] == "44555666"


IATI = """<iati-activities><iati-activity default-currency="EUR"><iati-identifier>XX-1</iati-identifier>
<reporting-org ref="XX"><narrative>Agencia Doadora</narrative></reporting-org><title><narrative>Projeto Floresta</narrative></title>
<participating-org role="1"><narrative>Governo X</narrative></participating-org>
<participating-org role="4" type="22"><narrative>Instituto Amigos da Floresta Amazonica</narrative></participating-org>
<participating-org role="4" type="22"><narrative>ISA</narrative></participating-org>
<activity-date iso-date="2020-01-01" type="2"/><activity-date iso-date="2022-12-31" type="3"/>
<transaction><transaction-type code="3"/><value currency="EUR">1000</value><receiver-org type="22"><narrative>Instituto Amigos da Floresta Amazonica</narrative></receiver-org></transaction>
<transaction><transaction-type code="3"/><value>500</value><receiver-org ref="BR-CNPJ-44.555.666/0001-10"><narrative>Saude Sao Jose</narrative></receiver-org></transaction>
</iati-activity></iati-activities>"""


def test_iati_e_montagem(org, tmp_path):
    ia = ongs.ler_iati(io.BytesIO(IATI.encode()))
    assert set(ia["papel"]) == {"executora", "recebedora"} and "Governo X" not in set(ia["nome"])
    fav = pd.DataFrame({"codigo_favorecido": ["11.222.333/0001-81", "46.068.425/0001-33"], "favorecido": ["INSTITUTO AMIGOS", "MUNICIPIO"],
                        "valor_recebido": [250000.0, 9.0], "ano": [2024, 2024], "nome_autor": ["FULANO", "BELTRANO"], "uf": ["AM", "SP"]})
    o, fichas = ongs.montar(org, fav, _conv(), ia, None, {"77888999": "Alemanha"})
    a = fichas["11222333"]
    assert a["emendas"]["total"] == 250000.0 and a["convenios"]["liberado"] == pytest.approx(400000.5)
    assert a["emendas"]["explorar"] == [["AM", ["INSTITUTO AMIGOS · 11.222.333/0001-81"]]]
    assert a["internacional"][0][0] == "Agencia Doadora" and a["internacional"][0][9] == "nome igual ao do cadastro"
    assert fichas["44555666"]["internacional"][0][9] == "CNPJ informado pelo doador"
    assert fichas["77888999"]["estrangeira"] == "Alemanha"
    assert "ISA" not in json.dumps(fichas)  # sigla curta não liga
    r = ongs.gravar(o, fichas, tmp_path, "17/11/2026", {})
    assert r["com_emendas"] == 1 and r["com_internacional"] == 2
    lote = json.loads((tmp_path / "ongs" / "d" / "112.json").read_text())
    assert "11222333" in lote
    assert "12121212" not in json.loads((tmp_path / "ongs" / "d" / "121.json").read_text()) if (tmp_path / "ongs" / "d" / "121.json").exists() else True
    am = json.loads((tmp_path / "ongs" / "l" / "AM.json").read_text())
    assert am[0][0] == "11222333" and am[0][3] & 1 and am[0][3] & 2 and am[0][3] & 4
    html = (tmp_path / "ongs" / "index.html").read_text()
    assert "Transparência das ONGs" in html and 'o/?c=11222333' in html


def test_internacionais_raiz_com_8_digitos(tmp_path):
    arq = tmp_path / "i.xlsx"
    pd.DataFrame({"cnpj_basico": ["05911345", "10517714"], "PaisChecagemIPEA": ["Brasil", "Estados Unidos"],
                  "ChecadoEstrangeiroIPEA": [0, 1]}).to_excel(arq, sheet_name="OSCs_Microdados", index=False)
    assert ongs.ler_internacionais(arq) == {"10517714": "Estados Unidos"}

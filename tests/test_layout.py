"""Template comum: nome do site, menu igual em todas as páginas e marcadores dos HTML estáticos."""
import re
from pathlib import Path

from etl import layout

RAIZ = Path(__file__).resolve().parent.parent


def test_nome_igual_no_cartao_de_previa():
    og = (RAIZ / "lib" / "og.js").read_text(encoding="utf-8")
    assert f'export const MARCA = "{layout.NOME_SITE}";' in og


def test_estaticos_usam_o_template():
    for arq in layout.ESTATICOS.rglob("*.html"):
        texto = arq.read_text(encoding="utf-8")
        assert '<header class="topo">' not in texto, f"{arq}: use <!--#cabecalho--> em vez de cabeçalho próprio"
        assert "<!--#cabecalho" in texto, arq


def test_renderizar_raiz_e_item_ativo():
    html = layout.renderizar('<!--#cabecalho sub="painel interativo"-->\n<footer><p>x</p><!--#rodape--></footer>', "painel/index.html")
    assert '<span class="sub">painel interativo</span>' in html
    assert 'href="../" class="marca">Painel Público<span>.</span>' in html
    assert '<a id="menu-painel" href="../painel/" aria-current="page">' in html
    assert 'href="../apoie/"' in html and "<!--#" not in html
    fundo = layout.renderizar("<!--#cabecalho-->", "ongs/o/index.html")
    assert 'href="../../" class="marca"' in fundo


def test_menu_igual_em_todas_as_paginas():
    menus = {re.sub(r' aria-current="page"', "", layout.menu("../", a)) for a in ["", "painel/", "explorar/"]}
    assert len(menus) == 1


def test_item_so_aparece_com_a_pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(layout, "ESTATICOS", tmp_path)
    assert "ongs/" not in [c for _, c in layout.itens_menu()]
    assert "ONGs" not in layout.atalhos_paineis("")
    (tmp_path / "ongs").mkdir()
    assert "ongs/" in [c for _, c in layout.itens_menu()]
    assert 'href="ongs/"' in layout.atalhos_paineis("")

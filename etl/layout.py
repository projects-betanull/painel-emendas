"""Template comum a todas as páginas: nome do site, cabeçalho com menu e rodapé.

Para mudar o nome ou o menu do site inteiro, mexa só aqui (e em MARCA de lib/og.js, que desenha o cartão de prévia;
um teste confere que os dois nomes batem).

As páginas geradas em Python chamam `cabecalho()` e `rodape()` (via `site.pagina`). As páginas estáticas de
`etl/site_static/` usam marcadores que `aplicar_em_estaticos()` troca no build:
    <!--#cabecalho sub="explorador: filtre, cruze e aprofunde"-->
    <footer><p>Fonte oficial: ...</p><!--#rodape--></footer>
O caminho relativo até a raiz (../, ../../) e o item ativo do menu saem da pasta do arquivo.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from . import config

NOME_SITE = "Painel Público"
SLOGAN = "dados públicos do Brasil para consultar, cruzar e baixar"

ESTATICOS = Path(__file__).parent / "site_static"

# (rótulo, caminho a partir da raiz, pasta de site_static exigida para o item aparecer ou None)
# A exigência deixa um painel novo entrar no menu sozinho quando a pasta dele chega ao repositório.
MENU: list[tuple[str, str, str | None]] = [
    ("Emendas", "painel/", None),
    ("Parlamento", "parlamento/", "parlamento"),
    ("ONGs", "ongs/", "ongs"),
    ("Explorar", "explorar/", None),
    ("IA", "ia/", None),
    ("Fontes", "sobre/", None),
    ("Passe ⚡", "dados/", None),
]

# Painéis do site, em atalhos na página inicial (mesma regra de pasta exigida do MENU).
PAINEIS: list[tuple[str, str, str, str | None]] = [
    ("Emendas", "painel/", "Gráficos das emendas que se filtram com um toque", None),
    ("Parlamento", "parlamento/", "Presença, votos e discursos no Senado e na Câmara", "parlamento"),
    ("ONGs", "ongs/", "Dinheiro público e estrangeiro de cada organização", "ongs"),
]


def _e(texto) -> str:
    return html.escape(str(texto), quote=True)


def itens_menu() -> list[tuple[str, str]]:
    return [(rotulo, caminho) for rotulo, caminho, pasta in MENU if _existe(pasta)]


def _existe(pasta: str | None) -> bool:
    return pasta is None or (ESTATICOS / pasta).is_dir()


def atalhos_paineis(raiz: str) -> str:
    """Links (classe .atalhos) para cada painel disponível."""
    return "\n".join(f'<a href="{raiz}{caminho}"><strong>{_e(nome)}</strong><span>{_e(texto)}</span></a>'
                     for nome, caminho, texto, pasta in PAINEIS if _existe(pasta))


def secao_de(caminho: str) -> str:
    """Primeira pasta de um caminho relativo à raiz ('ongs/o/' -> 'ongs/'), para marcar o item ativo do menu."""
    primeiro = caminho.strip("/").split("/")[0]
    return primeiro + "/" if primeiro else ""


def marca(raiz: str) -> str:
    return f'<a href="{raiz}" class="marca">{_e(NOME_SITE)}<span>.</span></a>'


def menu(raiz: str, atual: str = "") -> str:
    links = []
    for rotulo, caminho in itens_menu():
        nome = caminho.strip("/")
        ativo = ' aria-current="page"' if caminho == atual else ""
        links.append(f'<a id="menu-{nome}" href="{raiz}{caminho}"{ativo}>{_e(rotulo)}</a>')
    return f'<nav class="menu" aria-label="Seções do site">{"".join(links)}</nav>'


def cabecalho(raiz: str, sub: str = "", atual: str = "") -> str:
    sub_html = f'\n<span class="sub">{_e(sub)}</span>' if sub else ""
    return f'<header class="topo">{marca(raiz)}{sub_html}\n{menu(raiz, atual)}</header>'


def rodape(raiz: str) -> str:
    """Parte fixa do rodapé; a linha de fonte oficial fica em cada página, porque muda de painel para painel."""
    return (f'<p>{_e(NOME_SITE)} é um site independente, <strong>não oficial</strong> e sem vínculo com o governo, partidos '
            f'ou parlamentares. Encontrou um erro? <a href="{config.REPO_URL}/issues">Avise aqui</a>. '
            f'<a href="{raiz}apoie/">Apoie com Lightning ⚡</a></p>')


_MARCADOR_CAB = re.compile(r'<!--#cabecalho(?:\s+sub="([^"]*)")?\s*-->')
_MARCADOR_ROD = re.compile(r"<!--#rodape\s*-->")
_MARCADOR_NOME = re.compile(r"<!--#nome\s*-->")


def renderizar(texto: str, rel: str) -> str:
    """Troca os marcadores de um HTML estático; `rel` é o caminho do arquivo a partir da raiz do site."""
    profundidade = rel.count("/")
    raiz = "../" * profundidade if profundidade else "./"
    atual = secao_de(rel.rsplit("/", 1)[0] + "/") if profundidade else ""
    texto = _MARCADOR_CAB.sub(lambda m: cabecalho(raiz, html.unescape(m.group(1) or ""), atual), texto)
    texto = _MARCADOR_ROD.sub(lambda m: rodape(raiz), texto)
    return _MARCADOR_NOME.sub(_e(NOME_SITE), texto)


def aplicar_em_estaticos(destino: Path) -> int:
    """Aplica o template nos HTML copiados de site_static para `destino`. Devolve quantos arquivos mudaram."""
    n = 0
    for arq in destino.rglob("*.html"):
        texto = arq.read_text(encoding="utf-8")
        if "<!--#" not in texto:
            continue
        arq.write_text(renderizar(texto, arq.relative_to(destino).as_posix()), encoding="utf-8")
        n += 1
    return n

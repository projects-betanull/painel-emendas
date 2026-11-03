"""Gera o site estático: página inicial (busca + ranking) e uma página por município.

Tudo é HTML pronto, sem servidor: o Cloudflare Pages só entrega os arquivos.
"""

from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .normalize import slug

ESTATICOS = Path(__file__).parent / "site_static"


# --------------------------------------------------------------------------- formatação


def brl(x: float) -> str:
    """1234567.8 -> 'R$ 1.234.568'."""
    return "R$ " + f"{x:,.0f}".replace(",", ".")


def brl_curto(x: float) -> str:
    """1234567.8 -> 'R$ 1,2 mi'."""
    for limite, sufixo in ((1e9, "bi"), (1e6, "mi")):
        if abs(x) >= limite:
            return "R$ " + f"{x / limite:,.1f}".replace(".", ",") + " " + sufixo
    if abs(x) >= 1e3:
        return f"R$ {x / 1e3:,.0f} mil".replace(",", ".")
    return brl(x)


def e(texto) -> str:
    return html.escape("" if texto is None or (isinstance(texto, float) and pd.isna(texto)) else str(texto))


def caminho_municipio(nome: str, uf: str) -> str:
    return f"municipio/{slug(nome).replace(' ', '-')}-{uf.lower()}/"


# --------------------------------------------------------------------------- layout


def pagina(titulo: str, descricao: str, corpo: str, raiz: str, atualizado: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}">
<link rel="stylesheet" href="{raiz}estilo.css">
</head>
<body>
<header class="topo"><a href="{raiz}" class="marca">Emendas<span>.</span></a>
<span class="sub">para onde vai o dinheiro das emendas parlamentares</span></header>
<main>
{corpo}
</main>
<footer>
<p>Fonte: <a href="https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares">Portal da Transparência (CGU)</a>,
valores recebidos pelos favorecidos desde 2020. Dados atualizados em {e(atualizado)}.</p>
<p>Projeto independente, sem login e sem anúncios. <a href="{raiz}apoie/">Apoie com Lightning ⚡</a></p>
</footer>
</body>
</html>
"""


def tabela(cabecalho: list[str], linhas: list[list[str]], numericas: set[int] = frozenset()) -> str:
    th = "".join(f'<th class="{"n" if i in numericas else ""}">{e(c)}</th>' for i, c in enumerate(cabecalho))
    trs = "".join(
        "<tr>" + "".join(f'<td class="{"n" if i in numericas else ""}">{c}</td>' for i, c in enumerate(l)) + "</tr>"
        for l in linhas
    )
    return f'<div class="tabela"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def barras_ano(por_ano: pd.Series) -> str:
    """Gráfico de barras simples em HTML/CSS: valor recebido por ano."""
    maximo = float(por_ano.max()) or 1.0
    itens = "".join(
        f'<div class="barra"><span class="ano">{int(ano)}</span>'
        f'<span class="trilho"><span class="cheio" style="width:{100 * v / maximo:.1f}%"></span></span>'
        f'<span class="valor">{brl_curto(v)}</span></div>'
        for ano, v in por_ano.items()
    )
    return f'<div class="barras">{itens}</div>'


# --------------------------------------------------------------------------- geração


def gerar_site(fav: pd.DataFrame, municipios: list[dict], destino: Path) -> int:
    """Gera o site em `destino`. Devolve o número de páginas de município."""
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    for arq in ESTATICOS.iterdir():
        if arq.is_file():
            shutil.copy(arq, destino / arq.name)
        else:
            shutil.copytree(arq, destino / arq.name)

    atualizado = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y")
    nomes = {str(m["codigo_ibge"]): (m["nome"], m["uf"]) for m in municipios}
    df = fav[fav["municipio_ibge"].notna()].copy()
    df["municipio_ibge"] = df["municipio_ibge"].astype(str)

    totais = df.groupby("municipio_ibge")["valor_recebido"].sum().sort_values(ascending=False)
    por_ano = df.groupby(["municipio_ibge", "ano"])["valor_recebido"].sum()
    autores = df.groupby(["municipio_ibge", "nome_autor"])["valor_recebido"].sum()
    favorecidos = df.groupby(["municipio_ibge", "favorecido"])["valor_recebido"].sum()
    tipos = df.groupby(["municipio_ibge", "tipo_emenda"])["valor_recebido"].sum()

    # Ranking dentro da UF, por valor total.
    uf_de = {c: nomes.get(c, ("", ""))[1] for c in totais.index}
    rank_uf = (
        pd.DataFrame({"total": totais, "uf": pd.Series(uf_de)})
        .groupby("uf")["total"].rank(ascending=False, method="min").astype(int)
    )
    qtd_uf = pd.Series(uf_de).value_counts()

    # ---- páginas de município
    for codigo, total in totais.items():
        if codigo not in nomes:
            continue
        nome, uf = nomes[codigo]
        rel = caminho_municipio(nome, uf)
        top_aut = autores.loc[codigo].sort_values(ascending=False).head(10)
        top_fav = favorecidos.loc[codigo].sort_values(ascending=False).head(10)
        top_tipo = tipos.loc[codigo].sort_values(ascending=False)
        corpo = f"""
<p class="migalha"><a href="../../">Início</a> › {e(uf)} › {e(nome)}</p>
<h1>{e(nome)} <span class="uf">{e(uf)}</span></h1>
<p class="destaque"><strong>{brl(total)}</strong> recebidos em emendas parlamentares desde 2020 ·
{int(rank_uf[codigo])}º de {int(qtd_uf[uf])} municípios de {e(uf)} com emendas</p>
<section><h2>Por ano</h2>{barras_ano(por_ano.loc[codigo])}</section>
<section><h2>Quem mandou o dinheiro</h2>
{tabela(["Autor da emenda", "Valor"], [[e(a), brl(v)] for a, v in top_aut.items()], {1})}</section>
<section><h2>Quem recebeu</h2>
{tabela(["Favorecido", "Valor"], [[e(f), brl(v)] for f, v in top_fav.items()], {1})}</section>
<section><h2>Tipo de emenda</h2>
{tabela(["Tipo", "Valor", "%"], [[e(t), brl(v), f"{100 * v / total:.0f}%".replace('.', ',')] for t, v in top_tipo.items()], {1, 2})}</section>
"""
        pasta = destino / rel
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "index.html").write_text(
            pagina(
                f"Emendas parlamentares em {nome} ({uf})",
                f"{nome} ({uf}) recebeu {brl(total)} em emendas parlamentares desde 2020. Veja por ano, autor e favorecido.",
                corpo,
                "../../",
                atualizado,
            ),
            encoding="utf-8",
        )

    # ---- índice de busca (pequeno: só nome, UF, caminho e total)
    busca = [
        {"n": nomes[c][0], "u": nomes[c][1], "p": caminho_municipio(*nomes[c]), "v": round(float(v))}
        for c, v in totais.items()
        if c in nomes
    ]
    (destino / "busca.json").write_text(json.dumps(busca, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---- página inicial
    top = [
        [f'<a href="{caminho_municipio(*nomes[c])}">{e(nomes[c][0])}</a>', e(nomes[c][1]), brl(v)]
        for c, v in totais.head(20).items()
        if c in nomes
    ]
    total_geral = float(df["valor_recebido"].sum())
    corpo = f"""
<section class="hero">
<h1>Quanto o seu município recebeu em emendas parlamentares?</h1>
<p>{brl_curto(total_geral)} pagos a {len(totais):,} municípios desde 2020. Busque o seu:</p>
<input id="q" type="search" placeholder="Digite o nome do município" autocomplete="off" aria-label="Buscar município">
<ul id="res" class="resultados"></ul>
</section>
<section><h2>Os 20 municípios que mais receberam</h2>
{tabela(["Município", "UF", "Valor recebido"], top, {2})}</section>
<script src="busca.js" defer></script>
""".replace(f"{len(totais):,}", f"{len(totais):,}".replace(",", "."))
    (destino / "index.html").write_text(
        pagina(
            "Emendas parlamentares por município",
            "Veja quanto cada município recebeu em emendas parlamentares, de quais parlamentares e para quem.",
            corpo,
            "",
            atualizado,
        ),
        encoding="utf-8",
    )
    return len(totais)

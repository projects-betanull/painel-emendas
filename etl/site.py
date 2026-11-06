"""Gera o site estático: página inicial, uma página por município, Sobre e Apoie.

Tudo é HTML pronto, sem servidor: o Cloudflare Pages só entrega os arquivos.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from . import config
from .normalize import slug

ESTATICOS = Path(__file__).parent / "site_static"
PORTAL_DOWNLOAD = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares"
PORTAL_CONSULTA = "https://portaldatransparencia.gov.br/emendas"
POP_MIN_DESTAQUE = 50_000  # ranking por habitante só entre municípios desse porte para cima


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


def inteiro(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def pct(x: float) -> str:
    return f"{x:.0f}%"


def e(texto) -> str:
    return html.escape("" if texto is None or (isinstance(texto, float) and pd.isna(texto)) else str(texto))


def caminho_municipio(nome: str, uf: str) -> str:
    return f"municipio/{slug(nome).replace(' ', '-')}-{uf.lower()}/"


def mascarar_documento(cod: str) -> str:
    """CPF de pessoa física nunca aparece inteiro (LGPD); CNPJ fica como publicado."""
    dig = re.sub(r"\D", "", cod or "")
    if len(dig) == 11:
        return f"***.{dig[3:6]}.{dig[6:9]}-**"
    return cod or ""


# --------------------------------------------------------------------------- layout


def pagina(titulo: str, descricao: str, corpo: str, raiz: str, atualizado: str, desde="2014", url: str = "") -> str:
    og_url = f'<meta property="og:url" content="{e(config.SITE_URL + "/" + url)}">' if url is not None else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}">
<meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="{e(descricao)}">
<meta property="og:type" content="website">
<meta property="og:locale" content="pt_BR">
{og_url}
<link rel="icon" href="{raiz}icone.svg" type="image/svg+xml">
<link rel="stylesheet" href="{raiz}estilo.css">
</head>
<body>
<header class="topo"><a href="{raiz}" class="marca">Emendas<span>.</span></a>
<span class="sub">para onde vai o dinheiro das emendas parlamentares</span>
<nav class="menu"><a href="{raiz}painel/">Painel</a><a href="{raiz}explorar/">Explorar</a><a href="{raiz}ia/">IA</a><a href="{raiz}sobre/">Fontes</a></nav></header>
<main>
{corpo}
</main>
<footer>
<p><strong>Fonte oficial:</strong> <a href="{PORTAL_DOWNLOAD}">Portal da Transparência do Governo Federal (CGU)</a>, arquivos de emendas parlamentares
e de favorecidos, exercícios de {e(desde)} em diante, baixados e atualizados em {e(atualizado)}. Os valores são reproduzidos como publicados.
<a href="{raiz}sobre/">Fontes, método e limites</a>.</p>
<p>Site independente, <strong>não oficial</strong> e sem vínculo com o governo, partidos ou parlamentares. Encontrou um erro?
<a href="{config.REPO_URL}/issues">Avise aqui</a>. <a href="{raiz}apoie/">Apoie com Lightning ⚡</a></p>
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


def cnpj_prefeitura(favs: pd.Series) -> str:
    """CNPJ da prefeitura entre os favorecidos: 'MUNICIPIO DE …' ou 'PREFEITURA …' com CNPJ válido."""
    for (nome, doc), _ in favs.items():
        dig = re.sub(r"\D", "", str(doc))
        if len(dig) == 14 and re.match(r"^(MUNIC[IÍ]PIO|PREFEITURA)", str(nome).strip().upper()):
            return dig
    return ""


def glossario(termo: str, texto: str, raiz: str) -> str:
    return f'<a class="glos" href="{raiz}sobre/#{termo}" title="{e(texto)}">?</a>'


# --------------------------------------------------------------------------- geração


def gerar_site(fav: pd.DataFrame, municipios: list[dict], destino: Path, fato: pd.DataFrame | None = None,
               populacao: dict | None = None) -> int:
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
    desde = str(int(fav["ano"].min()))
    nomes = {str(m["codigo_ibge"]): (m["nome"], m["uf"]) for m in municipios}
    pop = {str(k): int(v) for k, v in (populacao or {}).get("pop", {}).items()}
    fonte_pop = (populacao or {}).get("fonte", "")
    df = fav[fav["municipio_ibge"].notna()].copy()
    df["municipio_ibge"] = df["municipio_ibge"].astype(str)

    # Área (função) de cada emenda, para a frase-resumo.
    if fato is not None and "funcao" in fato.columns:
        area = fato.dropna(subset=["funcao"]).groupby("codigo_emenda")["funcao"].agg(lambda s: s.mode().iat[0])
        df["area"] = df["codigo_emenda"].map(area).fillna("Não informada")
    else:
        df["area"] = "Não informada"

    totais = df.groupby("municipio_ibge")["valor_recebido"].sum().sort_values(ascending=False)
    por_ano = df.groupby(["municipio_ibge", "ano"])["valor_recebido"].sum()
    autores = df.groupby(["municipio_ibge", "nome_autor"])["valor_recebido"].sum()
    areas = df.groupby(["municipio_ibge", "area"])["valor_recebido"].sum()
    df["fav_rotulo"] = df["favorecido"].fillna("Sem nome").astype(str)
    df["fav_cod"] = df["codigo_favorecido"].fillna("").astype(str).map(mascarar_documento) if "codigo_favorecido" in df else ""
    favorecidos = df.groupby(["municipio_ibge", "fav_rotulo", "fav_cod"])["valor_recebido"].sum()
    tipos = df.groupby(["municipio_ibge", "tipo_emenda"])["valor_recebido"].sum()

    base = pd.DataFrame({"total": totais})
    base["uf"] = [nomes.get(c, ("", ""))[1] for c in base.index]
    base["pop"] = [pop.get(c) for c in base.index]
    base["per_capita"] = base["total"] / base["pop"]
    base["rank_uf"] = base.groupby("uf")["total"].rank(ascending=False, method="min").astype(int)
    qtd_uf = base["uf"].value_counts()
    mediana_uf = base.groupby("uf")["per_capita"].median()

    # ---- páginas de município
    for codigo, total in totais.items():
        if codigo not in nomes:
            continue
        nome, uf = nomes[codigo]
        rel = caminho_municipio(nome, uf)
        b = base.loc[codigo]
        top_aut = autores.loc[codigo].sort_values(ascending=False).head(10)
        top_fav = favorecidos.loc[codigo].sort_values(ascending=False).head(20)
        top_fav_todos = favorecidos.loc[codigo].sort_values(ascending=False)
        top_tipo = tipos.loc[codigo].sort_values(ascending=False)
        top_area = areas.loc[codigo].sort_values(ascending=False)

        # Frase-resumo e comparação por habitante.
        resumo = [f"<strong>{brl(total)}</strong> recebidos em emendas parlamentares de {desde} até hoje."]
        if pd.notna(b["per_capita"]):
            med = mediana_uf.get(uf)
            comp = ""
            if med and pd.notna(med) and med > 0:
                r = b["per_capita"] / med
                comp = (f", {r:.1f}".replace(".", ",") + f" vezes a mediana dos municípios de {e(uf)}") if r >= 1.15 else \
                       (f", abaixo da mediana de {e(uf)} ({brl(med)})" if r <= 0.85 else f", perto da mediana de {e(uf)}")
            resumo.append(f"Isso dá <strong>{brl(b['per_capita'])} por habitante</strong>{comp}.")
        if len(top_area) and top_area.index[0] != "Não informada":
            resumo.append(f"A maior parte foi para <strong>{e(top_area.index[0].lower())}</strong> ({pct(100 * top_area.iloc[0] / total)}).")
        if len(top_aut):
            resumo.append(f"Quem mais enviou: <strong>{e(top_aut.index[0])}</strong> ({brl_curto(top_aut.iloc[0])}).")
        hab = f" · {inteiro(b['pop'])} habitantes" if pd.notna(b["pop"]) else ""

        url_pagina = f"{config.SITE_URL}/{rel}"
        texto_wpp = f"{nome} ({uf}) recebeu {brl_curto(total)} em emendas parlamentares desde {desde}. Veja quem mandou e quem recebeu: {url_pagina}"
        rotulo_m = f"{nome} ({uf})"
        corpo = f"""
<p class="migalha"><a href="../../">Início</a> › {e(uf)} › {e(nome)}</p>
<h1>{e(nome)} <span class="uf">{e(uf)}</span></h1>
<p class="contexto">{int(b['rank_uf'])}º de {int(qtd_uf[uf])} municípios de {e(uf)} em valor recebido{hab}</p>
<p class="resumo-texto">{' '.join(resumo)}</p>
<p class="acoes"><a class="botao-wpp" href="https://wa.me/?text={quote(texto_wpp)}" rel="noopener">Compartilhar no WhatsApp</a>
<a class="botao2" href="../../painel/#f.municipio={quote(rotulo_m)}">Ver no painel</a></p>
<section><h2>Por ano</h2>{barras_ano(por_ano.loc[codigo])}</section>
<section><h2>Quem mandou o dinheiro {glossario("autor", "Parlamentar, bancada estadual ou comissão autora da emenda.", "../../")}</h2>
{tabela(["Autor da emenda", "Valor"], [[e(a), brl(v)] for a, v in top_aut.items()], {1})}</section>
<section><h2>Quem recebeu {glossario("favorecido", "Quem recebeu o dinheiro direto da União: prefeitura, fundo, entidade.", "../../")}</h2>
{tabela(["Favorecido", "CNPJ/CPF", "Valor"], [[e(f), e(c), brl(v)] for (f, c), v in top_fav.items()], {2})}
<p class="dica"><a href="../../explorar/#l=favorecido&amp;f.municipio={quote(rotulo_m)}">Ver todos os favorecidos no Explorar ›</a></p></section>
<section id="contratos" data-cnpj="{e(cnpj_prefeitura(top_fav_todos))}" hidden><h2>Empresas contratadas pela prefeitura</h2>
<p class="dica">Contratos dos últimos 12 meses publicados no <a href="https://pncp.gov.br/">PNCP</a>. Os dados públicos não indicam quais foram pagos com dinheiro de emendas.</p>
<div class="conteudo">Carregando…</div></section>
<script src="../../contratos.js" defer></script>
<section><h2>Tipo de emenda {glossario("tipo", "Individual, de bancada, de comissão ou de relator; transferências especiais são as Emendas Pix.", "../../")}</h2>
{tabela(["Tipo", "Valor", "%"], [[e(t), brl(v), pct(100 * v / total)] for t, v in top_tipo.items()], {1, 2})}</section>
<aside class="origem"><strong>De onde vêm estes números:</strong> soma do campo "Valor Recebido" do arquivo de favorecidos do
<a href="{PORTAL_DOWNLOAD}">Portal da Transparência</a> para favorecidos com sede em {e(nome)} ({e(uf)}), atualizado em {e(atualizado)}.
Confira emenda por emenda na <a href="{PORTAL_CONSULTA}">consulta oficial de emendas</a>.{(" População: " + e(fonte_pop) + ".") if pd.notna(b["pop"]) and fonte_pop else ""}</aside>
<aside class="apoio"><p><strong>Esta página foi útil?</strong> O site é independente, sem anúncios e se mantém com contribuições de qualquer valor.</p>
<a class="botao" href="../../apoie/">Apoiar com Lightning ⚡</a></aside>
<script>try{{localStorage.setItem("ultimoMunicipio",JSON.stringify({{n:{json.dumps(rotulo_m)},p:{json.dumps(rel)}}}))}}catch(e){{}}</script>
"""
        pasta = destino / rel
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "index.html").write_text(
            pagina(
                f"Emendas parlamentares em {nome} ({uf})",
                f"{nome} ({uf}) recebeu {brl(total)} em emendas parlamentares desde {desde}. Veja por ano, autor e favorecido.",
                corpo, "../../", atualizado, desde, rel,
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
    def linha_mun(c, valor_txt):
        return [f'<a href="{caminho_municipio(*nomes[c])}">{e(nomes[c][0])}</a>', e(nomes[c][1]), valor_txt]

    top = [linha_mun(c, brl(v)) for c, v in totais.head(10).items() if c in nomes]
    por_hab = base[(base["pop"] >= POP_MIN_DESTAQUE)].sort_values("per_capita", ascending=False).head(10)
    bloco_hab = ""
    if len(por_hab):
        bloco_hab = f"""<section><h2>Mais dinheiro por habitante</h2>
<p class="dica">Entre municípios com mais de {inteiro(POP_MIN_DESTAQUE)} habitantes.</p>
{tabela(["Município", "UF", "Por habitante"], [linha_mun(c, brl(r["per_capita"])) for c, r in por_hab.iterrows() if c in nomes], {2})}</section>"""
    total_geral = float(df["valor_recebido"].sum())
    corpo = f"""
<section class="hero">
<h1>Quanto o seu município recebeu em emendas parlamentares?</h1>
<p>{brl_curto(total_geral)} pagos a {inteiro(len(totais))} municípios de {desde} até hoje, segundo o Portal da Transparência. Busque o seu:</p>
<input id="q" type="search" placeholder="Digite o nome do município" autocomplete="off" aria-label="Buscar município">
<ul id="res" class="resultados"></ul>
<p id="ultimo" class="ultimo" hidden></p>
</section>
<section class="atalhos">
<a href="painel/"><strong>Painel</strong><span>Gráficos que se filtram com um toque</span></a>
<a href="explorar/#l=autor&amp;c=ano"><strong>Quem mais enviou</strong><span>Parlamentares e bancadas, ano a ano</span></a>
<a href="explorar/#l=uf&amp;c=area"><strong>Para quais áreas</strong><span>Saúde, educação, urbanismo… por estado</span></a>
</section>
<section><h2>Os 10 municípios que mais receberam</h2>
{tabela(["Município", "UF", "Valor recebido"], top, {2})}</section>
{bloco_hab}
<script src="busca.js" defer></script>
"""
    (destino / "index.html").write_text(
        pagina("Emendas parlamentares por município",
               "Veja quanto cada município recebeu em emendas parlamentares, de quais parlamentares e para quem.",
               corpo, "", atualizado, desde, ""),
        encoding="utf-8",
    )
    gerar_sobre(destino, atualizado, desde, fonte_pop)
    gerar_apoie(destino, atualizado, desde)
    return len(totais)


def gerar_sobre(destino: Path, atualizado: str, desde: str, fonte_pop: str) -> None:
    fontes = [
        ["Emendas e valores recebidos por favorecido", f'<a href="{PORTAL_DOWNLOAD}">Portal da Transparência (CGU)</a>', "Diária, no dia seguinte à publicação"],
        ["Composição das bancadas", '<a href="https://dadosabertos.camara.leg.br/">Dados abertos da Câmara</a> e <a href="https://legis.senado.leg.br/dadosabertos/">do Senado</a>', "Diária"],
        ["Lista e códigos dos municípios", '<a href="https://www.ibge.gov.br/explica/codigos-dos-municipios.php">IBGE</a> (cópia pública em <a href="https://github.com/kelvins/municipios-brasileiros">kelvins/municipios-brasileiros</a>)', "Diária"],
        ["População", e(fonte_pop) or "IBGE", "Diária"],
    ]
    corpo = f"""
<h1>Fontes, método e limites</h1>
<p>Este site reorganiza <strong>dados públicos oficiais</strong> para facilitar a consulta. Nada aqui é opinião, acusação ou
juízo sobre a legalidade de qualquer emenda: os valores são reproduzidos como o governo federal os publica.</p>
<h2>De onde vêm os dados</h2>
{tabela(["Dado", "Fonte original", "Atualização"], fontes)}
<p>Última atualização: {e(atualizado)}. Período: exercícios de {e(desde)} em diante (o Portal publica emendas desde 2014).
O código que baixa e processa os dados é aberto: <a href="{config.REPO_URL}">{e(config.REPO_URL)}</a>.</p>
<h2>Como os números são calculados</h2>
<ul>
<li>"Valor recebido" é a soma do campo <em>Valor Recebido</em> do arquivo de favorecidos do Portal, sem correção pela inflação.</li>
<li>O município é o da sede do favorecido informada pelo Portal. Cerca de 0,2% do valor vem "sem informação" na fonte e não aparece nas páginas de município.</li>
<li>"Por habitante" divide o total recebido no período pela população mais recente.</li>
</ul>
<h2>Limites importantes</h2>
<ul>
<li>O <strong>favorecido</strong> é quem recebeu o dinheiro direto da União (prefeitura, fundo, entidade). Empresas contratadas depois não aparecem aqui.</li>
<li>Em emendas de bancada, a lista de membros mostra quem tinha mandato na legislatura, não quem pediu cada emenda.</li>
<li>Os dados podem ser corrigidos pelo próprio governo depois de publicados. Em caso de diferença, vale o <a href="{PORTAL_CONSULTA}">Portal da Transparência</a>.</li>
</ul>
<h2>Base legal e dados pessoais</h2>
<p>As informações são públicas por força da Lei de Acesso à Informação (Lei 12.527/2011) e da Política de Dados Abertos
(Decreto 8.777/2016), e são reutilizadas citando a fonte. Dados pessoais seguem a LGPD (Lei 13.709/2018): CPFs aparecem sempre
mascarados, nunca há página dedicada a pessoa física, e o uso se limita à finalidade de transparência para a qual foram publicados.</p>
<h2>Correções e remoção</h2>
<p>Encontrou um erro, ou é titular de um dado e quer pedir revisão? <a href="{config.REPO_URL}/issues">Abra um aviso aqui</a>.
Pedidos são analisados e, quando procedentes, corrigidos na atualização seguinte.</p>
<h2 id="glossario">Glossário</h2>
<dl class="glossario">
<dt id="autor">Autor da emenda</dt><dd>Quem apresentou a emenda ao orçamento: um parlamentar, uma bancada estadual (todos os deputados e senadores de um estado) ou uma comissão do Congresso.</dd>
<dt id="tipo">Tipo de emenda</dt><dd>Individual (de um parlamentar), de bancada, de comissão ou de relator. "Transferências especiais" são as chamadas <strong>Emendas Pix</strong>: o dinheiro vai direto ao estado ou município, sem convênio.</dd>
<dt id="favorecido">Favorecido</dt><dd>Quem recebeu o pagamento: prefeitura, fundo municipal, entidade ou, mais raramente, pessoa física.</dd>
<dt id="empenhado">Empenhado, liquidado e pago</dt><dd>Etapas da despesa: o empenho reserva o dinheiro, a liquidação confirma a entrega e o pagamento transfere de fato. Este site usa o valor efetivamente recebido.</dd>
</dl>
"""
    pasta = destino / "sobre"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "index.html").write_text(
        pagina("Fontes, método e limites", "De onde vêm os dados de emendas parlamentares, como são calculados e seus limites.", corpo, "../", atualizado, desde, "sobre/"),
        encoding="utf-8",
    )


def qr_svg(texto: str) -> str:
    """QR code em SVG (usa segno; sem ele, devolve vazio e a página mostra só o endereço)."""
    try:
        import segno
    except ImportError:
        print("aviso: segno não instalado; página Apoie sem QR code")
        return ""
    import io

    buf = io.BytesIO()
    segno.make(texto, error="m").save(buf, kind="svg", scale=6, border=2, xmldecl=False, svgns=True, dark="#1c1f24", light="#ffffff")
    return buf.getvalue().decode("utf-8")



def gerar_apoie(destino: Path, atualizado: str, desde: str) -> None:
    endereco = config.LIGHTNING_ADDRESS
    qr = qr_svg(f"lightning:{endereco}")
    corpo = f"""
<h1>Apoie o projeto ⚡</h1>
<p>Este painel é independente, sem login e sem anúncios. Ele se mantém com contribuições em bitcoin
pela rede Lightning, de qualquer valor.</p>
<div class="apoie">
{f'<a class="qr" href="lightning:{e(endereco)}" aria-label="Abrir na carteira Lightning">{qr}</a>' if qr else ''}
<p class="endereco"><strong>{e(endereco)}</strong></p>
<p><button type="button" id="copiar" data-endereco="{e(endereco)}">Copiar endereço</button>
<a class="botao" href="lightning:{e(endereco)}">Abrir na carteira</a></p>
<p class="dica">Aponte a câmera da sua carteira Lightning para o QR code, ou copie o endereço e cole na
opção de enviar. Funciona com qualquer carteira que aceite Lightning Address.</p>
</div>
<script>
document.getElementById("copiar").addEventListener("click", async (ev) => {{
  const b = ev.currentTarget;
  try {{ await navigator.clipboard.writeText(b.dataset.endereco); b.textContent = "Copiado ✓"; }}
  catch (e) {{ b.textContent = b.dataset.endereco; }}
}});
</script>
"""
    pasta = destino / "apoie"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "index.html").write_text(
        pagina("Apoie o projeto", "Contribua com bitcoin pela rede Lightning para manter o painel no ar.", corpo, "../", atualizado, desde, "apoie/"),
        encoding="utf-8",
    )


def gerar_api(destino: Path, fav: pd.DataFrame, municipios: list[dict], populacao: dict | None, fato: pd.DataFrame | None,
              qualidade: dict | None = None) -> None:
    """Arquivos JSON pequenos lidos pelo servidor MCP (um por município + rankings)."""
    api = destino / "api"
    (api / "m").mkdir(parents=True, exist_ok=True)
    (api / "ranking").mkdir(parents=True, exist_ok=True)
    nomes = {str(m["codigo_ibge"]): (m["nome"], m["uf"]) for m in municipios}
    pop = {str(k): int(v) for k, v in (populacao or {}).get("pop", {}).items()}
    df = fav[fav["municipio_ibge"].notna()].copy()
    df["municipio_ibge"] = df["municipio_ibge"].astype(str)
    if fato is not None and "funcao" in fato.columns:
        area = fato.dropna(subset=["funcao"]).groupby("codigo_emenda")["funcao"].agg(lambda s: s.mode().iat[0])
        df["area"] = df["codigo_emenda"].map(area).fillna("Não informada")
    else:
        df["area"] = "Não informada"
    df["doc"] = df["codigo_favorecido"].fillna("").astype(str).map(mascarar_documento) if "codigo_favorecido" in df else ""
    fonte = {"fonte": "Portal da Transparência (CGU), arquivo de emendas por favorecido", "url": PORTAL_DOWNLOAD,
             "aviso": "Valores reproduzidos como publicados pela fonte oficial; não constituem juízo sobre legalidade."}
    def top(g, n):
        return [{"nome": k if not isinstance(k, tuple) else k[0], **({"documento": k[1]} if isinstance(k, tuple) else {}), "valor": round(float(v), 2)}
                for k, v in g.sort_values(ascending=False).head(n).items()]
    linhas = []
    for cod, parte in df.groupby("municipio_ibge"):
        if cod not in nomes:
            continue
        total = float(parte["valor_recebido"].sum())
        p = pop.get(cod)
        info = {
            "codigo_ibge": cod, "municipio": nomes[cod][0], "uf": nomes[cod][1], "total_recebido": round(total, 2),
            "populacao": p, "por_habitante": round(total / p, 2) if p else None,
            "por_ano": {str(int(a)): round(float(v), 2) for a, v in parte.groupby("ano")["valor_recebido"].sum().items()},
            "autores": top(parte.groupby("nome_autor")["valor_recebido"].sum(), 15),
            "favorecidos": top(parte.groupby(["favorecido", "doc"])["valor_recebido"].sum(), 15),
            "areas": top(parte.groupby("area")["valor_recebido"].sum(), 10),
            "tipos": top(parte.groupby("tipo_emenda")["valor_recebido"].sum(), 10),
            "cnpj_prefeitura": cnpj_prefeitura(parte.groupby(["favorecido", "doc"])["valor_recebido"].sum().sort_values(ascending=False)) or None,
            "pagina": f"{config.SITE_URL}/{caminho_municipio(*nomes[cod])}", **fonte,
        }
        (api / "m" / f"{cod}.json").write_text(json.dumps(info, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        linhas.append({"codigo_ibge": cod, "municipio": nomes[cod][0], "uf": nomes[cod][1], "total": round(total, 2),
                       "por_habitante": info["por_habitante"], "populacao": p})
    tab = pd.DataFrame(linhas)
    for uf in ["BR"] + sorted(tab["uf"].unique()):
        t = tab if uf == "BR" else tab[tab["uf"] == uf]
        grandes = t[t["populacao"].fillna(0) >= POP_MIN_DESTAQUE]
        rk = {"uf": uf, "por_total": t.sort_values("total", ascending=False).head(50).to_dict("records"),
              "por_habitante_acima_50mil": grandes.sort_values("por_habitante", ascending=False).head(50).to_dict("records"), **fonte}
        (api / "ranking" / f"{uf}.json").write_text(json.dumps(rk, ensure_ascii=False, separators=(",", ":"), default=lambda x: None), encoding="utf-8")
    (api / "indice.json").write_text(json.dumps({f"{n}|{u}": c for c, (n, u) in nomes.items()}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # Descoberta: robots, sitemap e llms.txt para buscadores e assistentes de IA.
    urls = ["", "painel/", "explorar/", "sobre/", "ia/", "apoie/"] + [caminho_municipio(*nomes[l["codigo_ibge"]]) for l in linhas]
    (destino / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{config.SITE_URL}/{html.escape(u)}</loc></url>" for u in urls) + "</urlset>\n", encoding="utf-8")
    (destino / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /gestao/\nSitemap: {config.SITE_URL}/sitemap.xml\n", encoding="utf-8")
    (destino / "llms.txt").write_text(f"""# Emendas parlamentares do Brasil

> Quanto cada município recebeu em emendas parlamentares federais, de quais parlamentares e para quem. Dados do Portal da Transparência (CGU), de 2014 em diante, atualizados diariamente.

## Para agentes de IA
- Servidor MCP (Streamable HTTP): {config.SITE_URL}/mcp — ferramentas buscar_municipio e resumo_municipio gratuitas; detalhes e rankings com passe de 24 h pago em Lightning.
- Documentação: {config.SITE_URL}/ia/

## Páginas
- [Painel]({config.SITE_URL}/painel/)
- [Explorar]({config.SITE_URL}/explorar/)
- [Fontes, método e limites]({config.SITE_URL}/sobre/)
""", encoding="utf-8")
    if qualidade:
        (api / "qualidade.json").write_text(json.dumps(qualidade, ensure_ascii=False), encoding="utf-8")
    print(f"api: {len(linhas):,} municípios, {len(tab['uf'].unique()) + 1} rankings")

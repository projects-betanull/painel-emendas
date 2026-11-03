// Painel: indicadores e gráficos com filtro cruzado; compartilha estado e motor com o Explorar.
"use strict";
(async function () {
  const $ = (id) => document.getElementById(id);
  const brl = (v) => v >= 1e9 ? "R$ " + (v / 1e9).toFixed(1).replace(".", ",") + " bi"
    : v >= 1e6 ? "R$ " + (v / 1e6).toFixed(1).replace(".", ",") + " mi"
    : v >= 1e3 ? "R$ " + Math.round(v / 1e3).toLocaleString("pt-BR") + " mil"
    : "R$ " + Math.round(v).toLocaleString("pt-BR");
  const num = (v) => Math.round(v).toLocaleString("pt-BR");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const TOP = { uf: 27, municipio: 10, autor: 10, tipo: 8, area: 10, natureza: 8, favorecido: 15 };

  let cubo = null, est = deHash(location.hash.slice(1));

  // Um gráfico de uma dimensão ignora o próprio filtro, para mostrar as alternativas
  // (filtro cruzado): os valores filtrados ficam destacados, os demais esmaecidos.
  const serie = (dim, med = "valor") => {
    const f = { ...est.f }; delete f[dim];
    return pivotar(cubo, { lin: dim, col: "", med, f });
  };

  function barrasH(dim) {
    const r = serie(dim), rot = cubo.dims[dim], sel = new Set(est.f[dim] || []);
    const linhas = r.linhas.slice(0, TOP[dim]);
    const max = linhas.length ? linhas[0][1].total : 1;
    $("g-" + dim).innerHTML = linhas.map(([i, x]) => {
      const nome = rot[i], ativo = !sel.size || sel.has(nome);
      return `<button type="button" class="hbar${ativo ? "" : " apagado"}${sel.has(nome) ? " sel" : ""}" data-d="${dim}" data-v="${esc(nome)}" title="${esc(nome)}: ${brl(x.total)}">
        <span class="rot">${esc(nome)}</span><span class="trilho"><span class="cheio" style="width:${(100 * x.total / max).toFixed(1)}%"></span></span><span class="val">${brl(x.total)}</span></button>`;
    }).join("") || '<p class="dica">Sem dados com estes filtros.</p>';
  }

  function colunasAno() {
    const r = serie("ano"), rot = cubo.dims.ano, sel = new Set(est.f.ano || []);
    const anos = r.linhas.slice().sort((a, b) => rot[a[0]].localeCompare(rot[b[0]]));
    const max = Math.max(1, ...anos.map(([, x]) => x.total));
    $("g-ano").innerHTML = anos.map(([i, x]) => {
      const a = rot[i], ativo = !sel.size || sel.has(a);
      return `<button type="button" class="vbar${ativo ? "" : " apagado"}${sel.has(a) ? " sel" : ""}" data-d="ano" data-v="${a}" title="${a}: ${brl(x.total)}">
        <span class="valor-ano">${brl(x.total).replace("R$ ", "")}</span><span class="coluna"><span class="cheio" style="height:${(100 * x.total / max).toFixed(1)}%"></span></span><span class="ano">${a.slice(2)}</span></button>`;
    }).join("");
  }

  function kpis() {
    const v = pivotar(cubo, { ...est, lin: "uf", col: "", med: "valor" });
    const n = pivotar(cubo, { ...est, lin: "uf", col: "", med: "n" });
    const m = pivotar(cubo, { ...est, lin: "municipio", col: "", med: "n" }).nLinhas;
    const a = pivotar(cubo, { ...est, lin: "autor", col: "", med: "n" }).nLinhas;
    $("kpis").innerHTML = [["Valor recebido", brl(v.total)], ["Pagamentos", num(n.total)], ["Municípios", num(m)], ["Autores", num(a)]]
      .map(([t, x]) => `<div class="kpi"><span>${t}</span><strong>${x}</strong></div>`).join("");
  }

  function desenhar() {
    const chips = Object.entries(est.f).filter(([, v]) => v.length)
      .map(([d, v]) => `<button type="button" class="chip" data-subir="${d}">${NOMES[d]}: ${esc(v.length > 2 ? v.length + " selecionados" : v.join(", "))} ✕</button>`);
    $("trilha").innerHTML = '<button type="button" class="chip raiz" data-subir="*">Brasil</button>' + chips.join("");
    kpis(); colunasAno();
    for (const d of ["uf", "municipio", "autor", "tipo", "area", "natureza"]) barrasH(d);
    if (cubo.dims.favorecido) barrasH("favorecido");
    else $("g-favorecido").innerHTML = '<p class="dica">Toque numa UF ou num município para ver quem recebeu.</p>';
    const h = paraHash(est);
    $("irExplorar").href = "../explorar/#" + h;
    document.querySelectorAll(".cab a[data-dim]").forEach((a) => (a.href = "../explorar/#" + paraHash({ ...est, lin: a.dataset.dim, col: a.dataset.dim === "ano" ? "" : est.col === a.dataset.dim ? "" : est.col })));
  }

  async function ir(novo) {
    try { cubo = await carregarCubo(novo, "../explorar/"); } catch (e) { $("kpis").textContent = "Não foi possível carregar os dados."; return; }
    est = ajustar(novo, cubo);
    history.replaceState(null, "", "#" + paraHash(est)); mostrarBancada(est, $("bancada"), "../"); desenhar();
  }

  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-d],[data-subir]");
    if (!b) return;
    if (b.dataset.subir === "*") return ir({ ...est, f: {} });
    if (b.dataset.subir) { const f = { ...est.f }; delete f[b.dataset.subir]; return ir({ ...est, f }); }
    const d = b.dataset.d, atual = new Set(est.f[d] || []);
    atual.has(b.dataset.v) ? atual.delete(b.dataset.v) : atual.add(b.dataset.v);
    ir({ ...est, f: { ...est.f, [d]: [...atual] } });
  });
  window.addEventListener("hashchange", () => ir(deHash(location.hash.slice(1))));
  ir(est);
})();

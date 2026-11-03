// Explorador: pivô, facetas e drill-down/up sobre cubo.json, tudo no navegador.
"use strict";
const NOMES = { ano: "Ano", uf: "UF", municipio: "Município", autor: "Autor da emenda", tipo: "Tipo de emenda", natureza: "Natureza do favorecido", area: "Área" };
const DESCE = { ano: "uf", uf: "municipio", municipio: "autor", autor: "municipio", tipo: "autor", natureza: "municipio", area: "uf" };
const LIMITE = 50, MAX_COLS = 8;

// ---------- motor (sem DOM; testável no Node)
function filtrosParaSets(cubo, f) {
  const s = {};
  for (const [d, rotulos] of Object.entries(f)) {
    if (!rotulos.length) continue;
    const idx = new Map(cubo.dims[d].map((r, i) => [r, i]));
    s[d] = new Set(rotulos.map((r) => idx.get(r)).filter((i) => i !== undefined));
  }
  return s;
}

function pivotar(cubo, est) {
  const sets = filtrosParaSets(cubo, est.f), dimsF = Object.keys(sets);
  const L = cubo.cols[est.lin], C = est.col ? cubo.cols[est.col] : null, M = cubo[est.med];
  const linhas = new Map(), totCol = new Map();
  let total = 0;
  outer: for (let i = 0; i < M.length; i++) {
    for (const d of dimsF) if (!sets[d].has(cubo.cols[d][i])) continue outer;
    const v = M[i], l = L[i], c = C ? C[i] : 0;
    let lin = linhas.get(l);
    if (!lin) linhas.set(l, (lin = { total: 0, cols: new Map() }));
    lin.total += v;
    lin.cols.set(c, (lin.cols.get(c) || 0) + v);
    totCol.set(c, (totCol.get(c) || 0) + v);
    total += v;
  }
  let cols = [...totCol.keys()];
  if (C) {
    const rot = cubo.dims[est.col];
    cols = est.col === "ano" ? cols.sort((a, b) => rot[a].localeCompare(rot[b])) : cols.sort((a, b) => totCol.get(b) - totCol.get(a)).slice(0, MAX_COLS);
  }
  const ordenadas = [...linhas.entries()].sort((a, b) => b[1].total - a[1].total);
  return { total, nLinhas: ordenadas.length, cols, linhas: ordenadas.slice(0, LIMITE) };
}

function descer(est, rotulo) {
  const f = { ...est.f, [est.lin]: [rotulo] };
  let prox = DESCE[est.lin];
  const livres = Object.keys(NOMES).filter((d) => !(f[d] && f[d].length) && d !== est.col);
  if (!livres.includes(prox)) prox = livres[0] || est.lin;
  return { ...est, f, lin: prox };
}

function subir(est, dim) {
  const f = { ...est.f };
  delete f[dim];
  return { ...est, f, lin: dim };
}

const paraHash = (e) => {
  const p = new URLSearchParams({ l: e.lin, c: e.col || "", m: e.med });
  for (const [d, v] of Object.entries(e.f)) if (v.length) p.set("f." + d, v.join("|"));
  return p.toString();
};
const deHash = (h) => {
  const p = new URLSearchParams(h), f = {};
  for (const [k, v] of p) if (k.startsWith("f.") && NOMES[k.slice(2)]) f[k.slice(2)] = v.split("|");
  const l = NOMES[p.get("l")] ? p.get("l") : "uf", c = NOMES[p.get("c")] ? p.get("c") : "";
  return { lin: l, col: c === l ? "" : c, med: p.get("m") === "n" ? "n" : "valor", f };
};

if (typeof module !== "undefined") module.exports = { pivotar, descer, subir, paraHash, deHash };

// ---------- interface
if (typeof document !== "undefined") (async function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (v, med) => med === "n" ? Math.round(v).toLocaleString("pt-BR")
    : v >= 1e9 ? "R$ " + (v / 1e9).toFixed(1).replace(".", ",") + " bi"
    : v >= 1e6 ? "R$ " + (v / 1e6).toFixed(1).replace(".", ",") + " mi"
    : "R$ " + Math.round(v).toLocaleString("pt-BR");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  let cubo;
  try { cubo = await (await fetch("cubo.json")).json(); }
  catch (e) { $("resumo").textContent = "Não foi possível carregar os dados."; return; }
  let est = deHash(location.hash.slice(1));

  for (const [id, vazio] of [["linhas", false], ["colunas", true]]) {
    $(id).innerHTML = (vazio ? '<option value="">(nenhuma)</option>' : "") + Object.entries(NOMES).map(([d, n]) => `<option value="${d}">${n}</option>`).join("");
  }
  $("linhas").onchange = () => ir({ ...est, lin: $("linhas").value, col: est.col === $("linhas").value ? "" : est.col });
  $("colunas").onchange = () => ir({ ...est, col: $("colunas").value === est.lin ? "" : $("colunas").value });
  $("medida").onchange = () => ir({ ...est, med: $("medida").value });

  // Facetas: caixas de seleção para dimensões curtas, busca para as longas.
  $("listas").innerHTML = Object.keys(NOMES).map((d) => {
    const r = cubo.dims[d];
    if (r.length <= 60) return `<fieldset><legend>${NOMES[d]}</legend>${r.map((x) => `<label><input type="checkbox" data-d="${d}" value="${esc(x)}"> ${esc(x)}</label>`).join("")}</fieldset>`;
    return `<fieldset><legend>${NOMES[d]}</legend><input list="dl-${d}" data-busca="${d}" placeholder="Digite e escolha"><datalist id="dl-${d}">${r.map((x) => `<option value="${esc(x)}">`).join("")}</datalist></fieldset>`;
  }).join("");
  $("listas").addEventListener("change", (ev) => {
    const t = ev.target, d = t.dataset.d || t.dataset.busca;
    if (!d) return;
    const atual = new Set(est.f[d] || []);
    if (t.dataset.d) t.checked ? atual.add(t.value) : atual.delete(t.value);
    else if (cubo.dims[d].includes(t.value)) { atual.add(t.value); t.value = ""; }
    ir({ ...est, f: { ...est.f, [d]: [...atual] } });
  });

  function ir(novo) { est = novo; history.replaceState(null, "", "#" + paraHash(est)); desenhar(); }

  function desenhar() {
    $("linhas").value = est.lin; $("colunas").value = est.col; $("medida").value = est.med;
    document.querySelectorAll("#listas input[type=checkbox]").forEach((c) => (c.checked = (est.f[c.dataset.d] || []).includes(c.value)));
    const chips = Object.entries(est.f).filter(([, v]) => v.length)
      .map(([d, v]) => `<button type="button" class="chip" data-subir="${d}" title="Remover filtro (drill-up)">${NOMES[d]}: ${esc(v.length > 2 ? v.length + " selecionados" : v.join(", "))} ✕</button>`);
    $("trilha").innerHTML = '<button type="button" class="chip raiz" data-subir="*">Brasil</button>' + chips.join("");

    const r = pivotar(cubo, est), rotL = cubo.dims[est.lin], rotC = est.col ? cubo.dims[est.col] : null;
    $("resumo").innerHTML = `<strong>${fmt(r.total, est.med)}</strong> em ${r.nLinhas.toLocaleString("pt-BR")} ${NOMES[est.lin].toLowerCase()}${r.nLinhas === 1 ? "" : "s"}`;
    const cab = `<thead><tr><th>${NOMES[est.lin]}</th>${rotC ? r.cols.map((c) => `<th class="n">${esc(rotC[c])}</th>`).join("") : ""}<th class="n">Total</th></tr></thead>`;
    const corpo = r.linhas.map(([l, x]) => `<tr><td><a href="#" data-descer="${esc(rotL[l])}">${esc(rotL[l])}</a></td>${rotC ? r.cols.map((c) => `<td class="n">${x.cols.has(c) ? fmt(x.cols.get(c), est.med) : "–"}</td>`).join("") : ""}<td class="n"><strong>${fmt(x.total, est.med)}</strong></td></tr>`).join("");
    $("pivo").innerHTML = cab + "<tbody>" + corpo + "</tbody>";
    $("mais").textContent = r.nLinhas > LIMITE ? `Mostrando as ${LIMITE} maiores de ${r.nLinhas.toLocaleString("pt-BR")}. Use os filtros para refinar. Tabela completa e exportação em CSV: em breve.` : "";
  }

  document.addEventListener("click", (ev) => {
    const a = ev.target.closest("[data-descer],[data-subir]");
    if (!a) return;
    ev.preventDefault();
    if (a.dataset.descer !== undefined) ir(descer(est, a.dataset.descer));
    else if (a.dataset.subir === "*") ir({ ...est, f: {} });
    else ir(subir(est, a.dataset.subir));
  });
  window.addEventListener("hashchange", () => { est = deHash(location.hash.slice(1)); desenhar(); });
  ir(est);
})();

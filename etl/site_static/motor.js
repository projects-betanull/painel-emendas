// Motor compartilhado do Explorar e do Painel: pivô, filtros e estado na URL.
"use strict";
const NOMES = { ano: "Ano", uf: "UF", municipio: "Município", autor: "Autor da emenda", tipo: "Tipo de emenda", natureza: "Natureza do favorecido", area: "Área", favorecido: "Favorecido" };
const DESCE = { ano: "uf", uf: "municipio", municipio: "favorecido", favorecido: "autor", autor: "municipio", tipo: "autor", natureza: "municipio", area: "uf" };
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

function descer(est, rotulo, dims = Object.keys(NOMES)) {
  const f = { ...est.f, [est.lin]: [rotulo] };
  let prox = DESCE[est.lin];
  // Com município ou UF escolhidos, o cubo da UF tem favorecidos: o próximo nível pode ser ele.
  if (ufDoEstado({ f }) && !dims.includes("favorecido")) dims = [...dims, "favorecido"];
  const livres = Object.keys(NOMES).filter((d) => dims.includes(d) && !(f[d] && f[d].length) && d !== est.col);
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

// UF única implícita nos filtros (uma UF, ou municípios todos da mesma UF: "Campinas (SP)").
function ufDoEstado(est) {
  const u = est.f.uf, m = est.f.municipio;
  if (u && u.length === 1) return u[0];
  if (m && m.length && m.every((x) => x.slice(-3, -1) === m[0].slice(-3, -1))) return m[0].slice(-3, -1);
  return null;
}

// Ajusta o estado ao cubo carregado: dimensões que ele não tem saem das linhas, colunas e filtros.
function ajustar(est, cubo) {
  const tem = (d) => d && cubo.dims[d];
  const f = {};
  for (const [d, v] of Object.entries(est.f)) if (tem(d)) f[d] = v;
  return { ...est, lin: tem(est.lin) ? est.lin : "uf", col: tem(est.col) ? est.col : "", f };
}

const _cubos = {};
async function carregarCubo(est, base) {
  const uf = ufDoEstado(est), url = base + (uf ? "fav/" + uf + ".json" : "cubo.json");
  if (!_cubos[url]) _cubos[url] = fetch(url).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
  try { return await _cubos[url]; }
  catch (e) { delete _cubos[url]; if (uf) return carregarCubo({ f: {} }, base); throw e; }
}

if (typeof module !== "undefined") module.exports = { pivotar, descer, subir, paraHash, deHash, ufDoEstado, ajustar, NOMES };


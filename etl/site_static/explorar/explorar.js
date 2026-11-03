// Explorar: tabela dinâmica (usa ../motor.js).
"use strict";
const UM = { ano: "ano", uf: "UF", municipio: "município", autor: "autor", tipo: "tipo", natureza: "natureza", area: "área", favorecido: "favorecido" };
const VARIOS = { ano: "anos", uf: "UFs", municipio: "municípios", autor: "autores", tipo: "tipos", natureza: "naturezas", area: "áreas", favorecido: "favorecidos" };
// ---------- interface
if (typeof document !== "undefined") (async function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (v, med) => med === "n" ? Math.round(v).toLocaleString("pt-BR")
    : v >= 1e9 ? "R$ " + (v / 1e9).toFixed(1).replace(".", ",") + " bi"
    : v >= 1e6 ? "R$ " + (v / 1e6).toFixed(1).replace(".", ",") + " mi"
    : "R$ " + Math.round(v).toLocaleString("pt-BR");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  let cubo = null, est = deHash(location.hash.slice(1));
  const dimsDe = (c) => Object.keys(NOMES).filter((d) => c.dims[d]);

  function montarControles() {
    for (const [id, vazio] of [["linhas", false], ["colunas", true]]) {
      $(id).innerHTML = (vazio ? '<option value="">(nenhuma)</option>' : "") + dimsDe(cubo).map((d) => `<option value="${d}">${NOMES[d]}</option>`).join("");
    }
    $("listas").innerHTML = dimsDe(cubo).map((d) => {
      const r = cubo.dims[d];
      if (r.length <= 60) return `<fieldset><legend>${NOMES[d]}</legend>${r.map((x) => `<label><input type="checkbox" data-d="${d}" value="${esc(x)}"> ${esc(x)}</label>`).join("")}</fieldset>`;
      return `<fieldset><legend>${NOMES[d]}</legend><input list="dl-${d}" data-busca="${d}" placeholder="Digite e escolha"><datalist id="dl-${d}">${r.map((x) => `<option value="${esc(x)}">`).join("")}</datalist></fieldset>`;
    }).join("") + (cubo.dims.favorecido ? "" : '<p class="dica">Escolha uma UF ou um município para filtrar e cruzar por favorecido.</p>');
  }
  $("linhas").onchange = () => ir({ ...est, lin: $("linhas").value, col: est.col === $("linhas").value ? "" : est.col });
  $("colunas").onchange = () => ir({ ...est, col: $("colunas").value === est.lin ? "" : $("colunas").value });
  $("medida").onchange = () => ir({ ...est, med: $("medida").value });
  $("listas").addEventListener("change", (ev) => {
    const t = ev.target, d = t.dataset.d || t.dataset.busca;
    if (!d) return;
    const atual = new Set(est.f[d] || []);
    if (t.dataset.d) t.checked ? atual.add(t.value) : atual.delete(t.value);
    else if (cubo.dims[d].includes(t.value)) { atual.add(t.value); t.value = ""; }
    ir({ ...est, f: { ...est.f, [d]: [...atual] } });
  });

  async function ir(novo) {
    let c;
    try { c = await carregarCubo(novo, ""); } catch (e) { $("resumo").textContent = "Não foi possível carregar os dados."; return; }
    if (c !== cubo) { cubo = c; montarControles(); }
    est = ajustar(novo, cubo);
    history.replaceState(null, "", "#" + paraHash(est)); mostrarBancada(est, $("bancada"), "../"); $("irPainel").href = "../painel/#" + paraHash(est); desenhar();
  }

  function desenhar() {
    $("linhas").value = est.lin; $("colunas").value = est.col; $("medida").value = est.med;
    document.querySelectorAll("#listas input[type=checkbox]").forEach((c) => (c.checked = (est.f[c.dataset.d] || []).includes(c.value)));
    const chips = Object.entries(est.f).filter(([, v]) => v.length)
      .map(([d, v]) => `<button type="button" class="chip" data-subir="${d}" title="Remover filtro (drill-up)">${NOMES[d]}: ${esc(v.length > 2 ? v.length + " selecionados" : v.join(", "))} ✕</button>`);
    $("trilha").innerHTML = '<button type="button" class="chip raiz" data-subir="*">Brasil</button>' + chips.join("");

    const r = pivotar(cubo, est), rotL = cubo.dims[est.lin], rotC = est.col ? cubo.dims[est.col] : null;
    $("resumo").innerHTML = `<strong>${fmt(r.total, est.med)}</strong> em ${r.nLinhas.toLocaleString("pt-BR")} ${r.nLinhas === 1 ? UM[est.lin] : VARIOS[est.lin]}`;
    const cab = `<thead><tr><th>${NOMES[est.lin]}</th>${rotC ? r.cols.map((c) => `<th class="n">${esc(rotC[c])}</th>`).join("") : ""}<th class="n">Total</th></tr></thead>`;
    const corpo = r.linhas.map(([l, x]) => `<tr><td><a href="#" data-descer="${esc(rotL[l])}">${esc(rotL[l])}</a></td>${rotC ? r.cols.map((c) => `<td class="n">${x.cols.has(c) ? fmt(x.cols.get(c), est.med) : "–"}</td>`).join("") : ""}<td class="n"><strong>${fmt(x.total, est.med)}</strong></td></tr>`).join("");
    $("pivo").innerHTML = cab + "<tbody>" + corpo + "</tbody>";
    $("mais").textContent = r.nLinhas > LIMITE ? `Mostrando as ${LIMITE} maiores de ${r.nLinhas.toLocaleString("pt-BR")}. Use os filtros para refinar. Tabela completa e exportação em CSV: em breve.` : "";
  }

  document.addEventListener("click", (ev) => {
    const a = ev.target.closest("[data-descer],[data-subir]");
    if (!a) return;
    ev.preventDefault();
    if (a.dataset.descer !== undefined) ir(descer(est, a.dataset.descer, dimsDe(cubo)));
    else if (a.dataset.subir === "*") ir({ ...est, f: {} });
    else ir(subir(est, a.dataset.subir));
  });
  window.addEventListener("hashchange", () => ir(deHash(location.hash.slice(1))));
  ir(est);
})();

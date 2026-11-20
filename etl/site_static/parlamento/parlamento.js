"use strict";
// Acompanhamento parlamentar: Senado (cúpula, semicírculo para baixo) e Câmara (tigela, para cima),
// como no prédio do Congresso. Uma bolinha por parlamentar.

// ---------------------------------------------------------------- geometria (pura, testada em Node)

// Posições de n assentos num semicírculo de raio 1, da esquerda para a direita.
// virada = false: cúpula (arco para cima, Senado); true: tigela (arco para baixo, Câmara).
function assentos(n, virada) {
  if (n <= 0) return { pontos: [], raio: 0 };
  const filas = Math.max(2, Math.round(Math.sqrt(n) * 0.6));
  const interno = 0.32, passo = (1 - interno) / (filas - 1);
  const raios = Array.from({ length: filas }, (_, i) => interno + i * passo);
  const soma = raios.reduce((a, b) => a + b, 0);
  const porFila = raios.map((r) => Math.round((n * r) / soma));
  let dif = n - porFila.reduce((a, b) => a + b, 0);
  for (let i = filas - 1; dif !== 0; i = (i - 1 + filas) % filas) { const d = Math.sign(dif); if (porFila[i] + d >= 0) { porFila[i] += d; dif -= d; } }
  const pontos = [];
  raios.forEach((r, i) => {
    const k = porFila[i];
    for (let j = 0; j < k; j++) {
      const t = k === 1 ? Math.PI / 2 : Math.PI - (Math.PI * j) / (k - 1);
      pontos.push({ t, r, x: r * Math.cos(t), y: (virada ? 1 : -1) * r * Math.sin(t) });
    }
  });
  // Ordena por ângulo (esquerda -> direita); no mesmo ângulo, de dentro para fora.
  pontos.sort((a, b) => b.t - a.t || a.r - b.r);
  const arco = Math.min(...raios.map((r, i) => (porFila[i] > 1 ? (Math.PI * r) / (porFila[i] - 1) : 1)));
  return { pontos, raio: 0.46 * Math.min(passo, arco) };
}

// Ordem dos parlamentares no arco: grupos (bloco ou partido) do maior para o menor, partidos idem.
function ordenar(membros, blocoDe) {
  const tamPartido = {}, tamGrupo = {};
  for (const m of membros) { tamPartido[m.p] = (tamPartido[m.p] || 0) + 1; const g = blocoDe(m.p) || m.p; tamGrupo[g] = (tamGrupo[g] || 0) + 1; }
  const grupo = (m) => blocoDe(m.p) || m.p;
  return [...membros].sort((a, b) =>
    tamGrupo[grupo(b)] - tamGrupo[grupo(a)] || grupo(a).localeCompare(grupo(b)) ||
    tamPartido[b.p] - tamPartido[a.p] || a.p.localeCompare(b.p) || a.n.localeCompare(b.n));
}

// Membros em exercício no dia: janela [de, ate] de cada um no mês (null = mês todo).
function membrosDoDia(mes, dia) {
  const out = [];
  for (const [id, [de, ate, p]] of Object.entries((mes && mes.membros) || {})) {
    if ((de && dia < de) || (ate && dia > ate)) continue;
    out.push({ id, p });
  }
  return out;
}

const CORES_PARTIDO = {
  PT: "#c8102e", PL: "#1d3c8f", "UNIÃO": "#3a7bd5", UNIAO: "#3a7bd5", PP: "#5bb6e8", MDB: "#4d7f2a", PSD: "#f0a500",
  REPUBLICANOS: "#0f7f7a", PSB: "#e8590c", PDT: "#8e1b3a", PSDB: "#2f5fa7", PODE: "#33a852", PODEMOS: "#33a852",
  PSOL: "#f4c20d", "PC do B": "#a31d1d", PCdoB: "#a31d1d", PV: "#7cb342", REDE: "#00a19a", CIDADANIA: "#e91e63",
  AVANTE: "#ff8f00", SOLIDARIEDADE: "#ff6f00", NOVO: "#ff7a1a", PRD: "#6d4c41", AGIR: "#7e57c2", PMB: "#ad1457", MOBILIZA: "#5d4037",
};
const PALETA = ["#1d3c8f", "#c8102e", "#4d7f2a", "#f0a500", "#3a7bd5", "#0f7f7a", "#e8590c", "#7e57c2", "#5bb6e8", "#ad1457", "#33a852", "#6d4c41"];
function corDe(nome, mapa) {
  if (mapa && mapa[nome]) return mapa[nome];
  let h = 0; for (const c of nome || "") h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return `hsl(${h % 360} 45% 50%)`;
}
const PRESENCA = { P: ["Presente", "#2e9e5b"], F: ["Ausente", "#d64545"], J: ["Ausência justificada", "#e9b949"], "?": ["Não divulgada", "#b9bec6"] };
const VOTO = { S: ["Sim", "#2e9e5b"], N: ["Não", "#d64545"], A: ["Abstenção", "#e9b949"], O: ["Obstrução", "#7e57c2"],
  P: ["Presente, sem voto", "#8aa0b8"], J: ["Ausência justificada", "#f2d68c"], F: ["Não compareceu", "#c9cdd3"], "": ["Não votou", "#e3e5e8"] };

// Comissões: integrantes ativos no dia ([id, cargo, de, ate]) e comissões de um parlamentar.
const ativoNoDia = (m, dia) => (!m[2] || m[2] <= dia) && (!m[3] || m[3] >= dia);
function membrosComissao(com, dia) {
  const vistos = new Map();
  for (const m of (com && com.m) || []) if (ativoNoDia(m, dia)) {
    const atual = vistos.get(m[0]);
    if (!atual || pesoCargo(m[1]) > pesoCargo(atual[1])) vistos.set(m[0], m);
  }
  return [...vistos.values()].sort((a, b) => pesoCargo(b[1]) - pesoCargo(a[1]));
}
function pesoCargo(c) {
  c = (c || "").toLowerCase();
  if (c.startsWith("presidente")) return 5;
  if (c.includes("vice-presidente")) return 4;
  if (c.startsWith("relator") || c.startsWith("coordenador")) return 3;
  if (c.startsWith("titular")) return 2;
  if (c.startsWith("suplente")) return 1;
  return 2;
}
function comissoesDe(comissoes, id, dia) {
  const out = [];
  for (const [cod, com] of Object.entries(comissoes || {})) {
    const ms = membrosComissao(com, dia).filter((m) => m[0] === String(id));
    if (ms.length) out.push({ cod, s: com.s, n: com.n, t: com.t, cargo: ms[0][1] });
  }
  return out.sort((a, b) => pesoCargo(b.cargo) - pesoCargo(a.cargo) || a.s.localeCompare(b.s));
}
const CARGO = { 5: ["Presidente", "#0b3d2e"], 4: ["Vice-presidente", "#1f6f50"], 3: ["Relator ou coordenador", "#2e9e5b"],
  2: ["Titular", "#5cbf7f"], 1: ["Suplente", "#b5e0c3"], 0: ["Não integra", "#e3e5e8"] };

if (typeof module !== "undefined") module.exports = { assentos, ordenar, membrosDoDia, corDe, membrosComissao, comissoesDe, pesoCargo };

// ---------------------------------------------------------------- página

if (typeof document !== "undefined") (async () => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const fmt = (d) => d.split("-").reverse().join("/");
  const CASAS = ["senado", "camara"], NOME = { senado: "Senado", camara: "Câmara" };
  const j = (u) => fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const [indice, cadastro, blocos, comissoes] = await Promise.all([j("dados/indice.json"), j("dados/membros.json"), j("dados/blocos.json"), j("dados/comissoes.json")]);
  if (!indice || !cadastro) { $("aviso").hidden = false; $("aviso").textContent = "Dados ainda não publicados. Volte depois da próxima atualização diária."; return; }
  const meses = {};
  const mes = (casa, m) => (meses[casa + m] ??= j(`dados/${casa}-${m}.json`));
  const diasSessao = [...new Set(CASAS.flatMap((c) => Object.keys(indice.dias[c] || {})))].sort();
  const lerHash = () => {
    const p = new URLSearchParams(location.hash.slice(1));
    return { dia: /^\d{4}-\d\d-\d\d$/.test(p.get("d") || "") ? p.get("d") : diasSessao[diasSessao.length - 1] || indice.atualizado,
      cor: ["partido", "bloco", "presenca", "voto", "comissao"].includes(p.get("cor")) ? p.get("cor") : "partido",
      v: { senado: p.get("vs") || "", camara: p.get("vc") || "" }, sel: p.get("p") || "", com: p.get("c") || "" };
  };
  let est = lerHash();
  $("dia").min = diasSessao[0] || ""; $("dia").max = indice.atualizado;
  const blocoDe = (casa) => (partido) => (blocos && blocos[casa] && blocos[casa][partido]) || "";
  const coresBloco = {};
  for (const c of CASAS) { const nomes = [...new Set(Object.values((blocos && blocos[c]) || {}))]; coresBloco[c] = Object.fromEntries(nomes.map((n, i) => [n, PALETA[i % PALETA.length]])); }
  let atual = {};

  function salvar() {
    const h = new URLSearchParams({ d: est.dia, cor: est.cor });
    if (est.v.senado) h.set("vs", est.v.senado); if (est.v.camara) h.set("vc", est.v.camara); if (est.sel) h.set("p", est.sel); if (est.com) h.set("c", est.com);
    history.replaceState(null, "", "#" + h);
  }

  function presencaDe(dados, id) {
    const pr = dados && dados.presenca && dados.presenca[est.dia];
    if (!pr) return "?";
    if (Array.isArray(pr)) return pr.includes(Number(id)) ? "P" : "F";
    return pr[id] || "F";
  }

  function svg(casa, lista, cores, titulo) {
    const virada = casa === "camara";
    const { pontos, raio } = assentos(lista.length, virada);
    const mg = raio + 0.02, vb = `${(-1 - mg).toFixed(3)} ${(virada ? -mg : -1 - mg).toFixed(3)} ${(2 + 2 * mg).toFixed(3)} ${(1 + 2 * mg).toFixed(3)}`;
    const circ = lista.map((m, i) => { const q = pontos[i];
      return `<circle data-casa="${casa}" data-id="${m.id}" cx="${q.x.toFixed(4)}" cy="${q.y.toFixed(4)}" r="${raio.toFixed(4)}" fill="${cores[i]}"${casa + ":" + m.id === est.sel ? ' class="sel"' : ""}><title>${esc(titulo[i])}</title></circle>`; }).join("");
    return `<svg viewBox="${vb}" role="img" aria-label="${NOME[casa]}: ${lista.length} parlamentares">${circ}</svg>`;
  }

  async function desenhar() {
    $("dia").value = est.dia; $("cor").value = est.cor;
    const m = est.dia.slice(0, 7);
    const dados = Object.fromEntries(await Promise.all(CASAS.map(async (c) => [c, await mes(c, m)])));
    atual = dados;
    for (const casa of CASAS) {
      const d = dados[casa], cad = cadastro[casa] || {};
      let membros = membrosDoDia(d, est.dia);
      if (!membros.length) membros = Object.entries(cad).filter(([, x]) => x.a).map(([id, x]) => ({ id, p: x.p }));
      membros = membros.map((x) => ({ ...x, p: x.p || (cad[x.id] || {}).p || "", n: (cad[x.id] || {}).n || x.id }));
      const lista = ordenar(membros, blocoDe(casa));
      const sess = (d && d.sessoes && d.sessoes[est.dia]) || [];
      const pr = d && d.presenca && d.presenca[est.dia];
      const nPres = lista.filter((x) => presencaDe(d, x.id) === "P").length;
      $("e-" + casa).textContent = sess.length
        ? sess.map((s) => s.t + (s.h ? " às " + s.h : "")).join(" · ") + (pr ? ` · ${nPres} presentes de ${lista.length}` : "")
        : "Sem sessão neste dia";
      // Pautas do dia
      const vots = ((d && d.votacoes) || []).filter((v) => v.d === est.dia);
      const sel = $("v-" + casa), rot = sel.parentElement;
      rot.hidden = est.cor !== "voto";
      sel.innerHTML = vots.length ? vots.map((v) => `<option value="${esc(v.id)}">${esc((v.h ? v.h + " · " : "") + (v.titulo || "Votação") + " · " + (v.desc || "").slice(0, 90))}</option>`).join("")
        : "<option value=''>Sem votação nominal neste dia</option>";
      if (!vots.some((v) => v.id === est.v[casa])) est.v[casa] = vots.length ? vots[vots.length - 1].id : "";
      sel.value = est.v[casa];
      const vot = vots.find((v) => v.id === est.v[casa]);
      $("i-" + casa).innerHTML = est.cor === "voto" && vot
        ? `${vot.res ? `<strong>${esc(vot.res)}</strong> · ` : ""}${esc(vot.ementa || vot.desc)} ${vot.prop ? `<a href="${esc(vot.prop)}" target="_blank" rel="noopener">matéria ›</a>` : ""} ${vot.url ? `<a href="${esc(vot.url)}" target="_blank" rel="noopener">sessão ›</a>` : ""}`
        : "";
      // Cores
      let chave, rotulo, cor;
      const [comCasa, comCod] = est.com.split(":");
      const com = est.cor === "comissao" && comCasa === casa && comissoes && (comissoes[casa] || {})[comCod];
      const cargos = com ? Object.fromEntries(membrosComissao(com, est.dia).map((m) => [m[0], pesoCargo(m[1])])) : null;
      if (com) { chave = (x) => cargos[x.id] || 0; rotulo = (k) => CARGO[k][0]; cor = (k) => CARGO[k][1]; }
      else if (est.cor === "presenca") { chave = (x) => presencaDe(d, x.id); rotulo = (k) => PRESENCA[k][0]; cor = (k) => PRESENCA[k][1]; }
      else if (est.cor === "voto") { chave = (x) => (vot ? vot.v[x.id] || "" : ""); rotulo = (k) => VOTO[k][0]; cor = (k) => VOTO[k][1]; }
      else if (est.cor === "bloco") { chave = (x) => blocoDe(casa)(x.p) || x.p + " (sem bloco)"; rotulo = (k) => k; cor = (k) => coresBloco[casa][k] || corDe(k, CORES_PARTIDO); }
      else { chave = (x) => x.p || "Sem partido"; rotulo = (k) => k; cor = (k) => corDe(k, CORES_PARTIDO); }
      const ks = lista.map(chave);
      const cores = ks.map(cor);
      const titulo = lista.map((x, i) => `${x.n} (${x.p}${cad[x.id] ? "-" + cad[x.id].uf : ""}) · ${rotulo(ks[i])}`);
      $("h-" + casa).innerHTML = lista.length ? svg(casa, lista, cores, titulo) : `<p class="vazio">Sem dados de composição.</p>`;
      const cont = {}; ks.forEach((k) => (cont[k] = (cont[k] || 0) + 1));
      $("l-" + casa).innerHTML = Object.entries(cont).sort((a, b) => b[1] - a[1])
        .map(([k, n]) => `<li><i style="background:${cor(k)}"></i>${esc(rotulo(k))} <b>${n}</b></li>`).join("");
    }
    discursosDoDia(); comissoesDoDia(); detalhe(); salvar();
  }

  const reunioesDoDia = (casa) => (atual[casa] && atual[casa].reunioes && atual[casa].reunioes[est.dia]) || [];
  const presReuniao = (casa, ev) => (atual[casa] && atual[casa].presencaReuniao && atual[casa].presencaReuniao[ev]) || null;
  const nomeCom = (casa, cod) => ((comissoes && comissoes[casa]) || {})[cod];
  const link = (u, t = "ver ›") => (u ? ` <a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>` : "");
  const realizada = (sit) => !/cancel|adiad|suspens|n[aã]o realizada/i.test(sit || "");

  function comissoesDoDia() {
    const box = $("comissoes");
    if (!comissoes) { box.innerHTML = `<p class="dica">Dados de comissões ainda não publicados.</p>`; return; }
    const [comCasa, comCod] = est.com.split(":");
    box.innerHTML = `<div class="congresso">${CASAS.map((casa) => {
      const rs = reunioesDoDia(casa);
      const ops = Object.entries(comissoes[casa] || {}).filter(([, c]) => membrosComissao(c, est.dia).length)
        .sort((a, b) => a[1].s.localeCompare(b[1].s));
      const temReuniao = new Set(rs.map((r) => r[0]));
      const escolhida = comCasa === casa && (comissoes[casa] || {})[comCod];
      const cad = cadastro[casa] || {};
      return `<div><h3>${NOME[casa]}</h3>
        <p class="dica">${rs.length ? `${rs.length} reunião(ões) de comissão em ${fmt(est.dia)}:` : `Nenhuma reunião de comissão publicada em ${fmt(est.dia)}.`}</p>
        <ul>${rs.map((r) => { const c = nomeCom(casa, r[0]) || {}; const pr = presReuniao(casa, r[5]);
          return `<li><a href="#" class="com" data-com="${casa}:${esc(r[0])}">${esc(c.s || r[0])}</a> ${esc(c.n || "")} <span class="dica">· ${esc(r[1])}${r[2] ? " às " + esc(r[2]) : ""} · ${esc(r[3])}${pr ? ` · ${pr.length} presentes` : ""}</span>${link(r[4])}</li>`; }).join("")}</ul>
        <label class="pauta">Integrantes da comissão<select data-casa="${casa}" class="escolhe-com"><option value="">Escolha uma comissão…</option>
          ${ops.map(([cod, c]) => `<option value="${esc(cod)}"${escolhida && cod === comCod ? " selected" : ""}>${temReuniao.has(cod) ? "● " : ""}${esc(c.s)} · ${esc(c.n.slice(0, 70))}</option>`).join("")}</select></label>
        ${escolhida ? `<p class="dica">${esc(escolhida.n)}${escolhida.t ? " · " + esc(escolhida.t) : ""}. As bolinhas do ${NOME[casa]} mostram os integrantes.</p>
          <ul class="integrantes">${membrosComissao(escolhida, est.dia).map((m) => { const x = cad[m[0]] || {};
            return `<li><a href="#" class="quem" data-casa="${casa}" data-id="${esc(m[0])}">${esc(x.n || m[0])}</a> <span class="dica">${esc(x.p || "")}${x.uf ? "-" + esc(x.uf) : ""} · ${esc(m[1])}</span></li>`; }).join("")}</ul>` : ""}
      </div>`; }).join("")}</div>`;
  }

  function escolherComissao(valor) {
    est.com = valor; est.cor = valor ? "comissao" : (est.cor === "comissao" ? "partido" : est.cor);
    desenhar();
  }

  function discursosDoDia() {
    const [selCasa, selId] = est.sel.split(":");
    const linha = (casa, x, dia) => { const c = (cadastro[casa] || {})[x.id] || {};
      return `<li>${dia ? `<strong>${fmt(dia)}</strong> · ` : ""}<a href="#" data-casa="${casa}" data-id="${x.id}" class="quem">${esc(c.n || x.id)}</a> <span class="dica">${esc(c.p || "")}${c.uf ? "-" + esc(c.uf) : ""} · ${esc(x.t)}</span> ${esc(x.r)} ${x.u ? `<a href="${esc(x.u)}" target="_blank" rel="noopener">ver ›</a>` : ""}</li>`; };
    $("t-discursos").textContent = "Discursos do dia";
    if (selId && (cadastro[selCasa] || {})[selId]) {
      // Parlamentar selecionado: só os discursos dele (no dia e no resto do mês).
      const nome = cadastro[selCasa][selId].n;
      const todos = Object.entries((atual[selCasa] && atual[selCasa].discursos) || {}).sort()
        .flatMap(([dia, ds]) => ds.filter((x) => String(x.id) === selId).map((x) => [dia, x]));
      const hoje = todos.filter(([dia]) => dia === est.dia), outros = todos.filter(([dia]) => dia !== est.dia);
      $("t-discursos").textContent = `Discursos de ${nome}`;
      $("discursos").innerHTML = `<p class="dica"><a href="#" id="todos-discursos">Ver os discursos de todos em ${fmt(est.dia)} ›</a></p>
        ${hoje.length ? `<ul>${hoje.map(([, x]) => linha(selCasa, x)).join("")}</ul>` : `<p class="dica">Nenhum discurso de ${esc(nome)} publicado em ${fmt(est.dia)}.</p>`}
        ${outros.length ? `<h3>Outros discursos no mês (${outros.length})</h3><ul>${outros.map(([dia, x]) => linha(selCasa, x, dia)).join("")}</ul>` : ""}`;
      return;
    }
    const partes = CASAS.map((casa) => {
      const ds = (atual[casa] && atual[casa].discursos && atual[casa].discursos[est.dia]) || [];
      if (!ds.length) return `<h3>${NOME[casa]}</h3><p class="dica">Nenhum discurso publicado para ${fmt(est.dia)}.</p>`;
      const cad = cadastro[casa] || {};
      return `<h3>${NOME[casa]} (${ds.length})</h3><ul>${ds.map((x) => { const c = cad[x.id] || {};
        return `<li><a href="#" data-casa="${casa}" data-id="${x.id}" class="quem">${esc(c.n || x.id)}</a> <span class="dica">${esc(c.p || "")}${c.uf ? "-" + esc(c.uf) : ""} · ${esc(x.t)}</span> ${esc(x.r)} ${x.u ? `<a href="${esc(x.u)}" target="_blank" rel="noopener">ver ›</a>` : ""}</li>`; }).join("")}</ul>`;
    }).join("");
    $("discursos").innerHTML = partes + `<p class="dica">No Senado, o resumo e o texto do discurso saem cerca de três semanas depois; até lá aparece quem usou a palavra, com o vídeo da sessão.</p>`;
  }

  function detalhe() {
    const box = $("detalhe");
    const [casa, id] = est.sel.split(":");
    const c = casa && (cadastro[casa] || {})[id];
    if (!c) { box.hidden = true; return; }
    const d = atual[casa];
    const pres = presencaDe(d, id);
    const vots = ((d && d.votacoes) || []).filter((v) => v.d === est.dia && v.v[id] !== undefined);
    const disc = ((d && d.discursos && d.discursos[est.dia]) || []).filter((x) => String(x.id) === id);
    const m = d && d.membros && d.membros[id];
    const emendas = c.e ? `<a class="botao2" href="../painel/#${new URLSearchParams({ "f.autor": c.e })}">Emendas de ${esc(c.n)} ›</a>` : `<span class="dica">Sem emendas com este nome no Portal da Transparência.</span>`;
    box.hidden = false;
    box.innerHTML = `<div class="pessoa"><img src="${esc(c.f)}" alt="" loading="lazy" onerror="this.remove()">
      <div><h2>${esc(c.n)} <span class="dica">${esc((m && m[2]) || c.p)}-${esc(c.uf)} · ${casa === "camara" ? "Deputado(a) federal" : "Senador(a)"}</span></h2>
      <p>${fmt(est.dia)}: <strong>${PRESENCA[pres][0]}</strong>${pres === "?" && d && d.sessoes && d.sessoes[est.dia] ? " (sem registro publicado)" : ""}</p>
      <p>${emendas} <a class="botao2" href="${esc(c.u)}" target="_blank" rel="noopener">Perfil oficial ›</a></p></div></div>
      ${vots.length ? `<h3>Votos no dia</h3><ul>${vots.map((v) => `<li><strong>${VOTO[v.v[id]] ? VOTO[v.v[id]][0] : esc(v.v[id])}</strong> · ${esc(v.titulo)} · ${esc((v.desc || "").slice(0, 160))}</li>`).join("")}</ul>` : ""}
      ${(() => { const cs = comissoesDe((comissoes || {})[casa], id, est.dia); if (!cs.length) return "";
        const rs = reunioesDoDia(casa);
        return `<h3>Comissões (${cs.length})</h3><ul>${cs.map((c) => { const r = rs.filter((x) => x[0] === c.cod);
          const info = r.map((x) => { const pr = presReuniao(casa, x[5]);
            const st = pr ? (pr.includes(Number(id)) ? " · presente" : realizada(x[3]) ? " · sem registro de presença" : "") : "";
            return `reunião: ${esc(x[1])}${x[2] ? " às " + esc(x[2]) : ""} (${esc(x[3])})${st}${link(x[4])}`; }).join("; ");
          return `<li><a href="#" class="com" data-com="${casa}:${esc(c.cod)}">${esc(c.s)}</a> ${esc(c.n)} <span class="dica">· ${esc(c.cargo)}</span>${info ? `<br><span class="reuniao">${info}</span>` : ""}</li>`; }).join("")}</ul>
          <p class="dica">${rs.length ? "" : `Nenhuma reunião de comissão publicada em ${fmt(est.dia)}.`}</p>`; })()}
      ${disc.length ? `<h3>Discursos no dia</h3><ul>${disc.map((x) => `<li>${esc(x.t)} · ${esc(x.r)} ${x.u ? `<a href="${esc(x.u)}" target="_blank" rel="noopener">ver ›</a>` : ""}</li>`).join("")}</ul>` : ""}`;
  }

  function pular(dir) {
    const i = diasSessao.findIndex((d) => (dir > 0 ? d > est.dia : false));
    const alvo = dir > 0 ? (i >= 0 ? diasSessao[i] : null) : [...diasSessao].reverse().find((d) => d < est.dia);
    if (alvo) { est.dia = alvo; desenhar(); }
  }

  $("dia").addEventListener("change", (e) => { if (e.target.value) { est.dia = e.target.value; desenhar(); } });
  $("ant").addEventListener("click", () => pular(-1));
  $("prox").addEventListener("click", () => pular(1));
  $("cor").addEventListener("change", (e) => { est.cor = e.target.value; desenhar(); });
  for (const c of CASAS) $("v-" + c).addEventListener("change", (e) => { est.v[c] = e.target.value; desenhar(); });
  document.addEventListener("change", (e) => {
    if (e.target.matches("select.escolhe-com")) escolherComissao(e.target.value ? e.target.dataset.casa + ":" + e.target.value : "");
  });
  document.addEventListener("click", (e) => {
    if (e.target.id === "todos-discursos") { e.preventDefault(); est.sel = ""; document.querySelectorAll("circle.sel").forEach((x) => x.classList.remove("sel")); detalhe(); discursosDoDia(); salvar(); return; }
    const c = e.target.closest("a.com");
    if (c) { e.preventDefault(); escolherComissao(c.dataset.com); $("c-comissoes").scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    const t = e.target.closest("circle[data-id], a.quem");
    if (!t) return;
    e.preventDefault();
    est.sel = t.dataset.casa + ":" + t.dataset.id;
    document.querySelectorAll("circle.sel").forEach((x) => x.classList.remove("sel"));
    document.querySelectorAll(`circle[data-casa="${t.dataset.casa}"][data-id="${t.dataset.id}"]`).forEach((x) => x.classList.add("sel"));
    detalhe(); discursosDoDia(); salvar();
    if (t.tagName === "A") $("detalhe").scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  window.addEventListener("hashchange", () => { est = lerHash(); desenhar(); });
  desenhar();
})();

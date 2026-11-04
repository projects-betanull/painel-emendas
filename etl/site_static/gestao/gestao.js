// Página de gestão: vendas (via /api/gestao, protegida por chave), execuções do ETL e qualidade.
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const num = (v) => (v == null ? "–" : Number(v).toLocaleString("pt-BR"));
const data = (v) => (v ? new Date(v).toLocaleString("pt-BR") : "–");
const tab = (cab, linhas) => `<table><thead><tr>${cab.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${linhas.map((l) => `<tr>${l.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${cab.length}">Nada ainda.</td></tr>`}</tbody></table>`;

async function carregar(chave) {
  const r = await fetch("/api/gestao", { headers: { "x-admin-key": chave } });
  if (r.status === 401) { alert("Chave inválida."); sessionStorage.removeItem("chave"); return; }
  const g = await r.json();
  sessionStorage.setItem("chave", chave);
  $("entrar").hidden = true; $("painel").hidden = false;
  const pags = g.pagamentos || [];
  const mcp = pags.filter((p) => /painel-emendas/.test(p.memo) && p.sats > 0);
  $("kpis").innerHTML = [["Saldo (sats)", num(g.saldo_sats)], ["Passes MCP vendidos", num(mcp.length)], ["Receita MCP (sats)", num(mcp.reduce((a, p) => a + Number(p.sats || 0), 0))], ["Preço do passe", num(g.configurado?.preco_sats) + " sats"]]
    .map(([t, v]) => `<div class="kpi"><span>${t}</span><strong>${v}</strong></div>`).join("");
  $("vendas").innerHTML = g.configurado?.coinos ? tab(["Quando", "Sats", "Descrição", "Tipo"], pags.map((p) => [data(p.quando), num(p.sats), esc(p.memo), esc(p.tipo)]))
    : "<p>Coinos não configurado: cadastre o segredo COINOS_TOKEN no GitHub.</p>";

  try {
    const runs = (await (await fetch("https://api.github.com/repos/projects-betanull/painel-emendas/actions/runs?per_page=15")).json()).workflow_runs || [];
    $("etl").innerHTML = tab(["Início", "Resultado", "Duração", ""], runs.map((x) => [data(x.run_started_at), x.conclusion === "success" ? "✓ ok" : esc(x.conclusion || x.status),
      Math.round((new Date(x.updated_at) - new Date(x.run_started_at)) / 60000) + " min", `<a href="${esc(x.html_url)}">ver</a>`]));
  } catch (e) { $("etl").textContent = "Não foi possível consultar o GitHub."; }

  try {
    const q = await (await fetch("../api/qualidade.json")).json(), f = q.favorecidos || {};
    $("qual").innerHTML = tab(["Indicador", "Valor"], [["Emendas (linhas)", num(q.linhas)], ["Pagamentos a favorecidos", num(f.linhas)], ["Valor recebido total (R$)", num(Math.round(f.valor_recebido_total || 0))],
      ["Ligado a um município", (f.pct_valor_recebido_com_municipio ?? "–") + "%"], ["Municípios", num(f.municipios_distintos)], ["Anos", esc((q.anos || []).join(", "))]]);
  } catch (e) { $("qual").textContent = "Relatório indisponível."; }
}

$("entrar").addEventListener("submit", (ev) => { ev.preventDefault(); carregar($("chave").value); });
const salva = sessionStorage.getItem("chave");
if (salva) carregar(salva);

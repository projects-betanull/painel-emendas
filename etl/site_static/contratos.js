// Carrega os contratos da prefeitura (PNCP) na página do município.
(async function () {
  const sec = document.getElementById("contratos");
  if (!sec || !sec.dataset.cnpj) return;
  sec.hidden = false;
  const alvo = sec.querySelector(".conteudo");
  const brl = (v) => "R$ " + Math.round(v).toLocaleString("pt-BR");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  try {
    const d = await (await fetch("/api/contratos?cnpj=" + sec.dataset.cnpj)).json();
    if (d.erro) throw new Error(d.erro);
    if (!d.total_contratos) { alvo.innerHTML = "<p>Nenhum contrato publicado no PNCP nos últimos 12 meses. Municípios de até 20 mil habitantes ainda estão no prazo de adesão.</p>"; return; }
    alvo.innerHTML = `<p><strong>${d.total_contratos.toLocaleString("pt-BR")} contratos</strong> somando <strong>${brl(d.valor_total)}</strong>.</p>
      <div class="tabela"><table><thead><tr><th>Fornecedor</th><th>CNPJ</th><th class="n">Contratos</th><th class="n">Valor</th></tr></thead><tbody>
      ${d.fornecedores.map((f) => `<tr><td>${esc(f.fornecedor)}</td><td>${esc(f.cnpj)}</td><td class="n">${f.contratos}</td><td class="n">${brl(f.valor)}</td></tr>`).join("")}</tbody></table></div>
      <details><summary>Contratos mais recentes</summary><ul class="recentes">${d.recentes.map((c) => `<li>${esc(c.data)} · ${esc(c.fornecedor)} · ${brl(c.valor)}<br><span>${esc(c.objeto)}</span>${c.link ? ` <a href="${esc(c.link)}">ver no PNCP</a>` : ""}</li>`).join("")}</ul></details>
      ${d.omitidos_pessoa_fisica ? `<p class="dica">${d.omitidos_pessoa_fisica} contrato(s) com pessoa física omitido(s).</p>` : ""}`;
  } catch (e) { alvo.innerHTML = '<p class="dica">O PNCP não respondeu agora. Tente mais tarde.</p>'; }
})();

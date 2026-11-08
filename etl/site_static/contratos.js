// Carrega os contratos da prefeitura (PNCP) na página do município.
// O PNCP é lento (15–40 s por consulta); a busca só começa quando a seção chega perto da tela,
// mostra quanto tempo já passou e oferece "Tentar de novo" se falhar.
(function () {
  const sec = document.getElementById("contratos");
  if (!sec || !sec.dataset.cnpj) return;
  sec.hidden = false;
  const alvo = sec.querySelector(".conteudo");
  const brl = (v) => "R$ " + Math.round(v).toLocaleString("pt-BR");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function mostrar(d) {
    if (!d.total_contratos) { alvo.innerHTML = "<p>Nenhum contrato publicado no PNCP nos últimos 12 meses. Municípios de até 20 mil habitantes ainda estão no prazo de adesão.</p>"; return; }
    alvo.innerHTML = `<p><strong>${d.total_contratos.toLocaleString("pt-BR")} contratos</strong> somando <strong>${brl(d.valor_total)}</strong>.</p>
      <div class="tabela"><table><thead><tr><th>Fornecedor</th><th>CNPJ</th><th class="n">Contratos</th><th class="n">Valor</th></tr></thead><tbody>
      ${d.fornecedores.map((f) => `<tr><td>${esc(f.fornecedor)}</td><td>${esc(f.cnpj)}</td><td class="n">${f.contratos}</td><td class="n">${brl(f.valor)}</td></tr>`).join("")}</tbody></table></div>
      <details><summary>Contratos mais recentes</summary><ul class="recentes">${d.recentes.map((c) => `<li>${esc(c.data)} · ${esc(c.fornecedor)} · ${brl(c.valor)}<br><span>${esc(c.objeto)}</span>${c.link ? ` <a href="${esc(c.link)}">ver no PNCP</a>` : ""}</li>`).join("")}</ul></details>
      ${d.parcial ? `<p class="dica">Lista incompleta: o PNCP não entregou todas as páginas agora. Volte mais tarde para ver o total.</p>` : ""}
      ${d.omitidos_pessoa_fisica ? `<p class="dica">${d.omitidos_pessoa_fisica} contrato(s) com pessoa física omitido(s).</p>` : ""}
      ${d.atualizado_em ? `<p class="dica">Consulta ao PNCP em ${new Date(d.atualizado_em).toLocaleDateString("pt-BR")}.</p>` : ""}`;
  }

  async function carregar() {
    const t0 = Date.now();
    const tique = () => { alvo.innerHTML = `<p>Consultando o PNCP… ${Math.round((Date.now() - t0) / 1000)} s</p><p class="dica">O sistema do governo costuma levar de 20 a 60 segundos na primeira consulta do dia. Depois fica guardado e abre na hora.</p>`; };
    tique();
    const relogio = setInterval(tique, 1000);
    try {
      const r = await fetch("/api/contratos?cnpj=" + sec.dataset.cnpj, { signal: AbortSignal.timeout ? AbortSignal.timeout(150000) : undefined });
      const d = await r.json();
      if (d.erro) throw new Error(d.erro);
      clearInterval(relogio);
      mostrar(d);
    } catch (e) {
      clearInterval(relogio);
      alvo.innerHTML = '<p class="dica">O PNCP não respondeu a tempo. <button type="button" class="botao2">Tentar de novo</button></p>';
      alvo.querySelector("button").onclick = carregar;
    }
  }

  if ("IntersectionObserver" in window) {
    const ob = new IntersectionObserver((es) => { if (es.some((x) => x.isIntersecting)) { ob.disconnect(); carregar(); } }, { rootMargin: "600px" });
    ob.observe(sec);
  } else carregar();
})();

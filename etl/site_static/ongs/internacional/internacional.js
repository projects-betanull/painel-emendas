// Lista de projetos IATI no Brasil: nome da organização como o doador escreveu, sem ligação com CNPJ.
(function () {
  const q = document.getElementById("q"), res = document.getElementById("res"), contagem = document.getElementById("contagem");
  if (!q) return;
  const sem = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  let linhas = [];
  // [doador, projeto, ano início, ano fim, organização (como declarada), papel, valor, moeda, id IATI]
  fetch("projetos.json").then((r) => r.json()).then((d) => {
    linhas = d.map((l) => ({ l, k: sem(l[0] + " " + l[1] + " " + l[4]) }));
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.get("q")) q.value = p.get("q");
    mostrar();
  });
  function mostrar() {
    const t = sem(q.value.trim());
    history.replaceState(null, "", t ? "#" + new URLSearchParams({ q: q.value.trim() }) : location.pathname);
    const achados = linhas.filter((x) => !t || x.k.includes(t));
    contagem.textContent = achados.length.toLocaleString("pt-BR") + " citações" + (achados.length > 200 ? ". Mostrando as 200 de maior valor declarado." : ".");
    res.innerHTML = '<div class="tabela"><table><thead><tr><th>Doador</th><th>Projeto</th><th>Anos</th><th>Organização (como o doador escreveu)</th><th>Papel</th><th class="n">Valor declarado</th></tr></thead><tbody>' +
      achados.slice(0, 200).map(({ l }) => "<tr><td>" + esc(l[0]) + '</td><td><a href="https://d-portal.org/ctrack.html#view=act&aid=' + encodeURIComponent(l[8]) + '">' + esc(l[1]) +
        "</a></td><td>" + esc(l[2]) + (l[3] && l[3] !== l[2] ? "–" + esc(l[3]) : "") + "</td><td>" + esc(l[4]) + "</td><td>" + esc(l[5]) +
        '</td><td class="n">' + (l[6] ? Number(l[6]).toLocaleString("pt-BR") + " " + esc(l[7]) : "—") + "</td></tr>").join("") + "</tbody></table></div>";
  }
  let tm;
  q.addEventListener("input", () => { clearTimeout(tm); tm = setTimeout(mostrar, 200); });
})();

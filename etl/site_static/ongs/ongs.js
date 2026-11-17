// Busca de ONGs: destaques nacionais (quem recebeu dinheiro) ou todas as OSCs de um estado, filtradas no navegador.
(function () {
  const q = document.getElementById("q"), ufSel = document.getElementById("uf"), filtro = document.getElementById("filtro");
  const lista = document.getElementById("res"), contagem = document.getElementById("contagem");
  if (!q) return;
  const sem = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const brl = (v) => v >= 1e9 ? "R$ " + (v / 1e9).toFixed(1).replace(".", ",") + " bi"
    : v >= 1e6 ? "R$ " + (v / 1e6).toFixed(1).replace(".", ",") + " mi"
    : v > 0 ? "R$ " + Math.round(v).toLocaleString("pt-BR") : "";
  const SELOS = [[1, "emendas"], [2, "convênios"], [16, "estrangeira"], [8, "CEPIM", true], [32, "inativa"]];
  const cache = {};

  async function carregar(uf) {
    const chave = uf || "BR";
    if (!cache[chave]) {
      const r = await fetch(uf ? "l/" + uf + ".json" : "destaques.json");
      const linhas = await r.json();
      // Destaques: [cnpj8, nome, uf, município, bits, valor]; por UF: [cnpj8, nome, município, bits, valor].
      cache[chave] = linhas.map((l) => uf
        ? { c: l[0], n: l[1], u: uf, m: l[2], b: l[3], v: l[4] }
        : { c: l[0], n: l[1], u: l[2], m: l[3], b: l[4], v: l[5] });
      for (const o of cache[chave]) o.k = sem(o.n + " " + o.m);
    }
    return cache[chave];
  }

  async function buscar() {
    const uf = ufSel.value, bit = +filtro.value, termo = sem(q.value.trim()), dig = q.value.replace(/\D/g, "");
    history.replaceState(null, "", "#" + new URLSearchParams({ uf, f: bit || "", q: q.value.trim() }).toString());
    contagem.textContent = "Carregando…";
    const todos = await carregar(uf);
    const achados = todos.filter((o) => (!bit || (o.b & bit)) &&
      (!termo || (dig.length >= 3 && o.c.startsWith(dig.slice(0, 8))) || o.k.includes(termo)));
    contagem.textContent = achados.length.toLocaleString("pt-BR") + (achados.length === 1 ? " organização" : " organizações") +
      (uf ? " em " + ufSel.selectedOptions[0].textContent.replace(" (todas)", "") : " com dinheiro federal, impedimento ou sede no exterior") +
      (achados.length > 60 ? ". Mostrando as 60 primeiras; refine a busca." : ".");
    lista.textContent = "";
    for (const o of achados.slice(0, 60)) {
      const li = document.createElement("li"), a = document.createElement("a");
      a.href = "o/?c=" + o.c;
      const nome = document.createElement("span"); nome.className = "nome-ong";
      nome.textContent = o.n + " · " + o.m + " (" + o.u + ")";
      const lado = document.createElement("span"); lado.className = "selos";
      for (const [b, t, alerta] of SELOS) if (o.b & b) { const s = document.createElement("i"); s.className = "selo" + (alerta ? " alerta" : ""); s.textContent = t; lado.append(s); }
      if (o.v) lado.append(" " + brl(o.v));
      a.append(nome, lado); li.append(a); lista.append(li);
    }
  }

  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get("uf")) ufSel.value = p.get("uf");
  if (p.get("f")) filtro.value = p.get("f");
  if (p.get("q")) q.value = p.get("q");
  let t;
  q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(buscar, 200); });
  ufSel.addEventListener("change", buscar);
  filtro.addEventListener("change", buscar);
  document.querySelectorAll("a[data-uf]").forEach((a) => a.addEventListener("click", (ev) => {
    ev.preventDefault(); ufSel.value = a.dataset.uf; q.value = ""; buscar(); q.scrollIntoView({ behavior: "smooth" });
  }));
  buscar();
})();

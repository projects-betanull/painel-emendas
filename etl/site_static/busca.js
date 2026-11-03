// Busca de municípios na página inicial: carrega busca.json (pequeno) e filtra no navegador.
(function () {
  const campo = document.getElementById("q");
  const lista = document.getElementById("res");
  if (!campo || !lista) return;

  const sem = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const brl = (v) =>
    v >= 1e9 ? "R$ " + (v / 1e9).toFixed(1).replace(".", ",") + " bi"
    : v >= 1e6 ? "R$ " + (v / 1e6).toFixed(1).replace(".", ",") + " mi"
    : "R$ " + Math.round(v).toLocaleString("pt-BR");

  let dados = null;
  async function carregar() {
    if (!dados) {
      const r = await fetch("busca.json");
      dados = (await r.json()).map((m) => ({ ...m, k: sem(m.n) }));
    }
    return dados;
  }

  campo.addEventListener("focus", carregar, { once: true });
  campo.addEventListener("input", async () => {
    const termo = sem(campo.value.trim());
    lista.textContent = "";
    if (termo.length < 2) return;
    const todos = await carregar();
    const achados = todos
      .filter((m) => m.k.includes(termo))
      .sort((a, b) => (a.k.startsWith(termo) ? 0 : 1) - (b.k.startsWith(termo) ? 0 : 1) || b.v - a.v)
      .slice(0, 8);
    for (const m of achados) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = m.p;
      a.textContent = m.n + " (" + m.u + ")";
      const s = document.createElement("span");
      s.textContent = brl(m.v);
      a.appendChild(s);
      li.appendChild(a);
      lista.appendChild(li);
    }
    if (!achados.length) {
      const li = document.createElement("li");
      li.textContent = "Nenhum município encontrado.";
      lista.appendChild(li);
    }
  });
})();

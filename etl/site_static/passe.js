// Passe de 24 h no navegador: compra por Pix (checkout da Kiwify) ou Lightning (QR), conferência automática e token guardado.
// O mesmo token vale no MCP e no site. Uso: Passe.valido(), Passe.exigir(acao).
(function () {
  const CHAVE = "passeEmendas";
  const ler = () => { try { return JSON.parse(localStorage.getItem(CHAVE) || "null"); } catch (e) { return null; } };
  const valido = () => { const p = ler(); return !!(p && p.exp > Date.now()); };
  const guardar = (token, exp) => { try { localStorage.setItem(CHAVE, JSON.stringify({ token, exp })); } catch (e) {} };
  // Tokens do MCP (exp.id.assinatura) também valem aqui.
  const deToken = (t) => { const exp = Number(String(t).split(".")[0]); return exp > Date.now() ? exp : 0; };

  function qr(texto) {
    if (!window.qrcode) return "";
    const q = window.qrcode(0, "L"); q.addData(texto.toUpperCase()); q.make();
    return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }

  let janela;
  function fechar() { if (janela) janela.remove(); janela = null; }

  const brl = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  function liberar(d, corpo, depois) {
    guardar(d.token, d.exp);
    corpo.innerHTML = "<p><strong>Pago ✓</strong> Passe liberado por 24 horas.</p>";
    setTimeout(() => { fechar(); depois && depois(); }, 1200);
  }

  async function comprar(depois) {
    fechar();
    const minha = (janela = document.createElement("div"));
    janela.className = "passe-fundo";
    janela.innerHTML = `<div class="passe" role="dialog" aria-modal="true" aria-labelledby="passe-t">
      <button type="button" class="passe-x" aria-label="Fechar">✕</button>
      <h2 id="passe-t">Passe de 24 horas</h2>
      <p>Libera a tabela completa e o CSV no Explorar e o relatório em PDF dos municípios. Sem cadastro no site.</p>
      <div class="passe-abas" role="tablist" hidden>
        <button type="button" role="tab" class="passe-aba" data-aba="pix" aria-selected="true">Pix</button>
        <button type="button" role="tab" class="passe-aba" data-aba="ln" aria-selected="false">Lightning ⚡</button>
      </div>
      <div class="passe-corpo"><p>Carregando…</p></div>
      <details><summary>Já tenho um token</summary><input class="passe-tk" placeholder="Cole o token"><button type="button" class="passe-usar">Usar</button></details>
    </div>`;
    document.body.appendChild(janela);
    janela.querySelector(".passe-x").onclick = fechar;
    janela.addEventListener("click", (e) => { if (e.target === janela) fechar(); });
    janela.querySelector(".passe-usar").onclick = () => {
      const t = janela.querySelector(".passe-tk").value.trim(), exp = deToken(t);
      if (!exp) { janela.querySelector(".passe-tk").value = "Token inválido ou vencido"; return; }
      guardar(t, exp); fechar(); depois && depois();
    };
    const corpo = janela.querySelector(".passe-corpo");
    let aba = 0; // muda a cada troca de aba; laços de conferência antigos param sozinhos
    const viva = (n) => janela === minha && aba === n;
    const abrir = (qual) => {
      const n = ++aba;
      janela.querySelectorAll(".passe-aba").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.aba === qual)));
      return qual === "pix" ? pix(n) : lightning(n);
    };
    janela.querySelectorAll(".passe-aba").forEach((b) => (b.onclick = () => abrir(b.dataset.aba)));

    // Pix (checkout da Kiwify): se não estiver configurado no servidor, mostra só Lightning.
    let compraPix = null;
    try {
      const r = await fetch("/api/passe-pix", { method: "POST" });
      if (r.ok) compraPix = await r.json();
    } catch (e) {}
    if (janela !== minha) return;
    if (compraPix && compraPix.checkout) { janela.querySelector(".passe-abas").hidden = false; abrir("pix"); }
    else abrir("ln");

    async function pix(n) {
      const f = compraPix;
      corpo.innerHTML = `${f.reais ? `<p><strong>${brl(f.reais)}</strong></p>` : ""}
        <p><a class="botao passe-pagar" href="${f.checkout}" target="_blank" rel="noopener">Pagar com Pix</a></p>
        <p class="dica">Abre o pagamento seguro da Kiwify em outra aba. Pague o Pix e volte para esta página: o passe libera sozinho.
        Mantenha esta janela aberta até confirmar.</p>
        <p class="dica passe-status">Aguardando o pagamento…</p>`;
      const ini = Date.now();
      while (Date.now() - ini < 45 * 60e3) {
        await espera(5000);
        if (!viva(n)) return;
        if (document.hidden) continue;
        try {
          const r = await fetch("/api/passe-pix?ref=" + encodeURIComponent(f.ref));
          if (!viva(n)) return;
          if (r.ok) return liberar(await r.json(), corpo, depois);
        } catch (e) {}
      }
      if (viva(n)) corpo.querySelector(".passe-status").textContent = "Não encontramos o pagamento. Se já pagou, feche, abra de novo e cole o token ou fale conosco.";
    }

    async function lightning(n) {
      corpo.innerHTML = "<p>Gerando a fatura…</p>";
      let f;
      try {
        const r = await fetch("/api/passe", { method: "POST" }); f = await r.json();
        if (!f.fatura) throw new Error(f.erro);
      } catch (e) { if (viva(n)) corpo.innerHTML = "<p>Não foi possível gerar a fatura agora. Tente de novo em instantes.</p>"; return; }
      if (!viva(n)) return;
      const reais = f.reais ? ` <span class="dica">≈ ${brl(f.reais)}</span>` : "";
      corpo.innerHTML = `<p><strong>${f.preco.toLocaleString("pt-BR")} sats</strong>${reais}</p>
        <a class="passe-qr" href="lightning:${f.fatura}">${qr(f.fatura)}</a>
        <p><a class="botao" href="lightning:${f.fatura}">Abrir na carteira</a> <button type="button" class="botao2 passe-copiar">Copiar fatura</button></p>
        <p class="dica passe-status">Aguardando o pagamento…</p>
        <details class="dica"><summary>Não tenho carteira Lightning</summary>Instale uma carteira Lightning gratuita no celular
        ou abra uma conta pelo navegador em <a href="https://coinos.io/" rel="noopener">coinos.io</a>, coloque alguns reais em bitcoin
        e aponte a câmera para o QR code. O passe libera sozinho assim que o pagamento chega.</details>`;
      corpo.querySelector(".passe-copiar").onclick = async (e) => { try { await navigator.clipboard.writeText(f.fatura); e.target.textContent = "Copiada ✓"; } catch (x) {} };
      const ini = Date.now();
      while (Date.now() - ini < 15 * 60e3) {
        await espera(3000);
        if (!viva(n)) return;
        try {
          const r = await fetch("/api/passe?fatura=" + encodeURIComponent(f.fatura));
          if (!viva(n)) return;
          if (r.ok) return liberar(await r.json(), corpo, depois);
        } catch (e) {}
      }
      if (viva(n)) corpo.querySelector(".passe-status").textContent = "A fatura expirou. Feche e gere outra.";
    }
  }

  window.Passe = {
    valido,
    token: () => (valido() ? ler().token : null),
    validade: () => (valido() ? new Date(ler().exp) : null),
    exigir: (acao) => (valido() ? acao() : comprar(acao)),
  };
})();

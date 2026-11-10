// Passe de 24 h no navegador: compra por Lightning (QR), conferência automática e token guardado.
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

  async function comprar(depois) {
    fechar();
    janela = document.createElement("div");
    janela.className = "passe-fundo";
    janela.innerHTML = `<div class="passe" role="dialog" aria-modal="true" aria-labelledby="passe-t">
      <button type="button" class="passe-x" aria-label="Fechar">✕</button>
      <h2 id="passe-t">Passe de 24 horas ⚡</h2>
      <p>Libera a tabela completa e o CSV no Explorar e o relatório em PDF dos municípios. Sem cadastro: pague com qualquer carteira Lightning.</p>
      <div class="passe-corpo"><p>Gerando a fatura…</p></div>
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
    let f;
    try {
      const r = await fetch("/api/passe", { method: "POST" }); f = await r.json();
      if (!f.fatura) throw new Error(f.erro);
    } catch (e) { corpo.innerHTML = "<p>Não foi possível gerar a fatura agora. Tente de novo em instantes.</p>"; return; }
    corpo.innerHTML = `<p><strong>${f.preco.toLocaleString("pt-BR")} sats</strong></p>
      <a class="passe-qr" href="lightning:${f.fatura}">${qr(f.fatura)}</a>
      <p><a class="botao" href="lightning:${f.fatura}">Abrir na carteira</a> <button type="button" class="botao2 passe-copiar">Copiar fatura</button></p>
      <p class="dica passe-status">Aguardando o pagamento…</p>`;
    corpo.querySelector(".passe-copiar").onclick = async (e) => { try { await navigator.clipboard.writeText(f.fatura); e.target.textContent = "Copiada ✓"; } catch (x) {} };
    const ini = Date.now();
    while (janela && Date.now() - ini < 15 * 60e3) {
      await new Promise((r) => setTimeout(r, 3000));
      if (!janela) return;
      try {
        const r = await fetch("/api/passe?fatura=" + encodeURIComponent(f.fatura));
        if (r.ok) { const d = await r.json(); guardar(d.token, d.exp); corpo.innerHTML = "<p><strong>Pago ✓</strong> Passe liberado por 24 horas.</p>"; setTimeout(() => { fechar(); depois && depois(); }, 1200); return; }
      } catch (e) {}
    }
    if (janela) janela.querySelector(".passe-status").textContent = "A fatura expirou. Feche e gere outra.";
  }

  window.Passe = {
    valido,
    token: () => (valido() ? ler().token : null),
    validade: () => (valido() ? new Date(ler().exp) : null),
    exigir: (acao) => (valido() ? acao() : comprar(acao)),
  };
})();

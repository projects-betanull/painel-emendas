// Rota /api/gestao: dados privados da página de gestão (saldo e pagamentos no coinos).
// Exige o cabeçalho X-Admin-Key igual ao segredo ADMIN_KEY do projeto.
const json = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export async function onRequest({ request, env }) {
  if (!env.ADMIN_KEY || request.headers.get("x-admin-key") !== env.ADMIN_KEY) return json({ erro: "chave inválida" }, 401);
  const out = { configurado: { coinos: !!env.COINOS_TOKEN, preco_sats: Number(env.PRECO_SATS || 1000) } };
  if (env.COINOS_TOKEN) {
    const h = { authorization: `Bearer ${env.COINOS_TOKEN}` };
    try {
      const me = await (await fetch("https://coinos.io/api/me", { headers: h })).json();
      out.saldo_sats = me.balance ?? null;
      out.usuario = me.username ?? null;
    } catch (e) { out.erro_saldo = String(e); }
    try {
      const p = await (await fetch("https://coinos.io/api/payments?limit=100", { headers: h })).json();
      out.pagamentos = (p.payments || p || []).slice(0, 100).map((x) => ({ quando: x.created, sats: x.amount, memo: x.memo || "", tipo: x.type || "" }));
    } catch (e) { out.erro_pagamentos = String(e); }
  }
  return json(out);
}

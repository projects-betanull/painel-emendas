// Rota /api/gestao: dados privados da página de gestão. Exige o cabeçalho X-Admin-Key igual a ADMIN_KEY.
const json = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export async function onRequest({ request, env }) {
  if (!env.ADMIN_KEY || request.headers.get("x-admin-key") !== env.ADMIN_KEY) return json({ erro: "chave inválida" }, 401);
  return json({ configurado: { preco_sats: Number(env.PRECO_SATS || 1000), endereco: env.LIGHTNING_ADDRESS || "lizard43@coinos.io", assinatura_tokens: !!env.TOKEN_SECRET } });
}

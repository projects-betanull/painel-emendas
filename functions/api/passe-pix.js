// /api/passe-pix: compra do passe de 24 h por Pix (checkout da Kiwify).
//   POST          -> { ref, checkout, reais } | 503 se a Kiwify não estiver configurada
//   GET ?ref=...  -> { token, exp } | 402 (ainda não pago) | 400
import { pixAtivo, novaReferencia, linkCheckout, ativarPassePix } from "../../lib/kiwify.js";

const json = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export async function onRequest({ request, env }) {
  if (!pixAtivo(env)) return json({ erro: "Pix indisponível." }, 503);
  try {
    if (request.method === "POST") {
      const ref = await novaReferencia(env);
      console.log(JSON.stringify({ evento: "passe", acao: "comprar", origem: "pix" }));
      return json({ ref, checkout: linkCheckout(env, ref), reais: Number(env.PRECO_PIX_REAIS) || null });
    }
    const r = await ativarPassePix(env, new URL(request.url).searchParams.get("ref"));
    if (r.token) console.log(JSON.stringify({ evento: "passe", acao: "ativado", origem: "pix" }));
    return r.token ? json(r) : json(r, r.pendente ? 402 : 400);
  } catch (e) {
    return json({ erro: "Conferência indisponível no momento. Tente de novo." }, 502);
  }
}

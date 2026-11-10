// /api/passe: compra do passe de 24 h pelo site.
//   POST            -> { fatura, preco }      (fatura Lightning do endereço do painel)
//   GET ?fatura=... -> { token, exp } | 402   (confere o pagamento)
import { criarFatura, ativarPasse, precoDe } from "../../lib/mcp.js";

const json = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export async function onRequest({ request, env }) {
  try {
    if (request.method === "POST") {
      const inv = await criarFatura(env, precoDe(env), "site");
      console.log(JSON.stringify({ evento: "passe", acao: "comprar", origem: "site" }));
      return json({ fatura: inv.pr, preco: precoDe(env) });
    }
    const fatura = new URL(request.url).searchParams.get("fatura");
    const r = await ativarPasse(env, fatura);
    if (r.token) console.log(JSON.stringify({ evento: "passe", acao: "ativado", origem: "site" }));
    return r.token ? json(r) : json(r, r.pendente ? 402 : 400);
  } catch (e) {
    return json({ erro: "Pagamento indisponível no momento. Tente de novo." }, 502);
  }
}

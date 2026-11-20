// /og/<chave>.png: cartão de prévia (Open Graph) para WhatsApp e redes, desenhado sob demanda.
// chave = "site", sigla da UF ("sp") ou UF + código IBGE ("sp-3509502"). Os textos vêm de /og-dados/<uf>.json,
// gerados pelo ETL; a imagem fica no cache da Cloudflare, então cada cartão é desenhado poucas vezes por dia.
import { desenharCartao } from "../../lib/og.js";

const CHAVE = /^\/og\/(site|[a-z]{2}|([a-z]{2})-(\d{7}))\.png$/;

async function lerJson(env, request, caminho) {
  const r = await env.ASSETS.fetch(new URL(caminho, request.url));
  if (!r.ok) return null;
  try { return await r.json(); } catch { return null; }
}

function versaoValida(v, agora = Date.now()) {
  const m = /^(\d{2})(\d{2})(\d{4})$/.exec(v || "");
  if (!m) return false;
  const t = Date.UTC(+m[3], +m[2] - 1, +m[1]);
  return Math.abs(agora - t) < 3 * 864e5;
}

export async function onRequest({ request, env, waitUntil }) {
  const m = new URL(request.url).pathname.match(CHAVE);
  if (!m) return new Response("Não encontrado", { status: 404 });
  const cache = typeof caches !== "undefined" ? caches.default : null;
  // Chave do cache: só o caminho e um ?v= de data recente (ddmmaaaa, como o ETL gera). Qualquer outra
  // query é ignorada, para que ?lixo-aleatório não force desenhar a mesma imagem de novo a cada pedido.
  const u = new URL(request.url), chave = u.origin + u.pathname + (versaoValida(u.searchParams.get("v")) ? "?v=" + u.searchParams.get("v") : "");
  const guardado = cache && (await cache.match(chave));
  if (guardado) return guardado;

  let dados;
  if (m[1] === "site") dados = await lerJson(env, request, "/og-dados/site.json");
  else {
    const uf = m[2] || m[1];
    const tab = await lerJson(env, request, `/og-dados/${uf}.json`);
    dados = tab && tab[m[3] || "uf"];
  }
  if (!dados && m[1] === "site") return new Response("Não encontrado", { status: 404 });
  if (!dados) return Response.redirect(new URL("/og/site.png", request.url).toString(), 302);

  const resposta = new Response(await desenharCartao(dados), {
    headers: { "content-type": "image/png", "cache-control": "public, max-age=86400" },
  });
  if (cache) waitUntil(cache.put(chave, resposta.clone()));
  return resposta;
}

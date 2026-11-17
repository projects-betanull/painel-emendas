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

export async function onRequest({ request, env, waitUntil }) {
  const m = new URL(request.url).pathname.match(CHAVE);
  if (!m) return new Response("Não encontrado", { status: 404 });
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const guardado = cache && (await cache.match(request.url));
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
  if (cache) waitUntil(cache.put(request.url, resposta.clone()));
  return resposta;
}

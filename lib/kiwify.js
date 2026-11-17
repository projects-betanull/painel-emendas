// Passe de 24 h pago por Pix pela Kiwify (a venda é feita em nome da Kiwify; o nome do dono não aparece no Pix).
// Sem banco de dados: o site gera uma referência assinada, que vai no link do checkout (?s1=ref&sck=ref);
// depois confere pela API pública da Kiwify se há venda paga do produto com essa referência.
import { emitirToken } from "./mcp.js";

const API = "https://public-api.kiwify.com/v1";
const HORAS = 24;

export const pixAtivo = (env) => !!(env.KIWIFY_CLIENT_ID && env.KIWIFY_CLIENT_SECRET && env.KIWIFY_ACCOUNT_ID && env.KIWIFY_PRODUCT_ID && env.KIWIFY_CHECKOUT_URL && env.TOKEN_SECRET);

const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
async function assinatura(env, msg) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode("kiwify|" + env.TOKEN_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg))).slice(0, 16);
}

// Referência: <criação em ms>-<aleatório>-<assinatura>. Só letras, números, "-" e "_" (vai na URL do checkout).
export async function novaReferencia(env, agora = Date.now()) {
  const al = b64(crypto.getRandomValues(new Uint8Array(6)));
  const corpo = `${agora}-${al}`;
  return `${corpo}-${await assinatura(env, corpo)}`;
}
export async function lerReferencia(env, ref) {
  const m = /^(\d{13})-([\w-]{8})-([\w-]{16})$/.exec(String(ref || ""));
  if (!m) return null;
  if (m[3] !== (await assinatura(env, `${m[1]}-${m[2]}`))) return null;
  return { criada: Number(m[1]) };
}

export function linkCheckout(env, ref) {
  const u = new URL(env.KIWIFY_CHECKOUT_URL);
  u.searchParams.set("s1", ref);
  u.searchParams.set("sck", ref);
  return u.href;
}

// Token da API (vale 96 h); guardado na memória do isolate.
let cacheToken = { v: "", ate: 0 };
async function tokenApi(env, f) {
  if (cacheToken.v && cacheToken.ate > Date.now()) return cacheToken.v;
  const r = await f(`${API}/oauth/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: env.KIWIFY_CLIENT_ID, client_secret: env.KIWIFY_CLIENT_SECRET }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || !d.access_token) throw new Error(`kiwify token ${r.status}`);
  cacheToken = { v: d.access_token, ate: Date.now() + Math.min(Number(d.expires_in) || 86400, 86400) * 1000 - 60e3 };
  return cacheToken.v;
}

const dia = (ms) => new Date(ms).toISOString().slice(0, 10);
// Vendas recentes do produto, com detalhes (rastreio s1/sck). Cache curto: várias janelas abertas fazendo
// conferência não estouram o limite de 100 chamadas/min da Kiwify.
let cacheVendas = { chave: "", t: 0, dados: [] };
async function vendasRecentes(env, desde, f) {
  const chave = dia(desde);
  if (cacheVendas.chave === chave && Date.now() - cacheVendas.t < 4000) return cacheVendas.dados;
  const q = new URLSearchParams({
    start_date: dia(desde - 864e5), end_date: dia(Date.now() + 864e5),
    product_id: env.KIWIFY_PRODUCT_ID, view_full_sale_details: "true", page_size: "100",
  });
  const h = { authorization: `Bearer ${await tokenApi(env, f)}`, "x-kiwify-account-id": env.KIWIFY_ACCOUNT_ID };
  const r = await f(`${API}/sales?${q}`, { headers: h });
  if (r.status === 401) cacheToken = { v: "", ate: 0 };
  if (!r.ok) throw new Error(`kiwify vendas ${r.status}`);
  const dados = (await r.json()).data || [];
  cacheVendas = { chave, t: Date.now(), dados };
  return dados;
}

const PAGAS = new Set(["paid", "approved"]);
// Confere a referência e devolve { token, exp } | { pendente: true } | { erro }.
export async function ativarPassePix(env, ref, f = fetch) {
  const r = await lerReferencia(env, ref);
  if (!r) return { erro: "Referência de compra inválida." };
  const exp = r.criada + HORAS * 3600e3;
  if (exp < Date.now()) return { erro: "Esta compra já tem mais de 24 horas. Compre um novo passe." };
  const vendas = await vendasRecentes(env, r.criada, f);
  const venda = vendas.find((v) => (v.tracking?.s1 === ref || v.tracking?.sck === ref) && (!v.product?.id || v.product.id === env.KIWIFY_PRODUCT_ID));
  if (!venda || !PAGAS.has(String(venda.status))) return { pendente: true };
  // O passe vale 24 h a partir da criação da referência: reapresentar a mesma não estende o prazo.
  return { token: await emitirToken(env, "k", exp), exp };
}

export function _limparCache() { cacheToken = { v: "", ate: 0 }; cacheVendas = { chave: "", t: 0, dados: [] }; }

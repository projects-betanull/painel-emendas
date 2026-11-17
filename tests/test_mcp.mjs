// Testa o servidor MCP com dados de amostra (node tests/test_mcp.mjs <pasta-do-site>).
import { readFileSync } from "node:fs";
import { tratar, emitirToken } from "../lib/mcp.js";
const site = process.argv[2];
const env = {
  TOKEN_SECRET: "teste",
  ASSETS: { fetch: async (u) => { try { return new Response(readFileSync(site + new URL(u).pathname)); } catch { return new Response("", { status: 404 }); } } },
};
const rpc = async (method, params, id = 1) => {
  const r = await tratar(new Request("https://x.dev/mcp", { method: "POST", body: JSON.stringify({ jsonrpc: "2.0", id, method, params }) }), env);
  return r.status === 202 ? null : r.json();
};
const ok = (c, m) => { if (!c) { console.error("FALHOU:", m); process.exit(1); } };
const ini = await rpc("initialize", { protocolVersion: "2025-06-18" });
ok(ini.result.capabilities.tools, "initialize");
ok((await rpc("notifications/initialized", {}, null)) === null, "notificação 202");
const lista = await rpc("tools/list", {});
ok(lista.result.tools.length === 6 && !("pago" in lista.result.tools[0]), "tools/list");
const busca = JSON.parse((await rpc("tools/call", { name: "buscar_municipio", arguments: { nome: "campi" } })).result.content[0].text);
ok(busca.resultados[0].codigo_ibge === "3509502", "buscar_municipio " + JSON.stringify(busca));
const gratis = JSON.parse((await rpc("tools/call", { name: "resumo_municipio", arguments: { codigo_ibge: "3509502" } })).result.content[0].text);
ok(gratis.total_recebido > 0 && !gratis.autores && gratis.detalhes, "resumo grátis");
const neg = (await rpc("tools/call", { name: "ranking_municipios", arguments: { token: "x.y.z" } })).result;
ok(neg.isError, "ranking sem token");
const token = await emitirToken(env, "fatura1");
const pago = JSON.parse((await rpc("tools/call", { name: "resumo_municipio", arguments: { codigo_ibge: "3509502", token } })).result.content[0].text);
ok(pago.autores.length && pago.favorecidos[0].documento, "resumo pago");
const rk = JSON.parse((await rpc("tools/call", { name: "ranking_municipios", arguments: { uf: "sp", token } })).result.content[0].text);
ok(rk.uf === "SP" && rk.por_total.length, "ranking pago");
const falso = token.slice(0, -2) + "xx";
ok((await rpc("tools/call", { name: "ranking_municipios", arguments: { token: falso } })).result.isError, "token adulterado");
import { resumir } from "../lib/pncp.js";
const r = resumir("1", [{ niFornecedor: "11222333000181", nomeRazaoSocialFornecedor: "EMPRESA A", valorGlobal: 100, dataAssinatura: "2026-01-02", objetoContrato: "obra" },
  { niFornecedor: "11222333000181", nomeRazaoSocialFornecedor: "EMPRESA A", valorGlobal: 50, dataAssinatura: "2026-02-02" },
  { niFornecedor: "12345678901", tipoPessoa: "PF", nomeRazaoSocialFornecedor: "FULANO", valorGlobal: 10 }]);
ok(r.total_contratos === 2 && r.omitidos_pessoa_fisica === 1 && r.fornecedores[0].valor === 150 && r.recentes[0].data === "2026-02-02", "pncp resumir");
console.log("mcp ok");
// Passe por Pix (Kiwify), com a API simulada.
import { novaReferencia, lerReferencia, linkCheckout, ativarPassePix, pixAtivo, _limparCache } from "../lib/kiwify.js";
import { tokenValido } from "../lib/mcp.js";
const envK = { TOKEN_SECRET: "teste", KIWIFY_CLIENT_ID: "c", KIWIFY_CLIENT_SECRET: "s", KIWIFY_ACCOUNT_ID: "acc", KIWIFY_PRODUCT_ID: "prod", KIWIFY_CHECKOUT_URL: "https://pay.kiwify.com.br/abc?x=1" };
ok(pixAtivo(envK) && !pixAtivo({ ...envK, KIWIFY_PRODUCT_ID: "" }), "pixAtivo");
const ref = await novaReferencia(envK);
ok(await lerReferencia(envK, ref), "referência válida");
ok(!(await lerReferencia(envK, ref.slice(0, -1) + (ref.endsWith("A") ? "B" : "A"))), "referência adulterada");
ok(!(await lerReferencia({ ...envK, TOKEN_SECRET: "outro" }, ref)), "referência de outro segredo");
const lk = new URL(linkCheckout(envK, ref));
ok(lk.searchParams.get("s1") === ref && lk.searchParams.get("sck") === ref && lk.searchParams.get("x") === "1", "link do checkout");
let vendas = [], chamadas = [];
const kiwifyFalsa = async (url, op = {}) => {
  chamadas.push(url);
  if (url.endsWith("/oauth/token")) return new Response(JSON.stringify({ access_token: "tk", expires_in: "86400" }));
  ok(op.headers.authorization === "Bearer tk" && op.headers["x-kiwify-account-id"] === "acc", "cabeçalhos da Kiwify");
  const q = new URL(url).searchParams;
  ok(q.get("product_id") === "prod" && q.get("view_full_sale_details") === "true" && /^\d{4}-\d\d-\d\d$/.test(q.get("start_date")), "consulta de vendas");
  return new Response(JSON.stringify({ data: vendas }));
};
ok((await ativarPassePix(envK, ref, kiwifyFalsa)).pendente, "pix pendente sem venda");
_limparCache();
vendas = [{ status: "waiting_payment", product: { id: "prod" }, tracking: { s1: ref } }];
ok((await ativarPassePix(envK, ref, kiwifyFalsa)).pendente, "pix aguardando pagamento");
_limparCache();
vendas = [{ status: "paid", product: { id: "outro" }, tracking: { s1: ref } }];
ok((await ativarPassePix(envK, ref, kiwifyFalsa)).pendente, "venda de outro produto não vale");
_limparCache();
vendas = [{ status: "paid", product: { id: "prod" }, tracking: { s1: null, sck: ref } }];
const pk = await ativarPassePix(envK, ref, kiwifyFalsa);
ok(pk.token && (await tokenValido(envK, pk.token)) && pk.exp > Date.now(), "pix pago libera passe " + JSON.stringify(pk));
ok((await ativarPassePix(envK, "123", kiwifyFalsa)).erro, "referência inválida");
const velha = await novaReferencia(envK, Date.now() - 25 * 3600e3);
ok((await ativarPassePix(envK, velha, kiwifyFalsa)).erro, "referência vencida");
console.log("kiwify ok");


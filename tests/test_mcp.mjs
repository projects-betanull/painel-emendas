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

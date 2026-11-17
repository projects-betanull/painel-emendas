// Testa a Function /og/: lê os textos gerados pelo ETL (pasta do site) e desenha os cartões.
// Uso: node tests/test_og.mjs <pasta-do-site> [pasta-para-salvar-os-png]
import { readFileSync, existsSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { onRequest } from "../functions/og/[[caminho]].js";

const site = process.argv[2], salvar = process.argv[3];
const env = { ASSETS: { fetch: async (u) => {
  const f = join(site, new URL(u).pathname);
  return existsSync(f) ? new Response(readFileSync(f)) : new Response("", { status: 404 });
} } };
const pedir = (p) => onRequest({ request: new Request("https://x.dev" + p), env, waitUntil: () => {} });
const falha = (msg) => { console.error(msg); process.exit(1); };

const chaves = ["site"];
for (const arq of readdirSync(join(site, "og-dados"))) {
  if (arq === "site.json") continue;
  const uf = arq.replace(".json", "");
  for (const k of Object.keys(JSON.parse(readFileSync(join(site, "og-dados", arq), "utf8")))) chaves.push(k === "uf" ? uf : `${uf}-${k}`);
}
if (chaves.length < 3) falha("poucos cartões: " + chaves);
for (const k of chaves) {
  const r = await pedir(`/og/${k}.png`);
  const b = new Uint8Array(await r.arrayBuffer());
  if (r.status !== 200 || r.headers.get("content-type") !== "image/png") falha(`${k}: status ${r.status}`);
  if (b[1] !== 0x50 || b[2] !== 0x4e || b[3] !== 0x47 || b.length > 300_000) falha(`${k}: PNG inválido (${b.length} bytes)`);
  if (salvar) writeFileSync(join(salvar, `${k}.png`), b);
}
if ((await pedir("/og/../x.png")).status !== 404) falha("caminho inválido não deu 404");
const r = await pedir("/og/sp-9999999.png");
if (r.status !== 302) falha("município inexistente deveria redirecionar para o cartão do site");
console.log("og ok", chaves.length);

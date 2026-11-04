// /api/contratos?cnpj=<órgão>: contratos do órgão no PNCP, resumidos e em cache de 24 h.
import { comCache } from "../../lib/pncp.js";

export async function onRequest({ request, waitUntil }) {
  const cnpj = (new URL(request.url).searchParams.get("cnpj") || "").replace(/\D/g, "");
  const json = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { "content-type": "application/json", "cache-control": "public, max-age=3600" } });
  if (cnpj.length !== 14) return json({ erro: "informe o CNPJ do órgão (14 dígitos)" }, 400);
  try { return json(await comCache(cnpj, { waitUntil })); }
  catch (e) { return json({ erro: "PNCP indisponível no momento", detalhe: String(e.message || e) }, 502); }
}

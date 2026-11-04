// Servidor MCP (Streamable HTTP, sem estado) das emendas parlamentares, com cobrança Lightning via coinos.
// Roda como Cloudflare Pages Function em /mcp. Lê os JSON gerados pelo ETL em /api/.

const VERSAO_PROTOCOLO = "2025-06-18";
const SERVIDOR = { name: "painel-emendas", title: "Emendas parlamentares do Brasil", version: "1.0.0" };
const PRECO_PADRAO = 1000; // sats por passe de 24 h
const HORAS = 24;

const FONTE = "Fonte: Portal da Transparência (CGU). Valores reproduzidos como publicados; não constituem juízo sobre legalidade.";

const FERRAMENTAS = [
  {
    name: "buscar_municipio",
    description: "Encontra municípios pelo nome e devolve código IBGE, UF e total recebido em emendas parlamentares (gratuito).",
    inputSchema: { type: "object", properties: { nome: { type: "string", description: "Nome ou parte do nome do município" } }, required: ["nome"] },
    pago: false,
  },
  {
    name: "resumo_municipio",
    description: "Resumo das emendas parlamentares recebidas por um município: total, por habitante e página. Com token pago, inclui por ano, autores, favorecidos (com CNPJ), áreas e tipos.",
    inputSchema: { type: "object", properties: { codigo_ibge: { type: "string", description: "Código IBGE de 7 dígitos (use buscar_municipio)" }, token: { type: "string", description: "Token de acesso (opcional; obtido com comprar_acesso e ativar_acesso)" } }, required: ["codigo_ibge"] },
    pago: false,
  },
  {
    name: "ranking_municipios",
    description: "Ranking dos municípios que mais receberam emendas, no Brasil ou numa UF, por valor total e por habitante (municípios acima de 50 mil habitantes). Requer token pago.",
    inputSchema: { type: "object", properties: { uf: { type: "string", description: "Sigla da UF (ex.: SP) ou BR para o Brasil" }, token: { type: "string" } }, required: ["token"] },
    pago: true,
  },
  {
    name: "comprar_acesso",
    description: "Gera uma fatura Lightning para um passe de 24 horas às ferramentas pagas. Pague a fatura e depois chame ativar_acesso com o id.",
    inputSchema: { type: "object", properties: {} },
    pago: false,
  },
  {
    name: "ativar_acesso",
    description: "Confere o pagamento de uma fatura gerada por comprar_acesso e devolve o token de acesso de 24 horas.",
    inputSchema: { type: "object", properties: { fatura_id: { type: "string" } }, required: ["fatura_id"] },
    pago: false,
  },
];

// ---------- utilidades
const texto = (t, erro = false) => ({ content: [{ type: "text", text: typeof t === "string" ? t : JSON.stringify(t, null, 1) }], ...(erro ? { isError: true } : {}) });
const semAcento = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function hmac(segredo, msg) {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(segredo), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(msg)));
}
const segredoDe = (env) => env.TOKEN_SECRET || env.COINOS_TOKEN || "";

async function emitirToken(env, faturaId) {
  const exp = Date.now() + HORAS * 3600e3;
  const corpo = `${exp}.${faturaId}`;
  return `${corpo}.${await hmac(segredoDe(env), corpo)}`;
}

async function tokenValido(env, token) {
  if (!token || !segredoDe(env)) return false;
  const p = String(token).split(".");
  if (p.length !== 3) return false;
  const [exp, id, sig] = p;
  return Number(exp) > Date.now() && sig === (await hmac(segredoDe(env), `${exp}.${id}`));
}

async function lerApi(env, base, caminho) {
  const url = new URL(caminho, base);
  const r = env.ASSETS ? await env.ASSETS.fetch(url) : await fetch(url);
  if (!r.ok) return null;
  return r.json();
}

// ---------- coinos
const COINOS = "https://coinos.io/api";
async function criarFatura(env, sats) {
  const r = await fetch(`${COINOS}/invoice`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${env.COINOS_TOKEN}` },
    body: JSON.stringify({ invoice: { amount: sats, type: "lightning", memo: "painel-emendas: passe MCP 24h" } }),
  });
  if (!r.ok) throw new Error(`coinos ${r.status}`);
  return r.json();
}
async function consultarFatura(id) {
  const r = await fetch(`${COINOS}/invoice/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error(`coinos ${r.status}`);
  return r.json();
}
const bolt11 = (inv) => inv.text || inv.bolt11 || inv.hash || inv.payment_request || "";

// ---------- ferramentas
async function chamar(nome, args, env, base) {
  const preco = Number(env.PRECO_SATS || PRECO_PADRAO);
  switch (nome) {
    case "buscar_municipio": {
      const lista = (await lerApi(env, base, "/busca.json")) || [];
      const q = semAcento(args.nome).trim();
      if (q.length < 2) return texto("Informe ao menos 2 letras do nome.", true);
      const achados = lista.filter((m) => semAcento(m.n).includes(q)).sort((a, b) => b.v - a.v).slice(0, 10);
      const codigos = await Promise.all(achados.map(async (m) => {
        // O código IBGE vem do arquivo do município; a busca guarda só nome, UF e caminho.
        return { municipio: m.n, uf: m.u, total_recebido: m.v, pagina: new URL(m.p, base).href };
      }));
      const ids = (await lerApi(env, base, "/api/indice.json")) || {};
      return texto({ resultados: codigos.map((c) => ({ ...c, codigo_ibge: ids[`${c.municipio}|${c.uf}`] || null })), fonte: FONTE });
    }
    case "resumo_municipio": {
      const cod = String(args.codigo_ibge || "").replace(/\D/g, "");
      const d = await lerApi(env, base, `/api/m/${cod}.json`);
      if (!d) return texto("Município não encontrado. Use buscar_municipio para obter o código IBGE.", true);
      if (await tokenValido(env, args.token)) return texto(d);
      const { municipio, uf, total_recebido, populacao, por_habitante, pagina, fonte, url, aviso } = d;
      return texto({ municipio, uf, total_recebido, populacao, por_habitante, pagina, fonte, url, aviso,
        detalhes: `Por ano, autores, favorecidos, áreas e tipos exigem um passe de 24 h (${preco} sats): use comprar_acesso.` });
    }
    case "ranking_municipios": {
      if (!(await tokenValido(env, args.token))) return texto(`Esta ferramenta exige um passe de 24 h (${preco} sats). Use comprar_acesso e depois ativar_acesso.`, true);
      const uf = String(args.uf || "BR").toUpperCase().slice(0, 2);
      const d = await lerApi(env, base, `/api/ranking/${uf === "BR" || !uf ? "BR" : uf}.json`);
      return d ? texto(d) : texto("UF não encontrada.", true);
    }
    case "comprar_acesso": {
      if (!env.COINOS_TOKEN) return texto("Pagamentos ainda não configurados neste servidor.", true);
      const inv = await criarFatura(env, preco);
      return texto({ fatura_id: inv.id || bolt11(inv), fatura_lightning: bolt11(inv), valor_sats: preco, validade_do_passe: `${HORAS} horas`,
        proximo_passo: "Pague a fatura com qualquer carteira Lightning e chame ativar_acesso com fatura_id." });
    }
    case "ativar_acesso": {
      const id = String(args.fatura_id || "");
      if (!id) return texto("Informe fatura_id.", true);
      const inv = await consultarFatura(id);
      const recebido = Number(inv.received || 0), devido = Number(inv.amount || preco);
      if (recebido < devido) return texto(`Pagamento ainda não recebido (${recebido} de ${devido} sats). Tente de novo após pagar.`, true);
      return texto({ token: await emitirToken(env, id), validade: `${HORAS} horas`, uso: "Passe o token no argumento token das ferramentas pagas." });
    }
    default:
      return null;
  }
}

// ---------- JSON-RPC / Streamable HTTP
const resp = (corpo, status = 200) => new Response(corpo === null ? null : JSON.stringify(corpo), {
  status, headers: { "content-type": "application/json", "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "POST, GET, OPTIONS" },
});

export async function tratar(request, env = {}) {
  if (request.method === "OPTIONS") return resp(null, 204);
  if (request.method === "GET") {
    return resp({ servidor: SERVIDOR, transporte: "streamable-http (POST JSON-RPC)", ferramentas: FERRAMENTAS.map((f) => f.name), docs: new URL("/ia/", request.url).href });
  }
  if (request.method !== "POST") return resp({ error: "método não suportado" }, 405);
  let msg;
  try { msg = await request.json(); } catch { return resp({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "JSON inválido" } }, 400); }
  const lote = Array.isArray(msg) ? msg : [msg];
  const saidas = [];
  for (const m of lote) {
    const r = await uma(m, env, request.url);
    if (r) saidas.push(r);
  }
  if (!saidas.length) return resp(null, 202);
  return resp(Array.isArray(msg) ? saidas : saidas[0]);
}

async function uma(m, env, base) {
  const { id, method, params = {} } = m || {};
  if (id === undefined || id === null) return null; // notificação
  const ok = (result) => ({ jsonrpc: "2.0", id, result });
  const erro = (code, message) => ({ jsonrpc: "2.0", id, error: { code, message } });
  switch (method) {
    case "initialize":
      return ok({ protocolVersion: params.protocolVersion || VERSAO_PROTOCOLO, capabilities: { tools: {} }, serverInfo: SERVIDOR,
        instructions: "Dados de emendas parlamentares federais (Portal da Transparência, 2014 em diante). buscar_municipio e resumo_municipio são gratuitos; detalhes e rankings exigem um passe de 24 h pago em Lightning (comprar_acesso, ativar_acesso)." });
    case "ping":
      return ok({});
    case "tools/list":
      return ok({ tools: FERRAMENTAS.map(({ pago, ...f }) => f) });
    case "tools/call": {
      const t0 = Date.now();
      try {
        const r = await chamar(params.name, params.arguments || {}, env, base);
        console.log(JSON.stringify({ evento: "mcp", ferramenta: params.name, erro: !!(r && r.isError), ms: Date.now() - t0 }));
        return r ? ok(r) : erro(-32602, `ferramenta desconhecida: ${params.name}`);
      } catch (e) {
        console.log(JSON.stringify({ evento: "mcp", ferramenta: params.name, falha: String(e) }));
        return ok(texto(`Falha temporária: ${e.message}`, true));
      }
    }
    default:
      return erro(-32601, `método não suportado: ${method}`);
  }
}

export { FERRAMENTAS, emitirToken, tokenValido };

// Contratos de um órgão no PNCP (últimos 12 meses), com cache. Sem pessoas físicas (LGPD).
// O PNCP leva 15–40 s por consulta, qualquer que seja o tamanho da página; por isso a página 1 vem
// primeiro (traz totalPaginas) e as demais em paralelo. Página que falhar deixa o resultado "parcial".
const API = "https://pncp.gov.br/api/consulta/v1/contratos";
const dia = (d) => d.toISOString().slice(0, 10).replace(/-/g, "");
const TAM = 500, MAX_PAGINAS = 30, PARALELO = 8, ESPERA_MS = 60000;

async function pagina(cnpj, ini, fim, p) {
  const r = await fetch(`${API}?dataInicial=${dia(ini)}&dataFinal=${dia(fim)}&cnpjOrgao=${cnpj}&pagina=${p}&tamanhoPagina=${TAM}`,
    { headers: { accept: "application/json" }, signal: AbortSignal.timeout(ESPERA_MS) });
  if (r.status === 204) return { data: [], totalPaginas: 0 };
  if (!r.ok) throw new Error(`PNCP ${r.status}`);
  return r.json();
}

export async function contratosDoOrgao(cnpj, { maxPaginas = MAX_PAGINAS } = {}) {
  const fim = new Date(), ini = new Date(Date.now() - 364 * 864e5);
  const primeira = await pagina(cnpj, ini, fim, 1);
  const todos = [...(primeira.data || [])];
  const total = Math.min(primeira.totalPaginas || 1, maxPaginas);
  let falhas = 0;
  const resto = Array.from({ length: Math.max(total - 1, 0) }, (_, i) => i + 2);
  for (let i = 0; i < resto.length; i += PARALELO) {
    const lote = await Promise.allSettled(resto.slice(i, i + PARALELO).map((p) => pagina(cnpj, ini, fim, p)));
    for (const r of lote) r.status === "fulfilled" ? todos.push(...(r.value.data || [])) : falhas++;
  }
  const d = resumir(cnpj, todos);
  if (falhas || (primeira.totalPaginas || 1) > maxPaginas) d.parcial = true;
  d.atualizado_em = new Date().toISOString();
  return d;
}

export function resumir(cnpj, contratos) {
  const pj = contratos.filter((c) => String(c.tipoPessoa || "").toUpperCase() !== "PF" && String(c.niFornecedor || "").replace(/\D/g, "").length !== 11);
  const omitidos = contratos.length - pj.length;
  const porForn = new Map();
  for (const c of pj) {
    const k = c.niFornecedor || c.nomeRazaoSocialFornecedor;
    const f = porForn.get(k) || { fornecedor: c.nomeRazaoSocialFornecedor, cnpj: c.niFornecedor, valor: 0, contratos: 0 };
    f.valor += Number(c.valorGlobal || c.valorInicial || 0);
    f.contratos += 1;
    porForn.set(k, f);
  }
  const link = (c) => (c.orgaoEntidade?.cnpj && c.anoContrato && c.sequencialContrato) ? `https://pncp.gov.br/app/contratos/${c.orgaoEntidade.cnpj}/${c.anoContrato}/${c.sequencialContrato}` : null;
  return {
    orgao_cnpj: cnpj,
    periodo: "últimos 12 meses",
    total_contratos: pj.length,
    valor_total: Math.round(pj.reduce((a, c) => a + Number(c.valorGlobal || c.valorInicial || 0), 0)),
    omitidos_pessoa_fisica: omitidos,
    fornecedores: [...porForn.values()].sort((a, b) => b.valor - a.valor).slice(0, 15).map((f) => ({ ...f, valor: Math.round(f.valor) })),
    recentes: pj.sort((a, b) => String(b.dataAssinatura).localeCompare(String(a.dataAssinatura))).slice(0, 10).map((c) => ({
      data: c.dataAssinatura, fornecedor: c.nomeRazaoSocialFornecedor, cnpj: c.niFornecedor, valor: Math.round(Number(c.valorGlobal || c.valorInicial || 0)),
      objeto: String(c.objetoContrato || "").slice(0, 240), link: link(c) })),
    fonte: "Portal Nacional de Contratações Públicas (PNCP), contratos publicados pelo órgão.",
    aviso: "Contratos da prefeitura em geral; os dados públicos não indicam quais foram pagos com recursos de emendas.",
  };
}

// Cache do Cloudflare: novo por 24 h; até 7 dias é servido na hora e atualizado em segundo plano.
const FRESCO_MS = 864e5, GUARDA_S = 7 * 86400;

export async function comCache(cnpj, ctx) {
  const chave = new Request(`https://cache.local/contratos/v2/${cnpj}`);
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const guardar = (d) => {
    if (!cache) return;
    const ttl = d.parcial ? 3600 : GUARDA_S; // resultado parcial fica pouco tempo
    const p = cache.put(chave, new Response(JSON.stringify(d), { headers: { "content-type": "application/json", "cache-control": `max-age=${ttl}` } }));
    if (ctx?.waitUntil) ctx.waitUntil(p);
    return p;
  };
  if (cache) {
    const c = await cache.match(chave);
    if (c) {
      const d = await c.json();
      if (Date.now() - Date.parse(d.atualizado_em || 0) > FRESCO_MS && ctx?.waitUntil) {
        ctx.waitUntil(contratosDoOrgao(cnpj).then(guardar).catch(() => {}));
      }
      return d;
    }
  }
  const d = await contratosDoOrgao(cnpj);
  const p = guardar(d);
  if (p && !ctx?.waitUntil) await p;
  return d;
}

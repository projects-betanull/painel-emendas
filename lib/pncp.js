// Contratos de um órgão no PNCP (últimos 12 meses), com cache de 24 h. Sem pessoas físicas (LGPD).
const API = "https://pncp.gov.br/api/consulta/v1/contratos";
const dia = (d) => d.toISOString().slice(0, 10).replace(/-/g, "");

export async function contratosDoOrgao(cnpj, { maxPaginas = 4 } = {}) {
  const fim = new Date(), ini = new Date(Date.now() - 364 * 864e5);
  const todos = [];
  for (let p = 1; p <= maxPaginas; p++) {
    const r = await fetch(`${API}?dataInicial=${dia(ini)}&dataFinal=${dia(fim)}&cnpjOrgao=${cnpj}&pagina=${p}&tamanhoPagina=500`, { headers: { accept: "application/json" } });
    if (r.status === 204) break;
    if (!r.ok) throw new Error(`PNCP ${r.status}`);
    const j = await r.json(), dados = j.data || [];
    todos.push(...dados);
    if (dados.length < 500 || p >= (j.totalPaginas || 1)) break;
  }
  return resumir(cnpj, todos);
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

export async function comCache(cnpj, ctx) {
  const chave = new Request(`https://cache.local/contratos/${cnpj}`);
  const cache = typeof caches !== "undefined" ? caches.default : null;
  if (cache) { const c = await cache.match(chave); if (c) return c.json(); }
  const d = await contratosDoOrgao(cnpj);
  if (cache) {
    const resp = new Response(JSON.stringify(d), { headers: { "content-type": "application/json", "cache-control": "max-age=86400" } });
    const p = cache.put(chave, resp);
    if (ctx?.waitUntil) ctx.waitUntil(p); else await p;
  }
  return d;
}

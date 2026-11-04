// Os JSON detalhados em /api/m e /api/ranking são servidos só pelo servidor MCP (env.ASSETS), não direto.
export async function onRequest({ request, next }) {
  const p = new URL(request.url).pathname;
  if (p.startsWith("/api/m/") || p.startsWith("/api/ranking/")) {
    return new Response(JSON.stringify({ erro: "Use o servidor MCP em /mcp. Documentação em /ia/." }), { status: 403, headers: { "content-type": "application/json" } });
  }
  return next();
}

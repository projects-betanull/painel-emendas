// Os JSON detalhados em /api/m e /api/ranking são servidos só pelo servidor MCP (env.ASSETS), não direto.
// O servidor de arquivos do Pages decodifica %xx e junta barras repetidas, então o caminho é normalizado
// do mesmo jeito antes da checagem (senão /api/%6d/... ou /api//m/... passariam direto).
export function normalizar(pathname) {
  let p = String(pathname);
  for (let i = 0; i < 5; i++) {
    let d;
    try { d = decodeURIComponent(p); } catch { break; }
    if (d === p) break;
    p = d;
  }
  return p.replace(/\\/g, "/").replace(/\/{2,}/g, "/").toLowerCase();
}

export const bloqueado = (pathname) => {
  const p = normalizar(pathname);
  return p.startsWith("/api/m/") || p.startsWith("/api/ranking/") || p === "/api/m" || p === "/api/ranking";
};

export async function onRequest({ request, next }) {
  if (bloqueado(new URL(request.url).pathname)) {
    return new Response(JSON.stringify({ erro: "Use o servidor MCP em /mcp. Documentação em /ia/." }), { status: 403, headers: { "content-type": "application/json" } });
  }
  return next();
}

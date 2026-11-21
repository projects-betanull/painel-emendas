// Arquivo de verificação do Google Search Console. Servido por Function para responder 200 no caminho
// exato com .html (o Cloudflare Pages redireciona arquivos .html estáticos para o caminho sem extensão).
export const onRequest = () =>
  new Response("google-site-verification: google8ecfe43d66f97e93.html", { headers: { "content-type": "text/html; charset=utf-8" } });

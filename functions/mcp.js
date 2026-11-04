// Rota /mcp do Cloudflare Pages: servidor MCP das emendas.
import { tratar } from "../lib/mcp.js";

export const onRequest = ({ request, env }) => tratar(request, env);

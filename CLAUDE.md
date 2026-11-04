# Painel de Emendas — contexto para o Claude Code

Site público (https://painel-emendas.pages.dev) que mostra quanto cada município recebeu em emendas parlamentares federais, de quem e para quem. Custo zero: GitHub Actions + Cloudflare Pages. Sem login. Cobrança só no MCP, via Lightning (lizard43@coinos.io).

## Como funciona
- `.github/workflows/etl.yml` roda todo dia 06:17 (Brasília): baixa os dados, testa, gera `site/` e publica no Cloudflare Pages (com `functions/`).
- `etl/download.py`: Portal da Transparência (ZIP com 3 CSVs, novas tentativas se vier HTML), municípios (IBGE; cai para cópia kelvins no GitHub, pois o IBGE bloqueia o runner), população (IBGE/SIDRA).
- `etl/normalize.py`: colunas, valores BR, localidade → código IBGE; `normalizar_favorecidos` (fonte dos totais por município, porque 83% do arquivo principal vem como "MÚLTIPLO").
- `etl/build.py`: orquestra; `etl/site.py`: páginas estáticas, Sobre (fontes, base legal, LGPD), Apoie, JSON da API e sitemap/llms.txt; `etl/cubo.py`: cubo do Explorar (+ um por UF com favorecidos); `etl/bancadas.py`: membros das bancadas (Câmara e Senado).
- `etl/site_static/`: CSS, `motor.js` (pivô compartilhado), `explorar/`, `painel/`, `gestao/`, `ia/`.
- `lib/mcp.js` + `functions/mcp.js`: servidor MCP (Streamable HTTP) em /mcp. Grátis: buscar_municipio, resumo_municipio. Pago (passe 24 h, 1000 sats): detalhes e ranking. Fatura via LNURL do endereço Lightning; conferência pela API pública de faturas do coinos; token HMAC com TOKEN_SECRET.
- `functions/api/gestao.js`: dados da página /gestao/, exige cabeçalho X-Admin-Key = ADMIN_KEY.
- `functions/api/_middleware.js`: bloqueia acesso direto a /api/m e /api/ranking (só o MCP lê, via env.ASSETS).
- `server.json` + `.github/workflows/mcp-registry.yml`: publicação no registro oficial de MCP (OIDC). Suba a versão em server.json a cada mudança relevante do MCP.
- `.github/workflows/verificar.yml`: após cada ETL, testa site, MCP, bloqueios e fatura Lightning no ar.

## Segredos (GitHub → Settings → Secrets → Actions)
CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, ADMIN_KEY. TOKEN_SECRET é derivado da ADMIN_KEY no workflow.

## Regras do projeto
- Dados sempre com fonte oficial citada e "valores reproduzidos como publicados"; nada de juízo sobre legalidade.
- CPF sempre mascarado; nenhuma página dedicada a pessoa física.
- Mudanças rápidas e econômicas; testar com `python -m pytest -q` (inclui testes em Node do motor e do MCP).
- Ambiente sandbox não acessa portais do governo: valide no GitHub Actions (`gh workflow run etl.yml`, depois ver `verificar.yml`).

## Próximos passos em aberto
- Compra de teste real do passe MCP (pagar 1000 sats e chamar ativar_acesso).
- Cadastro em diretórios de MCP com formulário (Smithery, mcp.so, Glama) e divulgação.
- Emendas 2002–2013 (Siga Brasil) e cruzamento com licitações (PNCP): adiados.

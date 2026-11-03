# Painel de Emendas — ETL (semana 1)

Baixa as emendas parlamentares do Portal da Transparência, liga cada linha ao município (código IBGE) e gera as tabelas do painel. Roda de graça todo dia no GitHub Actions.

## O que sai em `data/out/`

| Arquivo | Conteúdo |
| --- | --- |
| `fato_emenda.parquet` | Uma linha por emenda × localidade × ano, com valores empenhado / liquidado / pago, `escopo` (municipal, estadual, regional, nacional, outro), `municipio_ibge`, `uf` e `modalidade` (pix / outras) |
| `metricas_municipio.parquet` | Totais por município e ano, nº de emendas e de autores, posição no ranking da UF |
| `autores.parquet` | Totais por parlamentar (ou bancada/comissão) e ano |
| `qualidade.json` | % do valor pago que foi ligado a um município e as 20 localidades não resolvidas de maior valor |

## Rodar no seu computador

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # testes com a amostra em tests/fixtures
python -m etl.build          # baixa os dados reais e gera data/out/
```

`ANO_INICIAL=2015 python -m etl.build` muda o primeiro ano (padrão: 2020).

## Colocar no ar (custo zero)

1. Crie um repositório **público** no GitHub e suba esta pasta (Actions é ilimitado em repositório público).
2. Em **Actions**, rode o workflow "ETL diário de emendas" na mão uma vez e baixe o artefato `qualidade`.
3. Quando quiser publicar os dados: crie um bucket no Cloudflare R2 e, em **Settings → Secrets and variables → Actions**, cadastre `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` e `R2_BUCKET`. Sem esses segredos o workflow só gera e guarda o relatório.

## Pontos a conferir na primeira execução real

- **Nomes das colunas do CSV:** o código aceita variações (`etl/normalize.py`, dicionário `COLUNAS`). Se o Portal mudar um rótulo, o build para e lista as colunas encontradas; basta acrescentar o novo nome ali.
- **Formato da localidade:** os padrões reconhecidos são `CIDADE - UF`, `CIDADE/UF`, `ESTADO (UF)`, `REGIÃO (REGIÃO)` e `NACIONAL`. O `qualidade.json` mostra o que sobrou; grafias diferentes entram em `ALIASES_MUNICIPIO`.
- **Emendas Pix:** identificadas pelo nome da ação ("Transferência Especial"). Conferir com o tipo de emenda do arquivo real.
- **Acesso ao Portal a partir do GitHub:** se o download falhar por bloqueio de IP estrangeiro, a alternativa é rodar o ETL no seu computador e subir os arquivos para o R2.

## Próximas etapas

- Semana 2: Transferegov (planos de ação das Emendas Pix) e população do IBGE para valor por habitante.
- Semanas 3–4: páginas estáticas por município e parlamentar.

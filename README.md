# juscraper-mcp

Servidor [MCP](https://modelcontextprotocol.io) público do [juscraper](https://github.com/jtrecenti/juscraper):
permite que Claude (e qualquer LLM com suporte a MCP) consulte jurisprudência, processos e
comunicações de tribunais brasileiros — **somente as funcionalidades que não exigem
autenticação nem captcha**.

Mantido pelo LabDados (FGV Direito SP). Transporte: **streamable HTTP, stateless** — roda em
Azure Container Apps com scale-to-zero (a primeira chamada após idle tem cold start de alguns
segundos).

## Tools

| Tool | O que faz | Cobertura |
| --- | --- | --- |
| `listar_tribunais` | Catálogo de tribunais, capacidades e filtros | — |
| `buscar_jurisprudencia` | Jurisprudência de 2º grau (cjsg), com ementas | TJSP, TJRS, TJRJ, TJGO + 20 tribunais eSAJ |
| `buscar_julgados_primeira_instancia` | Sentenças de 1º grau (cjpg) | TJSP |
| `consultar_processo` | Partes, movimentações e metadados (cpopg/cposg) | TJSP (1º e 2º grau), TRF3, TRF5 |
| `datajud_contar_processos` | Contagem de processos na API Pública do Datajud (CNJ) | todos os tribunais |
| `datajud_listar_processos` | Metadados de processos no Datajud | todos os tribunais |
| `buscar_comunicacoes_cnj` | Comunicações processuais (DJE Nacional / Comunica CNJ) | todos os tribunais |

Fora do escopo: **TJMG** (exige resolução de captcha de imagem) e **JusBR/PDPJ** (exige
autenticação gov.br).

## Conectando um cliente

A URL do endpoint é `https://<fqdn-do-container-app>/mcp` (após o deploy, o FQDN fica em
`terraform output mcp_url`; o padrão esperado é
`https://juscraper-mcp.livelydesert-3e3e3dd8.brazilsouth.azurecontainerapps.io/mcp`).

**Claude Code:**

```bash
claude mcp add --transport http juscraper https://<fqdn>/mcp
```

**claude.ai / Claude Desktop:** Settings → Connectors → *Add custom connector* → cole a URL.

**Qualquer outro cliente MCP** (Cursor, VS Code, etc.):

```json
{
  "mcpServers": {
    "juscraper": {
      "type": "http",
      "url": "https://<fqdn>/mcp"
    }
  }
}
```

## Rodando localmente

```bash
uv sync
uv run uvicorn main:app --reload --port 8080
# ou: docker compose up --build

# smoke test (lista tools e chama listar_tribunais)
uv run python scripts/smoke_client.py
# com uma busca real no TJSP:
uv run python scripts/smoke_client.py http://localhost:8080/mcp --real

# testes e lint
uv run pytest
uv run ruff check . && uv run ruff format .
```

Python é gerido exclusivamente por `uv`. O `uv.lock` não é commitado — é resolvido no build
da imagem (mesma convenção dos services do escritorio-servicos).

## Limites e custo

O serviço é público e roda com orçamento de **R$ 200/mês**. Os guarda-corpos:

- **Infra**: `min_replicas=0` (custo zero em idle), `max_replicas=20` (bursts de sala de
  aula), 0.25 vCPU / 0.5 Gi por réplica. Budget alert (50/80/100% de R$ 200) por e-mail —
  é ele o teto de custo real; se os alertas dispararem, reduza `max_replicas` ou coloque
  autenticação.
- **Servidor**: rate limit por IP (`JUSMCP_RATE_LIMIT_MAX`, padrão 30 req/60s), no máximo
  `JUSMCP_MAX_CONCORRENCIA` scrapes simultâneos (padrão 4), timeout de 200s por tool call.
- **Por chamada**: máximo de `JUSMCP_MAX_PAGINAS` páginas (padrão 5), `JUSMCP_MAX_PROCESSOS`
  números CNJ (padrão 5), `JUSMCP_MAX_LINHAS` linhas retornadas (padrão 50) e
  `JUSMCP_MAX_CHARS_CELULA` caracteres por campo de texto (padrão 6000).
- **Tribunais**: pausa fixa de `JUSMCP_SLEEP_TIME` (padrão 1s) entre requisições, não
  configurável pelo cliente.

Se o uso estourar o orçamento, o plano é colocar autenticação por API key (a estrutura do
escritorio-servicos já tem esse fluxo pronto).

> **Uso responsável**: este serviço consulta sistemas públicos dos tribunais. Ele existe para
> apoiar pesquisa acadêmica em pequena escala. Para extrações em volume, use o pacote Python
> [`juscraper`](https://github.com/jtrecenti/juscraper) na sua própria máquina.

## Deploy

A infraestrutura reaproveita o resource group (`resgroup`), o Container Apps Environment
(`labdados-env`) e o ACR (`labdadosdevacr`) do escritorio-servicos — nenhum recurso de custo
fixo novo é criado.

### Bootstrap (uma vez)

1. **Federated credential** para este repositório no app `labdados-gh-actions`
   (o OIDC atual só cobre o repo do escritorio):

   ```bash
   az ad app federated-credential create \
     --id bc024242-86a5-4ee8-b7a7-9d3b6000b623 \
     --parameters '{
       "name": "github-juscraper-mcp",
       "issuer": "https://token.actions.githubusercontent.com",
       "subject": "repo:jtrecenti/juscraper-mcp:ref:refs/heads/main",
       "audiences": ["api://AzureADTokenExchange"]
     }'
   ```

2. **Secrets do repositório** (mesmos valores do escritorio-servicos):

   ```bash
   gh secret set AZURE_CLIENT_ID --body bc024242-86a5-4ee8-b7a7-9d3b6000b623
   gh secret set AZURE_TENANT_ID --body 46efd7f6-ba21-4344-8e77-5c995e77a627
   gh secret set AZURE_SUBSCRIPTION_ID --body 66e9297b-9531-4d75-a0e0-004b2f4f8dde
   ```

3. **Primeira imagem** (o Terraform precisa dela para criar o app):

   ```bash
   az acr build --registry labdadosdevacr --image juscraper-mcp:latest .
   ```

4. **Terraform** (state local, rodado da sua máquina):

   ```bash
   cd infra
   terraform init
   terraform apply
   terraform output mcp_url
   ```

### Dia a dia

Push na `main` (ou `gh workflow run Deploy`) builda a imagem no ACR, atualiza o Container App
e faz smoke test no `/health`. O Terraform ignora mudanças de imagem (`ignore_changes`), então
`terraform apply` não reverte deploys.

## Arquitetura

```
cliente MCP (Claude, etc.)
   │  streamable HTTP (stateless, JSON)
   ▼
Azure Container Apps  juscraper-mcp  (min=0, max=1, 0.25 vCPU)
   │  RateLimitMiddleware (por IP) → FastMCP → tools
   │  semáforo global + timeout + thread por tool call
   ▼
juscraper (requests) → eSAJ / Projudi / PJe / Datajud / Comunica CNJ
```

- `juscraper_mcp/server.py` — instância FastMCP, instruções para o modelo, `/health`.
- `juscraper_mcp/tools.py` — as 7 tools; toda chamada bloqueante roda em thread com semáforo.
- `juscraper_mcp/registry.py` — catálogo de tribunais e validação de capacidades.
- `juscraper_mcp/serialize.py` — DataFrame → JSON com truncamento (linhas e texto).
- `juscraper_mcp/ratelimit.py` — middleware ASGI de rate limit por IP.

# CLAUDE.md

Servidor MCP público do juscraper (consultas a tribunais brasileiros sem autenticação),
deployado em Azure Container Apps. Segue os padrões do repo irmão
`../escritorio-servicos` (ver o CLAUDE.md de lá). O pacote consumido é
`../juscraper` (instalado via git+https no build).

## Comandos

Python é gerido **exclusivamente por `uv`**. Nunca `pip install`. O `uv.lock`
**não é commitado** (resolvido no build da imagem).

```bash
uv sync
uv run uvicorn main:app --reload --port 8080
uv run pytest
uv run ruff check . && uv run ruff format .
uv run python scripts/smoke_client.py [url] [--real]
```

## Estrutura

- `main.py` — entrypoint ASGI (`main:app`).
- `juscraper_mcp/server.py` — FastMCP (stateless + json_response, obrigatório para
  scale-to-zero), instructions, `/health`.
- `juscraper_mcp/tools.py` — tools MCP. Regras invioláveis:
  - toda chamada ao juscraper passa por `_executar` (semáforo + thread + timeout);
  - filtros `None` não são repassados (os schemas do juscraper têm `extra="forbid"`);
  - erros viram `ToolError` com mensagem em português que oriente o modelo a corrigir.
- `juscraper_mcp/registry.py` — catálogo de tribunais. Para adicionar um tribunal novo,
  adicione a entrada aqui (e nada mais, se o juscraper já o suporta via `jus.scraper(sigla)`).
  Critério de entrada: funciona **sem autenticação e sem captcha** (TJMG e JusBR ficam fora).
- `juscraper_mcp/serialize.py` — DataFrame → JSON truncado (limites em `settings.py`).
- `infra/` — Terraform que **reusa** o RG/CAE/ACR do escritorio-servicos. Não criar recursos
  de custo fixo. Orçamento do projeto: R$ 200/mês (budget alert já configurado);
  `max_replicas=1` e 0.25 vCPU são decisões de custo — não aumentar sem discutir.

## Testes

Os testes não acessam tribunais: `tests/test_tools.py` usa sessão MCP em memória
(`mcp.shared.memory`) com `_get_scraper` monkeypatchado. Ao corrigir um bug, adicione um
teste que falhe no código antigo. Verificação real contra tribunais: só via
`scripts/smoke_client.py --real`, manualmente.

## Deploy

Push na `main` → `.github/workflows/deploy.yml` (OIDC federado, `az acr build` +
`az containerapp update` + smoke no `/health`). Bootstrap e troubleshooting no README.
Para incidentes da infra compartilhada, o RUNBOOK do escritorio-servicos é a referência.

"""Instância FastMCP e construção do app ASGI (streamable HTTP, stateless).

Stateless + json_response para funcionar atrás do ingress do Azure Container
Apps com scale-to-zero: qualquer réplica atende qualquer requisição e não há
sessão a perder no cold start.
"""

import logging

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from .ratelimit import RateLimitMiddleware
from .settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("juscraper-mcp")

INSTRUCTIONS = """\
Servidor MCP do juscraper — consultas públicas a tribunais brasileiros, sem autenticação.

Capacidades:
- Jurisprudência de 2º grau (cjsg) em 24 tribunais estaduais (TJSP, TJRS, TJRJ, TJGO e os
  eSAJ). Julgados de 1º grau (cjpg) e consulta de processos (cpopg/cposg) no TJSP; consulta
  de processos de 1º grau no TRF3 e TRF5.
- Datajud (CNJ): contagem e listagem de metadados de processos de qualquer tribunal do país.
- Comunica CNJ: comunicações processuais (intimações, citações) do DJE Nacional.

Como usar bem:
1. Comece por `listar_tribunais` para ver siglas, capacidades e filtros disponíveis.
2. Para "quantos processos sobre X", prefira `datajud_contar_processos` (rápido e barato).
3. Para teor de decisões (ementas), use `buscar_jurisprudencia` com poucos páginas e filtros
   de data/classe — cada página leva alguns segundos porque o scraping respeita pausas entre
   requisições aos tribunais.
4. Números de processo devem estar no formato CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO), com ou sem
   pontuação.
5. As respostas são truncadas para caber no contexto (máximo de linhas e de caracteres por
   campo); o payload indica quando houve truncamento. Para extrações em massa, use o pacote
   Python `juscraper` (https://github.com/jtrecenti/juscraper) em vez deste MCP.

Este serviço é mantido pelo LabDados (FGV Direito SP) com orçamento limitado: as chamadas têm
limites de páginas, linhas e taxa por IP. Use com parcimônia.
"""

mcp = FastMCP(
    name="juscraper",
    instructions=INSTRUCTIONS,
    host="0.0.0.0",
    port=settings.port,
    stateless_http=True,
    json_response=True,
)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "juscraper-mcp", "version": __version__})


@mcp.custom_route("/", methods=["GET"])
async def root(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "service": "juscraper-mcp",
            "version": __version__,
            "mcp_endpoint": "/mcp",
            "transport": "streamable-http",
            "docs": "https://github.com/jtrecenti/juscraper-mcp",
        }
    )


# Importa para registrar as tools na instância `mcp` (efeito colateral intencional).
from . import tools  # noqa: E402,F401


def create_app():
    """App ASGI final: FastMCP streamable HTTP + rate limit por IP."""
    app = mcp.streamable_http_app()
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_max,
        window_seconds=settings.rate_limit_janela,
    )
    return app

"""Smoke test contra um servidor rodando (local ou em produção).

Uso:
    uv run python scripts/smoke_client.py                       # http://localhost:8080/mcp
    uv run python scripts/smoke_client.py https://<fqdn>/mcp    # produção
    uv run python scripts/smoke_client.py <url> --real          # também faz 1 busca real no TJSP
"""

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    url = args[0] if args else "http://localhost:8080/mcp"
    real = "--real" in sys.argv

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"servidor: {init.serverInfo.name} {init.serverInfo.version}")

            tools = await session.list_tools()
            print(f"tools ({len(tools.tools)}): {', '.join(sorted(t.name for t in tools.tools))}")

            result = await session.call_tool("listar_tribunais", {})
            payload = json.loads(result.content[0].text)
            print(f"tribunais com cjsg: {sum(1 for t in payload['tribunais'].values() if t['cjsg'])}")

            if real:
                print("busca real no TJSP (1 página)...")
                result = await session.call_tool(
                    "buscar_jurisprudencia",
                    {"tribunal": "tjsp", "pesquisa": "golpe do pix", "paginas": 1},
                )
                if result.isError:
                    print(f"ERRO: {result.content[0].text[:500]}")
                    sys.exit(1)
                payload = json.loads(result.content[0].text)
                print(f"ok — {payload['linhas_retornadas']} linhas, colunas: {payload['colunas'][:6]}...")

    print("smoke test ok")


if __name__ == "__main__":
    asyncio.run(main())

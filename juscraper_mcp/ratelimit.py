"""Rate limit por IP em middleware ASGI puro.

Janela fixa em memória, por réplica. Com max_replicas>1 o limite efetivo por
IP é multiplicado pelo número de réplicas que o ingress alcançar — aceitável,
porque o objetivo é conter abuso grosseiro, não impor cota exata (o teto de
custo real é o budget alert da infra). Apenas POSTs no endpoint MCP contam;
/health fica livre para probes.
"""

import json
import time
from collections import deque

_LIMPEZA_A_CADA = 512  # requisições entre varreduras de IPs inativos


def _client_ip(scope: dict) -> str:
    headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
    fwd = headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "desconhecido"


class RateLimitMiddleware:
    def __init__(self, app, max_requests: int, window_seconds: float):
        self.app = app
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._contador = 0

    def _permitido(self, ip: str) -> bool:
        agora = time.monotonic()
        fila = self._hits.setdefault(ip, deque())
        while fila and agora - fila[0] > self.window:
            fila.popleft()
        if len(fila) >= self.max_requests:
            return False
        fila.append(agora)
        self._contador += 1
        if self._contador % _LIMPEZA_A_CADA == 0:
            vazios = [k for k, v in self._hits.items() if not v or agora - v[-1] > self.window]
            for k in vazios:
                self._hits.pop(k, None)
        return True

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST" and scope.get("path", "").startswith("/mcp"):
            if not self._permitido(_client_ip(scope)):
                body = json.dumps(
                    {
                        "error": "rate_limit",
                        "detail": (
                            f"Limite de {self.max_requests} requisições por "
                            f"{int(self.window)}s por IP excedido. Aguarde e tente novamente."
                        ),
                    }
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"retry-after", str(int(self.window)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)

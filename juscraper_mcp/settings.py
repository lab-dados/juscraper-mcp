"""Configuração via variáveis de ambiente.

Todos os limites existem para manter o serviço dentro do orçamento mensal
(R$ 200/mês) e para que as respostas caibam no contexto de um LLM. Ajuste
com cautela — limites maiores = mais tempo de CPU ativa = mais custo.
"""

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw.strip() else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    return float(raw) if raw.strip() else default


@dataclass(frozen=True)
class Settings:
    port: int
    # Limites por chamada de tool
    max_paginas: int  # páginas de busca POR CHAMADA (lote); ~4-5s/página, limitado pelo timeout
    max_pagina_inicial: int  # página de início mais alta — define a profundidade total alcançável
    max_processos: int  # números CNJ por chamada de consultar_processo
    max_linhas: int  # linhas retornadas após serialização do DataFrame
    max_chars_celula: int  # truncamento de campos de texto longos (ementas)
    # Proteção do servidor e dos tribunais
    sleep_time: float  # pausa entre requests aos tribunais (fixo, não exposto)
    max_concorrencia: int  # tool calls com scraping simultâneo
    timeout_tool: float  # segundos até abortar uma tool call
    # Rate limit por IP (janela fixa)
    rate_limit_max: int
    rate_limit_janela: float


settings = Settings(
    port=_int("PORT", 8080),
    max_paginas=_int("JUSMCP_MAX_PAGINAS", 20),
    max_pagina_inicial=_int("JUSMCP_MAX_PAGINA_INICIAL", 100),
    max_processos=_int("JUSMCP_MAX_PROCESSOS", 5),
    max_linhas=_int("JUSMCP_MAX_LINHAS", 300),
    max_chars_celula=_int("JUSMCP_MAX_CHARS_CELULA", 6000),
    sleep_time=_float("JUSMCP_SLEEP_TIME", 1.0),
    max_concorrencia=_int("JUSMCP_MAX_CONCORRENCIA", 4),
    timeout_tool=_float("JUSMCP_TIMEOUT_TOOL", 200.0),
    rate_limit_max=_int("JUSMCP_RATE_LIMIT_MAX", 30),
    rate_limit_janela=_float("JUSMCP_RATE_LIMIT_JANELA", 60.0),
)

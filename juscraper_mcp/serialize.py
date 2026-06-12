"""Conversão de DataFrames do juscraper em payloads JSON adequados a LLMs.

Os scrapers devolvem ``pd.DataFrame`` com células que podem conter NaN,
Timestamps, tipos numpy e até estruturas aninhadas (listas de movimentações
no cpopg). Aqui tudo vira JSON puro, com dois cortes para caber em contexto
de modelo: número máximo de linhas e truncamento de textos longos.
"""

from datetime import date, datetime
from typing import Any

import pandas as pd

from .settings import settings

_SUFIXO_TRUNCADO = "… [texto truncado]"


def _clean(value: Any, max_chars: int) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean(v, max_chars) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v, max_chars) for v in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):  # escalares numpy
        value = value.item()
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + _SUFIXO_TRUNCADO
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def df_para_payload(
    df: pd.DataFrame,
    *,
    max_linhas: int | None = None,
    max_chars: int | None = None,
    aviso: str | None = None,
) -> dict[str, Any]:
    """Serializa um DataFrame em dict JSON-safe com metadados de truncamento."""
    max_linhas = max_linhas or settings.max_linhas
    max_chars = max_chars or settings.max_chars_celula

    total = len(df)
    recorte = df.head(max_linhas)
    linhas = [{str(col): _clean(val, max_chars) for col, val in row.items()} for row in recorte.to_dict("records")]

    payload: dict[str, Any] = {
        "total_resultados_obtidos": total,
        "linhas_retornadas": len(linhas),
        "truncado": total > len(linhas),
        "colunas": [str(c) for c in df.columns],
        "resultados": linhas,
    }
    if total > len(linhas):
        payload["aviso_truncamento"] = (
            f"A consulta obteve {total} linhas, mas apenas {len(linhas)} foram retornadas. "
            "Refine os filtros (datas, classe, assunto) ou pagine a consulta para ver o restante."
        )
    if aviso:
        payload["aviso"] = aviso
    return payload

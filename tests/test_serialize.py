import numpy as np
import pandas as pd

from juscraper_mcp.serialize import df_para_payload


def test_payload_basico():
    df = pd.DataFrame({"processo": ["123", "456"], "ementa": ["a", "b"]})
    payload = df_para_payload(df)
    assert payload["total_resultados_obtidos"] == 2
    assert payload["linhas_retornadas"] == 2
    assert payload["truncado"] is False
    assert payload["resultados"][0] == {"processo": "123", "ementa": "a"}


def test_truncamento_de_linhas():
    df = pd.DataFrame({"x": range(100)})
    payload = df_para_payload(df, max_linhas=10)
    assert payload["total_resultados_obtidos"] == 100
    assert payload["linhas_retornadas"] == 10
    assert payload["truncado"] is True
    assert "aviso_truncamento" in payload


def test_truncamento_de_texto_longo():
    df = pd.DataFrame({"ementa": ["x" * 10_000]})
    payload = df_para_payload(df, max_chars=100)
    texto = payload["resultados"][0]["ementa"]
    assert len(texto) < 200
    assert texto.endswith("[texto truncado]")


def test_tipos_nao_json():
    df = pd.DataFrame(
        {
            "nan": [np.nan],
            "data": [pd.Timestamp("2026-01-15")],
            "inteiro_np": [np.int64(7)],
            "aninhado": [[{"mov": "sentença", "data": pd.Timestamp("2025-12-01")}]],
        }
    )
    payload = df_para_payload(df)
    linha = payload["resultados"][0]
    assert linha["nan"] is None
    assert linha["data"] == "2026-01-15T00:00:00"
    assert linha["inteiro_np"] == 7
    assert linha["aninhado"] == [{"mov": "sentença", "data": "2025-12-01T00:00:00"}]


def test_df_vazio():
    payload = df_para_payload(pd.DataFrame())
    assert payload["total_resultados_obtidos"] == 0
    assert payload["resultados"] == []

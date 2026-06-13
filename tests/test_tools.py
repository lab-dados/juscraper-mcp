"""Testes das tools via sessão MCP em memória (cliente + servidor reais, scraper falso)."""

import json

import pandas as pd
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

import juscraper_mcp.tools as tools
from juscraper_mcp.server import mcp

ESPERADAS = {
    "listar_tribunais",
    "buscar_jurisprudencia",
    "buscar_julgados_primeira_instancia",
    "consultar_processo",
    "datajud_contar_processos",
    "datajud_listar_processos",
    "buscar_comunicacoes_cnj",
}


class FakeScraper:
    """Scraper falso que registra a chamada e devolve um DataFrame pequeno."""

    def __init__(self):
        self.chamadas = []

    def _df(self):
        return pd.DataFrame({"processo": ["0000001-02.2026.8.26.0100"], "ementa": ["Apelação. Provida."]})

    def cjsg(self, **kwargs):
        self.chamadas.append(("cjsg", kwargs))
        return self._df()

    def cjpg(self, **kwargs):
        self.chamadas.append(("cjpg", kwargs))
        return self._df()

    def cpopg(self, id_cnj):
        self.chamadas.append(("cpopg", id_cnj))
        return self._df()

    def cposg(self, id_cnj):
        self.chamadas.append(("cposg", id_cnj))
        return self._df()

    def contar_processos(self, **kwargs):
        self.chamadas.append(("contar", kwargs))
        return pd.DataFrame({"tribunal": ["TJSP"], "count": [42]})

    def listar_processos(self, **kwargs):
        self.chamadas.append(("listar", kwargs))
        return self._df()

    def listar_comunicacoes(self, **kwargs):
        self.chamadas.append(("comunicacoes", kwargs))
        return self._df()


@pytest.fixture
def fake(monkeypatch):
    scraper = FakeScraper()
    monkeypatch.setattr(tools, "_get_scraper", lambda sigla: scraper)
    return scraper


def _payload(result):
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


async def test_lista_tools_e_schemas():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        resposta = await client.list_tools()
        nomes = {t.name for t in resposta.tools}
        assert nomes == ESPERADAS
        for t in resposta.tools:
            assert t.description, f"tool {t.name} sem descrição"
            assert t.annotations and t.annotations.readOnlyHint is True


async def test_listar_tribunais():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        payload = _payload(await client.call_tool("listar_tribunais", {}))
        assert "tjsp" in payload["tribunais"]
        assert "tjmg" in payload["nao_suportados"]


async def test_buscar_jurisprudencia(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        payload = _payload(
            await client.call_tool(
                "buscar_jurisprudencia",
                {"tribunal": "TJSP", "pesquisa": "golpe do pix", "paginas": 2, "classe": "Apelação"},
            )
        )
        assert payload["total_resultados_obtidos"] == 1
        metodo, kwargs = fake.chamadas[0]
        assert metodo == "cjsg"
        assert kwargs["pesquisa"] == "golpe do pix"
        assert list(kwargs["paginas"]) == [1, 2]
        assert kwargs["classe"] == "Apelação"
        assert "comarca" not in kwargs  # filtros None não são repassados


async def test_buscar_jurisprudencia_tribunal_invalido(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool("buscar_jurisprudencia", {"tribunal": "tjmg", "pesquisa": "x"})
        assert result.isError
        assert "captcha" in result.content[0].text


async def test_paginas_acima_do_limite(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool("buscar_jurisprudencia", {"tribunal": "tjsp", "pesquisa": "x", "paginas": 999})
        assert result.isError


async def test_paginacao_pagina_inicial(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        payload = _payload(
            await client.call_tool(
                "buscar_jurisprudencia",
                {"tribunal": "tjsp", "pesquisa": "x", "paginas": 3, "pagina_inicial": 10},
            )
        )
        _metodo, kwargs = fake.chamadas[0]
        assert list(kwargs["paginas"]) == [10, 11, 12]
        # hint para continuar a partir da próxima página
        assert payload["proxima_pagina_inicial"] == 13
        assert "dica_paginacao" in payload


async def test_pagina_inicial_acima_do_maximo(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool(
            "buscar_jurisprudencia", {"tribunal": "tjsp", "pesquisa": "x", "pagina_inicial": 101}
        )
        assert result.isError


async def test_comunica_pagina_inicial(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        payload = _payload(
            await client.call_tool(
                "buscar_comunicacoes_cnj",
                {"pesquisa": "usucapião", "paginas": 2, "pagina_inicial": 5},
            )
        )
        _metodo, kwargs = fake.chamadas[0]
        assert list(kwargs["paginas"]) == [5, 6]
        assert payload["proxima_pagina_inicial"] == 7


async def test_consultar_processo_segundo_grau(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        payload = _payload(
            await client.call_tool(
                "consultar_processo",
                {"numeros_processo": ["0000001-02.2026.8.26.0100"], "tribunal": "tjsp", "instancia": 2},
            )
        )
        assert payload["consulta"]["instancia"] == 2
        assert fake.chamadas[0][0] == "cposg"


async def test_consultar_processo_trf_segundo_grau_rejeitado(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool(
            "consultar_processo",
            {"numeros_processo": ["1"], "tribunal": "trf3", "instancia": 2},
        )
        assert result.isError


async def test_consultar_processo_limite_de_numeros(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool(
            "consultar_processo",
            {"numeros_processo": [str(i) for i in range(50)], "tribunal": "tjsp"},
        )
        assert result.isError


async def test_datajud_exige_tribunal_ou_numero(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool("datajud_listar_processos", {"classe": "Apelação"})
        assert result.isError
        assert "tribunal" in result.content[0].text


async def test_datajud_contar(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        payload = _payload(await client.call_tool("datajud_contar_processos", {"tribunal": "TJSP"}))
        assert payload["resultados"][0]["count"] == 42


async def test_comunica_cnj(fake):
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        payload = _payload(await client.call_tool("buscar_comunicacoes_cnj", {"pesquisa": "usucapião"}))
        assert payload["consulta"]["pesquisa"] == "usucapião"
        metodo, kwargs = fake.chamadas[0]
        assert metodo == "comunicacoes"
        assert kwargs["itens_por_pagina"] == 20

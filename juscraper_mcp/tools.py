"""Tools MCP expostas pelo servidor.

Todas as tools são somente-leitura e chamam o pacote `juscraper` (bloqueante,
baseado em requests) dentro de uma thread, sob um semáforo global e com
timeout — o event loop nunca bloqueia e o número de scrapes simultâneos fica
limitado. Erros do juscraper (validação Pydantic, HTTP, parsing) viram
``ToolError`` com a mensagem original, que costuma ser autoexplicativa o
bastante para o modelo corrigir a chamada.
"""

import asyncio
from typing import Annotated, Any, Literal

import juscraper as jus
import pandas as pd
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .registry import AGREGADORES, NAO_SUPORTADOS, TRIBUNAIS, validar_tribunal
from .serialize import df_para_payload
from .server import logger, mcp
from .settings import settings

_semaforo = asyncio.Semaphore(settings.max_concorrencia)

_READONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def _get_scraper(sigla: str) -> Any:
    """Instancia o scraper com a pausa padrão entre requests, quando o construtor aceita."""
    for kwargs in ({"sleep_time": settings.sleep_time, "verbose": 0}, {"sleep_time": settings.sleep_time}, {}):
        try:
            return jus.scraper(sigla, **kwargs)
        except TypeError:
            continue
    return jus.scraper(sigla)


async def _executar(descricao: str, fn, /, **kwargs) -> Any:
    """Roda uma chamada bloqueante do juscraper com semáforo, thread e timeout."""
    async with _semaforo:
        logger.info("tool_start %s %s", descricao, {k: v for k, v in kwargs.items() if v is not None})
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, **kwargs), timeout=settings.timeout_tool)
        except TimeoutError:
            raise ToolError(
                f"A consulta '{descricao}' excedeu o limite de {int(settings.timeout_tool)}s. "
                "Reduza o número de páginas ou refine os filtros."
            ) from None
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 — traduz qualquer falha do scraper p/ o modelo
            logger.warning("tool_error %s: %s", descricao, exc)
            raise ToolError(f"Erro ao consultar {descricao}: {str(exc)[:2000]}") from None


def _montar_paginas(pagina_inicial: int, paginas: int) -> range:
    if pagina_inicial < 1:
        raise ToolError("pagina_inicial deve ser >= 1 (a paginação dos tribunais começa em 1).")
    if not 1 <= paginas <= settings.max_paginas:
        raise ToolError(f"paginas deve estar entre 1 e {settings.max_paginas} por chamada.")
    return range(pagina_inicial, pagina_inicial + paginas)


def _filtros_nao_nulos(**filtros: Any) -> dict[str, Any]:
    return {k: v for k, v in filtros.items() if v is not None}


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_READONLY)
async def listar_tribunais() -> dict[str, Any]:
    """Lista os tribunais e agregadores disponíveis neste MCP, com as capacidades de cada um.

    Chame esta tool primeiro para descobrir: a sigla correta do tribunal, quais consultas ele
    suporta (cjsg = jurisprudência de 2º grau; cjpg = julgados de 1º grau; cpopg/cposg =
    consulta de processo de 1º/2º grau) e quais filtros o cjsg aceita.
    """
    return {
        "tribunais": TRIBUNAIS,
        "agregadores": AGREGADORES,
        "nao_suportados": NAO_SUPORTADOS,
        "limites": {
            "max_paginas_por_chamada": settings.max_paginas,
            "max_processos_por_chamada": settings.max_processos,
            "max_linhas_retornadas": settings.max_linhas,
        },
    }


# ---------------------------------------------------------------------------
# Jurisprudência (cjsg / cjpg)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_READONLY)
async def buscar_jurisprudencia(
    tribunal: Annotated[str, Field(description="Sigla do tribunal (ex.: 'tjsp', 'tjrs'). Use listar_tribunais.")],
    pesquisa: Annotated[
        str,
        Field(
            description="Termos de busca livre. A maioria dos tribunais aceita operadores: "
            'aspas para expressão exata ("dano moral"), E / OU entre termos.'
        ),
    ],
    paginas: Annotated[
        int, Field(description="Quantas páginas de resultados baixar.", ge=1, le=settings.max_paginas)
    ] = 1,
    pagina_inicial: Annotated[int, Field(description="Página inicial (1-based), para paginar.", ge=1)] = 1,
    ementa: Annotated[str | None, Field(description="Busca restrita ao texto da ementa.")] = None,
    classe: Annotated[str | None, Field(description="Filtro por classe processual (nome ou código).")] = None,
    assunto: Annotated[str | None, Field(description="Filtro por assunto (nome ou código TPU).")] = None,
    comarca: Annotated[str | None, Field(description="Filtro por comarca de origem.")] = None,
    orgao_julgador: Annotated[str | None, Field(description="Filtro por órgão julgador (câmara, turma).")] = None,
    relator: Annotated[str | None, Field(description="Filtro por relator (suportado apenas no TJRS).")] = None,
    tipo_decisao: Annotated[
        Literal["acordao", "monocratica"] | None,
        Field(description="Tipo de decisão: 'acordao' (padrão dos tribunais) ou 'monocratica'."),
    ] = None,
    data_julgamento_inicio: Annotated[str | None, Field(description="Data de julgamento mínima, YYYY-MM-DD.")] = None,
    data_julgamento_fim: Annotated[str | None, Field(description="Data de julgamento máxima, YYYY-MM-DD.")] = None,
    data_publicacao_inicio: Annotated[str | None, Field(description="Data de publicação mínima, YYYY-MM-DD.")] = None,
    data_publicacao_fim: Annotated[str | None, Field(description="Data de publicação máxima, YYYY-MM-DD.")] = None,
) -> dict[str, Any]:
    """Busca jurisprudência de 2º grau (acórdãos e decisões, com ementa) em um tribunal.

    Cada página tem em torno de 10 a 20 resultados e leva alguns segundos para ser baixada,
    porque o scraping respeita pausas entre requisições. Comece com 1 página e filtros de data;
    aumente só se precisar. Nem todo filtro existe em todo tribunal — se um filtro não for
    suportado, o erro indicará isso; consulte listar_tribunais para a lista exata.
    """
    sigla = validar_tribunal(tribunal, "cjsg")
    intervalo = _montar_paginas(pagina_inicial, paginas)
    filtros = _filtros_nao_nulos(
        ementa=ementa,
        classe=classe,
        assunto=assunto,
        comarca=comarca,
        orgao_julgador=orgao_julgador,
        relator=relator,
        tipo_decisao=tipo_decisao,
        data_julgamento_inicio=data_julgamento_inicio,
        data_julgamento_fim=data_julgamento_fim,
        data_publicacao_inicio=data_publicacao_inicio,
        data_publicacao_fim=data_publicacao_fim,
    )
    scraper = _get_scraper(sigla)
    df = await _executar(f"jurisprudência ({sigla})", scraper.cjsg, pesquisa=pesquisa, paginas=intervalo, **filtros)
    payload = df_para_payload(df)
    payload["consulta"] = {"tribunal": sigla, "pesquisa": pesquisa, "paginas": list(intervalo), **filtros}
    return payload


@mcp.tool(annotations=_READONLY)
async def buscar_julgados_primeira_instancia(
    pesquisa: Annotated[str, Field(description="Termos de busca livre no texto das decisões.")],
    paginas: Annotated[
        int, Field(description="Quantas páginas de resultados baixar.", ge=1, le=settings.max_paginas)
    ] = 1,
    pagina_inicial: Annotated[int, Field(description="Página inicial (1-based), para paginar.", ge=1)] = 1,
    data_julgamento_inicio: Annotated[str | None, Field(description="Data de julgamento mínima, YYYY-MM-DD.")] = None,
    data_julgamento_fim: Annotated[str | None, Field(description="Data de julgamento máxima, YYYY-MM-DD.")] = None,
    tribunal: Annotated[
        Literal["tjsp"], Field(description="Por enquanto, apenas 'tjsp' suporta esta consulta.")
    ] = "tjsp",
) -> dict[str, Any]:
    """Busca julgados de 1ª instância (sentenças e decisões de 1º grau) — disponível no TJSP.

    Equivale à Consulta de Julgados de Primeiro Grau (CJPG) do eSAJ. Útil para pesquisar
    sentenças, que não aparecem na busca de jurisprudência de 2º grau.
    """
    sigla = validar_tribunal(tribunal, "cjpg")
    intervalo = _montar_paginas(pagina_inicial, paginas)
    filtros = _filtros_nao_nulos(
        data_julgamento_inicio=data_julgamento_inicio,
        data_julgamento_fim=data_julgamento_fim,
    )
    scraper = _get_scraper(sigla)
    df = await _executar(
        f"julgados de 1º grau ({sigla})", scraper.cjpg, pesquisa=pesquisa, paginas=intervalo, **filtros
    )
    payload = df_para_payload(df)
    payload["consulta"] = {"tribunal": sigla, "pesquisa": pesquisa, "paginas": list(intervalo), **filtros}
    return payload


# ---------------------------------------------------------------------------
# Consulta de processos (cpopg / cposg)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_READONLY)
async def consultar_processo(
    numeros_processo: Annotated[
        list[str],
        Field(
            description="Números CNJ dos processos (NNNNNNN-DD.AAAA.J.TR.OOOO, com ou sem pontuação). "
            "Máximo de alguns números por chamada — consultas grandes devem usar o pacote juscraper."
        ),
    ],
    tribunal: Annotated[
        Literal["tjsp", "trf3", "trf5"],
        Field(description="Tribunal onde consultar: 'tjsp' (1º e 2º grau), 'trf3' ou 'trf5' (1º grau)."),
    ] = "tjsp",
    instancia: Annotated[
        Literal[1, 2],
        Field(description="1 = primeiro grau (cpopg); 2 = segundo grau (cposg, apenas TJSP)."),
    ] = 1,
) -> dict[str, Any]:
    """Consulta os dados públicos de processos judiciais: partes, movimentações e metadados.

    Cada linha do resultado é um registro do processo (a estrutura varia por tribunal — pode
    haver várias linhas por processo, uma por movimentação ou parte). Para metadados rápidos de
    qualquer tribunal do país, considere datajud_listar_processos, que é mais leve.
    """
    if not numeros_processo:
        raise ToolError("Informe ao menos um número de processo no formato CNJ.")
    if len(numeros_processo) > settings.max_processos:
        raise ToolError(f"No máximo {settings.max_processos} processos por chamada.")
    metodo = "cposg" if instancia == 2 else "cpopg"
    sigla = validar_tribunal(tribunal, metodo)

    scraper = _get_scraper(sigla)
    if metodo == "cposg":

        def _consultar_segundo_grau(numeros: list[str]) -> pd.DataFrame:
            partes = [scraper.cposg(n) for n in numeros]
            return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()

        df = await _executar(f"processos 2º grau ({sigla})", _consultar_segundo_grau, numeros=numeros_processo)
    else:
        df = await _executar(f"processos 1º grau ({sigla})", scraper.cpopg, id_cnj=numeros_processo)

    payload = df_para_payload(df)
    payload["consulta"] = {"tribunal": sigla, "instancia": instancia, "numeros_processo": numeros_processo}
    return payload


# ---------------------------------------------------------------------------
# Datajud (CNJ)
# ---------------------------------------------------------------------------

_DESC_TRIBUNAL_DATAJUD = "Sigla do tribunal em maiúsculas, como usada pelo CNJ (ex.: 'TJSP', 'TRF1', 'TST', 'STJ')."


def _aviso_erros_datajud(df: pd.DataFrame) -> str | None:
    """A API pública do Datajud é instável: falhas por tribunal viram coluna 'error' no DataFrame."""
    if "error" in df.columns and df["error"].notna().any():
        return (
            "A API pública do Datajud falhou para parte da consulta (coluna 'error'). "
            "Causas comuns: instabilidade/timeout do CNJ (tente de novo) ou filtro inválido — "
            "'classe' e 'assuntos' exigem códigos numéricos das Tabelas Processuais Unificadas."
        )
    return None


def _validar_filtro_datajud(tribunal: str | None, numero_processo: str | None) -> None:
    if not tribunal and not numero_processo:
        raise ToolError(
            "Informe 'tribunal' (ex.: 'TJSP') ou 'numero_processo'. Sem isso a consulta varreria "
            "todos os tribunais do país, o que não é permitido neste MCP."
        )


@mcp.tool(annotations=_READONLY)
async def datajud_contar_processos(
    tribunal: Annotated[str | None, Field(description=_DESC_TRIBUNAL_DATAJUD)] = None,
    numero_processo: Annotated[
        str | None, Field(description="Número CNJ do processo — o tribunal é deduzido dos dígitos.")
    ] = None,
    classe: Annotated[
        str | None,
        Field(
            description="Código NUMÉRICO da classe processual nas Tabelas Processuais Unificadas do CNJ "
            "(ex.: '436' = Apelação Cível). Nomes por extenso NÃO funcionam — a API rejeita texto."
        ),
    ] = None,
    assuntos: Annotated[
        list[str] | None,
        Field(
            description="Códigos NUMÉRICOS de assunto nas Tabelas Processuais Unificadas do CNJ "
            "(ex.: ['1156'] = usucapião). Nomes por extenso NÃO funcionam — a API rejeita texto."
        ),
    ] = None,
    ano_ajuizamento: Annotated[
        int | None, Field(description="Ano de ajuizamento. Mutuamente exclusivo com as datas de ajuizamento.")
    ] = None,
    data_ajuizamento_inicio: Annotated[str | None, Field(description="Data de ajuizamento mínima, YYYY-MM-DD.")] = None,
    data_ajuizamento_fim: Annotated[str | None, Field(description="Data de ajuizamento máxima, YYYY-MM-DD.")] = None,
    orgao_julgador: Annotated[str | None, Field(description="Filtro por órgão julgador.")] = None,
) -> dict[str, Any]:
    """Conta processos na API Pública do Datajud (CNJ) sem baixar os documentos — rápido e barato.

    Ideal para perguntas do tipo "quantos processos sobre X existem no tribunal Y". O Datajud
    cobre todos os tribunais do país (exceto STF) com metadados processuais; o filtro é por
    data de AJUIZAMENTO, não de julgamento.
    """
    _validar_filtro_datajud(tribunal, numero_processo)
    filtros = _filtros_nao_nulos(
        tribunal=tribunal,
        numero_processo=numero_processo,
        classe=classe,
        assuntos=assuntos,
        ano_ajuizamento=ano_ajuizamento,
        data_ajuizamento_inicio=data_ajuizamento_inicio,
        data_ajuizamento_fim=data_ajuizamento_fim,
        orgao_julgador=orgao_julgador,
    )
    scraper = _get_scraper("datajud")
    df = await _executar("Datajud (contagem)", scraper.contar_processos, **filtros)
    payload = df_para_payload(df, aviso=_aviso_erros_datajud(df))
    payload["consulta"] = filtros
    return payload


@mcp.tool(annotations=_READONLY)
async def datajud_listar_processos(
    tribunal: Annotated[str | None, Field(description=_DESC_TRIBUNAL_DATAJUD)] = None,
    numero_processo: Annotated[
        str | None, Field(description="Número CNJ do processo — o tribunal é deduzido dos dígitos.")
    ] = None,
    classe: Annotated[
        str | None,
        Field(
            description="Código NUMÉRICO da classe processual nas Tabelas Processuais Unificadas do CNJ "
            "(ex.: '436' = Apelação Cível). Nomes por extenso NÃO funcionam — a API rejeita texto."
        ),
    ] = None,
    assuntos: Annotated[
        list[str] | None,
        Field(
            description="Códigos NUMÉRICOS de assunto nas Tabelas Processuais Unificadas do CNJ "
            "(ex.: ['1156'] = usucapião). Nomes por extenso NÃO funcionam — a API rejeita texto."
        ),
    ] = None,
    ano_ajuizamento: Annotated[
        int | None, Field(description="Ano de ajuizamento. Mutuamente exclusivo com as datas de ajuizamento.")
    ] = None,
    data_ajuizamento_inicio: Annotated[str | None, Field(description="Data de ajuizamento mínima, YYYY-MM-DD.")] = None,
    data_ajuizamento_fim: Annotated[str | None, Field(description="Data de ajuizamento máxima, YYYY-MM-DD.")] = None,
    orgao_julgador: Annotated[str | None, Field(description="Filtro por órgão julgador.")] = None,
    paginas: Annotated[int, Field(description="Quantas páginas baixar.", ge=1, le=settings.max_paginas)] = 1,
    tamanho_pagina: Annotated[int, Field(description="Processos por página na API (10 a 500).", ge=10, le=500)] = 100,
    mostrar_movs: Annotated[
        bool, Field(description="Incluir movimentações de cada processo (aumenta muito a resposta).")
    ] = False,
) -> dict[str, Any]:
    """Lista metadados de processos na API Pública do Datajud (CNJ): número, classe, assuntos,
    órgão julgador, datas e, opcionalmente, movimentações.

    O Datajud não tem o teor das decisões — para ementas use buscar_jurisprudencia. A resposta é
    truncada no número máximo de linhas do servidor; para volumes grandes use o pacote juscraper.
    """
    _validar_filtro_datajud(tribunal, numero_processo)
    if not 1 <= paginas <= settings.max_paginas:
        raise ToolError(f"paginas deve estar entre 1 e {settings.max_paginas} por chamada.")
    filtros = _filtros_nao_nulos(
        tribunal=tribunal,
        numero_processo=numero_processo,
        classe=classe,
        assuntos=assuntos,
        ano_ajuizamento=ano_ajuizamento,
        data_ajuizamento_inicio=data_ajuizamento_inicio,
        data_ajuizamento_fim=data_ajuizamento_fim,
        orgao_julgador=orgao_julgador,
    )
    scraper = _get_scraper("datajud")
    df = await _executar(
        "Datajud (listagem)",
        scraper.listar_processos,
        paginas=range(1, paginas + 1),
        tamanho_pagina=tamanho_pagina,
        mostrar_movs=mostrar_movs,
        **filtros,
    )
    payload = df_para_payload(df)
    payload["consulta"] = {**filtros, "paginas": paginas, "tamanho_pagina": tamanho_pagina}
    return payload


# ---------------------------------------------------------------------------
# Comunica CNJ
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_READONLY)
async def buscar_comunicacoes_cnj(
    pesquisa: Annotated[
        str, Field(description="Termo buscado no texto das comunicações (intimações, citações, editais).")
    ],
    data_disponibilizacao_inicio: Annotated[
        str | None, Field(description="Data de disponibilização mínima, YYYY-MM-DD.")
    ] = None,
    data_disponibilizacao_fim: Annotated[
        str | None, Field(description="Data de disponibilização máxima, YYYY-MM-DD.")
    ] = None,
    paginas: Annotated[int, Field(description="Quantas páginas baixar.", ge=1, le=settings.max_paginas)] = 1,
    itens_por_pagina: Annotated[int, Field(description="Itens por página na API (1 a 100).", ge=1, le=100)] = 20,
) -> dict[str, Any]:
    """Busca comunicações processuais no Comunica CNJ (Diário de Justiça Eletrônico Nacional).

    Cobre intimações, citações e editais publicados pelos tribunais. Cada item traz o número do
    processo, o tribunal de origem, o texto da comunicação e o link oficial. Bom para monitorar
    publicações recentes sobre um tema, nome ou número de processo.
    """
    if not 1 <= paginas <= settings.max_paginas:
        raise ToolError(f"paginas deve estar entre 1 e {settings.max_paginas} por chamada.")
    filtros = _filtros_nao_nulos(
        data_disponibilizacao_inicio=data_disponibilizacao_inicio,
        data_disponibilizacao_fim=data_disponibilizacao_fim,
    )
    scraper = _get_scraper("comunica_cnj")
    df = await _executar(
        "Comunica CNJ",
        scraper.listar_comunicacoes,
        pesquisa=pesquisa,
        paginas=range(1, paginas + 1),
        itens_por_pagina=itens_por_pagina,
        **filtros,
    )
    payload = df_para_payload(df)
    payload["consulta"] = {"pesquisa": pesquisa, "paginas": paginas, "itens_por_pagina": itens_por_pagina, **filtros}
    return payload

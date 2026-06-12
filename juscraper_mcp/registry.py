"""Catálogo dos tribunais expostos pelo MCP e suas capacidades.

Só entram aqui tribunais cujo acesso no juscraper funciona **sem
autenticação e sem resolver captcha**. A lista de filtros é informativa
(aparece em ``listar_tribunais``); a validação real é feita pelos schemas
Pydantic do próprio juscraper (``extra="forbid"``), então um filtro não
suportado vira erro com mensagem clara em vez de ser ignorado.
"""

# Filtros aceitos pelo cjsg dos tribunais eSAJ "puros"
_FILTROS_ESAJ = [
    "ementa",
    "classe",
    "assunto",
    "comarca",
    "orgao_julgador",
    "tipo_decisao",
    "data_julgamento_inicio",
    "data_julgamento_fim",
    "data_publicacao_inicio",
    "data_publicacao_fim",
]

_ESAJ = {
    "tjac": "Tribunal de Justiça do Acre",
    "tjal": "Tribunal de Justiça de Alagoas",
    "tjam": "Tribunal de Justiça do Amazonas",
    "tjap": "Tribunal de Justiça do Amapá",
    "tjba": "Tribunal de Justiça da Bahia",
    "tjce": "Tribunal de Justiça do Ceará",
    "tjdft": "Tribunal de Justiça do Distrito Federal e dos Territórios",
    "tjes": "Tribunal de Justiça do Espírito Santo",
    "tjms": "Tribunal de Justiça de Mato Grosso do Sul",
    "tjmt": "Tribunal de Justiça de Mato Grosso",
    "tjpa": "Tribunal de Justiça do Pará",
    "tjpb": "Tribunal de Justiça da Paraíba",
    "tjpe": "Tribunal de Justiça de Pernambuco",
    "tjpi": "Tribunal de Justiça do Piauí",
    "tjpr": "Tribunal de Justiça do Paraná",
    "tjrn": "Tribunal de Justiça do Rio Grande do Norte",
    "tjro": "Tribunal de Justiça de Rondônia",
    "tjrr": "Tribunal de Justiça de Roraima",
    "tjsc": "Tribunal de Justiça de Santa Catarina",
    "tjto": "Tribunal de Justiça do Tocantins",
}

TRIBUNAIS: dict[str, dict] = {
    "tjsp": {
        "nome": "Tribunal de Justiça de São Paulo",
        "cjsg": True,
        "cjpg": True,
        "cpopg": True,
        "cposg": True,
        "filtros_cjsg": [
            "ementa",
            "classe",
            "assunto",
            "comarca",
            "orgao_julgador",
            "tipo_decisao",
            "data_julgamento_inicio",
            "data_julgamento_fim",
        ],
        "observacoes": "Tribunal mais completo: jurisprudência de 2º grau (cjsg), julgados de "
        "1º grau (cjpg) e consulta de processos nos dois graus.",
    },
    **{
        sigla: {
            "nome": nome,
            "cjsg": True,
            "cjpg": False,
            "cpopg": False,
            "cposg": False,
            "filtros_cjsg": _FILTROS_ESAJ,
            "observacoes": "Jurisprudência de 2º grau via eSAJ.",
        }
        for sigla, nome in _ESAJ.items()
    },
    "tjgo": {
        "nome": "Tribunal de Justiça de Goiás",
        "cjsg": True,
        "cjpg": False,
        "cpopg": False,
        "cposg": False,
        "filtros_cjsg": ["data_publicacao_inicio", "data_publicacao_fim"],
        "observacoes": "Busca no Projudi. O texto da decisão vem na coluna 'texto' (não há 'ementa'). "
        "Não há filtro por data de julgamento, apenas por data de publicação.",
    },
    "tjrj": {
        "nome": "Tribunal de Justiça do Rio de Janeiro",
        "cjsg": True,
        "cjpg": False,
        "cpopg": False,
        "cposg": False,
        "filtros_cjsg": [],
        "observacoes": "Aceita apenas pesquisa livre e paginação via este MCP.",
    },
    "tjrs": {
        "nome": "Tribunal de Justiça do Rio Grande do Sul",
        "cjsg": True,
        "cjpg": False,
        "cpopg": False,
        "cposg": False,
        "filtros_cjsg": [
            "classe",
            "assunto",
            "orgao_julgador",
            "relator",
            "data_julgamento_inicio",
            "data_julgamento_fim",
            "data_publicacao_inicio",
            "data_publicacao_fim",
        ],
        "observacoes": "Busca no acervo de jurisprudência do TJRS.",
    },
    "trf3": {
        "nome": "Tribunal Regional Federal da 3ª Região (SP/MS)",
        "cjsg": False,
        "cjpg": False,
        "cpopg": True,
        "cposg": False,
        "filtros_cjsg": [],
        "observacoes": "Apenas consulta de processos de 1º grau (PJe).",
    },
    "trf5": {
        "nome": "Tribunal Regional Federal da 5ª Região (PE/CE/RN/PB/AL/SE)",
        "cjsg": False,
        "cjpg": False,
        "cpopg": True,
        "cposg": False,
        "filtros_cjsg": [],
        "observacoes": "Apenas consulta de processos de 1º grau (PJe).",
    },
}

NAO_SUPORTADOS: dict[str, str] = {
    "tjmg": "Exige resolução de captcha de imagem (dependência txtcaptcha) — fora do escopo deste MCP público.",
    "jusbr": "Exige autenticação gov.br (token JWT do PDPJ) — fora do escopo deste MCP público.",
}

AGREGADORES: dict[str, str] = {
    "datajud": "API Pública do Datajud (CNJ) — metadados de processos de todos os tribunais. "
    "Tools: datajud_contar_processos, datajud_listar_processos.",
    "comunica_cnj": "Comunica CNJ — comunicações processuais (intimações, citações) publicadas no "
    "Diário de Justiça Eletrônico Nacional. Tool: buscar_comunicacoes_cnj.",
}


def validar_tribunal(sigla: str, metodo: str) -> str:
    """Normaliza a sigla e garante que o tribunal suporta o método.

    Retorna a sigla normalizada (minúsculas) ou levanta ``ValueError`` com
    mensagem orientando o modelo a corrigir a chamada.
    """
    sigla_norm = sigla.strip().lower()
    if sigla_norm in NAO_SUPORTADOS:
        raise ValueError(f"Tribunal '{sigla_norm}' não está disponível neste MCP: {NAO_SUPORTADOS[sigla_norm]}")
    info = TRIBUNAIS.get(sigla_norm)
    if info is None:
        disponiveis = ", ".join(sorted(TRIBUNAIS))
        raise ValueError(f"Tribunal '{sigla}' desconhecido. Tribunais disponíveis: {disponiveis}.")
    if not info.get(metodo, False):
        suportados = ", ".join(sorted(s for s, i in TRIBUNAIS.items() if i.get(metodo)))
        raise ValueError(
            f"Tribunal '{sigla_norm}' não suporta '{metodo}' neste MCP. Tribunais com {metodo}: {suportados}."
        )
    return sigla_norm

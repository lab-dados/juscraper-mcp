import pytest

from juscraper_mcp.registry import TRIBUNAIS, validar_tribunal


def test_normaliza_sigla():
    assert validar_tribunal(" TJSP ", "cjsg") == "tjsp"


def test_tribunal_desconhecido():
    with pytest.raises(ValueError, match="desconhecido"):
        validar_tribunal("tjxx", "cjsg")


def test_tribunal_nao_suportado_tem_motivo():
    with pytest.raises(ValueError, match="captcha"):
        validar_tribunal("tjmg", "cjsg")
    with pytest.raises(ValueError, match="autenticação"):
        validar_tribunal("jusbr", "cpopg")


def test_metodo_nao_suportado_lista_alternativas():
    with pytest.raises(ValueError, match="tjsp"):
        validar_tribunal("tjac", "cpopg")


def test_capacidades_minimas():
    assert TRIBUNAIS["tjsp"]["cposg"] is True
    assert TRIBUNAIS["trf3"]["cpopg"] is True
    assert TRIBUNAIS["trf5"]["cpopg"] is True
    # 24 tribunais com cjsg: tjsp + 20 eSAJ + tjgo + tjrj + tjrs
    assert sum(1 for i in TRIBUNAIS.values() if i["cjsg"]) == 24

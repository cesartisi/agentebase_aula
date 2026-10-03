"""Testes unitários das ferramentas e do executor — sem rede, sem modelo."""

import json

import pytest

import agent

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        (1234, 5678, 6912),
        (0, 0, 0),
        (-5, 3, -2),
        (0.1, 0.2, pytest.approx(0.3)),
        (1e12, 1, 1_000_000_000_001),
    ],
)
def test_somar(a, b, esperado):
    assert agent.somar(a, b) == {"resultado": esperado}


def test_executar_ferramenta_devolve_json_string():
    saida = agent.executar_ferramenta("somar", {"a": 2, "b": 3})
    assert isinstance(saida, str)
    assert json.loads(saida) == {"resultado": 5}


def test_executar_ferramenta_inexistente_vira_erro_e_nao_crash():
    saida = json.loads(agent.executar_ferramenta("apagar_tudo", {}))
    assert "erro" in saida
    assert "apagar_tudo" in saida["erro"]


def test_executar_ferramenta_com_argumentos_errados_vira_erro():
    saida = json.loads(agent.executar_ferramenta("somar", {"a": 1}))  # falta "b"
    assert "erro" in saida
    assert "somar" in saida["erro"]


def test_executar_ferramenta_preserva_acentos():
    """ensure_ascii=False: o modelo deve ler 'não', não 'n\\u00e3o'."""
    saida = agent.executar_ferramenta("inexistente", {})
    assert "não" in saida

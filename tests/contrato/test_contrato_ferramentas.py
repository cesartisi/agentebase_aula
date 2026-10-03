"""Contrato entre as duas metades de uma ferramenta.

A DECLARAÇÃO (o JSON que o modelo lê) e a FUNÇÃO (o Python que roda) são
escritas separadamente. Se divergirem, o modelo chama com argumentos que a
função não aceita — e o erro só aparece em conversa. Estes testes pegam
isso no CI.
"""

import inspect

import pytest

import agent

pytestmark = pytest.mark.contrato

TIPOS_JSON = {"number", "integer", "string", "boolean", "array", "object"}


def _declaracoes():
    return {f["function"]["name"]: f["function"] for f in agent.FERRAMENTAS}


def test_toda_declaracao_tem_executor_e_vice_versa():
    assert set(_declaracoes()) == set(agent.EXECUTORES)


def test_nomes_de_ferramenta_sao_unicos():
    nomes = [f["function"]["name"] for f in agent.FERRAMENTAS]
    assert len(nomes) == len(set(nomes))


@pytest.mark.parametrize("nome", sorted(agent.EXECUTORES))
def test_declaracao_bem_formada(nome):
    decl = _declaracoes()[nome]
    ferramenta = next(f for f in agent.FERRAMENTAS if f["function"]["name"] == nome)

    assert ferramenta["type"] == "function"
    # A description é a interface com o modelo: vaga = ferramenta ignorada.
    assert len(decl["description"].split()) >= 4, "description curta demais para o modelo decidir"

    params = decl["parameters"]
    assert params["type"] == "object"
    assert set(params["required"]) <= set(params["properties"])
    for nome_param, spec in params["properties"].items():
        assert spec.get("type") in TIPOS_JSON, f"{nome}.{nome_param}: tipo JSON inválido"
        assert spec.get("description"), f"{nome}.{nome_param}: parâmetro sem description"


@pytest.mark.parametrize("nome", sorted(agent.EXECUTORES))
def test_assinatura_python_bate_com_a_declaracao(nome):
    decl = _declaracoes()[nome]["parameters"]
    assinatura = inspect.signature(agent.EXECUTORES[nome])

    params_py = set(assinatura.parameters)
    obrigatorios_py = {p.name for p in assinatura.parameters.values() if p.default is inspect.Parameter.empty}

    assert set(decl["properties"]) == params_py
    assert set(decl["required"]) == obrigatorios_py


@pytest.mark.parametrize("nome", sorted(agent.EXECUTORES))
def test_ferramenta_devolve_dict_serializavel(nome):
    """O executor faz json.dumps do retorno: tem que ser dict serializável."""
    exemplos = {"number": 1, "integer": 1, "string": "x", "boolean": True, "array": [], "object": {}}
    props = _declaracoes()[nome]["parameters"]["properties"]
    argumentos = {k: exemplos[v["type"]] for k, v in props.items()}

    retorno = agent.EXECUTORES[nome](**argumentos)

    assert isinstance(retorno, dict)
    assert "erro" not in agent.executar_ferramenta(nome, argumentos)

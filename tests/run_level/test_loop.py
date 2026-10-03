"""Testes de execução (run-level) do loop do agente.

Aqui `responder()` roda de verdade, ponta a ponta, mas com um modelo falso
que segue um roteiro. Assim dá para testar o loop — pedir ferramenta,
executar, devolver, repetir — sem gastar token e sem resposta aleatória.
"""

import json

import pytest

import agent
from tests.conftest import resposta_ferramenta, resposta_texto

pytestmark = pytest.mark.run_level


def _historico_inicial(pergunta="quanto é 1234 mais 5678?"):
    return [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": pergunta},
    ]


def test_resposta_direta_em_texto(modelo_falso):
    falso = modelo_falso([resposta_texto("Olá!")])
    mensagens = _historico_inicial("oi")

    assert agent.responder(mensagens) == "Olá!"
    assert len(falso.chamadas) == 1
    assert mensagens[-1] == {"role": "assistant", "content": "Olá!"}


def test_loop_chama_ferramenta_e_devolve_resultado_ao_modelo(modelo_falso):
    falso = modelo_falso(
        [
            resposta_ferramenta(("somar", {"a": 1234, "b": 5678})),
            resposta_texto("O resultado é 6912."),
        ]
    )
    mensagens = _historico_inicial()

    resposta = agent.responder(mensagens)

    assert resposta == "O resultado é 6912."
    assert len(falso.chamadas) == 2
    # Histórico: system, user, assistant(tool_calls), tool, assistant(texto)
    assert [m["role"] for m in mensagens] == ["system", "user", "assistant", "tool", "assistant"]
    tool_msg = mensagens[3]
    assert tool_msg["tool_call_id"] == "call_0"
    assert json.loads(tool_msg["content"]) == {"resultado": 6912}
    # A segunda chamada ao modelo já leva o resultado da ferramenta.
    assert falso.chamadas[1]["messages"][-1]["role"] == "tool"


def test_varias_ferramentas_na_mesma_resposta(modelo_falso):
    modelo_falso(
        [
            resposta_ferramenta(("somar", {"a": 1, "b": 2}), ("somar", {"a": 10, "b": 20})),
            resposta_texto("3 e 30."),
        ]
    )
    mensagens = _historico_inicial()

    agent.responder(mensagens)

    tools = [m for m in mensagens if m["role"] == "tool"]
    assert [t["tool_call_id"] for t in tools] == ["call_0", "call_1"]
    assert [json.loads(t["content"])["resultado"] for t in tools] == [3, 30]


def test_envia_ferramentas_modelo_e_temperatura(modelo_falso):
    falso = modelo_falso([resposta_texto("ok")])
    agent.responder(_historico_inicial())

    chamada = falso.chamadas[0]
    assert chamada["model"] == agent.MODELO
    assert chamada["tools"] == agent.FERRAMENTAS
    assert chamada["temperature"] == agent.TEMPERATURA


def test_ferramenta_inexistente_nao_derruba_o_loop(modelo_falso):
    modelo_falso([resposta_ferramenta(("nao_existe", {})), resposta_texto("Não consegui.")])
    mensagens = _historico_inicial()

    assert agent.responder(mensagens) == "Não consegui."
    assert "erro" in json.loads(mensagens[3]["content"])


def test_argumentos_json_invalidos_nao_derrubam_o_loop(modelo_falso):
    modelo_falso([resposta_ferramenta(("somar", "{isso não é json")), resposta_texto("Tentei.")])
    mensagens = _historico_inicial()

    assert agent.responder(mensagens) == "Tentei."
    assert "erro" in json.loads(mensagens[3]["content"])


def test_limite_de_iteracoes(modelo_falso, monkeypatch):
    monkeypatch.setattr(agent, "MAX_ITERACOES", 3)
    falso = modelo_falso([resposta_ferramenta(("somar", {"a": 1, "b": 1}))] * 3)

    resposta = agent.responder(_historico_inicial())

    assert "limite de iterações" in resposta
    assert len(falso.chamadas) == 3


def test_verboso_imprime_a_ferramenta(modelo_falso, capsys):
    modelo_falso([resposta_ferramenta(("somar", {"a": 1, "b": 2})), resposta_texto("3")])
    agent.responder(_historico_inicial(), verboso=True)
    assert "[ferramenta] somar" in capsys.readouterr().out


def test_historico_preservado_entre_turnos(modelo_falso):
    falso = modelo_falso([resposta_texto("Primeira."), resposta_texto("Segunda.")])
    mensagens = _historico_inicial("oi")
    agent.responder(mensagens)
    mensagens.append({"role": "user", "content": "e agora?"})
    agent.responder(mensagens)

    enviadas = falso.chamadas[1]["messages"]
    assert [m["role"] for m in enviadas] == ["system", "user", "assistant", "user"]


def test_main_sem_chave_sai_com_erro(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as saida:
        agent.main()
    assert saida.value.code == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out


def test_main_conversa_e_sai(modelo_falso, monkeypatch, capsys):
    modelo_falso([resposta_ferramenta(("somar", {"a": 2, "b": 2})), resposta_texto("Dá 4.")])
    entradas = iter(["", "quanto é 2 mais 2?", "/sair"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(entradas))

    agent.main()

    saida = capsys.readouterr().out
    assert "agente> Dá 4." in saida
    assert "Até mais." in saida

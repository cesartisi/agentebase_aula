"""Testes de execução (run-level) do loop do agente.

Aqui `responder()` roda de verdade, ponta a ponta, mas com um modelo falso
que segue um roteiro. Assim dá para testar o loop — pedir ferramenta,
executar, devolver, repetir — sem gastar token e sem resposta aleatória.
"""

import json

import pytest

import agent
from tests.conftest import resposta_ferramenta, resposta_recusa, resposta_texto

pytestmark = pytest.mark.run_level


def _historico_inicial(pergunta="quanto é 1234 mais 5678?"):
    return [{"role": "user", "content": pergunta}]


def _resultados(mensagens):
    """Todos os blocos tool_result que o agente devolveu ao modelo."""
    return [
        bloco
        for m in mensagens
        if m["role"] == "user" and isinstance(m["content"], list)
        for bloco in m["content"]
    ]


def test_resposta_direta_em_texto(modelo_falso):
    falso = modelo_falso([resposta_texto("Olá!")])
    mensagens = _historico_inicial("oi")

    assert agent.responder(mensagens) == "Olá!"
    assert len(falso.chamadas) == 1
    assert [m["role"] for m in mensagens] == ["user", "assistant"]


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
    # Histórico: user, assistant(tool_use), user(tool_result), assistant(texto)
    assert [m["role"] for m in mensagens] == ["user", "assistant", "user", "assistant"]
    [resultado] = _resultados(mensagens)
    assert resultado["type"] == "tool_result"
    assert resultado["tool_use_id"] == "toolu_0"
    assert resultado["is_error"] is False
    assert json.loads(resultado["content"]) == {"resultado": 6912}
    # A segunda chamada ao modelo já leva o resultado da ferramenta.
    assert falso.chamadas[1]["messages"][-1]["content"][0]["type"] == "tool_result"


def test_varias_ferramentas_voltam_numa_mensagem_so(modelo_falso):
    modelo_falso(
        [
            resposta_ferramenta(("somar", {"a": 1, "b": 2}), ("somar", {"a": 10, "b": 20})),
            resposta_texto("3 e 30."),
        ]
    )
    mensagens = _historico_inicial()

    agent.responder(mensagens)

    assert [m["role"] for m in mensagens] == ["user", "assistant", "user", "assistant"]
    resultados = _resultados(mensagens)
    assert [r["tool_use_id"] for r in resultados] == ["toolu_0", "toolu_1"]
    assert [json.loads(r["content"])["resultado"] for r in resultados] == [3, 30]


def test_envia_sistema_ferramentas_modelo_e_esforco(modelo_falso):
    falso = modelo_falso([resposta_texto("ok")])
    agent.responder(_historico_inicial())

    chamada = falso.chamadas[0]
    assert chamada["model"] == agent.MODELO
    assert chamada["system"] == agent.carregar_contexto()
    assert chamada["tools"] == agent.FERRAMENTAS
    assert chamada["output_config"] == {"effort": agent.ESFORCO}
    assert chamada["max_tokens"] == agent.MAX_TOKENS
    assert chamada["fallbacks"] == "default"
    assert "temperature" not in chamada  # o modelo recusa temperatura


def test_ferramenta_inexistente_vira_erro_e_nao_derruba_o_loop(modelo_falso):
    modelo_falso([resposta_ferramenta(("nao_existe", {})), resposta_texto("Não consegui.")])
    mensagens = _historico_inicial()

    assert agent.responder(mensagens) == "Não consegui."
    [resultado] = _resultados(mensagens)
    assert resultado["is_error"] is True
    assert "erro" in json.loads(resultado["content"])


def test_argumentos_errados_viram_erro_e_nao_derrubam_o_loop(modelo_falso):
    modelo_falso([resposta_ferramenta(("somar", {"a": 1})), resposta_texto("Tentei.")])
    mensagens = _historico_inicial()

    assert agent.responder(mensagens) == "Tentei."
    [resultado] = _resultados(mensagens)
    assert resultado["is_error"] is True


def test_recusa_do_modelo(modelo_falso):
    modelo_falso([resposta_recusa()])
    mensagens = _historico_inicial("pedido proibido")

    assert agent.responder(mensagens) == "Não posso ajudar com esse pedido."
    assert [m["role"] for m in mensagens] == ["user"]  # nada de assistente vazio


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
    assert [m["role"] for m in enviadas] == ["user", "assistant", "user"]


def test_main_sem_chave_sai_com_erro(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as saida:
        agent.main()
    assert saida.value.code == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_main_conversa_e_sai(modelo_falso, monkeypatch, capsys):
    modelo_falso([resposta_ferramenta(("somar", {"a": 2, "b": 2})), resposta_texto("Dá 4.")])
    entradas = iter(["", "quanto é 2 mais 2?", "/sair"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(entradas))

    agent.main()

    saida = capsys.readouterr().out
    assert "agente> Dá 4." in saida
    assert "Até mais." in saida


def test_main_descarta_turno_que_falhou(modelo_falso, monkeypatch, capsys):
    """Se o modelo falhar no meio, o histórico volta ao estado de antes do turno."""
    falso = modelo_falso([resposta_ferramenta(("somar", {"a": 1, "b": 1}))])  # depois disso, erro
    entradas = iter(["quanto é 1 mais 1?", "oi", "/sair"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(entradas))

    agent.main()

    assert "[erro ao chamar o modelo]" in capsys.readouterr().out
    # A 3ª chamada (turno "oi") não pode carregar restos do turno que falhou.
    assert falso.chamadas[-1]["messages"] == [{"role": "user", "content": "oi"}]

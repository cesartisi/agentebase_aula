"""Fixtures compartilhadas pelas quatro camadas de teste.

A regra de ouro: só a camada `eval` fala com a OpenAI de verdade. Todo o
resto roda offline, rápido e de graça — e por isso roda em todo push.
"""

import json
import sys
from pathlib import Path

import pytest
from openai.types.chat import ChatCompletion

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import agent  # noqa: E402


@pytest.fixture(autouse=True)
def cliente_limpo(monkeypatch):
    """Zera o singleton do cliente entre testes (estado global vaza entre testes)."""
    monkeypatch.setattr(agent, "_cliente", None)
    yield


# --------------------------------------------------------------------------
# Modelo falso: devolve respostas roteirizadas, no formato real da API.
# --------------------------------------------------------------------------


def resposta_texto(texto: str) -> ChatCompletion:
    """Uma resposta da API em que o modelo respondeu em texto."""
    return _completion({"role": "assistant", "content": texto})


def resposta_ferramenta(*chamadas: tuple[str, dict | str]) -> ChatCompletion:
    """Uma resposta da API em que o modelo pediu uma ou mais ferramentas.

    Cada chamada é (nome, argumentos). Argumentos em `str` vão crus — útil
    para simular o modelo mandando JSON quebrado.
    """
    tool_calls = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": nome,
                "arguments": args if isinstance(args, str) else json.dumps(args),
            },
        }
        for i, (nome, args) in enumerate(chamadas)
    ]
    return _completion({"role": "assistant", "content": None, "tool_calls": tool_calls})


def _completion(mensagem: dict) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-teste",
            "object": "chat.completion",
            "created": 0,
            "model": "modelo-falso",
            "choices": [{"index": 0, "finish_reason": "stop", "message": mensagem}],
        }
    )


class ModeloFalso:
    """Imita `OpenAI()` o suficiente para `responder()`: cliente.chat.completions.create."""

    def __init__(self, roteiro: list[ChatCompletion]):
        self.roteiro = list(roteiro)
        self.chamadas: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        # Copia a lista: `responder` muta `mensagens` depois da chamada.
        self.chamadas.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self.roteiro:
            raise AssertionError("O agente chamou o modelo mais vezes do que o roteiro previa.")
        return self.roteiro.pop(0)


@pytest.fixture
def modelo_falso(monkeypatch):
    """Fábrica: `modelo_falso([resposta_ferramenta(...), resposta_texto(...)])`."""

    def _instalar(roteiro):
        falso = ModeloFalso(roteiro)
        monkeypatch.setattr(agent, "_cliente", falso)
        return falso

    return _instalar

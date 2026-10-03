"""Fixtures compartilhadas pelas quatro camadas de teste.

A regra de ouro: só a camada `eval` fala com o Claude de verdade. Todo o
resto roda offline, rápido e de graça — e por isso roda em todo push.
"""

import sys
from pathlib import Path

import pytest
from anthropic.types.beta import BetaMessage

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


def resposta_texto(texto: str) -> BetaMessage:
    """Uma resposta da API em que o modelo respondeu em texto."""
    return _mensagem([{"type": "text", "text": texto}], "end_turn")


def resposta_ferramenta(*chamadas: tuple[str, dict]) -> BetaMessage:
    """Uma resposta da API em que o modelo pediu uma ou mais ferramentas.

    Cada chamada é (nome, argumentos).
    """
    blocos = [
        {"type": "tool_use", "id": f"toolu_{i}", "name": nome, "input": args}
        for i, (nome, args) in enumerate(chamadas)
    ]
    return _mensagem(blocos, "tool_use")


def resposta_recusa() -> BetaMessage:
    """O filtro de segurança recusou o pedido."""
    return _mensagem([], "refusal")


def _mensagem(conteudo: list[dict], stop_reason: str) -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_teste",
            "type": "message",
            "role": "assistant",
            "model": "modelo-falso",
            "content": conteudo,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )


class ModeloFalso:
    """Imita `Anthropic()` o suficiente para `responder()`: cliente.beta.messages.create."""

    def __init__(self, roteiro: list[BetaMessage]):
        self.roteiro = list(roteiro)
        self.chamadas: list[dict] = []
        self.beta = self
        self.messages = self

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

"""Evals: o agente com o modelo DE VERDADE.

Teste unitário diz se o código está certo. Eval diz se o AGENTE está bom:
chamou a ferramenta quando devia? A resposta tem o número certo?

Custa token e a resposta varia, então:
  - só roda se houver ANTHROPIC_API_KEY (no CI, um secret do repositório);
  - sem a chave, os casos são PULADOS (skip), não reprovados;
  - os casos ficam em casos.json — adicionar um caso não exige Python.
"""

import json
import os
import re
from pathlib import Path

import pytest

import agent

pytestmark = pytest.mark.eval

CASOS = json.loads((Path(__file__).parent / "casos.json").read_text(encoding="utf-8"))


def _normalizar(texto: str) -> str:
    """Tira separador de milhar para '6.912' e '6,912' casarem com '6912'."""
    return re.sub(r"(?<=\d)[.,\s](?=\d{3}\b)", "", texto.lower())


def test_casos_bem_formados():
    """Roda sempre, mesmo sem chave: valida o dataset de eval."""
    ids = [c["id"] for c in CASOS]
    assert len(ids) == len(set(ids)), "ids de caso repetidos"
    for caso in CASOS:
        assert caso["pergunta"].strip()
        assert caso.get("deve_conter") or caso.get("deve_chamar") or caso.get("nao_deve_chamar")
        for nome in caso.get("deve_chamar", []) + caso.get("nao_deve_chamar", []):
            assert nome in agent.EXECUTORES, f"{caso['id']}: ferramenta '{nome}' não existe"


SEM_CHAVE = not os.getenv("ANTHROPIC_API_KEY")


@pytest.mark.skipif(SEM_CHAVE, reason="sem ANTHROPIC_API_KEY: evals com modelo real pulados")
@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_eval_com_modelo_real(caso):
    mensagens = [{"role": "user", "content": caso["pergunta"]}]

    resposta = agent.responder(mensagens)

    chamadas = {
        bloco.name
        for m in mensagens
        if m["role"] == "assistant"
        for bloco in m["content"]
        if bloco.type == "tool_use"
    }
    for esperado in caso.get("deve_conter", []):
        assert _normalizar(esperado) in _normalizar(resposta), f"resposta sem '{esperado}': {resposta!r}"
    for nome in caso.get("deve_chamar", []):
        assert nome in chamadas, f"devia ter chamado '{nome}'; chamou {sorted(chamadas)}"
    for nome in caso.get("nao_deve_chamar", []):
        assert nome not in chamadas, f"não devia ter chamado '{nome}'"

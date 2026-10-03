"""Contrato entre os prompts (agent*.md) e o código.

Os perfis (Ada, Lint, Val) são trocados copiando o arquivo por cima do
agent.md, então todos precisam ter a mesma estrutura — e a tabela de
ferramentas precisa listar exatamente o que existe no agent.py.
"""

import re
import sys
from pathlib import Path

import pytest

import agent

pytestmark = pytest.mark.contrato

RAIZ = Path(agent.__file__).resolve().parent
PERFIS = sorted(RAIZ.glob("agent*.md"))
SECOES_OBRIGATORIAS = ["## Identidade", "## Como você responde", "## Regras", "## Ferramentas disponíveis"]


def test_existem_perfis():
    nomes = {p.name for p in PERFIS}
    assert "agent.md" in nomes
    assert len(PERFIS) >= 2


@pytest.mark.parametrize("perfil", PERFIS, ids=lambda p: p.name)
def test_perfil_tem_secoes_obrigatorias(perfil):
    texto = perfil.read_text(encoding="utf-8")
    for secao in SECOES_OBRIGATORIAS:
        assert secao in texto, f"{perfil.name} sem a seção '{secao}'"


@pytest.mark.parametrize("perfil", PERFIS, ids=lambda p: p.name)
def test_tabela_de_ferramentas_bate_com_o_codigo(perfil):
    texto = perfil.read_text(encoding="utf-8")
    secao = texto.split("## Ferramentas disponíveis", 1)[1].split("\n## ", 1)[0]
    listadas = set(re.findall(r"^\|\s*`(\w+)`\s*\|", secao, flags=re.MULTILINE))

    assert listadas == set(agent.EXECUTORES), (
        f"{perfil.name}: tabela lista {sorted(listadas)}, código tem {sorted(agent.EXECUTORES)}"
    )


def test_memory_md_existe_e_e_pequeno():
    """memory.md entra inteiro no prompt a cada mensagem — precisa ser enxuto."""
    linhas = agent.MEMORY_MD.read_text(encoding="utf-8").splitlines()
    assert len(linhas) < 200


def test_app_recusa_rodar_fora_do_streamlit(monkeypatch):
    """Contrato da interface: `python app.py` sai com código 1 e instrução clara."""
    monkeypatch.delitem(sys.modules, "app", raising=False)
    with pytest.raises(SystemExit) as saida:
        import app  # noqa: F401
    assert saida.value.code == 1

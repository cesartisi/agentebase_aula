"""Testes unitários da configuração (cliente) e do contexto (prompt de sistema)."""

import pytest

import agent

pytestmark = pytest.mark.unit


def test_get_cliente_sem_chave_falha_com_mensagem_clara(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        agent.get_cliente()


def test_get_cliente_e_singleton(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste-falsa")
    primeiro = agent.get_cliente()
    assert agent.get_cliente() is primeiro


def test_carregar_contexto_junta_identidade_e_memoria(tmp_path, monkeypatch):
    (tmp_path / "agent.md").write_text("Sou o agente X.", encoding="utf-8")
    (tmp_path / "memory.md").write_text("- Usuário: Ana", encoding="utf-8")
    monkeypatch.setattr(agent, "AGENT_MD", tmp_path / "agent.md")
    monkeypatch.setattr(agent, "MEMORY_MD", tmp_path / "memory.md")

    contexto = agent.carregar_contexto()

    assert contexto.startswith("Sou o agente X.")
    assert "# Memória" in contexto
    assert contexto.endswith("- Usuário: Ana")


def test_carregar_contexto_sem_arquivos_usa_padrao(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "AGENT_MD", tmp_path / "nao_existe.md")
    monkeypatch.setattr(agent, "MEMORY_MD", tmp_path / "tambem_nao.md")

    contexto = agent.carregar_contexto()

    assert contexto.startswith("Você é um assistente.")
    assert "# Memória" in contexto


def test_carregar_contexto_le_os_arquivos_reais_do_repo():
    contexto = agent.carregar_contexto()
    assert agent.AGENT_MD.read_text(encoding="utf-8") in contexto
    assert agent.MEMORY_MD.read_text(encoding="utf-8") in contexto


def test_parametros_numericos_validos():
    assert 0.0 <= agent.TEMPERATURA <= 2.0
    assert agent.MAX_ITERACOES >= 1
    assert agent.MODELO

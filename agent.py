"""
Agente base — esqueleto mínimo.

Este é o núcleo do agente. Ele não sabe nada sobre interface: pode ser
usado pelo terminal (o `main()` no fim do arquivo), pelo `app.py`
(Streamlit), por um teste ou por uma API.

Estrutura, na ordem em que as coisas acontecem:

    1. CONFIGURAÇÃO   — chave e modelo, vindos do .env
    2. CONTEXTO       — agent.md (quem ele é) + memory.md (o que sabe)
    3. FERRAMENTAS    — o que ele consegue FAZER além de falar
    4. O LOOP         — o coração do agente
    5. O TERMINAL     — a interface mais simples possível

Rode com:  python agent.py
"""

import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from anthropic.types.beta import BetaMessageParam, BetaToolParam, BetaToolResultBlockParam
from dotenv import load_dotenv

# ==========================================================================
# 1. CONFIGURAÇÃO
# ==========================================================================

load_dotenv()

RAIZ = Path(__file__).resolve().parent
AGENT_MD = RAIZ / "agent.md"
MEMORY_MD = RAIZ / "memory.md"

MODELO = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
# Quanto o modelo pensa antes de responder: low | medium | high | xhigh | max.
# Menos esforço = mais rápido e mais barato. (Este modelo não aceita temperatura.)
ESFORCO = os.getenv("AGENTE_ESFORCO", "medium")
MAX_TOKENS = int(os.getenv("AGENTE_MAX_TOKENS", "16000"))
MAX_ITERACOES = int(os.getenv("AGENTE_MAX_ITERACOES", "5"))

# Se o filtro de segurança do modelo recusar um pedido, a própria API tenta de
# novo num modelo reserva recomendado pela Anthropic, dentro da mesma chamada.
BETAS_FALLBACK = ["server-side-fallback-2026-07-01"]

_cliente = None


def get_cliente() -> Anthropic:
    """Instancia o cliente da Anthropic (Claude) — uma vez só, na primeira chamada.

    AQUI que o modelo entra no projeto. Trocar de provedor começa por aqui.
    """
    global _cliente
    if _cliente is None:
        chave = os.getenv("ANTHROPIC_API_KEY")
        if not chave:
            raise RuntimeError(
                "ANTHROPIC_API_KEY não encontrada. Copie .env.example para .env e coloque sua chave."
            )
        _cliente = Anthropic(api_key=chave)
    return _cliente


# ==========================================================================
# 2. CONTEXTO
# ==========================================================================


def carregar_contexto() -> str:
    """Monta o prompt de sistema a partir dos dois arquivos de contexto.

    agent.md  = identidade e regras do agente
    memory.md = o que ele sabe sobre o usuário (persiste entre execuções)

    Editar esses arquivos muda o comportamento sem tocar em Python.
    """
    identidade = AGENT_MD.read_text(encoding="utf-8") if AGENT_MD.exists() else "Você é um assistente."
    memoria = MEMORY_MD.read_text(encoding="utf-8") if MEMORY_MD.exists() else ""
    return f"{identidade}\n\n---\n\n# Memória\n\n{memoria}"


# ==========================================================================
# 3. FERRAMENTAS
# ==========================================================================
#
# Uma ferramenta tem duas metades:
#   - a DECLARAÇÃO (o JSON em FERRAMENTAS): é o que o modelo lê para decidir
#     se chama. A `description` importa mais que o código.
#   - a FUNÇÃO Python: é o que realmente roda na sua máquina.
#
# O modelo NUNCA executa nada. Ele só devolve "quero chamar X com estes
# argumentos" — quem executa é o seu código, no passo 4.
#
# >>> A ferramenta abaixo é só um EXEMPLO. Apague e coloque as suas. <<<


def somar(a: float, b: float) -> dict:
    """Exemplo de ferramenta. Modelos erram conta; Python não."""
    #    print(f"[somar] executando de verdade: {a} + {b}")
    return {"resultado": a + b}


FERRAMENTAS: list[BetaToolParam] = [
    {
        "name": "somar",
        "description": "Soma dois números. Use sempre que precisar de uma adição exata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "Primeiro número."},
                "b": {"type": "number", "description": "Segundo número."},
            },
            "required": ["a", "b"],
        },
    }
]

EXECUTORES = {
    "somar": somar,
}


def executar_ferramenta(nome: str, argumentos: dict) -> str:
    """Executa uma ferramenta e devolve SEMPRE uma string (o modelo só lê texto).

    Erro vira mensagem de erro para o modelo, não crash do programa — assim
    ele consegue tentar outro caminho.
    """
    funcao = EXECUTORES.get(nome)
    if funcao is None:
        return json.dumps({"erro": f"Ferramenta '{nome}' não existe."}, ensure_ascii=False)
    try:
        return json.dumps(funcao(**argumentos), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"erro": f"Falha em '{nome}': {exc}"}, ensure_ascii=False)


# ==========================================================================
# 4. O LOOP DO AGENTE
# ==========================================================================


def responder(mensagens: list[BetaMessageParam], verboso: bool = False) -> str:
    """O agente propriamente dito.

    O que diferencia um agente de uma simples chamada de API é ESTE loop:

        manda a conversa + as ferramentas para o modelo
          -> pediu ferramenta? executa, anexa o resultado, repete
          -> respondeu em texto?  acabou, essa é a resposta

    `mensagens` tem só os turnos de usuário e assistente; o prompt de sistema
    (agent.md + memory.md) vai à parte, em `system`. A lista é modificada no
    lugar, então o histórico (incluindo as chamadas de ferramenta) fica
    preservado entre turnos.
    """
    cliente = get_cliente()
    sistema = carregar_contexto()

    for _ in range(MAX_ITERACOES):
        resposta = cliente.beta.messages.create(
            model=MODELO,
            max_tokens=MAX_TOKENS,
            system=sistema,
            messages=mensagens,
            tools=FERRAMENTAS,
            output_config={"effort": ESFORCO},
            betas=BETAS_FALLBACK,
            fallbacks="default",
        )

        # O filtro de segurança recusou (e o modelo reserva também). Nada a anexar.
        if resposta.stop_reason == "refusal":
            return "Não posso ajudar com esse pedido."

        # Guarda a resposta INTEIRA (não só o texto): os blocos de raciocínio
        # e de chamada de ferramenta precisam voltar intactos na próxima chamada.
        mensagens.append({"role": "assistant", "content": resposta.content})

        # Caso 1: respondeu em texto. Fim.
        if resposta.stop_reason != "tool_use":
            return "".join(b.text for b in resposta.content if b.type == "text")

        # Caso 2: quer usar ferramentas. Todos os resultados voltam numa mensagem só.
        resultados: list[BetaToolResultBlockParam] = []
        for bloco in resposta.content:
            if bloco.type != "tool_use":
                continue
            argumentos = bloco.input if isinstance(bloco.input, dict) else {}
            if verboso:
                print(f"  [ferramenta] {bloco.name}({argumentos})")

            conteudo = executar_ferramenta(bloco.name, argumentos)
            resultados.append(
                {
                    "type": "tool_result",
                    "tool_use_id": bloco.id,
                    "content": conteudo,
                    "is_error": "erro" in json.loads(conteudo),
                }
            )
        mensagens.append({"role": "user", "content": resultados})

    return "Atingi o limite de iterações sem concluir. Tente reformular a pergunta."


# ==========================================================================
# 5. O TERMINAL
# ==========================================================================


def main() -> None:
    try:
        get_cliente()  # falha cedo e com mensagem clara se não houver chave
    except RuntimeError as exc:
        print(f"ERRO: {exc}")
        sys.exit(1)

    mensagens: list[BetaMessageParam] = []
    print(f"Agente base — {MODELO}. Digite /sair para encerrar.\n")

    while True:
        try:
            entrada = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté mais.")
            return

        if not entrada:
            continue
        if entrada in ("/sair", "/quit", "/exit"):
            print("Até mais.")
            return

        marca = len(mensagens)
        mensagens.append({"role": "user", "content": entrada})
        try:
            print(f"\nagente> {responder(mensagens, verboso=True)}\n")
        except Exception as exc:
            print(f"\n[erro ao chamar o modelo] {exc}\n")
            del mensagens[marca:]  # descarta o turno que falhou, inteiro


if __name__ == "__main__":
    main()

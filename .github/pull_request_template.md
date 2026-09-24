## O que muda

<!-- Descreva a mudança em 1–3 frases. Qual problema resolve? -->

## Área afetada

- [ ] Núcleo do agente (`agent.py`, ferramentas, loop)
- [ ] Prompt de sistema / perfil (`agent.md`, `agent-ada.md`, `agent-lint.md`, `agent-val.md`)
- [ ] Memória (`memory.md`)
- [ ] Interface (`app.py`)
- [ ] Dependências (`requirements.txt`)
- [ ] Governança (`.github/`)

## Checklist obrigatório

- [ ] **Testei o agente** — rodei `python agent.py` e/ou `streamlit run app.py` e conversei com ele
- [ ] **Rodei os evals** — executei os casos de avaliação e os resultados não pioraram
- [ ] **Documentei o prompt alterado** — se mudei algum `agent*.md` ou `memory.md`, expliquei abaixo o que mudou e por quê
- [ ] Se criei/alterei ferramenta, atualizei a tabela "Ferramentas disponíveis" nos `agent*.md`
- [ ] Não commitei `.env` nem chaves de API

## Como testei

<!-- Perguntas que fiz ao agente e o que ele respondeu. Ex.:
     "quanto é 1234 mais 5678?" → chamou somar(...) → 6912 -->

## Resultado dos evals

<!-- Cole a saída ou um resumo (casos que passaram / falharam). -->

## Mudança de prompt (se houver)

<!-- Arquivo, trecho antes → depois, e o comportamento esperado com a mudança. -->

# Deploy canary no Azure — guia

Pré-requisito: o deploy simples do [DEPLOY_AZURE.md](DEPLOY_AZURE.md) já
funcionando. Este guia troca o "publica direto para todo mundo" por um
**canary**: a versão nova vai primeiro para uma fração dos visitantes e só
chega a todos se continuar saudável. Tudo no plano **Free F1** — sem custo.

---

## Como funciona

São três Web Apps no mesmo plano:

| App | Papel |
|---|---|
| `agentebase` | **estável** — a produção, que você já tem |
| `agentebase-canary` | recebe a versão nova primeiro |
| `agentebase-router` | **a URL que você divulga**. Manda cada visitante (302) para o estável ou para o canary |

O roteador ([router/router.py](router/router.py)) lê o percentual do
[router/config.json](router/config.json). Um cookie mantém cada visitante na
mesma versão por 1 hora.

A cada push na `main`, o workflow
[deploy-canary.yml](.github/workflows/deploy-canary.yml) faz:

```
testes → deploy no canary → canary saudável?
       → roteador 10% → observa 5 min → roteador 50% → observa 5 min
       → deploy no estável → estável saudável? → roteador 0%
```

Se **qualquer** passo falhar, o roteador volta para 0% e o job fica vermelho.
O estável não foi tocado, então todo mundo volta para a versão anterior.

> Os slots nativos do Azure fazem isso sem roteador próprio, mas exigem plano
> Standard (pago). Este é o equivalente gratuito.

## Passo 1 — Criar os dois apps novos

Com o [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
logado (`az login`), troque `<rg>` e `<plano>` pelos do seu app atual:

```bash
az webapp create -g <rg> -p <plano> -n <seu-app>-canary --runtime "PYTHON:3.11"
az webapp create -g <rg> -p <plano> -n <seu-app>-router --runtime "PYTHON:3.11"
```

## Passo 2 — Configurar os apps

O canary precisa das **mesmas** configurações do estável (passos 3 e 4 do
DEPLOY_AZURE.md):

```bash
az webapp config appsettings set -g <rg> -n <seu-app>-canary \
  --settings ANTHROPIC_API_KEY=<sua-chave> SCM_DO_BUILD_DURING_DEPLOYMENT=true
az webapp config set -g <rg> -n <seu-app>-canary \
  --startup-file "python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0"
```

O roteador só precisa do Startup Command (ele não tem dependências):

```bash
az webapp config set -g <rg> -n <seu-app>-router --startup-file "python router.py"
```

Apps novos vêm com a autenticação por publish profile **desligada** — sem
isto, o deploy dá erro 401:

```bash
for app in <seu-app>-canary <seu-app>-router; do
  az resource update -g <rg> --namespace Microsoft.Web \
    --resource-type basicPublishingCredentialsPolicies \
    --parent sites/$app -n scm --set properties.allow=true
done
```

## Passo 3 — Apontar o roteador para os seus apps

Edite [router/config.json](router/config.json) com as URLs do **seu** estável
e do **seu** canary (veja em *Overview → Default domain* de cada app). Deixe
`pct` em `0` — quem mexe nele é o workflow.

## Passo 4 — Secrets e variables no GitHub

**Settings → Secrets and variables → Actions**.

Secrets (os `AZURE_WEBAPP_*` do estável você já tem):

| Secret | Valor |
|---|---|
| `AZURE_CANARY_NAME` | nome do app canary |
| `AZURE_CANARY_PUBLISH_PROFILE` | publish profile do app canary |
| `AZURE_ROUTER_PUBLISH_PROFILE` | publish profile do app roteador |

Variables (aba **Variables**):

| Variable | Valor | |
|---|---|---|
| `DEPLOY_ESTRATEGIA` | `canary` | liga o canary e desliga o deploy simples |
| `ROUTER_URL` | `https://<seu-app>-router.azurewebsites.net` | |
| `CANARY_PASSOS` | `10 50` | opcional — percentuais da rampa |
| `CANARY_ESPERA_MIN` | `5` | opcional — minutos observando cada passo |

Para voltar ao deploy simples, apague `DEPLOY_ESTRATEGIA`.

## Passo 5 — Deploy e acompanhamento

Push na `main`, ou **Actions → Deploy Canary → Run workflow**. Durante a
rampa, veja o percentual atual:

```bash
curl https://<seu-app>-router.azurewebsites.net/_router/status
```

E a divisão real do tráfego (sem cookie, cada `curl` é um visitante novo):

```bash
for i in $(seq 50); do
  curl -s -o /dev/null -w "%{redirect_url}\n" https://<seu-app>-router.azurewebsites.net
done | sort | uniq -c
```

---

## Limitações

| O quê | Por quê |
|---|---|
| A barra de endereço mostra a URL do estável ou do canary, não a do roteador | O roteador redireciona em vez de fazer proxy — é o que deixa o websocket do Streamlit funcionar sem tratamento especial |
| O health check só confirma que o Streamlit subiu | `/_stcore/health` não chama a API da Anthropic. A lógica do agente é coberta antes, pelos testes |
| Alguns segundos fora do ar no roteador a cada passo | Mudar o percentual = republicar o roteador, que reinicia |
| Se a promoção para o estável falhar no meio, o estável pode ficar quebrado | O rollback só zera o roteador; nesse caso, rode o workflow de novo com o commit anterior |
| O primeiro acesso a cada app pode levar ~1 min | O F1 dorme sem tráfego. O health check espera até 3 min por isso |

## Teste de tráfego no canary
```shell
URL=https://agentebase-router.azurewebsites.net
estavel=0; canary=0
for i in $(seq 50); do
  destino=$(curl -s -o /dev/null -w "%{redirect_url}" "$URL")
  if [[ $destino == *agentebase-canary* ]]; then
    canary=$((canary+1)); nome="CANARY "
  else
    estavel=$((estavel+1)); nome="estável"
  fi
  printf "%2d  %s   (estável: %d | canary: %d)\n" "$i" "$nome" "$estavel" "$canary"
done


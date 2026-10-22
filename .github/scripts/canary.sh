#!/usr/bin/env bash
# Funções do deploy canary, usadas pelo workflow deploy-canary.yml.
#
#   canary.sh publicar-router <pct>              -> republica o roteador com esse percentual
#   canary.sh saude <url> [tentativas]           -> espera o Streamlit responder /_stcore/health
#   canary.sh observar <url> <minutos>           -> checa a saúde a cada 30s durante N minutos
#
# publicar-router lê do ambiente:
#   ROUTER_PUBLISH_PROFILE  conteúdo do publish profile do app roteador
#   ROUTER_URL              URL pública do roteador (para conferir o /_router/status)
#
# Por que não usar a action azure/webapps-deploy para o roteador: o número de
# passos do canary é configurável (vars.CANARY_PASSOS), e steps de workflow
# não fazem laço. Aqui é o mesmo OneDeploy que a action usa, via curl.

set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"

publicar_router() {
  local pct="$1"
  local tmp
  tmp="$(mktemp -d)"
  cp "$RAIZ/router/router.py" "$tmp/"
  python3 - "$RAIZ/router/config.json" "$tmp/config.json" "$pct" <<'PY'
import json, sys
origem, destino, pct = sys.argv[1], sys.argv[2], float(sys.argv[3])
config = json.load(open(origem, encoding="utf-8"))
config["pct"] = pct
json.dump(config, open(destino, "w", encoding="utf-8"), indent=2)
PY
  (cd "$tmp" && zip -q router.zip router.py config.json)

  # Extrai usuário, senha e host do SCM do publish profile (XML).
  read -r usuario senha scm < <(python3 - <<'PY'
import os, xml.etree.ElementTree as ET
raiz = ET.fromstring(os.environ["ROUTER_PUBLISH_PROFILE"])
p = next(p for p in raiz.iter("publishProfile") if p.get("publishMethod") == "ZipDeploy")
print(p.get("userName"), p.get("userPWD"), p.get("publishUrl").split(":")[0])
PY
)
  echo "::add-mask::$senha"

  echo "Publicando roteador com pct=$pct"
  curl -fsS -u "$usuario:$senha" -X POST \
    "https://$scm/api/publish?type=zip&restart=true" \
    --data-binary @"$tmp/router.zip" -H "Content-Type: application/zip"

  # Confere que o roteador no ar já está com o percentual novo.
  for _ in $(seq 24); do
    atual="$(curl -fsS "$ROUTER_URL/_router/status" 2>/dev/null | python3 -c 'import json,sys; print(float(json.load(sys.stdin)["pct"]))' 2>/dev/null || true)"
    if [ "$atual" = "$(python3 -c "print(float($pct))")" ]; then
      echo "Roteador no ar com pct=$pct"
      return 0
    fi
    sleep 5
  done
  echo "::error::Roteador não confirmou pct=$pct em 2 minutos"
  return 1
}

saude() {
  local url="$1" tentativas="${2:-18}"
  for i in $(seq "$tentativas"); do
    if curl -fsS --max-time 10 "$url/_stcore/health" >/dev/null 2>&1; then
      echo "OK: $url respondeu (tentativa $i)"
      return 0
    fi
    sleep 10  # o F1 dorme sem tráfego; o primeiro acesso pode levar ~1 min
  done
  echo "::error::$url não respondeu /_stcore/health"
  return 1
}

observar() {
  local url="$1" minutos="$2"
  local fim=$(( $(date +%s) + minutos * 60 ))
  echo "Observando $url por $minutos min"
  while [ "$(date +%s)" -lt "$fim" ]; do
    saude "$url" 3 >/dev/null || { echo "::error::$url caiu durante o canary"; return 1; }
    sleep 30
  done
  echo "Canary saudável durante $minutos min"
}

case "${1:-}" in
  publicar-router) publicar_router "$2" ;;
  saude)           saude "$2" "${3:-18}" ;;
  observar)        observar "$2" "$3" ;;
  *) echo "uso: $0 publicar-router <pct> | saude <url> [tentativas] | observar <url> <minutos>" >&2; exit 2 ;;
esac

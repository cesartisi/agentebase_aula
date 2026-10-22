"""
Roteador de canary — a URL pública que decide quem atende cada visitante.

Não é um proxy: ele só responde 302 mandando o navegador para o app
estável ou para o app canary. Depois do redirecionamento o navegador fala
direto com o app escolhido — inclusive o websocket do Streamlit, que um
proxy em Python teria que tratar à parte.

    pct = 0    -> todo mundo no estável
    pct = 10   -> ~10% dos visitantes novos no canary
    pct = 100  -> todo mundo no canary

O cookie `versao` faz o visitante continuar na mesma versão entre visitas,
em vez de pular de uma para outra a cada acesso.

A configuração vem do config.json ao lado deste arquivo. Quem muda o
percentual é o workflow deploy-canary.yml, que republica este app com um
config.json novo. Só biblioteca padrão: o deploy não precisa instalar nada.

Rode com:  python router.py      (escuta na porta 8000, ou $PORT)
"""

import json
import os
import random
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG_JSON = Path(__file__).resolve().parent / "config.json"
DESTINOS = ("estavel", "canary")
COOKIE = "versao"
COOKIE_MAX_AGE = 3600


def carregar_config() -> dict:
    return json.loads(CONFIG_JSON.read_text(encoding="utf-8"))


def escolher_destino(pct: float, cookie: str | None, sorteio: float) -> str:
    """Decide para onde vai o visitante. Função pura, para dar para testar.

    `sorteio` é um número em [0, 1) — em produção, random.random().
    """
    if pct <= 0:
        return "estavel"  # canary desligado: ignora até quem tinha cookie de canary
    if cookie in DESTINOS:
        return cookie
    return "canary" if sorteio < pct / 100 else "estavel"


class Roteador(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        config = carregar_config()

        if self.path == "/_router/status":
            corpo = json.dumps(config, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return

        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        cookie = cookies[COOKIE].value if COOKIE in cookies else None
        destino = escolher_destino(config["pct"], cookie, random.random())

        self.send_response(302)
        self.send_header("Location", config["urls"][destino].rstrip("/") + self.path)
        self.send_header("Set-Cookie", f"{COOKIE}={destino}; Max-Age={COOKIE_MAX_AGE}; Path=/")
        self.send_header("Cache-Control", "no-store")  # senão o navegador memoriza o 302
        self.end_headers()


if __name__ == "__main__":
    porta = int(os.getenv("PORT", "8000"))
    print(f"Roteador de canary ouvindo na porta {porta}")
    ThreadingHTTPServer(("0.0.0.0", porta), Roteador).serve_forever()

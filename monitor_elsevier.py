#!/usr/bin/env python3
"""
Monitora o Elsevier Author Hub Tracker e avisa quando algo mudar.
Autor: Joahannes B. D. da Costa

Uso:
    pip install requests
    python monitor_elsevier.py          # checa uma vez (bom para cron)
    python monitor_elsevier.py --loop   # fica rodando e checa a cada INTERVALO segundos
"""

import json
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime

import requests

# ================== CONFIGURAÇÃO ==================
UUID = "c84e641c-f2ad-40d8-a856-d96c7d7e1234"
# https://github.com/KarlRaphel/elsevier-tracker-web
API_URL = f"https://tnlkuelk67.execute-api.us-east-1.amazonaws.com/tracker/{UUID}"

# Notificação via ntfy.sh (app gratuito p/ Android/iOS). Use um nome difícil de adivinhar.
NTFY_TOPIC = "meu-artigo-elsevier-2026"   # deixe "" para desativar

INTERVALO = 60 * 60   # segundos entre checagens no modo --loop (30 min)
ESTADO = Path(__file__).with_name("elsevier_estado.json")
# ==================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://track.authorhub.elsevier.com",
    "Referer": "https://track.authorhub.elsevier.com/",
}


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def buscar():
    r = requests.get(API_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def normalizar(dados):
    """JSON ordenado, para a comparação não disparar por ordem de chaves."""
    return json.dumps(dados, sort_keys=True, ensure_ascii=False, indent=2)


def diferencas(antigo, novo, caminho=""):
    """Lista recursivamente o que mudou entre dois JSONs."""
    mudancas = []
    if isinstance(antigo, dict) and isinstance(novo, dict):
        for k in sorted(set(antigo) | set(novo)):
            p = f"{caminho}.{k}" if caminho else k
            if k not in antigo:
                mudancas.append(f"+ {p}: {novo[k]}")
            elif k not in novo:
                mudancas.append(f"- {p}: {antigo[k]}")
            else:
                mudancas += diferencas(antigo[k], novo[k], p)
    elif isinstance(antigo, list) and isinstance(novo, list):
        if len(antigo) != len(novo):
            mudancas.append(f"~ {caminho}: {len(antigo)} -> {len(novo)} itens")
        for i, (a, b) in enumerate(zip(antigo, novo)):
            mudancas += diferencas(a, b, f"{caminho}[{i}]")
        for i, extra in enumerate(novo[len(antigo):], start=len(antigo)):
            mudancas.append(f"+ {caminho}[{i}]: {extra}")
    elif antigo != novo:
        mudancas.append(f"~ {caminho}: {antigo} -> {novo}")
    return mudancas


def notificar(titulo, texto):
    log(f"{titulo}\n{texto}")
    if NTFY_TOPIC:
        try:
            requests.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                data=texto[:3500].encode("utf-8"),
                headers={"Title": titulo, "Priority": "high", "Tags": "page_facing_up"},
                timeout=15,
            )
        except Exception as e:
            log(f"Falha ao enviar notificação: {e}")


def checar():
    try:
        novo = buscar()
    except Exception as e:
        log(f"Erro ao consultar a API: {e}")
        return

    if not ESTADO.exists():
        ESTADO.write_text(normalizar(novo), encoding="utf-8")
        status = novo.get("Status", "?") if isinstance(novo, dict) else "?"
        log(f"Primeira execução: estado salvo. Status atual: {status}")
        return

    antigo = json.loads(ESTADO.read_text(encoding="utf-8"))
    if normalizar(antigo) == normalizar(novo):
        log("Sem mudanças.")
        return

    mudancas = diferencas(antigo, novo)
    ESTADO.write_text(normalizar(novo), encoding="utf-8")
    notificar("Seu artigo na Elsevier mudou!", "\n".join(mudancas) or "Conteúdo alterado.")


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            checar()
            time.sleep(INTERVALO)
    else:
        checar()

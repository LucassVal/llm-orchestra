#!/usr/bin/env python3
# 3W: WHAT=ollama gate | WHY=verificar envs+binary antes pipeline | WHEN=pre-pipeline
"""
ollama_gate.py -- Checklist pre-pipeline Ollama.
Verifica: 6 envs ativas, binary correto, modelos >= 3, keep_alive configurado.
ERR bloqueante -- sem Ollama configurado, pipeline nao roda.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent

REQUIRED_ENVS = [
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_MAX_LOADED_MODELS",
    "OLLAMA_KV_CACHE_TYPE",
    "OLLAMA_FLASH_ATTENTION",
    "OLLAMA_MAX_QUEUE",
    "OLLAMA_CONTEXT_LENGTH",
]

OLLAMA_BINARY = "/data/data/com.termux/files/usr/lib/ollama/llama-server"


def check_envs():
    """Verifica 6 vars Ollama ativas no processo."""
    missing = []
    for var in REQUIRED_ENVS:
        val = os.environ.get(var)
        if not val:
            missing.append(var)
    if missing:
        return False, "{} vars ausentes: {}".format(len(missing), ",".join(missing[:3]))
    return True, "6/6 vars ativas"


def check_binary():
    """Verifica binary Ollama existe."""
    if os.path.exists(OLLAMA_BINARY):
        return True, "Ollama binary OK"
    return False, "binary ausente: " + OLLAMA_BINARY


def check_models():
    """Verifica >= 3 modelos no Ollama."""
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if r.returncode != 0:
        return False, "Ollama offline"
    count = len([l for l in r.stdout.split("\n") if l.strip()]) - 1
    if count < 3:
        return False, "{} modelos (min 3)".format(count)
    return True, "{} modelos".format(count)


def check_dotenv():
    """Verifica .env e .env.make existem."""
    env_ok = (BUILD/".env").exists()
    env_mk_ok = (BUILD/".env.make").exists()
    if env_ok and env_mk_ok:
        return True, "ambos presentes"
    return False, ".env={} .env.make={}".format(env_ok, env_mk_ok)


CHECKS = [
    ("ENV", check_envs),
    ("BINARY", check_binary),
    ("MODELS", check_models),
    ("DOTENV", check_dotenv),
]


def run():
    passed = 0
    failed = 0
    for name, fn in CHECKS:
        ok, detail = fn()
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print("  OLLAMA-{}: {:<6} {}".format(name, status, detail))

    print("  " + "-" * 30)
    print("  OLLAMA GATE: PASS={} FAIL={}".format(passed, failed))
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run())

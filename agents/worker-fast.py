# 3W: WHAT=agente gerado | WHY=fabrica AST | WHEN=d7d00a65
# 3W: WHAT=agente worker-fast | WHY=orquestracao LLM | WHEN=5742cd476cb2
"""
Agente: worker-fast
Modelo: qwen3:4b
Perfil: fast
Gerado por: factory_engine.py (AST + Jinja2)
Trace: 5742cd476cb2
"""
from pathlib import Path

BUILD = Path(__file__).parent.parent

# ═══════════════════════════════════════════════════════════
# Configuracao do agente
# ═══════════════════════════════════════════════════════════

AGENT_ID = "worker-fast"
MODEL = "qwen3:4b"
PROFILE = "fast"

def init():
    """Inicializa agente com configuracao do perfil."""
    return {
        "agent_id": AGENT_ID,
        "model": MODEL,
        "profile": PROFILE,
    }
def run(prompt: str) -> dict:
    """Executa prompt no modelo configurado."""
    import subprocess

    config = init()
    result = subprocess.run(
        ["ollama", "run", config["model"], prompt],
        capture_output=True, text=True, timeout=120,
    )
    return {
        "agent_id": config["agent_id"],
        "model": config["model"],
        "profile": config["profile"],
        "response": result.stdout.strip(),
        "status": "OK" if result.returncode == 0 else "ERR",
    }
# ═══════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Hello."
    result = run(prompt)
    print(result)
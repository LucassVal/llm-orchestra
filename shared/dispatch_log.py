#!/usr/bin/env python3
# 3W: WHAT=dispatch log JSON | WHY=rastrear cada disparo agente/teste | WHEN=toda acao
"""
dispatch_log.py — Registro de disparos (testes, agentes, pipelines).
Gera JSON com hash unico + agente/funcao/data/hora.
Cada disparo tem: pre (antes) e post (depois) com metricas.
"""
import hashlib
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

BUILD = Path(__file__).parent.parent
DISPATCH_DIR = BUILD / "logs" / "dispatch"
DISPATCH_DIR.mkdir(parents=True, exist_ok=True)


def create(agent_id, function, model="4b", profile="agent_default", prompt=""):
    """Cria registro de disparo PRE-execucao."""
    ts = datetime.now().isoformat()
    dispatch_id = uuid.uuid4().hex[:12]
    dispatch_hash = hashlib.sha256(
        f"{agent_id}:{function}:{ts}".encode()
    ).hexdigest()[:16]

    record = {
        "dispatch_id": dispatch_id,
        "dispatch_hash": dispatch_hash,
        "agent_id": agent_id,
        "function": function,
        "model": model,
        "profile": profile,
        "prompt_preview": prompt[:100],
        "pre_timestamp": ts,
        "pre_thermal_c": _read_thermal(),
        "pre_ram_mb": _read_ram(),
        "status": "running",
    }

    path = DISPATCH_DIR / f"{dispatch_hash}.json"
    path.write_text(json.dumps(record, indent=2))
    return dispatch_hash


def complete(dispatch_hash, result, tok_s=0, elapsed_s=0):
    """Atualiza registro de disparo POST-execucao."""
    path = DISPATCH_DIR / f"{dispatch_hash}.json"
    if not path.exists():
        return
    record = json.loads(path.read_text())
    record["status"] = "completed"
    record["post_timestamp"] = datetime.now().isoformat()
    record["post_thermal_c"] = _read_thermal()
    record["post_ram_mb"] = _read_ram()
    record["result_summary"] = str(result)[:200]
    record["tok_s"] = tok_s
    record["elapsed_s"] = elapsed_s
    path.write_text(json.dumps(record, indent=2))


def fail(dispatch_hash, error):
    """Marca disparo como falho."""
    path = DISPATCH_DIR / f"{dispatch_hash}.json"
    if not path.exists():
        return
    record = json.loads(path.read_text())
    record["status"] = "failed"
    record["error"] = str(error)[:200]
    record["post_timestamp"] = datetime.now().isoformat()
    path.write_text(json.dumps(record, indent=2))


def list_recent(limit=10):
    """Lista ultimos disparos."""
    files = sorted(DISPATCH_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[:limit]:
        d = json.loads(f.read_text())
        print("  {} | {:<15} | {:<12} | {} | {} tok/s".format(
            d["dispatch_hash"][:8],
            d["agent_id"][:15],
            d["function"][:12],
            d["status"],
            d.get("tok_s", "-"),
        ))


def _read_thermal():
    try:
        d = json.loads((BUILD / "shared" / "thermal_status.json").read_text())
        return d.get("thermal_c", 0)
    except Exception:
        return 0


def _read_ram():
    try:
        import subprocess
        r = subprocess.run(["free", "-m"], capture_output=True, text=True)
        for line in r.stdout.split("\n"):
            if "Mem:" in line:
                return int(line.split()[-1])
    except Exception:
        return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: dispatch_log.py create|complete|fail|list [args]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        list_recent()
    elif action == "create":
        dh = create(
            agent_id=sys.argv[2] if len(sys.argv) > 2 else "test",
            function=sys.argv[3] if len(sys.argv) > 3 else "unknown",
        )
        print("dispatch: {}".format(dh))
    elif action == "complete":
        complete(sys.argv[2], "ok", tok_s=float(sys.argv[3]) if len(sys.argv) > 3 else 0)
    elif action == "fail":
        fail(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "unknown")

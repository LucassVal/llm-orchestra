#!/usr/bin/env python3
# 3W: WHAT=kill-all processos orfaos | WHY=evitar bateria drenada por llama-server zumbi | WHEN=commit/checkpoint
"""
kill_all.py -- Mata TODOS os processos relacionados ao bench-llm.
Alcance: llama-server, bench_*.py, orchestrator.py, ollama serve.
Nao afeta cron jobs (sandbox separado).
ERR obrigatorio no gate -- sempre roda antes de commit.
"""
import os
import signal
import subprocess
import sys


def find_and_kill():
    """Encontra e mata processos orfaos do ecossistema bench-llm."""
    killed = []

    # Padroes de processo para matar
    patterns = [
        "llama-server",
        "llama-cli",
        "bench_orchestrator.py",
        "bench_temp_sweep.py",
        "bench_sweep.py",
        "bench_child.py",
        "bench_battery.py",
        "bench_creative.py",
        "bench_ppl.py",
        "bench_analyze.py",
        "bench_sys.py",
        "orchestrator.py",
        "meta_orchestrator.py",
    ]

    try:
        # Lista todos os processos
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            parts = line.split()
            if len(parts) < 11:
                continue
            cmdline = " ".join(parts[10:])
            for pattern in patterns:
                if pattern in cmdline and "grep" not in cmdline and "kill_all" not in cmdline:
                    # Protege ollama serve legitimo (porta 11434)
                    if pattern == "llama-server" and "--port" in cmdline and "8080" not in cmdline:
                        continue  # Nao mata llama-server do ollama
                    pid = int(parts[1])
                    try:
                        os.kill(pid, signal.SIGKILL)
                        killed.append((pid, pattern, cmdline[:80]))
                    except (ProcessLookupError, PermissionError):
                        pass
                    break
    except Exception as e:
        print(f"  ⚠ kill-all scan error: {e}", file=sys.stderr)

    return killed


def run():
    killed = find_and_kill()

    if killed:
        print(f"  KILL-ALL: {len(killed)} processos orfaos mortos:")
        for pid, pattern, cmd in killed:
            print(f"    PID {pid}: {pattern} -- {cmd}")
        # Sucesso -- processos zumbis removidos
        return 0
    else:
        print("  KILL-ALL: limpo (0 orfaos)")
        return 0


if __name__ == "__main__":
    sys.exit(run())

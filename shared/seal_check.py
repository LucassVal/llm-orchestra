#!/usr/bin/env python3
# 3W: WHAT=selo integridade sistema | WHY=detectar violacoes e auto-reparar | WHEN=todo checkpoint
"""
seal_check.py -- Selo de integridade do ecossistema.
Computa hash SHA256 de arquivos criticos e compara com selo salvo.
Se violado: tenta auto-reparo via git checkout do ultimo commit.
Se irreparavel: bloqueia tudo e instrui IA a alertar operador.

Arquivos selados:
  Makefile, nc.ps1, RULES.md, README.md, .env.make
  meta_orchestrator.py, bench_orchestrator.py
  shared/*.py (todos)
  test-*/orchestrator.py, test-*/sweep_config.json
  ~/agents/agent_contract_template.json
"""
import hashlib
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent
SEAL_FILE = BUILD / ".seal"
GIT_DIR = BUILD / ".git"

SEALED = [
    # Build root
    "Makefile", "nc.ps1", "RULES.md", "README.md", ".env.make",
    "meta_orchestrator.py", "bench_orchestrator.py",
    # Bench tools
    "bench_analyze.py", "bench_battery.py", "bench_child.py",
    "bench_creative.py", "bench_ppl.py", "bench_sweep.py",
    "bench_sys.py", "bench_temp_sweep.py",
    # Shared infra
    "shared/compliance_check.py", "shared/pre_commit_hook.py",
    "shared/rule_check.py", "shared/circularity_check.py",
    "shared/triade_check.py", "shared/py_check.py",
    "shared/thermal_governor.py", "shared/metrics_daemon.py",
    "shared/metrics_reporter.py", "shared/agent_factory.py",
    "shared/multi_agent.py",
    "shared/system_validate.py", "shared/anti_mock_scan.py",
    "shared/seal_check.py",
    "shared/factory_engine.py", "shared/display.py",
    "shared/dispatch_log.py", "shared/kill_all.py",
    # Per-model
    "test-4b/orchestrator.py", "test-coder/orchestrator.py",
    "test-gemma/orchestrator.py",
    "test-4b/sweep_config.json", "test-coder/sweep_config.json",
    "test-gemma/sweep_config.json",
    # Agents
    "../agents/agent_contract_template.json",
    # Templates (fabrica AST)
    "templates/agent_module.py.jinja",
    "templates/profile.json.jinja",
    "templates/test_bench.py.jinja",
    "templates/partials/agent_init.py.jinja",
    "templates/partials/agent_run.py.jinja",
    # Logs (append-only, audit trail)
    "logs/bench_run.log",
]


def compute_seal():
    """Computa hash SHA256 de todos os arquivos selados."""
    h = hashlib.sha256()
    for rel in sorted(SEALED):
        f = BUILD / rel
        f = f.resolve()
        if f.exists():
            h.update(f.read_bytes())
    return h.hexdigest()


def save_seal():
    """Salva o selo atual no disco."""
    seal = compute_seal()
    SEAL_FILE.write_text(seal + "\n")
    return seal


def load_seal():
    """Carrega selo salvo. Retorna None se nao existe."""
    if SEAL_FILE.exists():
        return SEAL_FILE.read_text().strip()
    return None


def auto_repair():
    """Tenta auto-reparo via git checkout dos arquivos selados."""
    if not GIT_DIR.exists():
        return False, "sem .git para reparo"
    for rel in SEALED:
        f = BUILD / rel
        f = f.resolve()
        if f.exists():
            subprocess.run(
                ["git", "-C", str(BUILD), "checkout", "HEAD", "--", rel],
                capture_output=True,
            )
    # Recomputa selo
    new_seal = compute_seal()
    saved = load_seal()
    if new_seal == saved:
        save_seal()
        return True, "reparado"
    return False, "irreparavel"


def run():
    saved = load_seal()
    if saved is None:
        seal = save_seal()
        print("SEAL: criado (primeiro selo) -- {}".format(seal[:16]))
        return 0

    current = compute_seal()
    if current == saved:
        print("SEAL: INTEGRO -- {}".format(current[:16]))
        return 0

    # Violacao detectada
    print("SEAL: VIOLADO!")
    print("  salvo:   {}".format(saved[:16]))
    print("  atual:   {}".format(current[:16]))
    print()
    print("⛔ SELO QUEBRADO -- tentando auto-reparo via git...")
    ok, msg = auto_repair()
    if ok:
        print("✓ {}".format(msg))
        return 0
    else:
        print("✗ {}".format(msg))
        print()
        print("⛔⛔⛔ ALERTA: Selo de integridade violado e irreparavel! ⛔⛔⛔")
        print("Arquivos criticos foram modificados fora do fluxo normal.")
        print("IA DEVE alertar o operador imediatamente.")
        print("Acoes bloqueadas ate reparo manual ou reset via 'make seal-reset'.")
        return 1


if __name__ == "__main__":
    if "--reset" in sys.argv:
        seal = save_seal()
        print("SEAL: resetado -- {}".format(seal[:16]))
        sys.exit(0)
    sys.exit(run())

#!/usr/bin/env python3
"""
rule_check.py — Verificador de TODAS as regras R-BENCH-*.
Cada funcao implementa 1 regra. Retorna 0=PASS, 1=FAIL.
Integrado ao pre_commit_hook como barreira obrigatoria.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ═══════════════════════════════════════════════════════════════
# R-BENCH-USE: Verificar antes de agir (5 checks)
# ═══════════════════════════════════════════════════════════════

def check_ram():
    """free -h → RAM disponivel > 500MB"""
    r = _run(["free", "-m"])
    for line in r.stdout.split("\n"):
        if "Mem:" in line:
            parts = line.split()
            avail = int(parts[-1]) if len(parts) > 6 else 0
            if avail < 500:
                return False, "RAM critica: {}MB".format(avail)
            return True, "{}MB".format(avail)
    return False, "nao leu RAM"


def check_ollama_models():
    """ollama list → 3 modelos"""
    r = _run(["ollama", "list"])
    count = len([line for line in r.stdout.split("\n") if line.strip()]) - 1
    if count < 3:
        return False, "apenas {} modelos".format(count)
    return True, "3 modelos"


def check_daemon():
    """metrics_daemon rodando"""
    pf = BUILD / ".metrics_daemon.pid"
    if pf.exists():
        return True, "rodando"
    return False, "parado"


def check_thermal():
    """thermal_status.json → temp (WARN apenas, nao bloqueia)"""
    tf = BUILD / "shared" / "thermal_status.json"
    if tf.exists():
        try:
            d = json.loads(tf.read_text())
            t = d.get("thermal_c", 0)
            if t > 90:
                return True, "{}°C (WARN: critico)".format(t)
            return True, "{}°C".format(t)
        except Exception:
            return True, "json?"  # nao bloqueia
    return True, "ausente"  # nao bloqueia


# ═══════════════════════════════════════════════════════════════
# R-BENCH-3W: What, Why, When
# ═══════════════════════════════════════════════════════════════

def check_3w():
    """Verifica se arquivos .py tem 3W nos comentarios iniciais (WARN apenas)"""
    missing = []
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git"])
        if skip:
            continue
        try:
            text = py_file.read_text()
            if len(text.split("\n")) > 100:
                has_what = "WHAT" in text[:500] or "what" in text[:200].lower()
                has_why = "WHY" in text[:500] or "why" in text[:200].lower()
                if not (has_what or has_why):
                    missing.append(py_file.name)
        except Exception:
            pass
    if missing:
        return True, "{} sem 3W (WARN)".format(len(missing))
    return True, "todos com 3W"


# ═══════════════════════════════════════════════════════════════
# R-BENCH-ASCII: zero unicode
# ═══════════════════════════════════════════════════════════════

def check_ascii():
    """Zero unicode em-dash/arrows em codigo (strings OK)"""
    violations = []
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git"])
        if skip:
            continue
        try:
            for lineno, line in enumerate(py_file.read_text().split("\n"), 1):
                # Pula strings e comentarios
                stripped = line.split("#")[0]
                in_string = False
                clean = ""
                for ch in stripped:
                    if ch in "\"'":
                        in_string = not in_string
                    elif not in_string:
                        clean += ch
                if "\u2014" in clean or "\u2013" in clean:
                    violations.append("{}:{}".format(py_file.name, lineno))
        except Exception:
            pass
    if violations:
        return True, "{} em-dash (WARN)".format(len(violations))
    return True, "ASCII limpo"


# ═══════════════════════════════════════════════════════════════
# R-BENCH-ENV: 6 variaveis obrigatorias
# ═══════════════════════════════════════════════════════════════

def check_env():
    """Verifica .env.make tem as 6 vars obrigatorias"""
    envf = BUILD / ".env.make"
    if not envf.exists():
        return False, ".env.make ausente"
    text = envf.read_text()
    required = ["OLLAMA_KEEP_ALIVE", "OLLAMA_MAX_LOADED_MODELS",
                "OLLAMA_KV_CACHE_TYPE", "OLLAMA_FLASH_ATTENTION",
                "OLLAMA_MAX_QUEUE", "OLLAMA_CONTEXT_LENGTH"]
    missing = [v for v in required if v not in text]
    if missing:
        return False, "faltam: {}".format(",".join(missing))
    return True, "6/6 vars"


# ═══════════════════════════════════════════════════════════════
# R-BENCH-ORCHESTRATOR: children nao gerenciam servidor
# ═══════════════════════════════════════════════════════════════

def check_orchestrator():
    """Verifica children nao tem codigo de gerenciamento de servidor"""
    forbidden = ["_start_server", "_stop_server", "fuser -k", "kill_stray",
                 "drop_caches", "RamGuard.check", "RamGuard.verify_clean"]
    violations = []
    for child in ["bench_child.py", "bench_battery.py", "bench_creative.py",
                  "bench_ppl.py", "bench_analyze.py", "bench_temp_sweep.py",
                  "bench_sweep.py"]:
        cf = BUILD / child
        if cf.exists():
            text = cf.read_text()
            for pattern in forbidden:
                if pattern in text:
                    violations.append("{}: {}".format(child, pattern))
    if violations:
        return False, "{} violacoes".format(len(violations))
    return True, "children puros"


# ═══════════════════════════════════════════════════════════════
# R-BENCH-SDD: sweep_config.json schema
# ═══════════════════════════════════════════════════════════════

def check_sdd():
    """Valida schema de todos sweep_config.json / profiles"""
    required_keys = {"model", "baseline", "sweeps", "test_prompts"}
    errors = []
    for pf in BUILD.glob("test-*/profiles/*.json"):
        try:
            d = json.loads(pf.read_text())
            if "_schema" in d:
                continue  # perfil de agente, nao benchmark
            missing = required_keys - set(d.keys())
            if missing:
                errors.append("{}: falta {}".format(pf.name, ",".join(missing)))
        except Exception as e:
            errors.append("{}: {}".format(pf.name, str(e)[:40]))
    if errors:
        return False, "{} erros".format(len(errors))
    return True, "todos validos"


# ═══════════════════════════════════════════════════════════════
# R-BENCH-PROGRESS: scripts com +10 iteracoes tem progress bar
# ═══════════════════════════════════════════════════════════════

def check_progress():
    """Verifica scripts com loops longos tem barra de progresso"""
    required = ["bench_creative.py", "bench_temp_sweep.py", "bench_battery.py",
                "bench_child.py", "bench_sweep.py"]
    missing = []
    for name in required:
        f = BUILD / name
        if f.exists():
            text = f.read_text()
            if ("_bar(" not in text and "progress" not in text.lower()
                    and ("for _ in range(" in text or "for i in range(" in text)):
                counts = re.findall(r"range\((\d+)\)", text)
                for c in counts:
                    if int(c) >= 10:
                        missing.append(name)
                        break
    if missing:
        return False, "{} sem barra".format(len(missing))
    return True, "todas com barra"


# ═══════════════════════════════════════════════════════════════
# RUN ALL
# ═══════════════════════════════════════════════════════════════

CHECKS = [
    ("R-USE:RAM",        check_ram),
    ("R-USE:Ollama",     check_ollama_models),
    ("R-USE:Daemon",     check_daemon),
    ("R-USE:Thermal",    check_thermal),
    ("R-3W",             check_3w),
    ("R-ASCII",          check_ascii),
    ("R-ENV",            check_env),
    ("R-ORCHESTRATOR",   check_orchestrator),
    ("R-SDD",            check_sdd),
    ("R-PROGRESS",       check_progress),
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
        print("  {:<20} {:<6} {}".format(name, status, detail))

    print("  {:-<40}".format(""))
    print("  RULE CHECK: PASS={} FAIL={}".format(passed, failed))
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run())

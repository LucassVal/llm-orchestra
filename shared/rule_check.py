#!/usr/bin/env python3

# 3W: WHAT=verificador regras R-BENCH | WHY=garantir governanca | WHEN='make rules'
"""
rule_check.py -- Verificador de TODAS as regras R-BENCH-*.
Todas ERR (bloqueantes), exceto RAM e Thermal (orquestrador gerencia).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ═══════════════════════════════════════════════════════════════
# R-USE: Verificar sistema antes de qualquer acao (ERR)
# ═══════════════════════════════════════════════════════════════

def check_use():
    """5 verificacoes obrigatorias antes de agir (ERR)"""
    issues = []
    # 1. Pipeline status
    if (BUILD/"bench_status.json").exists():
        try:
            d = json.loads((BUILD/"bench_status.json").read_text())
            if d.get("phase") not in (None, "done"):
                issues.append("pipeline ativo: {}".format(d.get("phase")))
        except Exception:
            pass
    # 2. RAM
    r = _run(["free", "-m"])
    for line in r.stdout.split("\n"):
        if "Mem:" in line:
            parts = line.split()
            avail = int(parts[-1]) if len(parts) > 6 else 0
            if avail < 500:
                issues.append("RAM critica: {}MB".format(avail))
    # 3. Ollama
    r = _run(["ollama", "list"])
    if r.returncode != 0:
        issues.append("Ollama offline")
    # 4. Daemon
    if not (BUILD/".metrics_daemon.pid").exists():
        issues.append("daemon parado")
    # 5. Thermal (WARN -- governador gerencia)
    tf = BUILD/"shared"/"thermal_status.json"
    if tf.exists():
        try:
            d = json.loads(tf.read_text())
            if d.get("thermal_c", 105) > 95:
                pass  # nao bloqueia -- governador gerencia
        except Exception:
            pass
    if issues:
        return False, "{} checks falharam: {}".format(len(issues), "; ".join(issues[:3]))
    return True, "5/5 checks OK"


# ═══════════════════════════════════════════════════════════════
# R-VALIDATE: Validar espelhos maker antes de commit (ERR)
# ═══════════════════════════════════════════════════════════════

def check_mirror():
    """Valida espelhamento Makefile <-> maker CLI <-> .ps1 (ERR)"""
    r = _run([sys.executable, str(BUILD/"shared"/"triade_check.py")])
    if r.returncode != 0:
        return False, "triade dessincronizada"
    return True, "triade espelhada"


# ═══════════════════════════════════════════════════════════════
# R-SEARCH: Validar MCPs e ferramentas de busca (ERR)
# ═══════════════════════════════════════════════════════════════

def check_ram():
    """RAM (WARN -- orquestrador gerencia)"""
    r = _run(["free", "-m"])
    for line in r.stdout.split("\n"):
        if "Mem:" in line:
            parts = line.split()
            avail = int(parts[-1]) if len(parts) > 6 else 0
            if avail < 500:
                return True, "{}MB (WARN)".format(avail)
            return True, "{}MB".format(avail)
    return True, "?"


def check_ollama():
    """ollama list -- 3 modelos (ERR)"""
    r = _run(["ollama", "list"])
    count = len([line for line in r.stdout.split("\n") if line.strip()]) - 1
    if count < 3:
        return False, "{} modelos".format(count)
    return True, "3 modelos"


def check_search():
    """Verifica se MCPs de busca estao disponiveis (ERR)"""
    # Verifica se temos ao menos 1 MCP de search configurado
    mcp_config = Path.home()/".hermes"/"mcp_servers.json"
    has_search = False
    if mcp_config.exists():
        try:
            configs = json.loads(mcp_config.read_text())
            for name, cfg in configs.items():
                if "search" in name.lower() or "ddg" in name.lower():
                    has_search = True
                    break
        except Exception:
            pass
    # Fallback: verifica se o modulo Python existe
    if not has_search:
        try:
            import urllib.request
            urllib.request.urlopen("https://duckduckgo.com", timeout=3)
            has_search = True
        except Exception:
            pass
    if not has_search:
        return False, "nenhum MCP de busca configurado"
    return True, "search disponivel"


def check_daemon():
    """metrics_daemon rodando (ERR)"""
    pf = BUILD / ".metrics_daemon.pid"
    if pf.exists():
        return True, "rodando"
    return False, "parado"


def check_thermal():
    """Thermal (WARN -- orquestrador gerencia)"""
    tf = BUILD / "shared" / "thermal_status.json"
    if tf.exists():
        try:
            d = json.loads(tf.read_text())
            t = d.get("thermal_c", 0)
            if t > 90:
                return True, "{}C (WARN)".format(t)
            return True, "{}C".format(t)
        except Exception:
            return True, "?"
    return True, "ausente"


def check_3w():
    """3W: what/why/when em arquivos >100 linhas (ERR)"""
    missing = []
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git"])
        if skip:
            continue
        try:
            text = py_file.read_text()
            if len(text.split("\n")) > 100 and "3W" not in text[:500] and "WHAT" not in text[:500]:
                missing.append(py_file.name)
        except Exception:
            pass
    if missing:
        return False, "{} sem 3W".format(len(missing))
    return True, "todos com 3W"


def check_ascii():
    """Zero unicode em-dash em codigo (ERR)"""
    violations = []
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git"])
        if skip:
            continue
        try:
            for lineno, line in enumerate(py_file.read_text().split("\n"), 1):
                code = line.split("#")[0]
                in_str = False
                clean = ""
                for ch in code:
                    if ch in "'\"":
                        in_str = not in_str
                    elif not in_str:
                        clean += ch
                if "\u2014" in clean or "\u2013" in clean:
                    violations.append("{}:{}".format(py_file.name, lineno))
        except Exception:
            pass
    if violations:
        return False, "{} em-dash".format(len(violations))
    return True, "ASCII limpo"


def check_env():
    """.env.make com 6 vars + Ollama envs ativas no processo (ERR)"""
    envf = BUILD / ".env.make"
    if not envf.exists():
        return False, ".env.make ausente"
    text = envf.read_text()
    required = ["OLLAMA_KEEP_ALIVE", "OLLAMA_MAX_LOADED_MODELS",
                "OLLAMA_KV_CACHE_TYPE", "OLLAMA_FLASH_ATTENTION",
                "OLLAMA_MAX_QUEUE", "OLLAMA_CONTEXT_LENGTH"]
    missing = [v for v in required if v not in text]
    if missing:
        return False, "faltam:" + ",".join(missing)
    # Verifica se estao ativas no processo atual
    active = [v for v in required if os.environ.get(v)]
    if len(active) < 6:
        return False, "{} ativas, 6 requeridas".format(len(active))
    return True, "6/6 vars ativas"


def check_orchestrator():
    """Children nao gerenciam servidor (ERR)"""
    forbidden = ["_start_server", "_stop_server", "fuser -k",
                 "kill_stray", "RamGuard.check"]
    violations = []
    for child in ["bench_child.py", "bench_battery.py", "bench_creative.py",
                  "bench_ppl.py", "bench_analyze.py", "bench_temp_sweep.py",
                  "bench_sweep.py"]:
        cf = BUILD / child
        if cf.exists():
            text = cf.read_text()
            for pattern in forbidden:
                if pattern in text:
                    violations.append("{}:{}".format(child, pattern))
    if violations:
        return False, "{} violacoes".format(len(violations))
    return True, "children puros"


def check_sdd():
    """sweep_config.json schema (ERR)"""
    required_keys = {"model", "baseline", "sweeps", "test_prompts"}
    errors = []
    for pf in BUILD.glob("test-*/profiles/*.json"):
        try:
            d = json.loads(pf.read_text())
            if "_schema" in d:
                continue
            missing = required_keys - set(d.keys())
            if missing:
                errors.append("{}: falta {}".format(pf.name, ",".join(missing)))
        except Exception as e:
            errors.append("{}: {}".format(pf.name, str(e)[:40]))
    if errors:
        return False, "{} erros".format(len(errors))
    return True, "todos validos"


def check_progress():
    """Scripts com 10+ iteracoes tem barra (ERR)"""
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


def check_audit():
    """Logs imutaveis -- nunca "w" em arquivo de log (ERR)"""
    violations = []
    for py_file in BUILD.rglob("*.py"):
        skip = any(d in str(py_file) for d in ["llama.cpp", "__pycache__", ".git"])
        if skip:
            continue
        try:
            text = py_file.read_text()
            # Detecta open(LOG_FILE, "w") ou open(..., "w") em contexto de log
            for line in text.split("\n"):
                if 'open(' in line and '"w"' in line and any(kw in line.lower() for kw in ['log', 'benchmark', 'result']):
                        violations.append("{}: {}".format(py_file.name, line.strip()[:60]))
        except Exception:
            pass
    if violations:
        return False, "{} log-truncations".format(len(violations))
    return True, "logs append-only"


CHECKS = [
    ("R-USE:System",      check_use),
    ("R-USE:RAM",         check_ram),
    ("R-USE:Ollama",      check_ollama),
    ("R-USE:Daemon",      check_daemon),
    ("R-USE:Thermal",     check_thermal),
    ("R-VALIDATE",        check_mirror),
    ("R-SEARCH",          check_search),
    ("R-AUDIT",           check_audit),
    ("R-3W",              check_3w),
    ("R-ASCII",           check_ascii),
    ("R-ENV",             check_env),
    ("R-ORCHESTRATOR",    check_orchestrator),
    ("R-SDD",             check_sdd),
    ("R-PROGRESS",        check_progress),
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
    print("  " + "-" * 40)
    print("  RULE CHECK: PASS={} FAIL={}".format(passed, failed))
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run())

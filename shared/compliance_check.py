#!/usr/bin/env python3
# 3W: WHAT=compliance audit | WHY=verificar integridade ecossistema | WHEN=checkpoint/commit
"""
compliance_check.py v3 -- Auditoria de conformidade por categorias.
Categorias: SYSTEM, CODE, ARCHITECTURE, TRIADE, SEAL.
Cada categoria tem sub-checks. Total: ~25 checks.
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BUILD = Path(__file__).parent.parent
VAULT = Path("/storage/emulated/0/Obsidian/Lucas/metricas")


def _json_ok(path):
    try:
        json.loads(path.read_text())
        return True
    except Exception:
        return False


def run():
    results = {}
    tstamp = datetime.now().strftime("%H:%M:%S")

    # ═══════════════════════════════════════════════════════
    # SYSTEM -- Infraestrutura operacional
    # ═══════════════════════════════════════════════════════
    system = {}

    # Daemon
    pid_file = BUILD / ".metrics_daemon.pid"
    alive = False
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        alive = Path("/proc/" + pid).exists()
    system["daemon"] = {"status": "PASS" if alive else "FAIL", "detail": "PID " + pid if alive else "morto"}

    # Ollama
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    count = len([line for line in r.stdout.split("\n") if line.strip()]) - 1
    system["ollama"] = {"status": "PASS" if count >= 3 else "FAIL", "detail": "{} modelos".format(count)}

    # RAM
    r = subprocess.run(["free", "-m"], capture_output=True, text=True)
    ram_detail = "?"
    for line in r.stdout.split("\n"):
        if "Mem:" in line:
            parts = line.split()
            ram_detail = "{}MB".format(parts[-1]) if len(parts) > 6 else "?"
    system["ram"] = {"status": "PASS", "detail": ram_detail}

    # Thermal
    tf = BUILD/"shared"/"thermal_status.json"
    thermal_detail = "?"
    if tf.exists():
        try:
            d = json.loads(tf.read_text())
            thermal_detail = "{}C".format(d.get("thermal_c", "?"))
        except Exception:
            pass
    system["thermal"] = {"status": "PASS", "detail": thermal_detail}

    # Env
    env_ok = (BUILD/".env.make").exists() and (BUILD/".env").exists()
    system["env"] = {"status": "PASS" if env_ok else "FAIL", "detail": "ambos" if env_ok else "faltando"}

    results["SYSTEM"] = system

    # ═══════════════════════════════════════════════════════
    # CODE -- Qualidade de codigo
    # ═══════════════════════════════════════════════════════
    code = {}

    # Ruff
    r = subprocess.run(
        ["ruff", "check", str(BUILD), "--exclude", "llama.cpp", "--statistics"],
        capture_output=True, text=True,
    )
    ruff_ok = r.returncode == 0
    code["ruff"] = {"status": "PASS" if ruff_ok else "FAIL", "detail": "0 erros" if ruff_ok else r.stdout.strip()[:60]}

    # Isort
    r = subprocess.run(
        ["isort", "--check-only", "--diff", str(BUILD), "--skip", "llama.cpp", "--skip", "__pycache__"],
        capture_output=True, text=True,
    )
    code["isort"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "detail": "ordenado" if r.returncode == 0 else "desordenado"}

    # PyCheck
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"py_check.py")],
        capture_output=True, text=True,
    )
    code["pycheck"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "detail": r.stdout.strip().split("\n")[-1][:40]}

    # Pytest
    r = subprocess.run(
        ["pytest", str(BUILD/"tests"), "--co", "-q"],
        capture_output=True, text=True,
    )
    n_tests = "?"
    for line in (r.stdout + r.stderr).split("\n"):
        if "collected" in line.lower():
            n_tests = line.strip()[:50]
            break
    code["pytest"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "detail": n_tests}

    # Circularity
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"circularity_check.py")],
        capture_output=True, text=True,
    )
    code["deps"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "detail": r.stdout.strip().split("\n")[-1][:40]}

    # AI Slop
    r = subprocess.run(
        ["aislop", str(BUILD), "--ignore", "llama.cpp", "--exit-zero"],
        capture_output=True, text=True,
    )
    slop_count = len([line for line in r.stdout.split("\n") if line.strip()])
    code["slop"] = {"status": "PASS" if slop_count == 0 else "FAIL", "detail": "{} slops".format(slop_count)}

    results["CODE"] = code

    # ═══════════════════════════════════════════════════════
    # ARCHITECTURE -- Design e estrutura
    # ═══════════════════════════════════════════════════════
    arch = {}

    # Profiles JSON
    ok_p = bad_p = 0
    for pf in BUILD.glob("test-*/profiles/*.json"):
        if _json_ok(pf):
            ok_p += 1
        else:
            bad_p += 1
    arch["profiles"] = {"status": "PASS" if bad_p == 0 else "FAIL", "detail": "{} ok".format(ok_p)}

    # SDD (sweep_config)
    req = {"model", "baseline", "sweeps", "test_prompts"}
    sdd_errors = 0
    for pf in BUILD.glob("test-*/sweep_config.json"):
        try:
            d = json.loads(pf.read_text())
            if req - set(d.keys()):
                sdd_errors += 1
        except Exception:
            sdd_errors += 1
    arch["sdd"] = {"status": "PASS" if sdd_errors == 0 else "FAIL", "detail": "{} erros".format(sdd_errors)}

    # DDD (cross-child)
    child_dirs = ["test-4b", "test-coder", "test-gemma"]
    ddd_violations = 0
    for child in child_dirs:
        for py_file in (BUILD/child).glob("**/*.py"):
            try:
                content = py_file.read_text()
                for other in child_dirs:
                    if other != child and other in content:
                        ddd_violations += 1
            except Exception:
                pass
    arch["ddd"] = {"status": "PASS" if ddd_violations == 0 else "FAIL", "detail": "{} violacoes".format(ddd_violations)}

    # Orphans
    root_ok = {
        "Makefile", "nc.ps1", "pyproject.toml", "RULES.md", "README.md", ".gitignore",
        "meta_orchestrator.py", "bench_orchestrator.py",
        "bench_analyze.py", "bench_battery.py", "bench_child.py",
        "bench_creative.py", "bench_ppl.py", "bench_sweep.py",
        "bench_sys.py", "bench_temp_sweep.py",
        "Qwen_Qwen3-4B-Q4_K_M.gguf",
        "benchmark_pipeline.json", "bench_status.json",
        ".metrics_daemon.pid", ".env", ".env.make", ".seal",
    }
    orphan_count = 0
    for f in BUILD.iterdir():
        if f.is_file() and not f.name.startswith(".") and f.name not in root_ok and not f.name.endswith(".pyc"):
            orphan_count += 1
    arch["orphans"] = {"status": "PASS" if orphan_count == 0 else "FAIL", "detail": "{} orfaos".format(orphan_count)}

    # RULES.md
    rules_dirs = [BUILD, BUILD/"shared", BUILD/"test-4b", BUILD/"test-coder", BUILD/"test-gemma", Path.home()/"agents"]
    missing_rules = [d.name for d in rules_dirs if not (d/"RULES.md").exists()]
    arch["rules_md"] = {"status": "PASS" if not missing_rules else "FAIL", "detail": "{} ausentes".format(len(missing_rules))}

    # Clean
    cache_count = len(list(BUILD.rglob("__pycache__")))
    arch["clean"] = {"status": "PASS" if cache_count < 10 else "WARN", "detail": "{} pycache".format(cache_count)}

    # Tests
    test_files = list((BUILD/"tests").glob("test_*.py")) if (BUILD/"tests").exists() else []
    arch["tests"] = {"status": "PASS" if len(test_files) >= 1 else "WARN", "detail": "{} files".format(len(test_files))}

    # Dispatch log
    dispatch_dir = BUILD / "logs" / "dispatch"
    dispatch_files = list(dispatch_dir.glob("*.json")) if dispatch_dir.exists() else []
    arch["dispatch"] = {"status": "PASS" if dispatch_dir.exists() else "WARN", "detail": "{} disparos".format(len(dispatch_files))}

    results["ARCHITECTURE"] = arch

    # ═══════════════════════════════════════════════════════
    # TRIADE -- Espelhamento e integracao
    # ═══════════════════════════════════════════════════════
    triade = {}

    # Triade mirror
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"triade_check.py")],
        capture_output=True, text=True,
    )
    triade["mirror"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "detail": r.stdout.strip().split("\n")[-1][:50]}

    # Skills
    skills_dir = Path.home()/".hermes"/"skills"/"mlops"
    if skills_dir.exists():
        names = [d.name for d in skills_dir.iterdir() if d.is_dir() and (d/"SKILL.md").exists()]
        triade["skills"] = {"status": "PASS" if len(names) >= 4 else "WARN", "detail": "{}:{}".format(len(names), ",".join(sorted(names)[:3]))}
    else:
        triade["skills"] = {"status": "WARN", "detail": "ausente"}

    # Maker CLI
    maker_file = Path.home()/"NeoCortex"/"maker"/"cmd_bench.py"
    triade["maker"] = {"status": "PASS" if maker_file.exists() else "FAIL", "detail": "presente" if maker_file.exists() else "ausente"}

    # Agents
    agents_dir = Path.home()/"agents"
    if agents_dir.exists():
        contracts = list(agents_dir.glob("*.json"))
        triade["agents"] = {"status": "PASS" if contracts else "WARN", "detail": "{} contratos".format(len(contracts))}
    else:
        triade["agents"] = {"status": "FAIL", "detail": "ausente"}

    # Rules check
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"rule_check.py")],
        capture_output=True, text=True,
    )
    triade["rules"] = {"status": "PASS" if r.returncode == 0 else "FAIL", "detail": r.stdout.strip().split("\n")[-1][:40]}

    # Metrics flow
    vault_ok = VAULT.exists()
    csv_ok = all((VAULT/f).exists() for f in ["history_phone.csv", "history_4b.csv", "history_coder.csv", "history_gemma.csv"])
    status_age = time.time() - (VAULT/"llm_status.md").stat().st_mtime if (VAULT/"llm_status.md").exists() else 0
    triade["metrics"] = {"status": "PASS" if vault_ok and csv_ok and status_age < 30 else "WARN", "detail": "vault={} age={:.0f}s".format(vault_ok, status_age)}

    results["TRIADE"] = triade

    # ═══════════════════════════════════════════════════════
    # VALIDATION -- Funcoes, testes, cobertura
    # ═══════════════════════════════════════════════════════
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"system_validate.py")],
        capture_output=True, text=True,
    )
    val_lines = r.stdout.split("\n")

    # Extrai metricas do output
    funcs_real = funcs_stubs = 0
    triad_ok = False
    seal_ok = False
    for line in val_lines:
        if "Total:" in line:
            pass  # funcs_total -- informativo
        elif "Reais:" in line:
            funcs_real = int(line.split(":")[-1].strip())
        elif "Stubs:" in line:
            funcs_stubs = int(line.split(":")[-1].strip())
        elif line.strip().startswith("✓ triade"):
            triad_ok = True
        elif line.strip().startswith("✓ commit:"):
            seal_ok = True

    validation = {
        "funcs": {"status": "PASS" if funcs_stubs == 0 else "FAIL", "detail": "{} reais, {} stubs".format(funcs_real, funcs_stubs)},
        "triade": {"status": "PASS" if triad_ok else "FAIL", "detail": "espelhada" if triad_ok else "gaps"},
        "seal_log": {"status": "PASS" if seal_ok else "FAIL", "detail": "vinculado" if seal_ok else "orfao"},
    }

    # Test coverage: verifica se cada .py tem correspondente test_
    py_files = [f for f in BUILD.rglob("*.py") if "llama.cpp" not in str(f) and "__pycache__" not in str(f) and ".git" not in str(f)]
    test_files = {f.stem.replace("test_", "") for f in (BUILD/"tests").glob("test_*.py")} if (BUILD/"tests").exists() else set()
    uncovered = [f.name for f in py_files if f.stem not in test_files and f.stat().st_size > 500]
    validation["coverage"] = {"status": "PASS" if len(uncovered) < 20 else "WARN", "detail": "{} sem teste".format(len(uncovered))}

    results["VALIDATION"] = validation
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"seal_check.py")],
        capture_output=True, text=True,
    )
    seal_ok = r.returncode == 0
    seal_text = r.stdout.strip().split("\n")[0] if r.stdout else "?"
    results["SEAL"] = {"integrity": {"status": "PASS" if seal_ok else "FAIL", "detail": seal_text[:40]}}

    # ═══════════════════════════════════════════════════════
    # OUTPUT (formato padronizado — NUNCA alterar)
    # ═══════════════════════════════════════════════════════
    print("")
    print("  COMPLIANCE AUDIT | v3 | " + tstamp)
    print("  " + "-" * 50)
    total_pass = 0
    total_fail = 0

    for category, checks in results.items():
        print("")
        print("  " + "=" * 50)
        print("  " + category)
        print("  " + "=" * 50)
        cat_pass = 0
        cat_fail = 0
        for name, info in checks.items():
            st = info["status"]
            if st == "PASS":
                cat_pass += 1
            elif st == "FAIL":
                cat_fail += 1
            print("    {:<15} {:<6} {}".format(name, st, info["detail"]))
        total_pass += cat_pass
        total_fail += cat_fail
        print("    " + "-" * 40)
        print("    {}: PASS={} FAIL={}".format(category, cat_pass, cat_fail))

    print("")
    print("  " + "=" * 50)
    print("  TOTAL: PASS={} FAIL={}".format(total_pass, total_fail))
    return 1 if total_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
"""
compliance_check.py v2 — Auditoria completa de conformidade.
Checks: triade, profiles, rules, daemon, ollama, ruff, env, skills,
        metrics_flow, ddd_hierarchy, orphan_files.
Termos: PASS (conforme), FAIL (bloqueante), WARN (nao-bloqueante), TBT (stub).
Regra DDD: children so comunicam com o pai. Violacao = FAIL.
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BUILD = Path(__file__).parent.parent
VAULT = Path("/storage/emulated/0/Obsidian/Lucas/metricas")

# ── Bloqueante: FAIL interrompe deploy/pipeline ──
# ── Nao-bloqueante: WARN/TBT informa mas nao trava ──

def _json_ok(path):
    try:
        json.loads(path.read_text())
        return True
    except Exception:
        return False


def run():
    results = {}
    tstamp = datetime.now().strftime("%H:%M:%S")

    # ═══ 1. TRIADE MIRROR ═══
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"triade_check.py")],
        capture_output=True, text=True,
    )
    triade_ok = r.returncode == 0
    results["1_triade"] = {
        "status": "PASS" if triade_ok else "FAIL",
        "detail": r.stdout.strip().split("\n")[-1][:80] if r.stdout else "?",
    }

    # ═══ 2. PROFILES JSON ═══
    ok = 0
    bad = 0
    for pf in BUILD.glob("test-*/profiles/*.json"):
        if _json_ok(pf):
            ok += 1
        else:
            bad += 1
    results["2_profiles"] = {
        "status": "PASS" if bad == 0 else "FAIL",
        "detail": "{} ok, {} invalidos".format(ok, bad),
    }

    # ═══ 3. RULES.md ═══
    missing = []
    for folder in [BUILD, BUILD/"shared", BUILD/"test-4b", BUILD/"test-coder",
                   BUILD/"test-gemma", Path.home()/"agents"]:
        if not (folder/"RULES.md").exists():
            missing.append(folder.name)
    results["3_rules"] = {
        "status": "PASS" if not missing else "FAIL",
        "detail": "faltando: " + ",".join(missing) if missing else "6/6 presentes",
    }

    # ═══ 4. DAEMON ═══
    pid_file = BUILD/".metrics_daemon.pid"
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        alive = Path("/proc/"+pid).exists()
    else:
        alive = False
    results["4_daemon"] = {
        "status": "PASS" if alive else "FAIL",
        "detail": "PID " + pid if alive else "morto",
    }

    # ═══ 5. OLLAMA ═══
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    count = len([line for line in r.stdout.split("\n") if line.strip()]) - 1
    results["5_ollama"] = {
        "status": "PASS" if count >= 3 else "FAIL",
        "detail": "{} modelos".format(count),
    }

    # ═══ 6. RUFF ═══
    r = subprocess.run(
        ["ruff", "check", str(BUILD), "--exclude", "llama.cpp", "--statistics"],
        capture_output=True, text=True,
    )
    ruff_ok = r.returncode == 0
    results["6_ruff"] = {
        "status": "PASS" if ruff_ok else "FAIL",
        "detail": "0 erros" if ruff_ok else r.stdout.strip()[:80],
    }

    # ═══ 6b. ISORT ═══
    r = subprocess.run(
        ["isort", "--check-only", "--diff", str(BUILD), "--skip", "llama.cpp"],
        capture_output=True, text=True,
    )
    isort_ok = r.returncode == 0
    results["6b_isort"] = {
        "status": "PASS" if isort_ok else "WARN",
        "detail": "ordenado" if isort_ok else "imports desordenados",
    }

    # ═══ 6c. MYPY ═══
    r = subprocess.run(
        ["mypy", str(BUILD), "--ignore-missing-imports"],
        capture_output=True, text=True,
    )
    mypy_ok = r.returncode == 0
    results["6c_mypy"] = {
        "status": "PASS" if mypy_ok else "WARN",
        "detail": "ok" if mypy_ok else r.stderr.strip()[:60] if r.stderr else "erro_desconhecido",
    }

    # ═══ 6d. PYTEST ═══
    r = subprocess.run(
        ["pytest", str(BUILD), "--co", "-q"],
        capture_output=True, text=True,
    )
    pytest_ok = r.returncode == 0
    n_tests = "?"
    for line in r.stdout.split("\n"):
        if "test" in line.lower() and "selected" in line.lower():
            n_tests = line.strip()
    results["6d_pytest"] = {
        "status": "PASS" if pytest_ok else "WARN",
        "detail": n_tests[:60],
    }

    # ═══ 6e. CIRCULARITY ═══
    r = subprocess.run(
        [sys.executable, str(BUILD/"shared"/"circularity_check.py")],
        capture_output=True, text=True,
    )
    circ_ok = r.returncode == 0
    results["6e_deps"] = {
        "status": "PASS" if circ_ok else "FAIL",
        "detail": r.stdout.strip().split("\n")[-1][:80] if r.stdout else "?",
    }

    # ═══ 7. ENV ═══
    env_ok = (BUILD/".env.make").exists() and (BUILD/".env").exists()
    results["7_env"] = {
        "status": "PASS" if env_ok else "FAIL",
        "detail": "ambos presentes" if env_ok else "faltando .env ou .env.make",
    }

    # ═══ 8. METRICS FLOW ═══
    vault_ok = VAULT.exists()
    csv_ok = all((VAULT/f).exists() for f in
                 ["history_phone.csv", "history_4b.csv", "history_coder.csv", "history_gemma.csv"])
    status_md_ok = (VAULT/"llm_status.md").exists()
    status_age = 0
    if status_md_ok:
        status_age = time.time() - (VAULT/"llm_status.md").stat().st_mtime
    recent = status_age < 30  # atualizado nos ultimos 30s
    results["8_metrics"] = {
        "status": "PASS" if (vault_ok and csv_ok and recent) else "FAIL",
        "detail": "vault={} csv={} age={:.0f}s".format(vault_ok, csv_ok, status_age),
    }

    # ═══ 9. DDD HIERARCHY ═══
    violations = []
    # Scan: children nao podem importar outros children
    child_dirs = ["test-4b", "test-coder", "test-gemma"]
    for child in child_dirs:
        for py_file in (BUILD/child).glob("**/*.py"):
            try:
                content = py_file.read_text()
                for other in child_dirs:
                    if other != child and other in content:
                        for line in content.split("\n"):
                            if (other in line
                                    and not line.strip().startswith("#")
                                    and ("import" in line or "from" in line)):
                                violations.append("{} importa {}".format(py_file.name, other))
            except Exception:
                pass
    results["9_ddd"] = {
        "status": "PASS" if not violations else "FAIL",
        "detail": "{} violacoes".format(len(violations)) if violations else "hierarquia limpa",
    }

    # ═══ 10. ORPHAN FILES ═══
    orphans = []
    root_allowed = {
        "Makefile", "nc.ps1", "pyproject.toml", "RULES.md",
        "meta_orchestrator.py", "bench_orchestrator.py",
        "bench_analyze.py", "bench_battery.py", "bench_child.py",
        "bench_creative.py", "bench_ppl.py", "bench_sweep.py",
        "bench_sys.py", "bench_temp_sweep.py",
        "Qwen_Qwen3-4B-Q4_K_M.gguf",
        "benchmark_pipeline.json",  # output ativo
        "bench_status.json",        # output ativo
        ".metrics_daemon.pid", ".env", ".env.make",
    }
    for f in BUILD.iterdir():
        if (f.is_file()
                and not f.name.startswith(".")
                and f.name not in root_allowed
                and not f.name.endswith(".pyc")):
            orphans.append(f.name)
    results["10_orphans"] = {
        "status": "PASS" if not orphans else "FAIL",
        "detail": "{} orfaos".format(len(orphans)) if orphans else "raiz limpa",
    }

    # ═══ 11. SKILLS ═══
    skills_dir = Path.home()/".hermes"/"skills"/"mlops"
    if skills_dir.exists():
        skill_names = [d.name for d in skills_dir.iterdir() if d.is_dir() and (d/"SKILL.md").exists()]
        results["11_skills"] = {
            "status": "PASS" if len(skill_names) >= 4 else "WARN",
            "detail": "{} skills: {}".format(len(skill_names), ",".join(sorted(skill_names))),
        }
    else:
        results["11_skills"] = {"status": "WARN", "detail": "skills_dir_ausente"}

    # ═══ TABELA ═══
    print("COMPLIANCE AUDIT v2 — " + tstamp)
    print("{:<5} {:<20} {:<6} {}".format("#", "CHECK", "STATUS", "DETAIL"))
    print("-" * 70)
    passed = 0
    failed = 0
    for key, info in results.items():
        st = info["status"]
        if st == "PASS":
            passed += 1
        elif st == "FAIL":
            failed += 1
        print("{:<5} {:<20} {:<6} {}".format(
            key.split("_")[0], key.split("_",1)[1] if "_" in key else key,
            st, info["detail"]))
    print("-" * 70)
    print("PASS={}  FAIL={}  TBT/WARN=nao-bloqueante".format(passed, failed))

    # FAIL = bloqueante (exit 1)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3

# 3W: WHAT=hub orquestracao | WHY=unificar comandos LLMs | WHEN=sempre
"""
META-ORQUESTRADOR v3 - Roteador + motor de agente com travas mecanicas.
Modos:
  python3 meta_orchestrator.py                          -> pipeline completo
  python3 meta_orchestrator.py --status                 -> progresso atual
  python3 meta_orchestrator.py --stop                   -> mata orquestrador ativo
  python3 meta_orchestrator.py --run "prompt" --model 4b  -> executa 1 inferencia
  python3 meta_orchestrator.py --serve --model 4b       -> sobe servidor seguro
  python3 meta_orchestrator.py --report [--obsidian]    -> relatorio de metricas
  python3 meta_orchestrator.py --daemon start|stop|status -> controle do coletor

HIERARQUIA:
  LEVEL 0: meta_orchestrator.py (hub unico)
    ├── children: test-4b/, test-coder/, test-gemma/ (orquestradores)
    ├── shared/thermal_governor.py (monitor sistema)
    ├── shared/metrics_reporter.py (coleta, usado por meta e daemon)
    └── shared/metrics_daemon.py (persistencia Obsidian+CSV, 5s)
  LEVEL 1: test-*/orchestrator.py → bench_orchestrator.py → bench_*.py
"""
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path

BUILD = Path(__file__).parent
STATUS_FILE = BUILD / "bench_status.json"

ORCHESTRATORS = [
    ("4b",    BUILD / "test-4b" / "orchestrator.py"),
    ("coder", BUILD / "test-coder" / "orchestrator.py"),
    ("gemma", BUILD / "test-gemma" / "orchestrator.py"),
]
TIMEOUT_PER_LLM = 7200
META_LOCK = BUILD / ".meta_running"


def show_status():
    """Exibe progresso atual do pipeline."""
    if not STATUS_FILE.exists():
        print("Nenhum pipeline rodando (bench_status.json ausente).")
        return
    try:
        s = json.loads(STATUS_FILE.read_text())
    except Exception:
        print("Status: JSON inválido.")
        return

    phase = s.get("phase", "?")
    model = s.get("model", "")
    step = s.get("step", "")
    sn = s.get("step_n", 0)
    st = s.get("step_total", 0)
    elapsed = s.get("elapsed_s", 0)
    updated = s.get("updated", "")[:19]

    bar_w = 30
    pct = sn / st if st else 0
    filled = int(bar_w * pct)
    bar = "[" + "#" * filled + "." * (bar_w - filled) + "]"

    print("META STATUS")
    print("  Fase:    {}".format(phase))
    print("  Modelo:  {}".format(model))
    print("  Etapa:   {} ({}/{})".format(step, sn, st))
    print("  Barra:   {} {:.0f}%".format(bar, pct * 100))
    print("  Elapsed: {}s ({:.0f}min)".format(elapsed, elapsed / 60))
    print("  Updated: {}".format(updated))


def stop_pipeline():
    """Mata processo do orquestrador ativo."""
    if not META_LOCK.exists():
        print("Nenhum meta rodando (lock ausente).")
        return
    try:
        pid = int(META_LOCK.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        META_LOCK.unlink()
        print("Sinal SIGTERM enviado ao PID {}.".format(pid))
    except ProcessLookupError:
        print("PID {} nao encontrado (ja morreu).".format(pid))
        META_LOCK.unlink()
    except Exception as e:
        print("Erro: {}".format(e))


def run_all():
    """Roda pipeline completo nos 3 LLMs."""
    if META_LOCK.exists():
        try:
            old_pid = int(META_LOCK.read_text().strip())
            os.kill(old_pid, 0)
            print("ERRO: Meta ja rodando (PID {}). Use --status ou --stop.".format(old_pid))
            return
        except (OSError, ValueError):
            META_LOCK.unlink()

    META_LOCK.write_text(str(os.getpid()))

    try:
        print("=" * 60)
        print("  META-ORQUESTRADOR v2 -- 3 LLMs")
        print("  4B > coder > gemma")
        print("  Status em tempo real: bench_status.json")
        print("=" * 60)
        print()

        total_start = time.time()
        results = {}

        for name, script in ORCHESTRATORS:
            test_dir = script.parent
            results_file = test_dir / "results.json"

            if not script.exists():
                print("! {}: script nao encontrado".format(name))
                results[name] = {"status": "MISSING"}
                continue

            print("> {} -- {}".format(name.upper(), datetime.now().strftime('%H:%M:%S')))
            start = time.time()
            try:
                r = subprocess.run([sys.executable, "-u", str(script)],
                                  timeout=TIMEOUT_PER_LLM)
                elapsed = time.time() - start
                status_str = "OK" if r.returncode == 0 else "FAIL({})".format(r.returncode)
                print("< {}: {} ({:.0f}min)".format(name.upper(), status_str, elapsed / 60))
            except subprocess.TimeoutExpired:
                status_str = "TIMEOUT"
                print("< {}: TIMEOUT ({}min)".format(name.upper(), TIMEOUT_PER_LLM // 60))
            except Exception as e:
                status_str = "CRASH"
                print("< {}: CRASH: {}".format(name.upper(), e))

            # Le metricas
            metrics = {"status": status_str, "model": name}
            if results_file.exists():
                try:
                    data = json.loads(results_file.read_text())
                    for r in data.get("results", []):
                        t = r.get("tests", {})
                        metrics["gb"] = r.get("gb", 0)
                        metrics["stress"] = t.get("stress", {}).get("status", "?")
                        metrics["battery"] = t.get("battery", {}).get("status", "?")
                        metrics["creative"] = t.get("creative", {}).get("status", "?")
                        metrics["temp_sweep"] = t.get("temp_sweep", {}).get("status", "?")
                        metrics["sweep"] = t.get("sweep", {}).get("status", "?")
                        metrics["ppl"] = t.get("ppl", {}).get("ppl", t.get("ppl", {}).get("status", "?"))
                        metrics["analyze"] = t.get("analyze", {}).get("status", "?")
                        metrics["ram_delta"] = r.get("ram_delta_mb", 0)
                except Exception:
                    metrics["error"] = "JSON invalido"
            else:
                metrics["error"] = "sem results.json"
            results[name] = metrics
            print()

        # Tabela
        total_elapsed = time.time() - total_start
        print("=" * 100)
        print("  META-ORQUESTRADOR -- RESULTADO FINAL")
        print("=" * 100)
        hdr = "  {:<8} {:>4} {:>7} {:>8} {:>9} {:>9} {:>6} {:>7} {:>7} {:>5} {:>6}".format(
            "LLM", "GB", "STRESS", "BATTERY", "CREATIVE", "T_SWEEP", "SWEEP", "PPL", "ANALYZE", "RAM", "STATUS")
        print(hdr)
        print("  " + "-" * 82)
        for name in ["4b", "coder", "gemma"]:
            r = results.get(name, {})
            if r.get("error"):
                print("  {:<8} {:>4} {:>7} {:>8} {:>9} {:>9} {:>6} {:>7} {:>7} {:>5} {:>6}".format(
                    name, "--", "--", "--", "--", "--", "--", "--", "--", "--", r.get("status", "?")))
                continue
            ppl_str = str(r.get("ppl", "?"))[:6]
            ram = r.get("ram_delta", 0)
            print("  {:<8} {:>4.1f} {:>7} {:>8} {:>9} {:>9} {:>6} {:>7} {:>7} {:>+4d} {:>6}".format(
                name, r.get("gb", 0), str(r.get("stress", "?"))[:7],
                str(r.get("battery", "?"))[:8], str(r.get("creative", "?"))[:9],
                str(r.get("temp_sweep", "?"))[:9], str(r.get("sweep", "?"))[:6],
                ppl_str, str(r.get("analyze", "?"))[:8], ram, r.get("status", "?")))
        print("  " + "-" * 82)
        print("  Tempo total: {:.0f}min".format(total_elapsed / 60))
        print("=" * 100)
    finally:
        if META_LOCK.exists():
            META_LOCK.unlink()


def run_agent(prompt, model_name, profile="agent_default"):
    """Executa 1 inferencia com governador termico + perfil JSON injetado."""
    import urllib.request
    sys.path.insert(0, str(BUILD))
    from bench_orchestrator import (OLLAMA_LD_PATH, OLLAMA_SERVER_BIN,
                                    ServerManager, cleanup_after_model,
                                    kill_stray)
    from shared.thermal_governor import get_governor

    # Mapeia modelo → pasta
    model_dirs = {"4b": "test-4b", "coder": "test-coder", "gemma": "test-gemma"}
    model_dir = model_dirs.get(model_name, "test-4b")

    # Carrega perfil JSON (injetado no agente)
    profile_path = BUILD / model_dir / "profiles" / "{}.json".format(profile)
    if profile_path.exists():
        p = json.loads(profile_path.read_text())
        params = p["params"]
        print("[perfil] {} ({})".format(profile_path.name, p.get("description", "")), file=sys.stderr)
    else:
        print("[perfil] {} nao encontrado, usando defaults".format(profile), file=sys.stderr)
        params = {"temperature": 0.3, "max_tokens": 256, "ctx_size": 2048,
                  "threads": 6, "batch_size": 256, "flash_attn": False, "ngl": 0}

    gguf_map = {
        "4b": BUILD / "Qwen_Qwen3-4B-Q4_K_M.gguf",
        "coder": None,
        "gemma": None,
    }
    gguf = gguf_map.get(model_name)
    if gguf and not gguf.exists():
        print("ERRO: GGUF nao encontrado: {}".format(gguf))
        return

    # Governador termico (nunca bloqueia)
    gov = get_governor()
    gov.start()
    time.sleep(0.5)

    limits = gov.limits
    # Governador pode reduzir max_tokens mas nao aumentar
    effective_tokens = min(params["max_tokens"], limits["max_tokens"])
    effective_temp = min(params["temperature"], limits["temperature"])

    print("AGENTE: {} | perfil={} | tier={} | tok={} | temp={:.1f} | thermal={:.0f}C | RAM={}MB".format(
        model_name, profile, limits["tier"], effective_tokens,
        effective_temp, limits["thermal_c"], limits["ram_avail_mb"]))

    kill_stray()
    cleanup_after_model()

    srv = ServerManager(OLLAMA_SERVER_BIN, OLLAMA_LD_PATH, port=8080)
    try:
        server_url = srv.start(str(gguf))
    except RuntimeError as e:
        print("ERRO: servidor nao subiu: {}".format(e))
        gov.stop()
        return

    try:
        body = json.dumps({
            "prompt": prompt,
            "max_tokens": effective_tokens,
            "temperature": effective_temp,
        }).encode()
        req = urllib.request.Request(
            "{}/v1/completions".format(server_url),
            data=body, headers={"Content-Type": "application/json"})
        t0 = time.time()
        resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
        elapsed = time.time() - t0
        text = resp["choices"][0]["text"]
        tokens = len(text.split())
        final_limits = gov.limits
        print("RESULTADO ({:.1f} tok/s, {:.1f}s, tier={}):".format(
            tokens/elapsed if elapsed else 0, elapsed, final_limits["tier"]))
        print(text)
        print("---")
    except Exception as e:
        print("ERRO inferencia: {}".format(e))
    finally:
        gov.stop()
        srv.stop()
        cleanup_after_model(model_name)


def serve_agent(model_name):
    """Sobe servidor seguro com travas e mantem rodando (Ctrl+C para sair)."""
    sys.path.insert(0, str(BUILD))
    from bench_orchestrator import (OLLAMA_LD_PATH, OLLAMA_SERVER_BIN,
                                    ServerManager, cleanup_after_model,
                                    kill_stray)
    gguf_map = {
        "4b": BUILD / "Qwen_Qwen3-4B-Q4_K_M.gguf",
    }
    gguf = gguf_map.get(model_name)
    if not gguf or not gguf.exists():
        print("ERRO: modelo '{}' nao suporta --serve (use 4b)".format(model_name))
        return

    kill_stray()
    cleanup_after_model()
    srv = ServerManager(OLLAMA_SERVER_BIN, OLLAMA_LD_PATH, port=8080)
    try:
        url = srv.start(str(gguf))
        print("SERVIDOR: {}".format(url))
        print("Pressione Ctrl+C para parar.")
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("Parando...")
    finally:
        srv.stop()
        cleanup_after_model(model_name)


if __name__ == "__main__":
    if "--status" in sys.argv:
        show_status()
    elif "--stop" in sys.argv:
        stop_pipeline()
    elif "--run" in sys.argv:
        idx = sys.argv.index("--run")
        prompt = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        model = "4b"
        profile = "agent_default"
        if "--model" in sys.argv:
            mi = sys.argv.index("--model")
            model = sys.argv[mi + 1] if mi + 1 < len(sys.argv) else "4b"
        if "--profile" in sys.argv:
            pi = sys.argv.index("--profile")
            profile = sys.argv[pi + 1] if pi + 1 < len(sys.argv) else "agent_default"
        run_agent(prompt, model, profile)
    elif "--serve" in sys.argv:
        model = "4b"
        if "--model" in sys.argv:
            mi = sys.argv.index("--model")
            model = sys.argv[mi + 1] if mi + 1 < len(sys.argv) else "4b"
        serve_agent(model)
    elif "--report" in sys.argv:
        from shared.metrics_reporter import (collect_metrics, format_obsidian,
                                             format_terminal)
        m = collect_metrics()
        print(format_terminal(m))
        if "--obsidian" in sys.argv:
            from shared.metrics_reporter import OBSIDIAN_REPORT
            try:
                OBSIDIAN_REPORT.parent.mkdir(parents=True, exist_ok=True)
                OBSIDIAN_REPORT.write_text(format_obsidian(m))
                print("[meta] obsidian atualizado", file=sys.stderr)
            except Exception as e:
                print("[meta] erro obsidian: {}".format(e), file=sys.stderr)
    elif "--daemon" in sys.argv:
        idx = sys.argv.index("--daemon")
        action = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "status"
        pid_file = BUILD / ".metrics_daemon.pid"

        if action == "start":
            import subprocess as _sp
            _sp.run([str(BUILD / "shared" / "watchdog_metrics.sh")])
        elif action == "stop":
            if pid_file.exists():
                pid = int(pid_file.read_text().strip())
                with suppress(Exception):
                    os.kill(pid, signal.SIGTERM)
                pid_file.unlink()
                print("daemon parado")
            else:
                print("daemon nao estava rodando")
        elif action == "status":
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    os.kill(pid, 0)
                    print("daemon rodando (PID {})".format(pid))
                except OSError:
                    print("daemon morto (PID file staled)")
            else:
                print("daemon parado")
    else:
        run_all()

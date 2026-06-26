#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
metrics_reporter.py -- Agregador de metricas em tempo real.
Le: thermal_status.json + bench_status.json + test-*/results.json
Entrega: Obsidian vault (markdown) + stdout (para bot/gateway).

Fontes:
  1. shared/thermal_status.json -- governador termico (5s pings)
  2. bench_status.json           -- progresso do pipeline (5s pings)
  3. test-*/results.json         -- resultados completos (pos-pipeline)

Modos:
  python3 shared/metrics_reporter.py                → stdout (bot)
  python3 shared/metrics_reporter.py --obsidian     → vault + stdout
  python3 shared/metrics_reporter.py --watch        → loop 5s (daemon)
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

BUILD = Path(__file__).parent.parent
SHARED = BUILD / "shared"
THERMAL_FILE = SHARED / "thermal_status.json"
STATUS_FILE = BUILD / "bench_status.json"
OBSIDIAN_VAULT = Path("/storage/emulated/0/Obsidian/Lucas")
OBSIDIAN_REPORT = OBSIDIAN_VAULT / "metricas" / "llm_status.md"


def fmt_bar(pct, width=20):
    filled = int(width * pct / 100)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def collect_metrics():
    """Coleta todas as metricas disponiveis e retorna dict formatado."""
    now = datetime.now()

    thermal = read_json(THERMAL_FILE) or {}
    status = read_json(STATUS_FILE) or {}

    # Pipeline
    phase = status.get("phase", "idle")
    model = status.get("model", "-")
    step = status.get("step", "-")
    step_n = status.get("step_n", 0)
    step_total = status.get("step_total", 0)
    elapsed = status.get("elapsed_s", 0)
    updated = status.get("updated", "")[:19]

    # Termico
    thermal_c = thermal.get("thermal_c", 0)
    ram_mb = thermal.get("ram_avail_mb", 0)
    swap_pct = thermal.get("swap_pct", 0)
    tier = thermal.get("tier", "?")
    max_tok = thermal.get("max_tokens", 0)
    temps_60s = thermal.get("temps_60s", [])

    # Resultados por modelo
    models_metrics = {}
    for test_dir in ["test-4b", "test-coder", "test-gemma"]:
        results_file = BUILD / test_dir / "results.json"
        data = read_json(results_file)
        if data:
            for r in data.get("results", []):
                t = r.get("tests", {})
                battery = t.get("battery", {})
                stress = t.get("stress", {})
                models_metrics[test_dir] = {
                    "model": r.get("model", test_dir),
                    "gb": r.get("gb", 0),
                    "stress": stress.get("status", "?"),
                    "battery": battery.get("status", "?"),
                    "battery_tok_s": battery.get("summary", {}).get("avg_tok_s", "?"),
                    "battery_score": battery.get("summary", {}).get("score", "?"),
                    "creative": t.get("creative", {}).get("status", "?"),
                    "temp_sweep": t.get("temp_sweep", {}).get("status", "?"),
                    "sweep": t.get("sweep", {}).get("status", "?"),
                    "ppl": t.get("ppl", {}).get("ppl", "?"),
                    "analyze": t.get("analyze", {}).get("status", "?"),
                    "thermal_log": r.get("thermal_log", []),
                }
        else:
            models_metrics[test_dir] = {"model": test_dir, "status": "pending"}

    # Temp history sparkline
    spark = ""
    if temps_60s:
        for t in temps_60s[-12:]:
            if t > 90:
                spark += "█"
            elif t > 80:
                spark += "▆"
            elif t > 70:
                spark += "▄"
            elif t > 60:
                spark += "▂"
            else:
                spark += " "

    return {
        "timestamp": now.isoformat(),
        "thermal": {"c": thermal_c, "tier": tier, "max_tok": max_tok,
                    "ram_mb": ram_mb, "swap_pct": swap_pct, "spark": spark,
                    "temps_60s": temps_60s},
        "pipeline": {"phase": phase, "model": model, "step": step,
                     "step_n": step_n, "step_total": step_total,
                     "elapsed_s": elapsed, "updated": updated},
        "models": models_metrics,
    }


def format_terminal(m):
    """Formato compacto para terminal/bot."""
    lines = []
    t = m["thermal"]
    p = m["pipeline"]

    # Linha termica
    lines.append("🌡 {:.0f}C {} | tier={} max_tok={} | RAM={}MB swap={:.0f}%".format(
        t["c"], t["spark"], t["tier"], t["max_tok"], t["ram_mb"], t["swap_pct"]))

    # Linha pipeline
    if p["phase"] != "idle":
        pct = p["step_n"] / p["step_total"] * 100 if p["step_total"] else 0
        bar = fmt_bar(pct)
        lines.append("⚙ {} | {} {} ({}/{}) | {}s".format(
            p["phase"], p["model"], bar, p["step_n"], p["step_total"], p["elapsed_s"]))

    # Tabela modelos
    lines.append("")
    lines.append("LLM       GB   STRESS   BATTERY  CREATIVE T_SWEEP  SWEEP  PPL    ANALYZE")
    lines.append("-" * 75)
    for name in ["test-4b", "test-coder", "test-gemma"]:
        r = m["models"].get(name, {})
        if r.get("status") == "pending":
            lines.append("{:<10} {:>4}  pendente".format(name, "-"))
        else:
            lines.append("{:<10} {:>4.1f}  {:<8} {:<9} {:<9} {:<8} {:<7} {:<7} {:<7}".format(
                name, r.get("gb", 0),
                str(r.get("stress", "?"))[:8],
                str(r.get("battery", "?"))[:9],
                str(r.get("creative", "?"))[:9],
                str(r.get("temp_sweep", "?"))[:8],
                str(r.get("sweep", "?"))[:7],
                str(r.get("ppl", "?"))[:7],
                str(r.get("analyze", "?"))[:7]))

    return "\n".join(lines)


def format_obsidian(m):
    """Formato markdown para Obsidian vault."""
    now = datetime.now().strftime("%H:%M")
    t = m["thermal"]
    p = m["pipeline"]

    md = []
    md.append("---")
    md.append("updated: {}".format(m["timestamp"]))
    md.append("---")
    md.append("")
    md.append("# 🔴 LLM Status -- {}".format(now))
    md.append("")
    md.append("## 🌡 Termico")
    md.append("- **Temp:** {:.0f}°C  {}  (tier: `{}`, max_tok: {})".format(
        t["c"], t["spark"], t["tier"], t["max_tok"]))
    md.append("- **RAM:** {}MB livre  |  swap: {:.0f}%".format(t["ram_mb"], t["swap_pct"]))
    md.append("")

    if p["phase"] != "idle":
        pct = p["step_n"] / p["step_total"] * 100 if p["step_total"] else 0
        md.append("## ⚙ Pipeline")
        md.append("- **Fase:** {} | modelo: {}".format(p["phase"], p["model"]))
        md.append("- **Etapa:** {} ({}/{}) -- {}%".format(p["step"], p["step_n"], p["step_total"], int(pct)))
        md.append("- **Elapsed:** {}s ({:.0f}min)".format(p["elapsed_s"], p["elapsed_s"] / 60))
        md.append("")

    md.append("## 📊 Modelos")
    md.append("")
    md.append("| LLM | GB | Stress | Battery | Creative | T_Sweep | Sweep | PPL | Analyze |")
    md.append("|-----|----|--------|---------|----------|---------|-------|-----|---------|")
    for name in ["test-4b", "test-coder", "test-gemma"]:
        r = m["models"].get(name, {})
        if r.get("status") == "pending":
            md.append("| {} | - | pendente | - | - | - | - | - | - |".format(name))
        else:
            md.append("| {} | {:.1f} | {} | {} | {} | {} | {} | {} | {} |".format(
                name, r.get("gb", 0),
                r.get("stress", "?"), r.get("battery", "?"),
                r.get("creative", "?"), r.get("temp_sweep", "?"),
                r.get("sweep", "?"), r.get("ppl", "?"), r.get("analyze", "?")))
    md.append("")

    return "\n".join(md)


def main():
    obsidian = "--obsidian" in sys.argv
    watch = "--watch" in sys.argv

    if obsidian:
        OBSIDIAN_REPORT.parent.mkdir(parents=True, exist_ok=True)

    while True:
        m = collect_metrics()

        # Terminal / bot
        print(format_terminal(m))
        print("")

        # Obsidian
        if obsidian:
            try:
                OBSIDIAN_REPORT.write_text(format_obsidian(m))
            except Exception as e:
                print("[obsidian] erro: {}".format(e), file=sys.stderr)

        if not watch:
            break
        time.sleep(5)


if __name__ == "__main__":
    main()

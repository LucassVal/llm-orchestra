#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
metrics_daemon.py -- Coletor persistente de metricas a cada 5s.
Fontes: thermal_governor (celular) + cada orquestrador (LLM).
Entrega: Obsidian vault (status atual) + CSV historico por modelo.
Sem LLM -- script puro, leve, via no_agent cron ou background.

Arquivos gerados:
  vault/metricas/llm_status.md       -- status atual (sobrescrito)
  vault/metricas/history_4b.csv      -- historico do worker 4B
  vault/metricas/history_coder.csv   -- historico do coder
  vault/metricas/history_gemma.csv   -- historico do gemma
  vault/metricas/history_phone.csv   -- historico do celular
"""
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

VAULT = Path("/storage/emulated/0/Obsidian/Lucas/metricas")
INTERVAL = 5  # segundos

VAULT.mkdir(parents=True, exist_ok=True)


def collect_all():
    """Coleta via meta -- mesma funcao que --report usa."""
    from metrics_reporter import collect_metrics
    m = collect_metrics()

    now = datetime.now()
    ts = now.isoformat()
    ts_short = now.strftime("%H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")

    thermal = m["thermal"]
    pipeline = m["pipeline"]
    models_data = m["models"]

    # ── Celular ──
    phone = {
        "ts": ts, "time": ts_short, "date": date_str,
        "thermal_c": thermal["c"], "tier": thermal["tier"],
        "max_tok": thermal["max_tok"], "ram_avail_mb": thermal["ram_mb"],
        "swap_pct": thermal["swap_pct"],
        "pipeline_phase": pipeline["phase"],
        "pipeline_model": pipeline["model"],
        "pipeline_step": pipeline["step"],
        "pipeline_elapsed_s": pipeline["elapsed_s"],
        "temps_60s": thermal.get("temps_60s", []),
    }

    # ── LLMs ──
    models = {}
    for name, data in models_data.items():
        if data.get("status") == "pending":
            models[name] = {"ts": ts, "time": ts_short, "date": date_str,
                           "model": name, "gb": 0, "status": "pending"}
        else:
            models[name] = {
                "ts": ts, "time": ts_short, "date": date_str,
                "model": data.get("model", name),
                "gb": data.get("gb", 0),
                "stress_status": data.get("stress", "?"),
                "battery_status": data.get("battery", "?"),
                "battery_avg_tok_s": 0,  # preenchido via results.json
                "battery_score": 0,
                "creative_status": data.get("creative", "?"),
                "temp_sweep_status": data.get("temp_sweep", "?"),
                "sweep_status": data.get("sweep", "?"),
                "ppl": data.get("ppl", 0),
                "analyze_status": data.get("analyze", "?"),
                "ram_delta_mb": 0,
            }

    return phone, models


def write_history(csv_path, fields, row):
    """Append uma linha ao CSV historico. Cria com header se novo."""
    new_file = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        w.writerow(row)


def write_status_md(phone, models):
    """Escreve status atual no vault (sobrescreve)."""
    now = datetime.now().strftime("%H:%M:%S")
    p = phone

    # Sparkline termica (ASCII-safe, sem unicode)
    spark = ""
    temps = p.get("temps_60s", [])
    if temps:
        for t in temps[-12:]:
            if t > 90:
                spark += "#"
            elif t > 80:
                spark += "="
            elif t > 70:
                spark += "-"
            elif t > 60:
                spark += "."
            else:
                spark += " "

    md = []
    md.append("---")
    md.append("updated: {}".format(p["ts"]))
    md.append("---")
    md.append("")
    md.append("# 📡 LLM Status -- {}".format(now))
    md.append("")
    md.append("## 📱 Celular")
    md.append("| Métrica | Valor |")
    md.append("|---------|-------|")
    md.append("| Temp | {:.0f}°C {} |".format(p["thermal_c"], spark))
    md.append("| Tier | `{}` (max_tok={}) |".format(p["tier"], p["max_tok"]))
    md.append("| RAM | {}MB livre |".format(p["ram_avail_mb"]))
    md.append("| Swap | {:.0f}% |".format(p["swap_pct"]))
    if p["pipeline_phase"] != "idle":
        md.append("| Pipeline | {} > {} ({}/{}) {}s |".format(
            p["pipeline_phase"], p["pipeline_step"],
            p.get("pipeline_step_n", "?"), p.get("pipeline_step_total", "?"),
            p["pipeline_elapsed_s"]))
    md.append("")

    md.append("## 🤖 LLMs")
    md.append("")
    md.append("| LLM | GB | Stress | Battery | Tok/s | Creative | T_Sweep | PPL | Analyze | ΔRAM |")
    md.append("|-----|----|--------|---------|-------|----------|---------|-----|---------|------|")
    for name in ["test-4b", "test-coder", "test-gemma"]:
        m = models.get(name, {})
        if m.get("status") == "pending":
            md.append("| {} | - | pendente | - | - | - | - | - | - | - |".format(name))
        else:
            md.append("| {} | {:.1f} | {} | {} | {:.1f} | {} | {} | {} | {} | {:+d} |".format(
                name, m.get("gb", 0),
                m.get("stress_status", "?"), m.get("battery_status", "?"),
                m.get("battery_avg_tok_s", 0),
                m.get("creative_status", "?"), m.get("temp_sweep_status", "?"),
                m.get("ppl", 0), m.get("analyze_status", "?"),
                m.get("ram_delta_mb", 0)))
    md.append("")

    (VAULT / "llm_status.md").write_text("\n".join(md))


def main():
    print("[daemon] ▶ metrics_daemon iniciado ({}s)".format(INTERVAL), file=sys.stderr)

    # Headers dos CSVs
    phone_fields = ["ts", "time", "date", "thermal_c", "tier", "max_tok",
                    "ram_avail_mb", "swap_pct", "pipeline_phase",
                    "pipeline_model", "pipeline_step", "pipeline_elapsed_s"]
    model_fields = ["ts", "time", "date", "model", "gb", "stress_status",
                    "battery_status", "battery_avg_tok_s", "battery_score",
                    "creative_status", "temp_sweep_status", "sweep_status",
                    "ppl", "analyze_status", "ram_delta_mb"]

    while True:
        try:
            phone, models = collect_all()

            # Status markdown (sobrescreve)
            write_status_md(phone, models)

            # Historico CSV (append)
            write_history(VAULT / "history_phone.csv", phone_fields, {k: phone.get(k, "") for k in phone_fields})
            for name, m in models.items():
                write_history(VAULT / "history_{}.csv".format(name.replace("test-", "")),
                            model_fields, {k: m.get(k, "") for k in model_fields})

        except Exception as e:
            print("[daemon] erro: {}".format(e), file=sys.stderr)

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

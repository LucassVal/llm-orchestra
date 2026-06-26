#!/usr/bin/env python3
# 3W: WHAT=orquestrador gemma | WHY=executar pipeline completo | WHEN=pipeline-gemma
"""
orquestrador-gemma - Orquestrador dedicado ao gemma4:e4b (8.9GB).
Orquestrador principal (maior). Pipeline: stress>battery>creative>temp_sweep>sweep>ppl>analyze.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.display import pipeline_header, status_ok

MODEL = "gemma4:e4b"
THIS_DIR = Path(__file__).parent
BUILD_DIR = THIS_DIR.parent
ORCH = BUILD_DIR / "bench_orchestrator.py"
LOG_FILE = BUILD_DIR / "logs" / "pipeline_gemma.log"
RESULTS_FILE = BUILD_DIR / "logs" / "pipeline_test-gemma.json"


def main():
    steps = ["stress", "battery", "creative", "temp_sweep", "sweep", "ppl", "analyze"]
    pipeline_header(run_id=datetime.now().strftime("%H%M%S"), model=MODEL, steps=steps)

    ts = datetime.now().isoformat()
    cmd = [sys.executable, "-u", str(ORCH), "--discover", "--pipeline", "--model", MODEL]

    with open(LOG_FILE, "a") as log:
        log.write(f"ORQUESTRADOR-GEMMA  |  {MODEL}  |  {ts}\n")
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=7200)
        log.write(r.stdout)

    src = BUILD_DIR / "benchmark_latest.json"
    if src.exists():
        with open(src) as f:
            data = json.load(f)
        with open(RESULTS_FILE, "a") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        status_ok(f"Resultados salvos: {RESULTS_FILE}")

    status_ok(f"Log: {LOG_FILE}")
    status_ok("ORQUESTRADOR-GEMMA CONCLUIDO.")


if __name__ == "__main__":
    main()

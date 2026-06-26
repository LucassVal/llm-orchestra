#!/usr/bin/env python3
# 3W: WHAT=orquestrador 4B | WHY=executar pipeline completo | WHEN=pipeline-4b
"""
orquestrador-4b — Orquestrador dedicado ao Qwen3-4B (2.4GB).
Worker leve. Pipeline: stress→battery→creative→temp_sweep→sweep→ppl→analyze.
Resultados em ~/build/logs/ (append-only, timestamp, NUNCA sobrescreve).
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MODEL = "Qwen_Qwen3-4B-Q4_K_M"
THIS_DIR = Path(__file__).parent
BUILD_DIR = THIS_DIR.parent
ORCH = BUILD_DIR / "bench_orchestrator.py"
LOG_FILE = BUILD_DIR / "logs" / "pipeline_4b.log"  # append-only


def main():
    print("╔══ ORQUESTRADOR-4B ══╗")
    print("║ Modelo: {}".format(MODEL))
    print("║ Pasta:  {}".format(THIS_DIR))
    print("║ Esteira: stress→battery→creative→temp_sweep→sweep→ppl→analyze")
    print("╚" + "═"*20 + "╝")

    ts = datetime.now().isoformat()
    cmd = [sys.executable, "-u", str(ORCH), "--discover", "--pipeline",
           "--model", MODEL]

    with open(LOG_FILE, "a") as log:
        log.write("ORQUESTRADOR-4B  |  {}  |  {}\n".format(MODEL, ts))
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=7200)
        log.write(r.stdout)

    # Le do symlink benchmark_latest.json (append-only, nunca sobrescreve)
    latest = BUILD_DIR / "benchmark_latest.json"
    if latest.exists():
        with open(latest) as f:
            data = json.load(f)
        # Salva copia com timestamp no test-4b/ também
        ts_file = THIS_DIR / "logs" / "pipeline_{}.json".format(
            datetime.now().strftime("%Y%m%d_%H%M%S"))
        ts_file.parent.mkdir(parents=True, exist_ok=True)
        with open(ts_file, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("✓ Resultados salvos: {}".format(ts_file))
        # Atualiza symlink local
        local_latest = THIS_DIR / "results_latest.json"
        if local_latest.exists():
            local_latest.unlink()
        local_latest.symlink_to(ts_file)

    print("✓ Log: {}".format(LOG_FILE))
    print("ORQUESTRADOR-4B CONCLUIDO.")


if __name__ == "__main__":
    main()

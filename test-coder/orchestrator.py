#!/usr/bin/env python3
"""
orquestrador-coder - Orquestrador dedicado ao qwen2.5-coder (4.7GB).
Worker pesado. Pipeline: stress > battery > creative > temp_sweep > sweep > ppl > analyze.
Resultados em ~/build/test-coder/
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MODEL = "qwen2.5-coder"
THIS_DIR = Path(__file__).parent
BUILD_DIR = THIS_DIR.parent
ORCH = BUILD_DIR / "bench_orchestrator.py"
LOG_FILE = THIS_DIR / "pipeline.log"
RESULTS_FILE = THIS_DIR / "results.json"

def main():
    print("╔══ ORQUESTRADOR-CODER ══╗")
    print(f"║ Modelo: {MODEL}")
    print(f"║ Pasta:  {THIS_DIR}")
    print("║ Esteira: stress→battery→creative→temp_sweep→sweep→ppl→analyze")
    print(f"╚{'═'*23}╝")
    
    ts = datetime.now().isoformat()
    cmd = [sys.executable, "-u", str(ORCH), "--discover", "--pipeline",
           "--model", MODEL]
    
    with open(LOG_FILE, "w") as log:
        log.write(f"ORQUESTRADOR-CODER  |  {MODEL}  |  {ts}\n")
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=7200)
        log.write(r.stdout)
    
    src = BUILD_DIR / "benchmark_pipeline.json"
    if src.exists():
        with open(src) as f:
            data = json.load(f)
        with open(RESULTS_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ Resultados salvos: {RESULTS_FILE}")
    
    print(f"✓ Log: {LOG_FILE}")
    print("ORQUESTRADOR-CODER CONCLUIDO.")

if __name__ == "__main__":
    main()

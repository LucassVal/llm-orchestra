#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
orquestrador-gemma - Orquestrador dedicado ao gemma4:e4b (8.9GB).
Orquestrador principal (maior). Pipeline: stress > battery > creative > temp_sweep > sweep > ppl > analyze.
Usa llama-server do Ollama (recompilado quebra Gemma).
Resultados em ~/build/test-gemma/
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MODEL = "gemma4:e4b"
THIS_DIR = Path(__file__).parent
BUILD_DIR = THIS_DIR.parent
ORCH = BUILD_DIR / "bench_orchestrator.py"
LOG_FILE = THIS_DIR / "pipeline.log"
RESULTS_FILE = THIS_DIR / "results.json"

def main():
    print("╔══ ORQUESTRADOR-GEMMA ══╗")
    print(f"║ Modelo: {MODEL}")
    print(f"║ Pasta:  {THIS_DIR}")
    print("║ Esteira: stress>battery>creative>temp_sweep>sweep>ppl>analyze")
    print(f"╚{'═'*24}╝")
    
    ts = datetime.now().isoformat()
    cmd = [sys.executable, "-u", str(ORCH), "--discover", "--pipeline",
           "--model", MODEL]
    
    with open(LOG_FILE, "w") as log:
        log.write(f"ORQUESTRADOR-GEMMA  |  {MODEL}  |  {ts}\n")
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
    print("ORQUESTRADOR-GEMMA CONCLUIDO.")

if __name__ == "__main__":
    main()

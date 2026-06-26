#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
bench_sweep.py -- Otimizador de parâmetros para LLMs locais.
Lê sweep_config.json, testa combinações, encontra ótimo.
Uso: python3 bench_sweep.py test-4b/sweep_config.json
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LLAMA_CLI = "/data/data/com.termux/files/usr/lib/ollama/llama-server"
LD_PATH   = "/data/data/com.termux/files/usr/lib/ollama"
BUILD     = os.path.expanduser("~/build")


def tee(msg: str):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# TODO(a8): reduzir 9 params → dataclass/config dict
def run_test(gguf: str, prompt: str, max_tokens: int, threads: int,
             batch_size: int, ctx_size: int, flash_attn: bool,
             ngl: int, mlock: bool, timeout: int = 120) -> dict:
    """Executa 1 teste com parâmetros específicos. Retorna métricas."""
    cmd = [LLAMA_CLI, "-m", gguf, "-p", prompt,
           "--threads", str(threads),
           "--batch-size", str(batch_size),
           "--ctx-size", str(ctx_size),
           "--n-gpu-layers", str(ngl),
           "-n", str(max_tokens),
           "--single-turn", "--no-perf", "--no-display-prompt",
           "--temp", "0.1"]
    
    if flash_attn:
        cmd += ["--flash-attn", "on"]
    if mlock:
        cmd += ["--mlock"]
    
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LD_PATH
    
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, env=env)
        elapsed = time.time() - t0
        output = r.stdout + r.stderr
        
        # Extrai tok/s
        import re
        tok_s = 0.0
        m = re.search(r'llama_perf_sampler_print:.*?(\d+\.?\d*)\s+tokens per second', output)
        if m:
            tok_s = float(m.group(1))
        
        return {"ok": True, "elapsed": round(elapsed, 1), "tok_s": round(tok_s, 1),
                "exit": r.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "elapsed": timeout, "tok_s": 0, "error": "TIMEOUT"}
    except Exception as e:
        return {"ok": False, "elapsed": time.time()-t0, "tok_s": 0, "error": str(e)[:100]}


def run_sweep(config_path: str):
    """Executa sweep completo a partir do arquivo de configuração."""
    with open(config_path) as f:
        cfg = json.load(f)
    
    model_name = cfg["model"]
    gguf = os.path.join(BUILD, f"{model_name}.gguf")
    if not os.path.exists(gguf):
        tee(f"ERRO: GGUF não encontrado: {gguf}")
        return
    
    prompts = cfg["test_prompts"]
    sweeps = cfg["sweeps"]
    warmup = cfg.get("warmup_runs", 1)
    measures = cfg.get("measure_runs", 2)
    
    tee(f"╔══ SWEEP: {model_name} ══╗")
    tee(f"║ Parâmetros: {[s['name'] for s in sweeps]}")
    tee(f"║ Prompts: {[p['id'] for p in prompts]}")
    tee(f"║ Warmup: {warmup} | Medições: {measures}")
    tee(f"╚{'═'*30}╝")
    
    results = []
    total_combos = 1
    for s in sweeps:
        total_combos *= len(s["values"])
    
    # Baseline primeiro
    baseline = cfg.get("baseline", {})
    tee(f"\n▶ BASELINE: threads={baseline.get('threads',6)} "
        f"batch={baseline.get('batch_size',256)} "
        f"flash_attn={baseline.get('flash_attn',False)} "
        f"ngl={baseline.get('ngl',0)}")
    
    # Testa cada parâmetro isoladamente (one-at-a-time)
    for sweep in sweeps:
        name = sweep["name"]
        values = sweep["values"]
        is_bool = sweep["type"] == "bool"
        
        tee(f"\n── {name} ({len(values)} valores) ──")
        
        for val in values:
            # Usa baseline para outros parâmetros
            th = baseline.get("threads", 6) if name != "threads" else val
            bs = baseline.get("batch_size", 256) if name != "batch_size" else (val if not is_bool else 256)
            fa = baseline.get("flash_attn", False) if name != "flash_attn" else (val if is_bool else False)
            ng = baseline.get("ngl", 0) if name != "ngl" else (val if not is_bool else 0)
            ml = baseline.get("mlock", False) if name != "mlock" else (val if is_bool else False)
            
            label = f"{name}={val}"
            tee(f"  ▶ {label}")
            
            # Warmup (descartado)
            for _ in range(warmup):
                run_test(gguf, prompts[0]["text"], 5, th, bs, 512, fa, ng, ml, timeout=60)
            
            # Medições
            all_toks = []
            for prompt in prompts:
                for _ in range(measures):
                    r = run_test(gguf, prompt["text"], prompt["max_tokens"],
                                th, bs, 512, fa, ng, ml, timeout=120)
                    if r["ok"]:
                        all_toks.append(r["tok_s"])
            
            if all_toks:
                avg_tok = sum(all_toks) / len(all_toks)
                tee(f"  ◀ {label}: {avg_tok:.1f} tok/s (n={len(all_toks)})")
                results.append({
                    "threads": th, "batch_size": bs, "flash_attn": fa,
                    "ngl": ng, "mlock": ml,
                    "param": name, "value": val,
                    "avg_tok_s": round(avg_tok, 1),
                    "samples": len(all_toks),
                })
            else:
                tee(f"  ✗ {label}: todas falhas")
    
    # ═══ RESULTADO ═══
    print(f"\n{'='*80}")
    print("  RESULTADO DO SWEEP")
    print(f"{'='*80}")
    print(f"  {'PARAM':<14} {'VALOR':<8} {'TOK/S':>7} {'N':>4}")
    print(f"  {'-'*40}")
    
    best = {}
    for r in sorted(results, key=lambda x: x["avg_tok_s"], reverse=True):
        p = r["param"]
        if p not in best or r["avg_tok_s"] > best[p]["avg_tok_s"]:
            best[p] = r
        marker = " ←" if p not in [x["param"] for x in list(best.values()) if x != best.get(p)] else ""
        print(f"  {r['param']:<14} {str(r['value']):<8} {r['avg_tok_s']:>6.1f} {r['samples']:>4}{marker}")
    
    print(f"  {'-'*40}")
    print(f"  Melhor combo: threads={best.get('threads',{}).get('value','?')} "
          f"batch={best.get('batch_size',{}).get('value','?')} "
          f"flash_attn={best.get('flash_attn',{}).get('value','?')} "
          f"ngl={best.get('ngl',{}).get('value','?')} "
          f"mlock={best.get('mlock',{}).get('value','?')}")
    print(f"{'='*80}")
    
    # Salva JSON
    out_path = Path(config_path).parent / "sweep_results.json"
    output = {
        "model": model_name,
        "timestamp": datetime.now().isoformat(),
        "baseline_tok_s": baseline.get("tok_s", 0),
        "best": {k: {"value": v["value"], "tok_s": v["avg_tok_s"]}
                 for k, v in best.items()},
        "results": results,
    }
    with open(out_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    tee(f"\nResultados salvos: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 bench_sweep.py <sweep_config.json>")
        print("Ex:   python3 bench_sweep.py test-4b/sweep_config.json")
        sys.exit(1)
    
    run_sweep(sys.argv[1])

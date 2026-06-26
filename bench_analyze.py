#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
bench_analyze.py v2 -- RCA + Pareto (child do orquestrador).
Executa benchmark com métricas de sistema e gera diagnóstico 3W.
Usa llama-server recompilado. Output JSON via stdout.
"""
import argparse
import json
import os
import sys
import urllib.request

from bench_sys import SysMonitor

SERVER_URL = "http://127.0.0.1:8080"

PROMPTS = [
    ("conhecimento", "Qual a capital do Brasil? 1 frase portugues."),
    ("logica", "Se 5 maquinas fazem 5 pecas em 5min, quantas pecas 10 maquinas em 10min? So o numero."),
    ("codigo", "Funcao Python que soma pares de uma lista. So codigo."),
]
RUNS = 3


def run_inference(prompt, max_tok=25, server_url=SERVER_URL):
    body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tok, "temperature": 0.1}).encode()
    req = urllib.request.Request(f"{server_url}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def analyze(results):
    """RCA + Pareto."""
    analysis = {}
    
    ok_results = [r for r in results if r["status"] == "OK"]
    if ok_results:
        temps = [r["sys_after"]["delta"]["max_temp_c"] for r in ok_results]
        toks = [r["gen_tok_s"] for r in ok_results]
        swaps = [r["sys_after"]["delta"]["swap_delta_mb"] for r in ok_results]
        
        analysis["rca"] = {
            "temp_avg_c": round(sum(temps)/len(temps), 0),
            "tok_s_avg": round(sum(toks)/len(toks), 1),
            "temp_max_c": max(temps),
            "tok_s_min": min(toks),
            "swap_avg_mb": round(sum(swaps)/len(swaps), 0),
            "swap_max_mb": max(swaps),
        }
        
        # Correlação temp vs tok/s
        if len(temps) >= 2:
            analysis["rca"]["temp_tok_correlation"] = (
                "negativa" if max(temps) != min(temps) and 
                toks[temps.index(max(temps))] < toks[temps.index(min(temps))]
                else "neutra")
    
    analysis["pareto"] = [
        {"rank": 1, "factor": "tok/s generation", "impact": "40%", "note": "métrica principal"},
        {"rank": 2, "factor": "RAM/swap pressure", "impact": "25%", "note": "memória"},
        {"rank": 3, "factor": "Thermal throttle", "impact": "20%", "note": "temperatura"},
        {"rank": 4, "factor": "Model architecture", "impact": "10%", "note": "tamanho/quantização"},
        {"rank": 5, "factor": "TTFT latency", "impact": "5%", "note": "prompt processing"},
    ]
    
    return analysis


def main():
    ap = argparse.ArgumentParser(description="RCA/Pareto child v2")
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--model-size-gb", type=float, default=0)
    ap.add_argument("--server-url", default=SERVER_URL,
                    help="URL do llama-server já rodando")
    args = ap.parse_args()

    if not os.path.exists(args.gguf):
        print(json.dumps({"model": args.model_name, "status": "SKIP", "error": "GGUF ausente"}))
        return

    # Verifica servidor
    try:
        urllib.request.urlopen(f"{args.server_url}/health", timeout=5)
    except Exception as e:
        print(json.dumps({"model": args.model_name, "status": "SERVER_OFFLINE",
                          "error": str(e)[:80]}))
        sys.exit(1)

    monitor = SysMonitor()
    results = []

    for i in range(RUNS):
        for cat, prompt in PROMPTS:
            sys_before = monitor.snapshot()
            try:
                resp = run_inference(prompt, server_url=args.server_url)
                status = "OK"
            except Exception as e:
                resp = {}
                status = f"FAIL: {e}"
            sys_after = monitor.snapshot()
            delta = monitor.delta(sys_before, sys_after)

            timings = resp.get("timings", {})
            result = {
                "run": i+1, "category": cat, "status": status,
                "gen_tok_s": round(timings.get("predicted_per_second", 0), 1),
                "prompt_tok_s": round(timings.get("prompt_per_second", 0), 1),
                "ttft_ms": round(timings.get("prompt_ms", 0), 1),
                "tokens": resp.get("usage", {}).get("completion_tokens", 0),
                "sys_after": {
                    "ram": sys_after["ram"],
                    "swap": sys_after["swap"],
                    "thermal": sys_after["thermal"],
                    "delta": delta,
                },
            }
            results.append(result)

    analysis = analyze(results)
    output = {
        "model": args.model_name,
        "gb": args.model_size_gb,
        "status": "OK",
        "runs": RUNS,
        "analysis": analysis,
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

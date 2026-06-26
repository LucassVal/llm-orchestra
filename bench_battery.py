#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
bench_battery.py v2 -- Bateria de testes práticos (child do orquestrador).
Cobre: código, lógica, tradução, instrução.
Usa llama-server recompilado. Output JSON via stdout.
"""
import argparse
import json
import os
import urllib.request

from bench_sys import SysMonitor

SERVER_URL = "http://127.0.0.1:8080"

BATTERY = [
    ("C1", "codigo", "Write a Python function that sums all even numbers in a list. Code only.", 120, 0.2, "def"),
    ("C2", "codigo", "Write a Python function that checks if a string is a palindrome. Code only.", 120, 0.2, "def"),
    ("C3", "codigo", "Write a Python function for binary search in a sorted list. Code only.", 120, 0.2, "def"),
    ("L1", "logica", "If 5 machines make 5 parts in 5 minutes, how many parts do 10 machines make in 10 minutes? Just the number.", 30, 0.1, "20"),
    ("L2", "logica", "Complete the sequence: 2, 6, 12, 20, ? Just the number.", 30, 0.1, "30"),
    ("T1", "traducao", "Translate to Portuguese: 'The cat sleeps on the warm roof.'", 40, 0.3, "gato"),
    ("I1", "instrucao", "List 3 Brazilian fruits. Names only, comma separated.", 40, 0.3, ","),
]
RUNS = 2


def infer(prompt, temp, max_tok, server_url=SERVER_URL):
    body = json.dumps({"messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tok, "temperature": temp}).encode()
    req = urllib.request.Request(f"{server_url}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    msg = resp["choices"][0]["message"]
    text = msg.get("content", "") or msg.get("reasoning_content", "")
    return {"text": text, "timings": resp.get("timings", {}), "usage": resp.get("usage", {})}


def main():
    ap = argparse.ArgumentParser(description="Battery test child v2")
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

    for run_id in range(1, RUNS + 1):
        for tid, cat, prompt, max_tok, temp, keyword in BATTERY:
            sys_before = monitor.snapshot()
            try:
                resp = infer(prompt, temp, max_tok, server_url=args.server_url)
                content = resp["text"]
                timings = resp["timings"]
                status = "OK"
            except Exception:
                content = ""
                timings = {}
                status = "ERR"
            tok_s = timings.get("predicted_per_second", 0)
            ttft = timings.get("prompt_ms", 0)
            has_kw = keyword.lower() in content.lower() if content else False
            sys_after = monitor.snapshot()
            delta = monitor.delta(sys_before, sys_after)

            results.append({
                "run": run_id, "id": tid, "category": cat,
                "tok_s": round(tok_s, 1), "ttft_ms": round(ttft, 0),
                "keyword_ok": has_kw, "status": status,
                "sample": content[:100],
                "temp_c": delta["max_temp_c"],
                "ram_mb": sys_after["ram"]["used_mb"],
                "cpu_mhz": delta["cpu_avg_mhz"],
            })

    total = len(results)
    ok = sum(1 for r in results if r["status"] == "OK")
    kw_ok = sum(1 for r in results if r["keyword_ok"])
    avg_tok = sum(r["tok_s"] for r in results if r["tok_s"] > 0) / max(ok, 1)
    avg_ttft = sum(r["ttft_ms"] for r in results) / max(total, 1)

    output = {
        "model": args.model_name,
        "gb": args.model_size_gb,
        "status": "OK",
        "summary": {
            "total": total, "ok": ok, "keyword_ok": kw_ok,
            "avg_tok_s": round(avg_tok, 1),
            "avg_ttft_ms": round(avg_ttft, 0),
            "score": round(kw_ok * avg_tok / max(total, 1), 0),
        },
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

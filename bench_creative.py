#!/usr/bin/env python3
"""
bench_creative.py v3 — Criatividade × temperatura (child do orquestrador).
Mede: diversidade lexical, variância entre runs, factualidade, repetição.
Usa llama-server recompilado. Output JSON via stdout.
Log de progresso via stderr (não contamina JSON).
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from collections import Counter

SERVER_URL = "http://127.0.0.1:8080"

CREATIVE_PROMPTS = [
    ("haiku", "Crie um haiku sobre programacao. 3 linhas. Portugues."),
    ("historia", "Conte uma mini-historia de 2 frases sobre um robo que aprendeu a sonhar. Portugues."),
    ("poesia", "Escreva um poeminha de 2 linhas sobre o ceu noturno. Portugues."),
]
FACTUAL_PROMPT = ("factual", "Qual a capital do Brasil? 1 frase.")
TEMPS = [0.1, 0.5, 0.7, 1.0]
RUNS_PER_TEMP = 2


def _bar(current, total, width=30):
    """Barra de progresso ASCII."""
    pct = current / total if total else 0
    filled = int(width * pct)
    return f"[{'#' * filled}{'.' * (width - filled)}] {current}/{total}"


def lexical_diversity(text):
    words = text.lower().split()
    if len(words) < 3:
        return 0
    return len(set(words)) / len(words)


def repetition_score(text):
    words = text.lower().split()
    if len(words) < 8:
        return 0
    bigrams = [tuple(words[i:i+2]) for i in range(len(words)-1)]
    counts = Counter(bigrams)
    repeated = sum(max(0, c-1) for c in counts.values())
    return round(repeated / max(len(bigrams), 1), 2)


def infer(prompt, temp, max_tok=80, server_url=SERVER_URL):
    body = json.dumps({"prompt": prompt, "max_tokens": max_tok,
                       "temperature": temp}).encode()
    req = urllib.request.Request(f"{server_url}/v1/completions",
                                 data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return resp["choices"][0]["text"]


def main():
    ap = argparse.ArgumentParser(description="Creative test child v3")
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
    except Exception:
        print(json.dumps({"model": args.model_name, "status": "SERVER_OFFLINE"}))
        return

    total_tests = len(TEMPS) * (len(CREATIVE_PROMPTS) + 1) * RUNS_PER_TEMP
    test_idx = 0
    results = []
    t_start = time.time()

    print(f"[creative] ▶ {args.model_name}  |  {total_tests} iterações  |  temps={TEMPS}", file=sys.stderr)

    for temp in TEMPS:
        t_temp = time.time()
        for cat, prompt in CREATIVE_PROMPTS + [FACTUAL_PROMPT]:
            responses = []
            times = []
            for run_i in range(RUNS_PER_TEMP):
                test_idx += 1
                t0 = time.time()
                status = "OK"
                try:
                    text = infer(prompt, temp, server_url=args.server_url)
                    elapsed = time.time() - t0
                    responses.append(text)
                    times.append(elapsed)
                except Exception as e:
                    status = f"ERR: {e}"
                    responses.append("")
                    times.append(0)

                print(f"[creative] {_bar(test_idx, total_tests)}  temp={temp} {cat} r{run_i+1}  "
                      f"{status}  ({time.time() - t0:.1f}s)", file=sys.stderr, flush=True)

            avg_text = responses[0] if responses and responses[0] else ""
            avg_time = sum(times) / max(len(times), 1)
            tokens_est = len(avg_text.split())
            tok_s = tokens_est / avg_time if avg_time > 0 else 0
            lex_div = lexical_diversity(avg_text)
            rep = repetition_score(avg_text)
            sample = avg_text[:60].replace("\n", " / ")

            if len(responses) >= 2 and responses[0] and responses[1]:
                var = 0 if responses[0] == responses[1] else 1
            else:
                var = -1

            results.append({
                "temp": temp, "category": cat, "tok_s": round(tok_s, 1),
                "lexical_diversity": round(lex_div, 2),
                "repetition": rep, "variance": var,
                "length": len(avg_text), "sample": sample,
            })

        print(f"[creative]   temp={temp} concluído em {time.time() - t_temp:.1f}s", file=sys.stderr, flush=True)

    # Sumário por temperatura
    summary = {}
    for temp in TEMPS:
        subset = [r for r in results if r["temp"] == temp]
        avg_lex = sum(r["lexical_diversity"] for r in subset) / len(subset)
        avg_rep = sum(r["repetition"] for r in subset) / len(subset)
        var_runs = sum(1 for r in subset if r["variance"] == 1)
        factual = [r for r in subset if r["category"] == "factual"]
        factual_ok = sum(1 for r in factual if "brasília" in r["sample"].lower())
        summary[str(temp)] = {
            "lexical_diversity": round(avg_lex, 2),
            "repetition": round(avg_rep, 2),
            "variance_runs": f"{var_runs}/{len(subset)}",
            "factual_ok": f"{factual_ok}/{len(factual)}",
        }

    output = {
        "model": args.model_name,
        "gb": args.model_size_gb,
        "status": "OK",
        "summary": summary,
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[creative] ◀ concluído em {time.time() - t_start:.1f}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()

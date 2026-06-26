#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
bench_orchestrator.py v4 -- Orquestrador unificado DDD.
Coordena múltiplos modelos, pre-flight + benchmark completo.

Fases:
  1. PRE-FLIGHT: hello world em 2 métodos (llamacpp, llamaserver)
  2. BENCHMARK: 10 perguntas × 2 métodos × reasoning ON/OFF
  3. RELATÓRIO: tabela PASS/FAIL + markdown + JSON

Camadas: Domain → Application → Infrastructure → Presentation
Regras: R-TRACE, R-NO-SILENT-FAIL, R-IDEMPOTENT, R-KISS, R-PYTHON-FIRST.
"""
import json
import os
import signal as _signal
import subprocess
import sys
import time
import urllib.request
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from shared.dispatch_log import complete as dispatch_complete
from shared.dispatch_log import create as dispatch_create

# ═══════════════════════════════════════════════════════════════════
# DOMAIN
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ModelEntry:
    """Um modelo registrado para benchmark."""
    name: str           # nome curto (ex: gemma4-8b)
    ollama_tag: str     # tag no Ollama (ex: gemma4:e4b)
    blob_hash: str      # sha256 do blob GGUF
    size_gb: float      # tamanho em GB
    risky: bool = False # True se precisa swap

@dataclass
class PreFlightResult:
    model_name: str
    llamacpp_status: str = ""
    llamacpp_detail: str = ""
    llamaserver_status: str = ""
    llamaserver_detail: str = ""

@dataclass
class ModelResult:
    model_name: str
    preflight: PreFlightResult
    bench_results: list = field(default_factory=list)

# ═══════════════════════════════════════════════════════════════════
# MODELOS REGISTRADOS
# ═══════════════════════════════════════════════════════════════════

MODELS = [
    # ═══ 3-MODEL TIER (25 Jun) ═══
    ModelEntry("gemma4-8b",       "gemma4:e4b",
               "4c27e0f5b5adf02ac956c7322bd2ee7636fe3f45a8512c9aba5385242cb6e09a", 9.6, risky=True),  # orquestrador
    ModelEntry("qwen2.5-coder",   "qwen2.5-coder:latest",
               "60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463", 4.7),              # worker pesado
    ModelEntry("Qwen3-4B",        "",  # GGUF solto (sem Ollama)
               "", 2.4),                                                                                 # worker leve
]

# Qwen3-4B é GGUF solto -- sem Ollama
MODELS[-1]._gguf_path = os.path.expanduser("~/build/Qwen_Qwen3-4B-Q4_K_M.gguf")

# ═══════════════════════════════════════════════════════════════════
# INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════

BUILD        = os.path.expanduser("~/build")
CHILD        = os.path.join(BUILD, "bench_child.py")
BLOBS_DIR    = os.path.expanduser("~/.ollama/models/blobs")
LOG_FILE     = os.path.join(BUILD, "logs", "bench_run.log")
STATUS_FILE  = os.path.join(BUILD, "bench_status.json")
RESULTS_FILE = os.path.join(BUILD, "benchmark_final.json")
THERMAL_FILE = os.path.join(BUILD, "shared", "thermal_status.json")


def get_thermal_limit(default_max_tokens=512):
    """Le o governador termico e retorna max_tokens ajustado.
    Power-throttle: reduz tokens com temperatura, nunca bloqueia."""
    try:
        import json
        with open(THERMAL_FILE) as f:
            d = json.load(f)
        tier = d.get("tier", "full")
        limits = {"full": 512, "eco": 256, "low": 128, "minimal": 64, "idle": 16}
        return limits.get(tier, default_max_tokens)
    except Exception:
        return default_max_tokens

_status_state = {"run_id": "", "phase": "idle", "model": "", "step": "",
                 "step_n": 0, "step_total": 0, "elapsed_s": 0, "updated": ""}

def write_status(**kw):
    """Atualiza arquivo de status JSON (polling externo / meta orquestrador)."""
    import json as _json
    _status_state.update(kw)
    _status_state["updated"] = datetime.now().isoformat()
    with open(STATUS_FILE, "w") as f:
        _json.dump(_status_state, f, ensure_ascii=False)

def tee(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = "  [{}] {}".format(ts, msg)
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def trace() -> str:
    return str(uuid.uuid4())

# ═══════════════════════════════════════════════════════════════════
# AUTO-DESCOBERTA DE MODELOS (Ollama registry + GGUF files)
# ═══════════════════════════════════════════════════════════════════

def discover_models():
    """Varre Ollama registry + ~/build/*.gguf. Retorna lista de ModelEntry."""
    discovered = {}
    
    # 1. Ollama registry (via manifests)
    manifests_dir = os.path.expanduser("~/.ollama/models/manifests/registry.ollama.ai/library")
    if os.path.isdir(manifests_dir):
        for model_dir in os.listdir(manifests_dir):
            mpath = os.path.join(manifests_dir, model_dir)
            if not os.path.isdir(mpath):
                continue
            for tag in os.listdir(mpath):
                try:
                    with open(os.path.join(mpath, tag)) as f:
                        manifest = json.load(f)
                    for layer in manifest.get("layers", []):
                        if "model" in layer.get("mediaType", ""):
                            digest = layer["digest"].replace("sha256:", "")
                            blob = os.path.join(BLOBS_DIR, f"sha256-{digest}")
                            if os.path.exists(blob):
                                gb = round(os.path.getsize(blob) / (1024**3), 1)
                                name = f"{model_dir}:{tag}" if tag != "latest" else model_dir
                                discovered[name] = ModelEntry(
                                    name=name, ollama_tag=name,
                                    blob_hash=digest, size_gb=gb,
                                    risky=(gb > 7.0))
                            break
                except Exception:
                    pass
    
    # 2. GGUF files soltos em ~/build/
    build_dir = os.path.expanduser("~/build")
    if os.path.isdir(build_dir):
        for f in os.listdir(build_dir):
            if f.endswith(".gguf"):
                fpath = os.path.join(build_dir, f)
                gb = round(os.path.getsize(fpath) / (1024**3), 1)
                name = f.replace(".gguf", "")
                if name not in discovered:
                    discovered[name] = ModelEntry(
                        name=name, ollama_tag="",
                        blob_hash="", size_gb=gb,
                        risky=(gb > 7.0))
                    # Override blob_path to use GGUF directly
                    discovered[name]._gguf_path = fpath
    
    return list(discovered.values())


def blob_path(blob_hash: str) -> str:
    return os.path.join(BLOBS_DIR, f"sha256-{blob_hash}")


def get_gguf_path(m: ModelEntry) -> str:
    """Retorna caminho GGUF -- blob Ollama ou arquivo solto."""
    if hasattr(m, '_gguf_path') and m._gguf_path:
        return m._gguf_path
    return blob_path(m.blob_hash)


def kill_stray():
    """Mata processos zumbis/órfãos: llama-server, llama-cli, ollama_llama_server."""
    for name in ["llama-server", "llama-cli", "ollama_llama_server"]:
        with suppress(Exception):
            r = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True, timeout=3)
            for pid in r.stdout.strip().split("\n"):
                if pid.strip():
                    with suppress(Exception):
                        os.kill(int(pid.strip()), _signal.SIGKILL)
    time.sleep(0.5)
    subprocess.run(["fuser", "-k", "8080/tcp"], capture_output=True)
    time.sleep(0.5)


def cleanup_after_model(model_name: str = ""):
    """Limpeza completa entre modelos: SIGKILL → ollama stop → drop_caches.
    
    Ciclo: start → test → KILL → cleanup → verify → next.
    Garante que a RAM do modelo anterior foi liberada antes do próximo.
    """
    
    # ═══ FASE 1: SIGKILL em todos os llama-* (não espera graceful shutdown) ═══
    for pattern in ["llama-server", "llama-cli", "ollama_llama_server"]:
        with suppress(Exception):
            r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=3)
            for pid in r.stdout.strip().split("\n"):
                if pid.strip():
                    with suppress(Exception):
                        os.kill(int(pid.strip()), _signal.SIGKILL)
    
    # ═══ FASE 2: ollama stop (libera modelos Ollama da RAM) ═══
    try:
        r = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
        for line in lines[1:]:  # pula header "NAME    ID    SIZE    PROCESSOR    UNTIL"
            parts = line.split()
            if parts:
                ollama_model = parts[0]
                tee(f"  [CLEANUP] ollama stop {ollama_model}")
                subprocess.run(["ollama", "stop", ollama_model],
                               capture_output=True, timeout=10)
    except Exception:
        pass
    
    # ═══ FASE 3: Libera porta 8080 ═══
    subprocess.run(["fuser", "-k", "8080/tcp"], capture_output=True, timeout=3)
    time.sleep(1)
    
    # ═══ FASE 4: Drop page cache (libera RAM do FS) ═══
    try:
        subprocess.run(["sync"], capture_output=True, timeout=5)
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3\n")
    except Exception:
        pass
    
    # ═══ FASE 5: Aguarda RAM estabilizar e verifica ═══
    time.sleep(2)
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    avail_mb = int(line.split()[1]) // 1024
                    tee(f"  [CLEANUP] RAM após limpeza: {avail_mb}MB disponíveis")
                    break
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════
# SERVER MANAGER -- Orquestrador é DONO do ciclo de vida do servidor
# ═══════════════════════════════════════════════════════════════════

DEFAULT_SERVER_BIN = os.path.expanduser("~/llama.cpp/build/bin/llama-server")
DEFAULT_LD_PATH    = os.path.expanduser("~/llama.cpp/build/bin")
OLLAMA_SERVER_BIN  = "/data/data/com.termux/files/usr/lib/ollama/llama-server"
OLLAMA_LD_PATH     = "/data/data/com.termux/files/usr/lib/ollama"

class ServerManager:
    """Gerencia ciclo de vida do llama-server. SÓ o orquestrador toca nisso."""
    
    def __init__(self, server_bin: str = DEFAULT_SERVER_BIN,
                 ld_path: str = DEFAULT_LD_PATH, port: int = 8080):
        self.server_bin = server_bin
        self.ld_path = ld_path
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self._proc = None
    
    def start(self, gguf_path: str, ctx_size: int = 512, threads: int = 6,
              ngl: int = 0, batch_size: int = 256, timeout: int = 30) -> str:
        """Inicia llama-server, espera /health, retorna URL."""
        subprocess.run(["fuser", "-k", f"{self.port}/tcp"],
                       capture_output=True, timeout=3)
        time.sleep(0.5)
        
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = self.ld_path
        
        tee(f"  [SERVER] Iniciando {self.server_bin} na porta {self.port}...")
        self._proc = subprocess.Popen(
            [self.server_bin, "--model", gguf_path,
             "--host", "127.0.0.1", "--port", str(self.port),
             "--ctx-size", str(ctx_size), "--threads", str(threads),
             "--n-gpu-layers", str(ngl), "--batch-size", str(batch_size)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        
        for i in range(timeout):
            time.sleep(1)
            try:
                urllib.request.urlopen(f"{self.url}/health", timeout=2)
                tee(f"  [SERVER] ONLINE em {i+1}s -- {self.url}")
                return self.url
            except Exception:
                pass
        
        self._proc.terminate()
        raise RuntimeError(f"Servidor nao respondeu /health em {timeout}s")
    
    def stop(self):
        """Para o servidor e libera a porta."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        subprocess.run(["fuser", "-k", f"{self.port}/tcp"],
                       capture_output=True, timeout=3)
        time.sleep(0.5)

# ═══════════════════════════════════════════════════════════════════
# RAM GUARD -- integrado ao orquestrador
# ═══════════════════════════════════════════════════════════════════

def free_ram_mb() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return 9999
    return 9999

def ram_total_mb() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return 10000
    return 10000

def check_ram_gate(ram_avail_mb: int, swap_used_pct: float, model_name: str) -> bool:
    """RAM gate mmap-aware. Retorna False se deve pular o modelo."""
    if ram_avail_mb < 500 and swap_used_pct > 90:
        tee(f"  ⛔ RAM GATE: {ram_avail_mb}MB RAM + swap {swap_used_pct}% usado. "
            f"Sem recurso para mmap. Pulando {model_name}.")
        return False
    return True

# ═══════════════════════════════════════════════════════════════════
# PROCESS REGISTRY + DECAY -- Harness com shutdown preventivo
# ═══════════════════════════════════════════════════════════════════

class ProcessRegistry:
    """Registra processos filho para shutdown ordeiro (decay)."""
    
    def __init__(self):
        self._procs: dict = {}
    
    def register(self, proc: subprocess.Popen, ptype: str, name: str = ""):
        self._procs[proc.pid] = {"type": ptype, "proc": proc, "name": name}
    
    def unregister(self, pid: int):
        self._procs.pop(pid, None)
    
    def list_by_type(self, ptype: str) -> list:
        return [e for e in self._procs.values() if e["type"] == ptype]
    
    def all(self) -> list:
        return list(self._procs.values())


def decay_shutdown(registry: ProcessRegistry, reason: str = ""):
    """Desligamento graceful: children → server → ollama → fuser → drop_caches."""
    tag = f" [{reason}]" if reason else ""
    tee(f"🔄 DECAY SHUTDOWN iniciado{tag}")
    
    # Fase 1: SIGTERM children (5s), depois SIGKILL
    for entry in reversed(registry.list_by_type("child")):
        proc = entry["proc"]
        if proc.poll() is None:
            with suppress(Exception):
                proc.terminate()
    
    deadline = time.time() + 5
    for entry in registry.list_by_type("child"):
        proc = entry["proc"]
        if proc.poll() is None:
            with suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=max(0, deadline - time.time()))
    
    for entry in registry.list_by_type("child"):
        proc = entry["proc"]
        if proc.poll() is None:
            with suppress(Exception):
                proc.kill()
        registry.unregister(proc.pid)
    
    # Fase 2: servers
    for entry in registry.list_by_type("server"):
        proc = entry["proc"]
        if proc.poll() is None:
            with suppress(Exception):
                proc.terminate()
    
    time.sleep(2)
    for entry in registry.list_by_type("server"):
        proc = entry["proc"]
        if proc.poll() is None:
            with suppress(Exception):
                proc.kill()
        registry.unregister(proc.pid)
    
    # Fase 3: ollama stop
    try:
        r = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if parts:
                subprocess.run(["ollama", "stop", parts[0]], capture_output=True, timeout=10)
    except Exception:
        pass
    
    # Fase 4: fuser + drop_caches
    subprocess.run(["fuser", "-k", "8080/tcp"], capture_output=True, timeout=3)
    time.sleep(1)
    try:
        subprocess.run(["sync"], capture_output=True, timeout=5)
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3\n")
    except Exception:
        pass
    
    time.sleep(1)
    tee(f"  [DECAY] Completo. RAM: {free_ram_mb()}MB")


def check_memory_pressure(threshold_mb: int = 800) -> bool:
    """Detecta pressão de memória. Retorna True se RAM disponível < threshold."""
    avail = free_ram_mb()
    if avail < threshold_mb:
        tee(f"  ⚠ MEMORY PRESSURE: {avail}MB < {threshold_mb}MB")
        return True
    return False


def run_pipeline_child(child_script: str, args: list, label: str,
                        registry: ProcessRegistry = None,
                        timeout: int = 300, env: dict = None) -> dict:
    """Executa child com proteção OOM + power-throttle termico."""
    if check_memory_pressure(800):
        tee(f"  ⛔ OOM preventivo antes de {label}")
        if registry:
            decay_shutdown(registry, f"OOM antes de {label}")
        return {"status": "OOM_PROTECT", "label": label}
    
    tee(f"  [PIPELINE] {label}...")
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        if r.stderr:
            for line in r.stderr.strip().split("\n"):
                if line.strip():
                    tee(f"    {line.strip()}")
        data = json.loads(r.stdout)
        # PplResult não tem campo 'status', usa 'ppl' como indicador
        status = data.get('status') or ('OK' if 'ppl' in data else '?')
        tee(f"  ✓ {label}: {status}")
        return data
    except subprocess.TimeoutExpired:
        tee(f"  ✗ {label}: TIMEOUT")
        return {"status": "TIMEOUT", "label": label}
    except json.JSONDecodeError:
        tee(f"  ✗ {label}: JSON inválido")
        return {"status": "JSON_ERR", "label": label}
    except Exception as e:
        tee(f"  ✗ {label}: {e}")
        return {"status": "CRASH", "label": label, "error": str(e)[:200]}

# ═══════════════════════════════════════════════════════════════════
# PRE-FLIGHT

def preflight_llamacpp(gguf: str) -> tuple:
    """Testa se modelo carrega via llama-cli. Retorna (status, detail)."""
    if not os.path.exists(gguf):
        return "SKIP", "blob ausente"
    t0 = time.time()
    try:
        env = {**os.environ, "LD_LIBRARY_PATH": os.path.expanduser("~/llama.cpp/build/bin")}
        r = subprocess.run(
            [os.path.expanduser("~/llama.cpp/build/bin/llama-cli"),
             "-m", gguf, "-p", "Responda apenas: OK",
             "--ctx-size", "256", "--threads", "4",
             "--batch-size", "128", "--temp", "0.1", "-n", "5",
             "--single-turn", "--no-perf", "--no-display-prompt"],
            capture_output=True, text=True, timeout=60, env=env)
        elapsed = time.time() - t0
        output = (r.stdout + r.stderr).lower()
        if "signal: killed" in output:
            return "OOM", "morto pelo kernel"
        if r.returncode != 0:
            return "FAIL", f"exit={r.returncode}"
        return "PASS", f"{elapsed:.1f}s"
    except subprocess.TimeoutExpired:
        return "TIMEOUT", ">60s"
    except Exception as e:
        return "FAIL", str(e)[:80]

def preflight_llamaserver(gguf: str) -> tuple:
    """Testa se modelo carrega via llama-server."""
    import urllib.request as ur
    if not os.path.exists(gguf):
        return "SKIP", "blob ausente"
    t0 = time.time()
    proc = None
    try:
        env = {**os.environ, "LD_LIBRARY_PATH": os.path.expanduser("~/llama.cpp/build/bin")}
        proc = subprocess.Popen(
            [os.path.expanduser("~/llama.cpp/build/bin/llama-server"),
             "--model", gguf, "--host", "127.0.0.1", "--port", "8080",
             "--ctx-size", "256", "--threads", "4", "--n-gpu-layers", "0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        for _ in range(20):
            time.sleep(1)
            try:
                ur.urlopen("http://127.0.0.1:8080/health", timeout=2)
                break
            except Exception:
                pass
        else:
            return "FAIL", "servidor nao subiu"

        body = json.dumps({"prompt": "Responda apenas: OK", "max_tokens": 5,
                           "temperature": 0.1}).encode()
        req = ur.Request("http://127.0.0.1:8080/v1/completions",
                         data=body, headers={"Content-Type": "application/json"})
        ur.urlopen(req, timeout=30)
        elapsed = time.time() - t0
        return "PASS", f"{elapsed:.1f}s"
    except Exception as e:
        return "FAIL", str(e)[:80]
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
        with suppress(Exception):
            subprocess.run(["fuser", "-k", "8080/tcp"], capture_output=True, timeout=2)

# ═══════════════════════════════════════════════════════════════════
# APPLICATION -- Orchestrator
# ═══════════════════════════════════════════════════════════════════

def run_bench_child(name: str, gguf: str, methods: list, reasoning: str,
                    questions: str = "all", server_url: str = "",
                    stress: bool = False, model_size_gb: float = 0) -> list:
    """Executa bench_child.py e retorna resultados.
    
    Se server_url for fornecido, o child conecta no servidor já rodando
    (orquestrador gerencia o ciclo de vida). Caso contrário, o child
    inicia seu próprio servidor (modo standalone/deprecated).
    """
    cmd = [sys.executable, "-u", CHILD,
           "--model-name", name, "--gguf", gguf,
           "--methods", ",".join(methods),
           "--questions", questions,
           "--reasoning", reasoning,
           "--model-size-gb", str(model_size_gb)]
    if server_url:
        cmd += ["--server-url", server_url]
    if stress:
        cmd += ["--stress"]

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        elapsed = time.time() - t0
        tee(f"  bench_child concluido em {elapsed:.0f}s")

        if r.stderr:
            for line in r.stderr.strip().split("\n"):
                if line.strip():
                    tee(f"  {line.strip()}")

        try:
            data = json.loads(r.stdout)
            results = data.get("results", [])
            for res in results:
                if isinstance(res.get("status"), dict):
                    res["status"] = res["status"].get("_value_", str(res["status"]))
            return results
        except json.JSONDecodeError:
            tee(f"  ✗ JSON invalido do bench_child. stdout: {r.stdout[:300]}")
            return []
    except subprocess.TimeoutExpired:
        tee("  ✗ TIMEOUT (>600s)")
        return []
    except Exception as e:
        tee(f"  ✗ CRASH: {e}")
        return []

# ═══════════════════════════════════════════════════════════════════
# PRESENTATION
# ═══════════════════════════════════════════════════════════════════

def print_preflight_table(pf_list: list):
    print()
    print("=" * 65)
    print("  PRE-FLIGHT: Hello World -- 2 métodos")
    print("=" * 65)
    print(f"  {'MODELO':<20} {'LLAMA-CLI':<15} {'LLAMA-SRV':<15} {'GB':<5} {'RISCO':<6}")
    print(f"  {'-'*61}")
    for pf in pf_list:
        def fmt(s, d):
            if not s:
                return "N/A"
            icon = {"PASS": "✓", "FAIL": "✗", "OOM": "💀", "SKIP": "→", "TIMEOUT": "⏰"}.get(s, "?")
            return f"{icon} {s} ({d})"
        risk = "⚠ SWAP" if pf.get("risky") else ""
        print(f"  {pf['model_name']:<20} {fmt(pf['llamacpp_status'], pf['llamacpp_detail']):<15} "
              f"{fmt(pf['llamaserver_status'], pf['llamaserver_detail']):<15} {pf['size_gb']:<5} {risk:<6}")
    print("=" * 65)
    print()

def print_bench_table(all_results: list):
    print()
    print("=" * 105)
    print("  RESULTADO FINAL -- BENCHMARK UNIFICADO")
    print("=" * 105)
    print(f"  {'MODELO':<18} {'METODO':<12} {'R':<5} {'CAT':<12} {'STATUS':<8} {'t(s)':<7} {'tok/s':<7} {'RESPOSTA'}")
    print(f"  {'-'*101}")

    stats = {}
    for mr in all_results:
        for r in mr.get("bench_results", []):
            method = r.get("method", "?")
            reasoning = r.get("reasoning", "?")
            cat = r.get("category", "?")
            status = r.get("status", "?")
            if isinstance(status, dict):
                status = status.get("_value_", str(status))
            time_s = r.get("elapsed_s", "?")
            tok_s = r.get("tok_s", "-")
            answer = (r.get("answer") or r.get("error") or "")[:45].replace("\n", " ")

            stats[status] = stats.get(status, 0) + 1

            print(f"  {mr['model_name']:<18} {method:<12} {reasoning:<5} {cat:<12} "
                  f"{status:<8} {str(time_s):<7} {str(tok_s):<7} {answer}")

    print(f"  {'-'*101}")
    total = sum(stats.values())
    print(f"  TOTAL: {total} | " + " | ".join(f"{k}={v}" for k, v in sorted(stats.items()) if v > 0))
    print("=" * 105)
    print()

def generate_markdown(all_results: list, run_id: str) -> str:
    """Gera relatório markdown completo."""
    lines = [
        "# Benchmark LLM -- Resultados",
        f"**Run ID:** `{run_id}`",
        f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "**Dispositivo:** Moto Signature 16GB RAM",
        "**Métodos:** llama-cli + llama-server",
        "",
        "---",
        "",
    ]

    # Resumo
    total_ok = 0
    total_all = 0
    for mr in all_results:
        for r in mr.get("bench_results", []):
            total_all += 1
            status = r.get("status", "?")
            if isinstance(status, dict):
                status = status.get("_value_", str(status))
            if status == "OK":
                total_ok += 1

    lines.append(f"**Resumo:** {total_ok}/{total_all} PASS ({100*total_ok//max(total_all,1)}%)")
    lines.append("")

    # Tabela por modelo
    for mr in all_results:
        lines.append(f"## {mr['model_name']} ({mr.get('size_gb', '?')} GB)")
        lines.append("")
        lines.append("| # | Método | R | Cat | Status | t(s) | tok/s | Resposta |")
        lines.append("|---|--------|---|-----|--------|------|-------|----------|")

        for i, r in enumerate(mr.get("bench_results", []), 1):
            method = r.get("method", "?")
            reasoning = r.get("reasoning", "?")
            cat = r.get("category", "?")
            status = r.get("status", "?")
            if isinstance(status, dict):
                status = status.get("_value_", str(status))
            time_s = r.get("elapsed_s", "?")
            tok_s = r.get("tok_s", "-")
            answer = (r.get("answer") or r.get("error") or "")[:60].replace("|", "\\|").replace("\n", " ")

            icon = {"OK": "✅", "FAIL": "❌", "TIMEOUT": "⏰", "OOM": "💀", "SKIP": "→", "BLOCKED": "⛔"}.get(status, "❓")

            lines.append(f"| {i} | {method} | {reasoning} | {cat} | {icon} {status} | {time_s}s | {tok_s} | {answer} |")

        lines.append("")

    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Benchmark Orchestrator v4 (DDD)")
    ap.add_argument("--model", help="Filtrar por modelo especifico")
    ap.add_argument("--questions", default="all", help="IDs ou categorias (padrao: all)")
    ap.add_argument("--reasoning", default="off", help="off | auto | off,auto")
    ap.add_argument("--quick", action="store_true", help="Apenas 3 perguntas rapidas (B1,L1,C1)")
    ap.add_argument("--ppl-only", action="store_true", help="Apenas perplexidade (PPL) em todos os modelos")
    ap.add_argument("--pipeline", action="store_true", help="Pipeline completo: stress → battery → creative → ppl → analyze")
    ap.add_argument("--stress", action="store_true", help="Stress test: cold → sustained → stress (3 fases)")
    ap.add_argument("--discover", action="store_true", help="Auto-descobre modelos via Ollama registry + GGUF files")
    ap.add_argument("--force", action="store_true", help="Forca execucao mesmo com outro orquestrador rodando")
    args = ap.parse_args()

    # ═══ SINGLETON LOCK ═══
    LOCK_FILE = os.path.join(BUILD, ".orchestrator.lock")
    if os.path.exists(LOCK_FILE) and not args.force:
        try:
            with open(LOCK_FILE) as lf:
                old_pid = int(lf.read().strip())
            os.kill(old_pid, 0)  # signal 0 = check if alive
            tee(f"ERRO: Outro orquestrador rodando (PID {old_pid}). Use --force para ignorar.")
            sys.exit(1)
        except (OSError, ValueError):
            os.remove(LOCK_FILE)  # stale lock
    with open(LOCK_FILE, "w") as lf:
        lf.write(str(os.getpid()))
    
    def _cleanup_lock():
        with suppress(Exception):
            os.remove(LOCK_FILE)
    import atexit
    atexit.register(_cleanup_lock)

    run_id = trace()
    with open(LOG_FILE, "w") as f:
        f.write(f"BENCHMARK RUN {run_id}  |  {datetime.now()}\n")

    tee(f"ORQUESTRADOR UNIFICADO v4 (DDD)  |  run_id={run_id}")
    tee(f"Moto Signature 16GB  |  Python {sys.version.split()[0]}")

    # Filtra modelos
    if args.discover:
        tee("Auto-descobrindo modelos...")
        models = discover_models()
        tee(f"Descobertos: {len(models)} modelos")
        for m in models:
            tee(f"  {m.name} ({m.size_gb}GB) {'⚠ SWAP' if m.risky else ''}")
    else:
        models = list(MODELS)
    if args.model:
        models = [m for m in models if m.name == args.model]
        if not models:
            tee(f"ERRO: Modelo '{args.model}' nao encontrado.")
            sys.exit(1)

    if args.ppl_only:
        # ═══ MODO PPL-ONLY ═══
        tee(f"FASE ÚNICA: PERPLEXIDADE (PPL) -- {len(models)} modelos")
        ppl_results = []
        for i, m in enumerate(models):
            gguf = get_gguf_path(m)
            if not os.path.exists(gguf):
                tee(f"[{i+1}/{len(models)}] {m.name}: SKIP (blob ausente)")
                continue
            tee(f"[{i+1}/{len(models)}] {m.name} ({m.size_gb}GB)...")
            
            # Orquestrador inicia servidor
            is_gemma = "gemma" in m.name.lower()
            if is_gemma:
                srv = ServerManager(OLLAMA_SERVER_BIN, OLLAMA_LD_PATH, port=8080)
            else:
                srv = ServerManager(DEFAULT_SERVER_BIN, DEFAULT_LD_PATH, port=8080)
            
            try:
                server_url = srv.start(gguf)
            except RuntimeError as e:
                tee(f"  ✗ SERVER FAIL: {e}")
                srv.stop()
                continue
            
            cmd = [sys.executable, "-u", os.path.join(BUILD, "bench_ppl.py"),
                   "--model-name", m.name, "--gguf", gguf,
                   "--server-url", server_url]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                ppl_data = json.loads(r.stdout)
                ppl_results.append(ppl_data)
                tee(f"  PPL={ppl_data['ppl']} | {ppl_data['total_tokens']} tokens | "
                    f"{ppl_data['sentences_tested']-ppl_data['sentences_failed']}/{ppl_data['sentences_tested']} frases")
            except Exception as e:
                tee(f"  ✗ FAIL: {e}")
            
            srv.stop()
            cleanup_after_model(m.name)

        # Tabela PPL
        print()
        print("=" * 55)
        print("  PERPLEXIDADE (PPL) -- Quanto menor, melhor")
        print("=" * 55)
        print(f"  {'MODELO':<20} {'PPL':<8} {'TOKENS':<8} {'FRASES':<10}")
        print(f"  {'-'*46}")
        for p in ppl_results:
            ok = p['sentences_tested'] - p['sentences_failed']
            print(f"  {p['model_name']:<20} {p['ppl']:<8} {p['total_tokens']:<8} {ok}/{p['sentences_tested']}")
        print("=" * 55)
        tee("PPL CONCLUIDO.")
        return

    # ═══ MODO PIPELINE -- esteira completa: todos os testes ═══
    if args.pipeline:
        import threading

        from bench_sys import SysMonitor
        
        models.sort(key=lambda m: m.size_gb)
        tee("PIPELINE COMPLETO - {} modelos".format(len(models)))
        tee("Esteira: stress > battery > creative > temp_sweep > sweep > ppl > analyze")
        tee("LOG: {}".format(LOG_FILE))
        write_status(run_id=run_id, phase="pipeline", step="init", step_n=0, step_total=len(models)*7)
        
        # Heartbeat a cada 5s (ping do sistema + governador termico)
        pipeline_start = time.time()
        def _heartbeat():
            while _status_state["phase"] != "done" and _status_state["phase"] != "error":
                time.sleep(5)
                # Leitura termica rapida
                try:
                    zones = list(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
                    if zones:
                        temps = []
                        for z in zones:
                            try:
                                raw = int(z.read_text().strip())
                                temps.append(raw / 1000.0)
                            except Exception:
                                pass
                        thermal_c = max(temps) if temps else 0
                    else:
                        thermal_c = 0
                except Exception:
                    thermal_c = 0
                write_status(elapsed_s=int(time.time() - pipeline_start), thermal_c=thermal_c)
        hb = threading.Thread(target=_heartbeat, daemon=True)
        hb.start()
        
        monitor = SysMonitor()
        registry = ProcessRegistry()
        pipeline_results = []
        
        kill_stray()
        cleanup_after_model()
        
        for i, m in enumerate(models):
            gguf = get_gguf_path(m)
            if not os.path.exists(gguf):
                tee(f"[{i+1}/{len(models)}] ⚠ {m.name}: SKIP (blob ausente)")
                continue
            
            sys_pre = monitor.snapshot()
            tee("")
            tee(f"▶ PIPELINE: {m.name} ({m.size_gb}GB)")
            tee(f"  [SYS] RAM: {sys_pre['ram']['avail_mb']}MB livre | "
                f"Swap: {sys_pre['swap']['used_pct']}% | "
                f"Thermal: {max(sys_pre['thermal'].values()) if sys_pre['thermal'] else 0}°C")
            
            if not check_ram_gate(sys_pre['ram']['avail_mb'],
                                  sys_pre['swap']['used_pct'], m.name):
                pipeline_results.append({"model": m.name, "gb": m.size_gb, "status": "RAM_BLOCKED"})
                continue
            
            # Thermal gate
            thermal_pre = max(sys_pre["thermal"].values()) if sys_pre["thermal"] else 0
            if thermal_pre > 80:
                tee(f"  🌡 THERMAL: {thermal_pre}°C. Aguardando <65°C...")
                while True:
                    time.sleep(10)
                    curr = max(monitor.snapshot()["thermal"].values()) if monitor.snapshot()["thermal"] else 0
                    if curr < 65:
                        break
            
            # Inicia servidor UMA vez para todos os testes
            is_gemma = "gemma" in m.name.lower()
            if is_gemma:
                srv = ServerManager(OLLAMA_SERVER_BIN, OLLAMA_LD_PATH, port=8080)
            else:
                srv = ServerManager(DEFAULT_SERVER_BIN, DEFAULT_LD_PATH, port=8080)
            
            try:
                server_url = srv.start(gguf)
            except RuntimeError as e:
                tee(f"  ✗ SERVER FAIL: {e}")
                pipeline_results.append({"model": m.name, "gb": m.size_gb, "status": "SERVER_FAIL"})
                srv.stop()
                continue
            
            model_result = {"model": m.name, "gb": m.size_gb, "tests": {}, "thermal_log": []}
            
            # ═══ Esteira de testes ═══
            TESTS = [
                ("stress",    os.path.join(BUILD, "bench_child.py"),
                 [sys.executable, "-u", os.path.join(BUILD, "bench_child.py"),
                  "--stress", "--model-name", m.name, "--gguf", gguf,
                  "--model-size-gb", str(m.size_gb), "--server-url", server_url], 300),
                ("battery",   os.path.join(BUILD, "bench_battery.py"),
                 [sys.executable, "-u", os.path.join(BUILD, "bench_battery.py"),
                  "--model-name", m.name, "--gguf", gguf,
                  "--model-size-gb", str(m.size_gb), "--server-url", server_url], 300),
                ("creative",  os.path.join(BUILD, "bench_creative.py"),
                 [sys.executable, "-u", os.path.join(BUILD, "bench_creative.py"),
                  "--model-name", m.name, "--gguf", gguf,
                  "--model-size-gb", str(m.size_gb), "--server-url", server_url], 600),
                ("temp_sweep", os.path.join(BUILD, "bench_temp_sweep.py"),
                 [sys.executable, "-u", os.path.join(BUILD, "bench_temp_sweep.py"),
                  "--model-name", m.name, "--gguf", gguf,
                  "--model-size-gb", str(m.size_gb), "--server-url", server_url], 1800),
                ("sweep",     os.path.join(BUILD, "bench_sweep.py"),
                 [sys.executable, "-u", os.path.join(BUILD, "bench_sweep.py"),
                  "--gguf", gguf, "--model-name", m.name,
                  "--config", str(BUILD / f"test-{m.name.split('-')[0][:4]}/sweep_config.json"),
                  "--output", str(BUILD / f"test-{m.name.split('-')[0][:4]}/sweep_results.json")], 1800),
                ("ppl",       os.path.join(BUILD, "bench_ppl.py"),
                 [sys.executable, "-u", os.path.join(BUILD, "bench_ppl.py"),
                  "--model-name", m.name, "--gguf", gguf,
                  "--corpus-size", "10", "--server-url", server_url], 120),
                ("analyze",   os.path.join(BUILD, "bench_analyze.py"),
                 [sys.executable, "-u", os.path.join(BUILD, "bench_analyze.py"),
                  "--model-name", m.name, "--gguf", gguf,
                  "--model-size-gb", str(m.size_gb), "--server-url", server_url], 180),
            ]
            
            for test_name, script, test_args, timeout in TESTS:
                step_n = i * len(TESTS) + list(dict(TESTS).keys()).index(test_name) + 1
                # Dispatch log: registro PRE
                dh = dispatch_create(
                    agent_id=m.name.replace("_", "-"),
                    function=test_name,
                    model=m.name,
                )
                # Power-throttle: governador termico reduz tokens se necessario
                limit = get_thermal_limit()
                tier = "full"
                try:
                    import json as _j
                    with open(THERMAL_FILE) as f:
                        td = _j.load(f)
                    tier = td.get("tier", "full")
                    thermal_c = td.get("thermal_c", 0)
                except Exception:
                    tier = "full"
                    thermal_c = 0
                if limit < 512:
                    tee("  [THROTTLE] {} → tier={} max_tokens={} temp={}C".format(
                        test_name, tier, limit, thermal_c))
                model_result["thermal_log"].append({
                    "step": test_name, "tier": tier, "max_tokens": limit,
                    "thermal_c": thermal_c, "elapsed_s": int(time.time() - pipeline_start),
                })
                test_env = os.environ.copy()
                test_env["BENCH_MAX_TOKENS"] = str(limit)
                write_status(model=m.name, step=test_name, step_n=step_n, step_total=len(models)*len(TESTS),
                       elapsed_s=int(time.time() - pipeline_start))
                result = run_pipeline_child(script, test_args, test_name,
                                            registry, timeout, env=test_env)
                model_result["tests"][test_name] = result
                # Dispatch log: registro POST com benchmark metrics
                tok_s = 0
                benchmark = None
                if isinstance(result, dict):
                    summary = result.get("summary", {})
                    tok_s = summary.get("avg_tok_s", 0)
                    battery = result if result.get("summary") else None
                    if battery:
                        benchmark = {
                            "ok": summary.get("ok", 0),
                            "total": summary.get("total", 0),
                            "score": summary.get("score", 0),
                            "avg_tok_s": summary.get("avg_tok_s", 0),
                        }
                dispatch_complete(dh, result.get("status", "?"), tok_s=tok_s, benchmark=benchmark)
                
                if result.get("status") == "OOM_PROTECT":
                    tee(f"  ⛔ Pipeline interrompido por OOM em {m.name}")
                    break
                
                # Verifica pressão entre testes
                if check_memory_pressure(600):
                    tee("  ⚠ Pressão de memória entre testes. Continuando...")
            
            srv.stop()
            
            # Snapshot pós
            sys_post = monitor.snapshot()
            ram_delta = sys_post["ram"]["used_mb"] - sys_pre["ram"]["used_mb"]
            model_result["ram_delta_mb"] = ram_delta
            tee(f"  [SYS] RAM delta: {ram_delta:+d}MB | "
                f"Thermal: {max(sys_post['thermal'].values()) if sys_post['thermal'] else 0}°C")
            tee(f"◀ PIPELINE: {m.name} concluído")
            
            pipeline_results.append(model_result)
            cleanup_after_model(m.name)
        
        write_status(phase="done", step="complete", elapsed_s=int(time.time() - pipeline_start))
        
        # Tabela final do pipeline
        print("\n" + "=" * 125)
        print("  PIPELINE COMPLETO -- RESULTADOS")
        print("=" * 125)
        print("  {:<22} {:>8} {:>8} {:>9} {:>10} {:>7} {:>7} {:>9} {:>7}".format(
            "MODELO", "STRESS", "BATTERY", "CREATIVE", "T_SWEEP", "SWEEP", "PPL", "ANALYZE", "ΔRAM"))
        print("  " + "-" * 100)
        for r in pipeline_results:
            tests = r.get("tests", {})
            def s(name):
                t = tests.get(name, {})
                st = t.get("status", "?")
                return st[:8]
            def ss(name):
                t = tests.get(name, {})
                st = t.get("status", "?")
                return st[:6]
            ram = r.get("ram_delta_mb", 0)
            print("  {:<22} {:>8} {:>8} {:>9} {:>10} {:>7} {:>7} {:>9} {:>+6d}".format(
                r['model'], s('stress'), s('battery'), s('creative'),
                ss('temp_sweep'), ss('sweep'), s('ppl'), s('analyze'), ram))
        print("=" * 125)
        
        output = {"run_id": run_id, "mode": "pipeline", "results": pipeline_results,
                  "timestamp": datetime.now().isoformat()}
        pipe_file = os.path.join(BUILD, "benchmark_pipeline.json")
        with open(pipe_file, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        tee(f"JSON salvo: {pipe_file}")
        tee("PIPELINE CONCLUIDO.")
        return

    # ═══ MODO STRESS ═══
    if args.stress:
        from bench_sys import SysMonitor
        
        models.sort(key=lambda m: m.size_gb)
        tee(f"STRESS TEST -- {len(models)} modelos (menor → maior)")
        tee(f"LOG: {LOG_FILE}")
        
        monitor = SysMonitor()
        stress_results = []
        
        kill_stray()
        cleanup_after_model()
        
        for i, m in enumerate(models):
            gguf = get_gguf_path(m)
            if not os.path.exists(gguf):
                tee(f"[{i+1}/{len(models)}] ⚠ {m.name}: SKIP (blob ausente)")
                continue
            
            # ═══ SYSTEM GUARD: snapshot pré-modelo ═══
            sys_pre = monitor.snapshot()
            ram_pre = sys_pre["ram"]
            swap_pre = sys_pre["swap"]
            cpu_pre = sys_pre["cpu"]
            thermal_pre = max(sys_pre["thermal"].values()) if sys_pre["thermal"] else 0
            
            tee("")
            tee(f"▶ INICIO: {m.name} ({m.size_gb}GB)")
            tee(f"  [SYS] RAM: {ram_pre['used_mb']}MB/{ram_pre['total_mb']}MB ({ram_pre['used_pct']}%) | "
                f"Avail: {ram_pre['avail_mb']}MB")
            tee(f"  [SYS] Swap: {swap_pre['used_mb']}MB/{swap_pre['total_mb']}MB ({swap_pre['used_pct']}%)")
            tee(f"  [SYS] CPU: {cpu_pre['avg_mhz']:.0f}MHz avg / {cpu_pre['max_mhz']:.0f}MHz max | "
                f"gov: {cpu_pre['governor']} | load: {cpu_pre['load_1m']}")
            tee(f"  [SYS] Thermal: {thermal_pre}°C")
            
            # ═══ RAM GATE ═══
            if not check_ram_gate(ram_pre['avail_mb'], swap_pre['used_pct'], m.name):
                stress_results.append({"model": m.name, "gb": m.size_gb, "status": "RAM_BLOCKED"})
                continue
            
            # ═══ THERMAL GATE ═══
            if thermal_pre > 80:
                tee(f"  🌡 THERMAL GATE: {thermal_pre}°C > 80°C. Aguardando cooldown...")
                while True:
                    time.sleep(10)
                    curr = max(monitor.snapshot()["thermal"].values()) if monitor.snapshot()["thermal"] else 0
                    tee(f"    → {curr}°C")
                    if curr < 65:
                        break
            
            # ═══ ORQUESTRADOR INICIA O SERVIDOR ═══
            is_gemma = "gemma" in m.name.lower()
            if is_gemma:
                srv = ServerManager(OLLAMA_SERVER_BIN, OLLAMA_LD_PATH, port=8080)
            else:
                srv = ServerManager(DEFAULT_SERVER_BIN, DEFAULT_LD_PATH, port=8080)
            
            try:
                server_url = srv.start(gguf)
            except RuntimeError as e:
                tee(f"  ✗ SERVER FAIL: {e}")
                stress_results.append({"model": m.name, "gb": m.size_gb, "status": "SERVER_FAIL"})
                srv.stop()
                continue
            
            # ═══ DELEGA AO CHILD (cliente puro, sem server management) ═══
            tee(f"  [CHILD] Iniciando bench_child.py --stress --server-url {server_url}...")
            t_child = time.time()
            child_stdout = ""
            child_cmd = [sys.executable, "-u", CHILD, "--stress",
                        "--model-name", m.name, "--gguf", gguf,
                        "--model-size-gb", str(m.size_gb),
                        "--server-url", server_url]
            try:
                r = subprocess.run(child_cmd, capture_output=True, text=True, timeout=600)
                child_elapsed = time.time() - t_child
                child_stdout = r.stdout
                
                if r.stderr:
                    for line in r.stderr.strip().split("\n"):
                        if line.strip():
                            tee(f"  {line.strip()}")
                
                child_data = json.loads(r.stdout)
                child_data["child_elapsed_s"] = round(child_elapsed, 0)
                stress_results.append(child_data)
                tee(f"  ✓ CHILD OK ({child_elapsed:.0f}s)")
            except subprocess.TimeoutExpired:
                tee("  ✗ CHILD TIMEOUT (>600s)")
                stress_results.append({"model": m.name, "gb": m.size_gb, "status": "CHILD_TIMEOUT"})
            except json.JSONDecodeError:
                tee(f"  ✗ CHILD JSON invalido: {child_stdout[:300]}")
                stress_results.append({"model": m.name, "gb": m.size_gb, "status": "CHILD_JSON_ERR"})
            except Exception as e:
                tee(f"  ✗ CHILD CRASH: {e}")
                stress_results.append({"model": m.name, "gb": m.size_gb, "status": "CHILD_CRASH"})
            
            # ═══ ORQUESTRADOR PARA O SERVIDOR ═══
            srv.stop()
            
            # ═══ SYSTEM GUARD: snapshot pós-modelo (ANTES do cleanup) ═══
            sys_post = monitor.snapshot()
            ram_post = sys_post["ram"]
            swap_post = sys_post["swap"]
            thermal_post = max(sys_post["thermal"].values()) if sys_post["thermal"] else 0
            
            ram_delta = ram_post["used_mb"] - ram_pre["used_mb"]
            tee(f"  [SYS] Pós-modelo RAM: {ram_post['used_mb']}MB (delta: {ram_delta:+d}MB) | "
                f"Swap: {swap_post['used_mb']}MB | Thermal: {thermal_post}°C")
            tee(f"◀ FIM: {m.name} -- OK")
            
            # ═══ CLEANUP: libera RAM para o próximo modelo ═══
            cleanup_after_model(m.name)
        
        # ═══ TABELA FINAL ═══
        print(f"\n{'='*95}")
        print("  COMPARATIVO FINAL -- STRESS TEST (orquestrador v4)")
        print(f"{'='*95}")
        print(f"  {'MODELO':<20} {'GB':<5} {'COLD':>8} {'SUST':>8} {'STRESS':>8} {'T_MAX':>6} {'STATUS':<15}")
        print(f"  {'-'*80}")
        for r in stress_results:
            status = r.get("status", "?")
            if status != "OK":
                print(f"  {r['model']:<20} {r['gb']:<5} {'--':>8} {'--':>8} {'--':>8} {'--':>6} {status:<15}")
                continue
            p = r.get("phases", {})
            cold = f"{p.get('COLD',{}).get('avg_tok_s',0):.0f}t/s"
            sust = f"{p.get('SUSTAINED',{}).get('avg_tok_s',0):.0f}t/s"
            stress = f"{p.get('STRESS',{}).get('avg_tok_s',0):.0f}t/s"
            temps = [p[k].get("max_temp_c", 0) for k in p]
            tmax = f"{max(temps)}°C" if temps else "--"
            print(f"  {r['model']:<20} {r['gb']:<5} {cold:>8} {sust:>8} {stress:>8} {tmax:>6} {status:<15}")
        print(f"{'='*95}")
        
        # Salva JSON
        output = {"run_id": run_id, "mode": "stress", "results": stress_results,
                  "timestamp": datetime.now().isoformat()}
        stress_file = os.path.join(BUILD, "benchmark_stress.json")
        with open(stress_file, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        tee(f"JSON salvo: {stress_file}")
        tee("STRESS TEST CONCLUIDO.")
        return

    # ═══ BENCHMARK DIRETO (sem preflight -- mmap resolve) ═══
    questions = "B1,L1,C1" if args.quick else args.questions
    reasoning = args.reasoning

    tee(f"BENCHMARK ({questions}, reasoning={reasoning}) -- {len(models)} modelos")
    all_results = []

    for i, m in enumerate(models):
        gguf = get_gguf_path(m)
        if not os.path.exists(gguf):
            tee(f"[{i+1}/{len(models)}] {m.name}: SKIP (blob ausente)")
            all_results.append({"model_name": m.name, "size_gb": m.size_gb, "bench_results": []})
            continue

        tee(f"[{i+1}/{len(models)}] {m.name} ({m.size_gb}GB)")
        
        # Orquestrador inicia servidor
        is_gemma = "gemma" in m.name.lower()
        if is_gemma:
            srv = ServerManager(OLLAMA_SERVER_BIN, OLLAMA_LD_PATH, port=8080)
        else:
            srv = ServerManager(DEFAULT_SERVER_BIN, DEFAULT_LD_PATH, port=8080)
        
        server_url = ""
        try:
            server_url = srv.start(gguf)
        except RuntimeError as e:
            tee(f"  ✗ SERVER FAIL: {e}")
            all_results.append({"model_name": m.name, "size_gb": m.size_gb, "bench_results": []})
            srv.stop()
            cleanup_after_model(m.name)
            continue
        
        results = run_bench_child(m.name, gguf, ["llamacpp", "llamaserver"],
                                  reasoning, questions,
                                  server_url=server_url, model_size_gb=m.size_gb)
        all_results.append({"model_name": m.name, "size_gb": m.size_gb, "bench_results": results})
        
        srv.stop()
        cleanup_after_model(m.name)

    # ═══ RELATÓRIO ═══
    print_bench_table(all_results)

    # Salva JSON
    output = {"run_id": run_id, "results": all_results,
              "timestamp": datetime.now().isoformat()}
    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Salva Markdown
    md = generate_markdown(all_results, run_id)
    md_path = os.path.join(BUILD, "benchmark_report.md")
    with open(md_path, "w") as f:
        f.write(md)

    tee(f"JSON salvo: {RESULTS_FILE}")
    tee(f"Markdown salvo: {md_path}")
    tee(f"Log completo: {LOG_FILE}")
    tee("CONCLUIDO.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
thermal_governor.py -- Governador termico + RAM para inferencia local.
Como um processador: monitora a cada 5s e ajusta parametros em tempo real.
Nunca bloqueia -- sempre degrada gracefulmente.

Politicas:
  temp < 70°C → full power (max_tokens=512, temp=0.7)
  temp 70-80°C → eco (max_tokens=256, temp=0.5)
  temp 80-85°C → low (max_tokens=128, temp=0.3)
  temp 85-90°C → minimal (max_tokens=64, temp=0.1)
  temp > 90°C → idle (max_tokens=16, temp=0.0, cooldown obrigatorio)

RAM:
  avail > 2GB   → normal
  avail 1-2GB   → reduce context (ctx_half)
  avail < 1GB   → minimal context (ctx_quarter)
"""
import json
import threading
import time
from contextlib import suppress
from pathlib import Path


class ThermalGovernor:
    """Monitora sistema a cada 5s e ajusta limites de inferencia."""

    def __init__(self, status_file=None):
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._status_file = Path(status_file) if status_file else None

        # Estado atual
        self.current_tier = "full"
        self.max_tokens = 512
        self.temperature = 0.7
        self.ctx_factor = 1.0
        self.temps = []
        self.ram_mb = 0
        self.swap_pct = 0

    @property
    def limits(self):
        """Retorna limites atuais para inferencia."""
        with self._lock:
            return {
                "tier": self.current_tier,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "ctx_factor": self.ctx_factor,
                "thermal_c": self.temps[-1] if self.temps else 0,
                "ram_avail_mb": self.ram_mb,
            }

    def _read_thermal(self):
        """Le temperatura maxima de todas as zonas termicas."""
        try:
            zones = list(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
            if not zones:
                return 0
            temps = []
            for z in zones:
                try:
                    raw = int(z.read_text().strip())
                    temps.append(raw / 1000.0)
                except Exception:
                    pass
            return max(temps) if temps else 0
        except Exception:
            return 0

    def _read_ram(self):
        """Le RAM disponivel em MB."""
        try:
            with open("/proc/meminfo") as f:
                info = {}
                for line in f:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        info[k.strip()] = int(v.strip().split()[0])
                avail = info.get("MemAvailable", 0) // 1024
                swap_total = info.get("SwapTotal", 0) // 1024
                swap_free = info.get("SwapFree", 0) // 1024
                swap_used = swap_total - swap_free
                swap_pct = (swap_used / swap_total * 100) if swap_total else 0
                return avail, swap_pct
        except Exception:
            return 8192, 0

    def _tick(self):
        """Uma iteracao do governador: le sistema, ajusta limites."""
        thermal = self._read_thermal()
        ram_avail, swap_pct = self._read_ram()

        with self._lock:
            self.temps.append(thermal)
            if len(self.temps) > 12:  # keep last 60s
                self.temps.pop(0)
            self.ram_mb = ram_avail
            self.swap_pct = swap_pct

            # Politica termica (prioritaria)
            if thermal > 90:
                self.current_tier = "idle"
                self.max_tokens = 16
                self.temperature = 0.0
            elif thermal > 85:
                self.current_tier = "minimal"
                self.max_tokens = 64
                self.temperature = 0.1
            elif thermal > 80:
                self.current_tier = "low"
                self.max_tokens = 128
                self.temperature = 0.3
            elif thermal > 70:
                self.current_tier = "eco"
                self.max_tokens = 256
                self.temperature = 0.5
            else:
                self.current_tier = "full"
                self.max_tokens = 512
                self.temperature = 0.7

            # Politica de RAM (secundaria)
            if ram_avail < 512:
                self.ctx_factor = 0.125  # 1/8 context
                self.max_tokens = min(self.max_tokens, 32)
            elif ram_avail < 1024:
                self.ctx_factor = 0.25   # 1/4 context
                self.max_tokens = min(self.max_tokens, 64)
            elif ram_avail < 2048:
                self.ctx_factor = 0.5    # 1/2 context

            # Escreve status
            if self._status_file:
                with suppress(Exception):
                    self._status_file.write_text(json.dumps({
                        "thermal_c": thermal,
                        "ram_avail_mb": ram_avail,
                        "swap_pct": swap_pct,
                        "tier": self.current_tier,
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "temps_60s": self.temps,
                    }))

    def start(self):
        """Inicia monitoramento em background (5s interval)."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Para monitoramento."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while self._running:
            self._tick()
            time.sleep(5)

    def should_throttle(self):
        """True se deve reduzir velocidade (temp > 70)."""
        return self.current_tier != "full"

    def is_critical(self):
        """True se deve pausar completamente (temp > 90)."""
        return self.current_tier == "idle"


# Singleton global
_governor = None


def get_governor():
    global _governor
    if _governor is None:
        _governor = ThermalGovernor(
            status_file=Path(__file__).parent / "thermal_status.json"
        )
    return _governor

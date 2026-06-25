#!/usr/bin/env python3
"""
bench_sys.py — Métricas de sistema por run (RCA/Pareto).
Captura: CPU clock, temp, RAM, swap, carga — antes/durante/depois.
"""
import os
import time


def read_file(path, default="0"):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return default

class SysMonitor:
    """Coleta métricas do sistema Android via /proc e /sys."""

    @staticmethod
    def snapshot():
        return {
            "ts": time.time(),
            "cpu": SysMonitor._cpu(),
            "ram": SysMonitor._ram(),
            "swap": SysMonitor._swap(),
            "thermal": SysMonitor._thermal(),
        }

    @staticmethod
    def _cpu():
        """CPU freq média (kHz) e governor."""
        freqs = []
        for i in range(8):
            f = read_file(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq")
            if f and f != "0":
                freqs.append(int(f))
        gov = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        load = os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0
        return {
            "freqs_khz": freqs,
            "avg_mhz": round(sum(freqs)/max(len(freqs),1)/1000, 0),
            "max_mhz": round(max(freqs)/1000, 0) if freqs else 0,
            "governor": gov,
            "load_1m": round(load, 2),
        }

    @staticmethod
    def _ram():
        """RAM via /proc/meminfo (em MB)."""
        mem = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        mem[k.strip()] = int(v.strip().split()[0]) // 1024  # KB→MB
        except Exception:
            pass
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", 0)
        used = total - avail if total and avail else 0
        return {
            "total_mb": total,
            "avail_mb": avail,
            "used_mb": used,
            "used_pct": round(used/max(total,1)*100, 1),
        }

    @staticmethod
    def _swap():
        """Swap via /proc/meminfo."""
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("SwapTotal"):
                        total = int(line.split()[1]) // 1024
                    elif line.startswith("SwapFree"):
                        free = int(line.split()[1]) // 1024
        except Exception:
            total = free = 0
        used = total - free
        return {
            "total_mb": total,
            "used_mb": used,
            "used_pct": round(used/max(total,1)*100, 1),
        }

    @staticmethod
    def _thermal():
        """Temperatura das zonas térmicas."""
        temps = {}
        for i in range(20):
            t = read_file(f"/sys/class/thermal/thermal_zone{i}/temp")
            if t and t != "0":
                name = read_file(f"/sys/class/thermal/thermal_zone{i}/type", f"zone{i}")
                temps[name] = int(t) // 1000  # miligraus → °C
        return temps

    @staticmethod
    def delta(before, after):
        """Calcula variação entre dois snapshots."""
        return {
            "elapsed_s": round(after["ts"] - before["ts"], 1),
            "ram_delta_mb": after["ram"]["used_mb"] - before["ram"]["used_mb"],
            "swap_delta_mb": after["swap"]["used_mb"] - before["swap"]["used_mb"],
            "cpu_max_mhz": after["cpu"]["max_mhz"],
            "cpu_avg_mhz": after["cpu"]["avg_mhz"],
            "max_temp_c": max(after["thermal"].values()) if after["thermal"] else 0,
        }


if __name__ == "__main__":
    import json
    m = SysMonitor()
    before = m.snapshot()
    time.sleep(1)
    after = m.snapshot()
    delta = m.delta(before, after)
    print(json.dumps({"before": before, "after": after, "delta": delta},
                     indent=2, ensure_ascii=False))

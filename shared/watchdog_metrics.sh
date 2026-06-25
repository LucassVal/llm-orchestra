#!/bin/sh
# watchdog_metrics.sh — Verifica se metrics_daemon esta rodando, inicia se nao.
# Uso: cron a cada 1min com no_agent=true
PID_FILE="$HOME/build/.metrics_daemon.pid"
DAEMON="$HOME/build/shared/metrics_daemon.py"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        exit 0  # rodando
    fi
fi

# Inicia
cd "$HOME/build" && nohup python3 "$DAEMON" > /dev/null 2>&1 &
echo $! > "$PID_FILE"
echo "[watchdog] metrics_daemon iniciado PID=$!"

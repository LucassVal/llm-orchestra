# shared/ -- Manifesto Local
# Infraestrutura compartilhada. Monitora, coleta, persiste.
# Autoridade: T2 (infra) | Parent: build/RULES.md (T1)

## Componentes
  thermal_governor.py  -- monitor termico + RAM (5s)
  metrics_reporter.py  -- coleta unificada de metricas
  metrics_daemon.py    -- persistencia Obsidian + CSV (5s)
  agent_factory.py     -- fabrica de agentes via contrato
  watchdog_metrics.sh  -- keep-alive do daemon (cron 1min)

## Regras
- NUNCA chamados diretamente -- sempre via meta (LEVEL 0)
- NUNCA iniciam servidores -- so leem status
- Dados fluem: children → arquivos → metrics_reporter → meta/daemon
- Sem dependencias externas alem de Python stdlib

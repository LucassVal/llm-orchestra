#!/usr/bin/env python3
# 3W: WHAT=multi-agent orchestrator | WHY=orquestrar agentes via cron | WHEN=cron job ou manual
"""
multi_agent.py -- Orquestrador simples de multi-agentes.
DDD: cron chama este script que delega para agentes individuais via meta --run.
Arquitetura: cron-based, sem cadeia de handoff complexa.
"""
import json
import subprocess
import sys
from pathlib import Path

AGENTS_DIR = Path.home() / "agents"
BUILD = Path.home() / "build"


def list_agents():
    """Lista agentes disponiveis em ~/agents/"""
    agents = []
    for d in sorted(AGENTS_DIR.iterdir()):
        contract = d / "contract.json"
        if d.is_dir() and contract.exists():
            c = json.loads(contract.read_text())
            agents.append({
                "id": c["agent_id"],
                "model": c["1_profile"]["model"],
                "profile": c["1_profile"].get("profile_ref", "agent_default"),
                "purpose": c["3_function"]["purpose"],
                "skills": c.get("8_skills", {}).get("preload", []),
            })
    return agents


def run_agent(agent_id, prompt, model=None, profile=None):
    """Executa 1 agente via meta --run."""
    agents = {a["id"]: a for a in list_agents()}
    if agent_id not in agents:
        print("Agente '{}' nao encontrado".format(agent_id))
        return 1
    a = agents[agent_id]
    cmd = [
        sys.executable, str(BUILD / "meta_orchestrator.py"),
        "--run", prompt,
        "--model", model or a["model"],
        "--profile", profile or a["profile"],
    ]
    return subprocess.run(cmd).returncode


def run_pipeline(agent_ids, prompt):
    """Executa pipeline de agentes em sequencia."""
    for aid in agent_ids:
        print("=" * 40)
        print("AGENTE: {}".format(aid))
        rc = run_agent(aid, prompt)
        if rc != 0:
            print("Falha no agente {}, parando pipeline".format(aid))
            return rc
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: multi_agent.py list|run|pipeline [args]")
        print("  list                  -- lista agentes")
        print("  run <id> <prompt>     -- roda 1 agente")
        print("  pipeline <id1,id2> <prompt> -- pipeline sequencial")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list":
        for a in list_agents():
            print("{:<25} {:<8} {:<20} {}".format(
                a["id"], a["model"], a["profile"], a["purpose"]))
    elif action == "run":
        run_agent(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "ok")
    elif action == "pipeline":
        run_pipeline(sys.argv[2].split(","), sys.argv[3] if len(sys.argv) > 3 else "ok")

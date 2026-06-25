#!/usr/bin/env python3

# 3W: WHAT=benchmark tool | WHY=avaliar LLMs locais | WHEN=pipeline run
"""
agent_factory.py -- Fabrica de agentes via contrato JSON.
Le um agent_contract.json e gera/valida o agente.
SDD: agent_contract_template.json como spec canonica.

Uso:
  python3 shared/agent_factory.py create --contract agent.json
  python3 shared/agent_factory.py validate --contract agent.json
  python3 shared/agent_factory.py list-profiles
"""
import json
import sys
from pathlib import Path

BUILD = Path(__file__).parent.parent
AGENTS = Path.home() / "agents"
TEMPLATE = AGENTS / "agent_contract_template.json"
SCHEMA_VERSION = "agent_contract_v1"
REQUIRED_SECTIONS = [
    "agent_id", "display_name",
    "1_profile", "2_personality", "3_function",
    "4_limits", "5_sources", "6_tools",
    "7_memory", "8_skills", "9_delegation",
    "10_fallback", "11_cron"
]


def validate_contract(contract_path):
    """Valida contrato contra o schema. Retorna (ok, errors)."""
    errors = []
    if not contract_path.exists():
        return False, ["arquivo nao encontrado: {}".format(contract_path)]

    try:
        c = json.loads(contract_path.read_text())
    except json.JSONDecodeError as e:
        return False, ["JSON invalido: {}".format(e)]

    if c.get("_schema") != SCHEMA_VERSION:
        errors.append("schema esperado: {}, encontrado: {}".format(
            SCHEMA_VERSION, c.get("_schema", "ausente")))

    for section in REQUIRED_SECTIONS:
        if section not in c:
            errors.append("secao obrigatoria ausente: {}".format(section))

    # Valida profile_ref existe
    profile = c.get("1_profile", {})
    profile_ref = profile.get("profile_ref", "")
    if profile_ref:
        prof_path = BUILD / profile_ref
        if not prof_path.exists():
            errors.append("profile_ref nao encontrado: {}".format(profile_ref))

    # Valida toolsets
    valid_toolsets = {
        "terminal", "file", "web", "search", "skills", "memory",
        "session_search", "browser", "image_gen", "delegation", "cronjob",
        "vision", "tts", "clarify", "todo", "coding"
    }
    tools = c.get("6_tools", {})
    for t in tools.get("allow", []):
        if t not in valid_toolsets:
            errors.append("toolset invalido: {}".format(t))

    return len(errors) == 0, errors


def create_agent(contract_path, output_dir=None):
    """Cria agente a partir do contrato. Gera HERMES.md + valida."""
    ok, errors = validate_contract(contract_path)
    if not ok:
        print("VALIDACAO FALHOU:")
        for e in errors:
            print("  - {}".format(e))
        return False

    c = json.loads(contract_path.read_text())
    agent_id = c["agent_id"]
    out = Path(output_dir) if output_dir else AGENTS / agent_id
    out.mkdir(parents=True, exist_ok=True)

    # Gera HERMES.md do agente
    personality = c["2_personality"]
    function = c["3_function"]
    limits = c["4_limits"]

    md = []
    md.append("# {} -- {}".format(c["display_name"], agent_id))
    md.append("")
    md.append("## Identidade")
    md.append("- **Modelo:** {}".format(c["1_profile"]["model"]))
    md.append("- **Perfil:** {}".format(c["1_profile"]["profile_ref"]))
    md.append("- **Proposito:** {}".format(function["purpose"]))
    md.append("- **Dominio:** {}".format(function["domain"]))
    md.append("")
    md.append("## Personalidade")
    md.append("- **Tom:** {}".format(personality["tone"]))
    md.append("- **Idioma:** {}".format(personality["language"]))
    md.append("- **Estilo:** {}".format(personality["style"]))
    md.append("")
    md.append("## Tarefas")
    for task in function.get("tasks", []):
        md.append("- {}".format(task))
    md.append("")
    md.append("## Limites")
    md.append("- Max turns: {}".format(limits["max_turns"]))
    md.append("- Timeout: {}s".format(limits["timeout_s"]))
    md.append("- Tokens/turn: {}".format(limits["max_tokens_per_turn"]))
    md.append("")
    md.append("## Ferramentas")
    tools = c["6_tools"]
    md.append("- Permitidas: {}".format(", ".join(tools["allow"])))
    md.append("- Bloqueadas: {}".format(", ".join(tools["deny"])))
    md.append("")
    md.append("## Fontes da Verdade")
    for src in c["5_sources"].get("rules", []):
        md.append("- {}".format(src))
    for doc in c["5_sources"].get("docs", []):
        md.append("- {}".format(doc))

    # Skills injection
    skills = c.get("8_skills", {})
    if skills.get("preload"):
        md.append("")
        md.append("## Skills (carregadas do Hermes)")
        for skill in skills["preload"]:
            md.append("- {}".format(skill))
        md.append("")
        md.append("Ao iniciar, carregar estas skills via `skill_view('{}')`.".format(
            skills["preload"][0]))

    (out / "AGENT.md").write_text("\n".join(md))

    # Copia contrato
    import shutil
    shutil.copy(contract_path, out / "contract.json")

    print("✓ Agente criado: {}".format(out))
    print("  AGENT.md    -- identidade e regras")
    print("  contract.json -- contrato canonico")
    return True


def list_profiles():
    """Lista perfis disponiveis por modelo."""
    for model_dir in sorted(BUILD.glob("test-*/profiles")):
        model = model_dir.parent.name
        print("{}:".format(model))
        for prof in sorted(model_dir.glob("*.json")):
            try:
                p = json.loads(prof.read_text())
                print("  {} -- {}".format(prof.stem, p.get("description", "?")))
            except Exception:
                print("  {} -- JSON invalido".format(prof.stem))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: agent_factory.py <create|validate|list-profiles> [--contract path]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "list-profiles":
        list_profiles()
    elif action in ("create", "validate"):
        contract = None
        if "--contract" in sys.argv:
            ci = sys.argv.index("--contract")
            contract = Path(sys.argv[ci + 1]) if ci + 1 < len(sys.argv) else None
        if not contract:
            print("ERRO: --contract obrigatorio")
            sys.exit(1)
        if action == "validate":
            ok, errors = validate_contract(contract)
            if ok:
                print("✓ Contrato valido")
            else:
                print("✗ Contrato invalido:")
                for e in errors:
                    print("  - {}".format(e))
        else:
            create_agent(contract)

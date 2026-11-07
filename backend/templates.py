"""Versioned specialist catalog and server-enforced tool permissions."""
import json

from .storage import ROOT

SPECIALISTS = ("ux", "graphic-designer", "architect", "coder", "community-manager")
FILE_TOOLS = ["project_list_files", "project_read_file", "project_write_file"]


def template(kind, instructions=False):
    if kind not in SPECIALISTS:
        raise ValueError("Plantilla no válida.")
    root = ROOT / "templates" / kind
    result = {**json.loads((root / "template.json").read_text(encoding="utf-8")), "kind": kind, "tools": tools_for(kind)}
    if instructions:
        result["instructions"] = (root / "SOUL.md").read_text(encoding="utf-8")
    return result


def tools_for(kind):
    if kind == "hapic":
        return ["get_ux_template", "create_ux_agent", "list_agent_templates", "list_project_agents", "create_specialist_agent", "restart_specialist_agent", "create_task", "list_tasks", "inspect_task", "run_task"]
    if kind not in SPECIALISTS:
        return []
    extra = {"ux": ["generate_project_image"], "graphic-designer": ["generate_project_image"], "architect": ["publish_architecture_plan"], "coder": ["get_architecture_plan"], "community-manager": ["generate_project_image"]}
    return FILE_TOOLS + extra[kind]

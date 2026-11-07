"""Reusable integrations. Templates set defaults; assignments authorize each agent."""
from .templates import tools_for

CATALOG = {
    "heygen": {
        "id": "heygen",
        "name": "HeyGen",
        "description": "Genera clips con audio desde texto o una imagen y guarda el MP4 en el proyecto.",
        "provider": "heygen",
        "access": "generate",
        "requires_connection": True,
        "actions": ["heygen_generate_video", "heygen_get_video", "heygen_list_videos"],
    },
    "youtube": {
        "id": "youtube",
        "name": "YouTube",
        "description": "Consulta el canal, sus vídeos, comentarios e informes de rendimiento.",
        "provider": "youtube",
        "access": "read",
        "requires_connection": True,
        "actions": ["youtube_get_channel", "youtube_list_videos", "youtube_list_comments", "youtube_get_analytics"],
    },
}


def defaults(kind):
    return ["youtube", "heygen"] if kind == "community-manager" else []


def effective_tools(agent, store):
    names = list(tools_for(agent["kind"]))
    for binding in store.all("SELECT tool_id FROM agent_tools WHERE agent_id=? AND enabled=1", (agent["id"],)):
        integration = CATALOG.get(binding["tool_id"])
        if integration:
            names.extend(integration["actions"])
    return list(dict.fromkeys(names))

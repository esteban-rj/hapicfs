"""Execute inside the control-plane container; uses an isolated validation project."""
import json
import os
from pathlib import Path
from uuid import uuid4

from backend.service import Service
from backend.storage import Store

directory = "development-validation-" + uuid4().hex[:12]
os.environ["HAPIC_HOST_DATA_DIR"] += "/" + directory
service = Service(Store(Path("/data") / directory))
org = service.create_org("Validación aislada")
project = service.create_project(org["id"], "Entorno")
architect = service.create_agent(project["id"], "Planner de prueba", "architect")
coder = service.create_agent(project["id"], "Coder de prueba", "coder", architect["id"])
service.tool(architect, "publish_architecture_plan", {"content": "Crear una página de diagnóstico local; verificar Python, Node y persistencia. Sin publicar."})
service.tool(coder, "get_architecture_plan", {})
command = "python -m venv .venv && .venv/bin/python -c 'from pathlib import Path; Path(\"persistencia.txt\").write_text(\"ok\"); print(\"Python OK\")' && node -e 'console.log(\"Node OK\")' && npm --version && test ! -e /var/run/docker.sock && test -z \"$OPENAI_API_KEY\" && test ! -w /usr/local/bin"
result = service.tool(coder, "development_run", {"command": command, "timeout": 60})
assert result["exit_code"] == 0, result
persisted = service.tool(coder, "development_run", {"command": "cat persistencia.txt"})
assert persisted["output"] == "ok"
failed = service.tool(coder, "development_run", {"command": "exit 7"})
assert failed["exit_code"] == 7
expired = service.tool(coder, "development_run", {"command": "sleep 10", "timeout": 1})
assert expired["timed_out"]
service.tool(coder, "project_write_file", {"path": "index.html", "content": "<!doctype html><html lang='es'><title>Entorno verificado</title><h1>Hapic: vista previa funcionando</h1></html>"})
preview = service.tool(coder, "development_preview", {"action": "start", "command": "python -m http.server 3000 --bind 0.0.0.0"})
print(json.dumps({"commands": result, "persistence": True, "failure_code": failed["exit_code"], "timeout": expired["timed_out"], "preview": preview, "preview_container": "hapic-preview-" + coder["id"]}, ensure_ascii=False))

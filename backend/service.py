from __future__ import annotations

import json
import os
import hashlib
import re
import shutil
import sqlite3
import threading
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlencode

from .images import IMAGE_TYPES, MAX_IMAGE_BYTES, ImageGenerator, atomic_write, image_type
from .heygen import HeyGen, MAX_VIDEO_BYTES, is_mp4
from .runtime import DockerRuntime, RuntimeUnavailable
from .storage import ROOT, DEFAULT_MODEL, Store, now, uid
from .templates import SPECIALISTS, template as load_template
from .tool_catalog import CATALOG, defaults, effective_tools
from .youtube import YouTube
from .voice import VoiceTranscriber

SAFE_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".css", ".svg", ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".sql", ".toml", ".xml", ".scss", ".vue", ".svelte", ".go", ".rs", ".java", ".kt", ".c", ".h", ".cpp", ".cs", ".sh", ".ps1"}
HIDDEN_NAMES = {"secrets", ".env", "auth.json", "logs", "cache", "installs", ".git", "node_modules", "mcp-tokens"}


def valid_name(value):
    value = value.strip()
    if not 1 <= len(value) <= 80 or any(ord(c) < 32 for c in value) or any(c in value for c in "/\\"):
        raise ValueError("Usa un nombre de 1 a 80 caracteres, sin rutas ni caracteres de control.")
    return value


def safe_path(root: Path, relative: str, *, writing=False, image=False, video=False):
    if not relative or "\\" in relative or ":" in relative:
        raise ValueError("Ruta no permitida.")
    parts = Path(relative).parts
    if any(p in {"..", "."} or p.startswith(".") or p in HIDDEN_NAMES for p in parts):
        raise ValueError("Ruta no permitida.")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink() or (current.exists() and getattr(current, "is_junction", lambda: False)()):
            raise ValueError("No se permite acceder a enlaces ni uniones de carpetas.")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("La ruta está fuera del proyecto autorizado.")
    extensions = {".mp4"} if video else IMAGE_TYPES if image else SAFE_EXTENSIONS
    if path.suffix.lower() not in extensions or path.name.startswith("auth") or path.name in {"config.yaml", "config.yml"}:
        raise ValueError("Este tipo de archivo no admite vista previa ni edición.")
    limit = MAX_VIDEO_BYTES if video else MAX_IMAGE_BYTES if image else 256_000
    if not writing and (not path.is_file() or path.stat().st_size > limit):
        raise ValueError("Archivo inexistente o demasiado grande.")
    return path


def valid_content(content):
    if not isinstance(content, str) or len(content.encode()) > 256_000:
        raise ValueError("El documento supera el máximo de 256 KB.")
    if re.search(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}", content):
        raise ValueError("No guardes credenciales en el workspace. Usa Configuración.")
    return content


class Service:
    def __init__(self, store: Store, runtime=None):
        self.store = store
        self.runtime = runtime or DockerRuntime()
        self.images = ImageGenerator()
        self.voice = VoiceTranscriber()
        self.youtube = YouTube(store, self.project)
        from .youtube_uploads import YouTubeUploads
        self.youtube_uploads = YouTubeUploads(self)
        self.heygen = HeyGen(store, self.project)
        self.locks = {}
        self.locks_guard = threading.Lock()
        from .tasks import Tasks
        self.tasks = Tasks(self)
        from .development import Development
        self.development = Development(self)
        # Existing coders gain the default once; explicit disabled bindings survive restarts.
        self.store.execute("INSERT OR IGNORE INTO agent_tools(agent_id,tool_id,connection_id,enabled) SELECT id,'development',NULL,1 FROM agents WHERE kind='coder'")
        self.store.execute("INSERT OR IGNORE INTO agent_tools(agent_id,tool_id,connection_id,enabled) SELECT id,'heygen',NULL,1 FROM agents WHERE kind='community-manager'")

    def lock(self, agent_id):
        with self.locks_guard:
            return self.locks.setdefault(agent_id, threading.Lock())

    def execution(self, agent_id):
        agent = self.agent(agent_id)
        tasks = self.store.all("SELECT t.*,a.name AS agent_name FROM tasks t JOIN agents a ON a.id=t.agent_id WHERE t.project_id=? ORDER BY t.rowid", (agent["project_id"],))
        if agent["kind"] != "hapic":
            tasks = [task for task in tasks if task["agent_id"] == agent_id]
        for task in tasks:
            task["objective"] = json.loads(task["contract"])["objective"]
            task["executing"] = task["state"] == "running" and self.lock(task["agent_id"]).locked()
            event = self.store.one("SELECT message,created_at FROM events WHERE agent_id=? AND created_at>=? ORDER BY id DESC LIMIT 1", (task["agent_id"], task["updated_at"]))
            task["latest_activity"] = event["message"] if event else None
            task["activity_at"] = event["created_at"] if event else None
            task.pop("contract")
        run = self.store.one("SELECT * FROM chat_runs WHERE agent_id=? ORDER BY rowid DESC LIMIT 1", (agent_id,))
        busy = self.lock(agent_id).locked()
        return {"busy": busy, "provisioning": agent["status"] == "provisioning", "run": run,
                "tasks": tasks, "active_tasks": sum(task["executing"] for task in tasks),
                "queued_tasks": sum(task["state"] == "queued" for task in tasks), "task_timeout_seconds": 600, "max_concurrent_tasks": 2}

    def voice_status(self, agent_id):
        agent = self.agent(agent_id)
        execution = self.execution(agent_id)
        parts = [f"Estado de {agent['name']}."]
        if execution["provisioning"]:
            parts.append("Se está preparando su runtime.")
        elif execution["busy"]:
            parts.append("Está trabajando en un turno o una tarea.")
            run = execution["run"]
            if run and run["state"] == "running" and not any(task["executing"] and task["agent_id"] == agent_id for task in execution["tasks"]):
                turn = self.store.setting("input-" + run["request_id"])
                if turn and turn.get("agent_id") == agent_id:
                    parts.append(f"Mensaje en curso: {turn['content'][:300]}.")
        else:
            parts.append("No tiene un turno en ejecución.")
        scope = "El equipo" if agent["kind"] == "hapic" else "El agente"
        parts.append(f"{scope} tiene {execution['active_tasks']} tareas en ejecución confirmada y {execution['queued_tasks']} en cola.")
        unconfirmed = [task for task in execution["tasks"] if task["state"] == "running" and not task["executing"]]
        if unconfirmed:
            parts.append(f"Hay {len(unconfirmed)} tareas con ejecución sin confirmar; requieren revisión.")
        active = [task for task in execution["tasks"] if task["executing"] or task["state"] == "queued"]
        for task in active[:3]:
            label = "En ejecución" if task["executing"] else "En cola"
            parts.append(f"{label}, {task['agent_name']}: {task['objective'][:300]}.")
            if task["executing"] and task["latest_activity"]:
                parts.append(f"Última actividad registrada: {task['latest_activity'][:200]}.")
        if execution["run"] and not execution["busy"]:
            state = execution["run"]["state"]
            if state == "interrupted":
                parts.append("El último turno se interrumpió. Revisa sus avances antes de repetirlo.")
            elif state == "failed":
                parts.append("El último turno terminó con un error. Revisa la actividad.")
            elif state == "running":
                parts.append("El último turno figura en curso, pero su ejecución no está confirmada; requiere revisión.")
        if not active and execution["tasks"]:
            latest = max(execution["tasks"], key=lambda task: task["updated_at"])
            labels = {"delivered": "Entregada, pendiente de validación", "failed": "Fallida", "blocked": "Bloqueada", "planned": "Asignada"}
            if latest["state"] in labels:
                parts.append(f"Última tarea: {latest['objective'][:300]}. {labels[latest['state']]}.")
        runtime = self.runtime.inspect(agent, self.store)
        if runtime.get("ready"):
            parts.append("Su runtime está disponible para conversar.")
        else:
            labels = {"pending": "pendiente de iniciar", "provisioning": "en preparación", "starting": "iniciando", "stopped": "detenido", "blocked": "pendiente de configuración", "error": "con error"}
            parts.append(f"Su runtime está {labels.get(runtime.get('status'), 'sin conexión comprobada')}.")
        return {"agent_id": agent_id, "content": " ".join(parts), "checked_at": now()}

    def project(self, project_id, user="local-owner"):
        result = self.store.one("SELECT p.* FROM projects p JOIN memberships m ON m.organization_id=p.organization_id WHERE p.id=? AND m.user_id=?", (project_id, user))
        if not result:
            raise LookupError("Proyecto no encontrado o sin permiso.")
        return result

    def agent(self, agent_id):
        result = self.store.one("SELECT * FROM agents WHERE id=?", (agent_id,))
        if not result:
            raise LookupError("Agente no encontrado.")
        self.project(result["project_id"])
        return result

    def create_org(self, name):
        org = {"id": uid("org"), "name": valid_name(name), "created_at": now()}
        with self.store.db() as db:
            db.execute("INSERT INTO organizations VALUES (:id,:name,:created_at)", org)
            db.execute("INSERT INTO memberships VALUES ('local-owner',?,'owner')", (org["id"],))
        path = self.store.root / "organizations" / org["id"]
        (path / "projects").mkdir(parents=True)
        (path / "organization.json").write_text(json.dumps(org, ensure_ascii=False, indent=2), encoding="utf-8")
        return org

    def create_project(self, org_id, name):
        if not self.store.one("SELECT 1 FROM memberships WHERE organization_id=? AND user_id='local-owner'", (org_id,)):
            raise LookupError("Organización no encontrada o sin permiso.")
        project = {"id": uid("prj"), "organization_id": org_id, "name": valid_name(name), "created_at": now()}
        self.store.execute("INSERT INTO projects VALUES (:id,:organization_id,:name,:created_at)", project)
        path = self.store.project_path(project)
        (path / "workspace").mkdir(parents=True)
        (path / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        self.create_agent(project["id"], "Hapic", "hapic")
        return project

    def create_agent(self, project_id, name, kind="ux", planner_id=None):
        project = self.project(project_id)
        name = valid_name(name)
        if kind != "hapic" and kind not in SPECIALISTS:
            raise ValueError("Plantilla no válida.")
        if kind == "coder":
            if not planner_id:
                raise ValueError("Selecciona un arquitecto/planner del mismo proyecto.")
            planner = self.agent(planner_id)
            if planner["project_id"] != project_id or planner["kind"] != "architect":
                raise ValueError("Selecciona un arquitecto/planner del mismo proyecto.")
        elif planner_id:
            raise ValueError("Solo un coder puede vincularse a un arquitecto.")
        settings = self.store.setting("model", {"model": DEFAULT_MODEL, "effort": "xhigh"})
        agent = {"id": uid("agt"), "organization_id": project["organization_id"], "project_id": project_id, "name": name, "kind": kind, "template": load_template(kind)["id"] if kind != "hapic" else "hapic-v1", **settings, "status": "pending", "container_id": None, "error": None, "created_at": now(), "planner_id": planner_id}
        try:
            self.store.execute("INSERT INTO agents(id,organization_id,project_id,name,kind,template,model,effort,status,container_id,error,created_at,planner_id) VALUES (:id,:organization_id,:project_id,:name,:kind,:template,:model,:effort,:status,:container_id,:error,:created_at,:planner_id)", agent)
        except sqlite3.IntegrityError:
            raise ValueError("Ya existe un agente con ese nombre en el proyecto.") from None
        for tool_id in defaults(kind):
            connections = self.integration(tool_id).connections(project_id) if CATALOG[tool_id]["requires_connection"] else []
            selected = [c for c in connections if c["status"] == "connected"]
            connection_id = selected[0]["id"] if len(selected) == 1 else None
            self.store.execute("INSERT INTO agent_tools VALUES (?,?,?,1)", (agent["id"], tool_id, connection_id))
        home = self.store.agent_path(agent) / "hermes"
        home.mkdir(parents=True)
        template = ROOT / "templates" / kind
        soul = (template / "SOUL.md").read_text(encoding="utf-8")
        if kind == "ux":
            shutil.copytree(template / "skills", home / "skills")
            soul += "\n\n## Método de trabajo incluido\n" + (template / "skills/ux-method/SKILL.md").read_text(encoding="utf-8")
        (home / "SOUL.md").write_text(f"Tu nombre es {name}.\n\n" + soul, encoding="utf-8")
        # Fresh memory only: never copy state.db, USER.md or credentials from another profile.
        (home / "memories").mkdir()
        (home / "memories/MEMORY.md").write_text("# Memoria del agente\n\nSin recuerdos todavía.\n", encoding="utf-8")
        (home / "memories/USER.md").write_text("# Contexto compartido\n\nPendiente de conocer al usuario.\n", encoding="utf-8")
        self.runtime.prepare(agent, self.store)
        self.store.event(agent["id"], "Perfil persistente creado desde una plantilla limpia. Contenedor pendiente de iniciar.")
        return agent

    def provision(self, agent_id, *, lock_acquired=False, renew_session=False):
        if not lock_acquired and not self.lock(agent_id).acquire(blocking=False):
            return self.agent(agent_id)
        try:
            agent = self.agent(agent_id)
            if renew_session:
                epoch_key = "runtime-epoch-" + agent_id
                self.store.set_setting(epoch_key, (self.store.setting(epoch_key) or 0) + 1)
                self.store.event(agent_id, "Hapic solicitó recuperar el runtime y renovar su sesión, conservando archivos y vista previa.")
            self.store.execute("UPDATE agents SET status='provisioning',error=NULL WHERE id=?", (agent_id,))
            self.store.event(agent_id, "Comenzando provisión Docker.")
            try:
                result = self.runtime.start(agent, self.store)
                self.store.execute("UPDATE agents SET status=?,container_id=?,error=NULL WHERE id=?", (result["status"], result["container_id"], agent_id))
                self.store.event(agent_id, "API Hermes comprobada. Runtime disponible.")
            except RuntimeUnavailable as exc:
                self.store.execute("UPDATE agents SET status='blocked',error=? WHERE id=?", (str(exc), agent_id))
                self.store.event(agent_id, str(exc))
            except Exception:
                # Provider/Docker exceptions can contain credentials. Never persist their raw text.
                self.store.execute("UPDATE agents SET status='error',error=? WHERE id=?", ("La provisión falló. Comprueba la imagen, los volúmenes y los logs locales de Docker.", agent_id))
                self.store.event(agent_id, "La provisión Docker falló; no se ha marcado el agente como disponible.")
            return self.agent(agent_id)
        finally:
            self.lock(agent_id).release()

    def scope(self, token):
        if not token:
            raise PermissionError("Falta autorización MCP.")
        import secrets
        for agent in self.store.all("SELECT * FROM agents"):
            if secrets.compare_digest(self.store.token(agent["id"], "mcp"), token):
                self.project(agent["project_id"])
                return agent
        raise PermissionError("Autorización MCP inválida.")

    def project_tools(self, project_id):
        self.project(project_id)
        return {"connections": self.youtube.connections(project_id) + self.heygen.connections(project_id),
                "assignments": self.store.all("SELECT t.* FROM agent_tools t JOIN agents a ON a.id=t.agent_id WHERE a.project_id=?", (project_id,))}

    def integration(self, provider):
        if provider == "youtube":
            return self.youtube
        if provider == "heygen":
            return self.heygen
        raise ValueError("Proveedor no disponible.")

    def disconnect(self, project_id, connection_id):
        self.project(project_id)
        connection = self.store.one("SELECT provider FROM connections WHERE id=? AND project_id=?", (connection_id, project_id))
        if not connection:
            raise LookupError("Conexión no encontrada en este proyecto.")
        return self.integration(connection["provider"]).disconnect(project_id, connection_id)

    def assign_tool(self, agent_id, tool_id, enabled, connection_id=None):
        agent = self.agent(agent_id)
        if tool_id not in CATALOG:
            raise ValueError("Selecciona una herramienta disponible en el catálogo.")
        if connection_id and not CATALOG[tool_id]["requires_connection"]:
            raise ValueError("Esta herramienta no requiere una conexión externa.")
        if connection_id:
            connection = self.integration(CATALOG[tool_id]["provider"]).connection(agent["project_id"], connection_id, active=False)
            if connection["provider"] != CATALOG[tool_id]["provider"] or connection["status"] == "disconnected":
                raise ValueError("Selecciona una conexión disponible para esta herramienta.")
        if not self.lock(agent_id).acquire(blocking=False):
            raise RuntimeUnavailable("Espera a que termine el turno o la provisión antes de cambiar herramientas.")
        try:
            previous = self.store.one("SELECT * FROM agent_tools WHERE agent_id=? AND tool_id=?", (agent_id, tool_id))
            self.store.execute("INSERT INTO agent_tools VALUES (?,?,?,?) ON CONFLICT(agent_id,tool_id) DO UPDATE SET connection_id=excluded.connection_id,enabled=excluded.enabled", (agent_id, tool_id, connection_id, int(enabled)))
            try:
                self.runtime.prepare(agent, self.store)
            except Exception:
                if previous:
                    self.store.execute("UPDATE agent_tools SET connection_id=?,enabled=? WHERE agent_id=? AND tool_id=?", (previous["connection_id"], previous["enabled"], agent_id, tool_id))
                else:
                    self.store.execute("DELETE FROM agent_tools WHERE agent_id=? AND tool_id=?", (agent_id, tool_id))
                raise RuntimeUnavailable("No se pudo preparar el perfil con estas herramientas. Se conservó la asignación anterior.") from None
            self.store.event(agent_id, f"Herramienta {CATALOG[tool_id]['name']} {'habilitada' if enabled else 'deshabilitada'} por el operador.")
            if tool_id == "development" and not enabled:
                self.development.preview(agent, "stop")
            return {"tool_id": tool_id, "enabled": enabled, "connection_id": connection_id, "runtime_restart_required": bool(agent["container_id"])}
        finally:
            self.lock(agent_id).release()

    def set_public_game(self, caller, agent_id, user_approved=False):
        caller = self.agent(caller["id"])
        if caller["kind"] != "hapic":
            raise PermissionError("Solo Hapic puede elegir el juego público.")
        if user_approved is not True:
            raise ValueError("El usuario debe pedir qué juego queda en línea.")
        target = self.agent(agent_id)
        if target["project_id"] != caller["project_id"] or target["kind"] != "coder":
            raise PermissionError("Elige un coder de este proyecto.")
        if self.development.preview(target, "status").get("status") != "running":
            raise ValueError("Ese juego no tiene una vista previa en marcha. No se cerró el enlace actual.")
        closed = []
        for other in self.store.all("SELECT * FROM agents WHERE project_id=? AND kind='coder' AND id!=?", (caller["project_id"], target["id"])):
            current = self.development.share(other, "status")
            if current.get("status") not in {None, "stopped"} or current.get("url"):
                self.development.share(other, "stop")
                closed.append(other["name"])
        opened = self.development.share(target, "start", True)
        self.store.set_setting("public-game-" + caller["project_id"], target["id"])
        return {"agent_id": target["id"], "name": target["name"], "closed": closed, "url": opened.get("url"),
                "http_status": opened.get("http_status"), "status": opened.get("status")}

    def tool(self, agent, name, args):
        agent = self.agent(agent["id"])
        project = self.project(agent["project_id"])
        if name not in effective_tools(agent, self.store):
            raise PermissionError("Herramienta fuera del alcance autorizado.")
        if name in CATALOG["development"]["actions"]:
            with self.lock("development-" + agent["id"]), self.lock("plan-" + agent["planner_id"]) if agent["kind"] == "coder" else nullcontext():
                # Commands can write code too, so enforce the same architecture contract.
                if agent["kind"] == "coder" and (name == "development_run" or args.get("action") == "start"):
                    if self.store.setting("plan-read-" + agent["id"]) != self.architecture_plan(agent)["revision"]:
                        raise ValueError("Lee el plan vigente con get_architecture_plan antes de ejecutar código.")
                if name == "development_run":
                    result = self.development.run(agent, args["command"], args.get("timeout", 60))
                elif name == "development_share":
                    result = self.development.share(agent, args.get("action", "status"), args.get("user_approved", False))
                else:
                    result = self.development.preview(agent, args.get("action", "status"), args.get("command", ""))
                return {**result, "owner_agent_id": agent["id"], "scope": "agent_workspace_only",
                        "preview_namespace": "hapic-preview-" + agent["id"],
                        "isolation": "El servidor valida propietario e instalación antes de iniciar, reemplazar o detener. No puede operar vistas previas de otros agentes."}
        if name in CATALOG["youtube"]["actions"]:
            binding = self.store.one("SELECT * FROM agent_tools WHERE agent_id=? AND tool_id='youtube' AND enabled=1", (agent["id"],))
            if not binding or not binding["connection_id"]:
                raise ValueError("YouTube está pendiente de conexión. Selecciona un canal en Herramientas para este agente.")
            if name == "youtube_upload_video":
                if args.get("user_approved") is not True:
                    raise PermissionError("La subida requiere autorización explícita del usuario y su visibilidad elegida.")
                return self.youtube_uploads.upload(agent, binding["connection_id"], **args)
            if name == "youtube_get_upload":
                return self.youtube_uploads.get(agent, binding["connection_id"], args["upload_id"])
            result = self.youtube.run(project["id"], binding["connection_id"], name, args)
            self.store.event(agent["id"], f"YouTube: consulta {name} completada en el canal autorizado.")
            return result
        if name in CATALOG["heygen"]["actions"]:
            binding = self.store.one("SELECT * FROM agent_tools WHERE agent_id=? AND tool_id='heygen' AND enabled=1", (agent["id"],))
            if not binding or not binding["connection_id"]:
                raise ValueError("HeyGen está pendiente de conexión. Selecciona una cuenta en Herramientas para este agente.")
            connection_id = binding["connection_id"]
            connection = self.heygen.connection(project["id"], connection_id)
            if name == "heygen_generate_video":
                valid_content(args.get("prompt", ""))
                result = self.heygen.generate(agent, connection_id, args)
                self.store.event(agent["id"], "HeyGen: solicitud de vídeo registrada con id " + result["id"])
                return result
            if name == "heygen_get_video":
                return self.heygen.get(project["id"], args["video_id"], agent["id"], connection_id)
            return {**self.heygen.list_jobs(project["id"], agent["id"], connection_id),
                    "connection": {key: connection[key] for key in ("id", "provider", "account_name", "status")},
                    "message": "La cuenta está asignada y su configuración está conectada. Una lista vacía solo significa que este agente todavía no tiene vídeos; no implica que falte conectar la cuenta."}
        if name == "get_ux_template" and agent["kind"] == "hapic":
            return load_template("ux")
        if name == "list_agent_templates":
            return {"templates": [load_template(kind) for kind in SPECIALISTS]}
        if name == "set_public_game":
            return self.set_public_game(agent, args.get("agent_id"), args.get("user_approved", False))
        if name == "restart_specialist_agent":
            if agent["kind"] != "hapic":
                raise PermissionError("Solo Hapic puede recuperar especialistas.")
            target = self.agent(args["agent_id"])
            if target["project_id"] != project["id"] or target["kind"] == "hapic":
                raise PermissionError("Selecciona un especialista del mismo proyecto.")
            if not self.lock(target["id"]).acquire(blocking=False):
                raise RuntimeUnavailable("El especialista tiene un turno o provisión activo. No se ha interrumpido.")
            result = self.provision(target["id"], lock_acquired=True, renew_session=True)
            return {"id": result["id"], "name": result["name"], "status": result["status"],
                    "restarted": result["status"] == "running", "error": result["error"]}
        if name == "list_project_agents":
            agents = self.store.all("SELECT id,name,kind,planner_id,status FROM agents WHERE project_id=?", (project["id"],))
            for item in agents:
                item["tools"] = self.store.all("""SELECT b.tool_id,b.enabled,b.connection_id,c.status AS connection_status
                    FROM agent_tools b LEFT JOIN connections c ON c.id=b.connection_id AND c.project_id=?
                    WHERE b.agent_id=?""", (project["id"], item["id"]))
            return {"agents": agents}
        if name in {"create_ux_agent", "create_specialist_agent"} and agent["kind"] == "hapic":
            kind = "ux" if name == "create_ux_agent" else args["template"]
            if kind not in SPECIALISTS:
                raise ValueError("Plantilla no válida.")
            existing = self.store.one("SELECT * FROM agents WHERE project_id=? AND name=?", (project["id"], valid_name(args["name"])))
            if existing:
                if existing["kind"] != kind or (kind == "coder" and existing["planner_id"] != args.get("planner_id")):
                    raise ValueError("Ese nombre ya pertenece a otro perfil. Elige un nombre diferente.")
                return {"id": existing["id"], "name": existing["name"], "status": existing["status"], "already_exists": True}
            created = self.create_agent(project["id"], args["name"], kind, args.get("planner_id"))
            # Queueing is explicit; the agent never claims readiness from a successful enqueue.
            threading.Thread(target=self.provision, args=(created["id"],), daemon=True).start()
            return {"id": created["id"], "name": created["name"], "status": "pending", "message": "Perfil creado. Provisión en cola; consulta el estado real en la plataforma."}
        if name == "generate_project_image":
            prompt = args["prompt"]
            valid_content(prompt)
            data = self.images.generate(self.store.api_key(), prompt, args.get("size", "1024x1024"))
            image_id = uid("img")
            relative = f"images/{image_id}.png"
            path = safe_path(self.store.agent_path(agent) / "workspace", relative, writing=True, image=True)
            atomic_write(path, data)
            # The image is on disk before any success message or tool result is emitted.
            project_relative = path.relative_to(self.store.project_path(project)).as_posix()
            with self.store.db() as db:
                message_id = db.execute("INSERT INTO messages(agent_id,role,content,source,created_at) VALUES (?,?,?,?,?)", (agent["id"], "assistant", f"Imagen guardada en {relative}", "artifact", now())).lastrowid
                db.execute("INSERT INTO images VALUES (?,?,?,?,?,?)", (image_id, agent["id"], message_id, project_relative, "image/png", now()))
            self.store.event(agent["id"], f"Imagen guardada en el workspace: {relative}")
            return {"id": image_id, "path": relative, "saved": True, "bytes": len(data), "message": "La imagen ya está guardada y adjunta al chat. No repitas la generación."}
        if name == "publish_architecture_plan":
            content = valid_content(args["content"])
            if not content.strip():
                raise ValueError("El plan no puede estar vacío.")
            path = safe_path(self.store.project_path(project) / "workspace", f"plans/{agent['id']}/plan.md", writing=True)
            with self.lock("plan-" + agent["id"]):
                atomic_write(path, content.encode("utf-8"))
            self.store.event(agent["id"], "Plan publicado para los coders vinculados del proyecto.")
            return {"saved": True, "path": path.relative_to(self.store.project_path(project)).as_posix(), "revision": hashlib.sha256(content.encode()).hexdigest()}
        if name == "get_architecture_plan":
            plan = self.architecture_plan(agent)
            self.store.set_setting("plan-read-" + agent["id"], plan["revision"])
            return plan
        root = self.store.agent_path(agent) / "workspace"
        if name == "project_list_files":
            files = []
            for directory, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [name for name in dirs if not name.startswith('.') and name not in HIDDEN_NAMES and name != '__pycache__'
                           and not (Path(directory) / name).is_symlink() and not getattr(Path(directory) / name, 'is_junction', lambda: False)()]
                for filename in names:
                    p = Path(directory) / filename
                    try:
                        safe_path(root, p.relative_to(root).as_posix(), image=p.suffix.lower() in IMAGE_TYPES, video=p.suffix.lower() == ".mp4")
                        files.append(p.relative_to(root).as_posix())
                    except ValueError:
                        continue
                    if len(files) >= 300:
                        return {"files": files, "truncated": True}
            return {"files": files}
        if name == "project_read_file":
            candidate = safe_path(root, args["path"], writing=True)
            if not candidate.exists():
                return {"path": args["path"], "exists": False, "message": "El archivo no existe. Consulta project_list_files y conserva los avances; no repitas lecturas de rutas inventadas."}
        path = safe_path(root, args["path"], writing=name == "project_write_file")
        if name == "project_read_file":
            return {"path": args["path"], "content": path.read_text(encoding="utf-8")}
        content = valid_content(args["content"])
        with self.lock("plan-" + agent["planner_id"]) if agent["kind"] == "coder" else nullcontext():
            if agent["kind"] == "coder" and self.store.setting("plan-read-" + agent["id"]) != self.architecture_plan(agent)["revision"]:
                raise ValueError("Lee el plan vigente con get_architecture_plan antes de escribir código.")
            atomic_write(path, content.encode("utf-8"))
            if "development_run" in effective_tools(agent, self.store):
                self.development.own_file(agent, path)
        self.store.event(agent["id"], f"Archivo guardado en el workspace: {args['path']}")
        return {"path": args["path"], "bytes": path.stat().st_size, "saved": True}

    def architecture_plan(self, agent):
        planner = self.agent(agent.get("planner_id"))
        if planner["kind"] != "architect" or planner["project_id"] != agent["project_id"]:
            raise PermissionError("El arquitecto está fuera del proyecto autorizado.")
        root = self.store.project_path(self.project(agent["project_id"]))
        try:
            path = safe_path(root / "workspace", f"plans/{planner['id']}/plan.md")
        except ValueError:
            raise ValueError("El arquitecto todavía no ha publicado un plan. Pídele que lo publique antes de implementar.") from None
        content = path.read_text(encoding="utf-8")
        return {"planner_id": planner["id"], "planner_name": planner["name"], "path": path.relative_to(root).as_posix(), "content": content, "revision": hashlib.sha256(content.encode()).hexdigest()}

    def image_file(self, project_id, relative):
        project = self.project(project_id)
        parts = Path(relative).parts
        # Only workspaces are publishable. Hermes profiles/caches stay private.
        if parts[:1] == ("agents",) and len(parts) >= 4 and parts[2] == "workspace":
            owner = self.agent(parts[1])
            if owner["project_id"] != project_id:
                raise ValueError("La imagen está fuera del proyecto.")
        elif parts[:1] != ("workspace",):
            raise ValueError("Solo se permiten imágenes del workspace.")
        path = safe_path(self.store.project_path(project), relative, image=True)
        with path.open("rb") as file:
            mime = image_type(file.read(16))
        if mime != IMAGE_TYPES[path.suffix.lower()]:
            raise ValueError("El contenido no coincide con el formato de la imagen.")
        return path, mime

    def messages(self, agent_id):
        agent = self.agent(agent_id)
        messages = self.store.all("SELECT * FROM messages WHERE agent_id=? ORDER BY id", (agent_id,))
        images = self.store.all("SELECT * FROM images WHERE agent_id=? ORDER BY created_at", (agent_id,))
        by_message = {}
        for item in images:
            by_message.setdefault(item["message_id"], []).append({**item, "name": Path(item["path"]).name, "url": f"/api/projects/{agent['project_id']}/image?" + urlencode({"path": item["path"]})})
        videos = self.store.all("SELECT * FROM video_jobs WHERE agent_id=? AND path IS NOT NULL ORDER BY created_at", (agent_id,))
        for item in videos:
            by_message.setdefault(item["message_id"], []).append({"id": item["id"], "path": item["path"], "name": Path(item["path"]).name, "mime_type": "video/mp4", "url": f"/api/projects/{agent['project_id']}/video?" + urlencode({"path": item["path"]})})
        from .artifacts import describe
        receipts = self.store.all("SELECT n.message_id,t.agent_id,t.result FROM task_notifications n JOIN tasks t ON n.task_id=t.id WHERE n.state='delivered' AND t.project_id=?", (agent['project_id'],))
        for receipt in receipts:
            owner = self.agent(receipt['agent_id'])
            result = json.loads(receipt['result'] or '{}')
            ids = [receipt['message_id']] if agent['kind'] == 'hapic' else [m['id'] for m in messages if m['source'] == 'task' and m['content'] == result.get('answer') and owner['id'] == agent_id]
            for evidence in result.get('evidence', []):
                relative = f"agents/{owner['id']}/workspace/{evidence['path']}"
                try:
                    artifact = describe(self, agent['project_id'], relative, owner)
                except (ValueError, LookupError, OSError):
                    continue
                for message_id in ids:
                    items = by_message.setdefault(message_id, [])
                    if not any(item['path'] == relative for item in items):
                        items.append(artifact)
        return [{**message, "attachments": by_message.get(message["id"], [])} for message in messages]

    def video_file(self, project_id, relative):
        project = self.project(project_id)
        # Serve only a persisted video registered in this project, never arbitrary files.
        if not self.store.one("SELECT id FROM video_jobs WHERE project_id=? AND path=?", (project_id, relative)):
            raise LookupError("Vídeo no encontrado en este proyecto.")
        path = safe_path(self.store.project_path(project), relative, video=True)
        with path.open("rb") as file:
            if not is_mp4(file.read(16)):
                raise ValueError("El archivo no contiene un vídeo MP4 válido.")
        return path, "video/mp4"

    def upload_image(self, agent_id, data):
        agent = self.agent(agent_id)
        if not data or len(data) > 8 * 1024 * 1024:
            raise ValueError("Cada imagen debe pesar como máximo 8 MB.")
        mime = image_type(data)
        if mime == "image/gif":
            raise ValueError("Usa una imagen PNG, JPEG o WebP.")
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[mime]
        image_id = uid("upload")
        relative = f"uploads/{image_id}{suffix}"
        path = safe_path(self.store.agent_path(agent) / "workspace", relative, writing=True, image=True)
        atomic_write(path, data)
        project_relative = f"agents/{agent_id}/workspace/{relative}"
        self.store.execute("INSERT INTO images VALUES (?,?,?,?,?,?)", (image_id, agent_id, None, project_relative, mime, now()))
        return {"id": image_id, "path": project_relative, "mime_type": mime,
                "name": path.name, "url": f"/api/projects/{agent['project_id']}/image?" + urlencode({"path": project_relative})}

    def chat_images(self, agent_id, ids, message_id=None):
        agent = self.agent(agent_id)
        if len(ids) > 3 or len(set(ids)) != len(ids):
            raise ValueError("Adjunta como máximo tres imágenes distintas.")
        rows = []
        for image_id in ids:
            row = self.store.one("SELECT * FROM images WHERE id=? AND agent_id=?", (image_id, agent_id))
            if not row or not image_id.startswith("upload_") or (row["message_id"] is not None and row["message_id"] != message_id):
                raise ValueError("Imagen no disponible para este mensaje o agente.")
            self.image_file(agent["project_id"], row["path"])
            rows.append(row)
        return rows

    def tree(self, project_id):
        project = self.project(project_id)
        root = self.store.project_path(project)
        count = 0
        technical_count = 0

        def visit(path, depth=0):
            nonlocal count, technical_count
            relative = path.relative_to(root).as_posix()
            parts = Path(relative).parts
            technical = len(parts) >= 3 and parts[0] == 'agents' and parts[2] == 'hermes'
            if technical:
                technical_count += 1
            else:
                count += 1
            node = {"name": path.name, "path": relative, "type": "directory" if path.is_dir() else "file"}
            if path.is_dir() and depth < 8 and (technical_count < 150 if technical else count < 600):
                node["children"] = [visit(p, depth + 1) for p in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name)) if not p.is_symlink() and not getattr(p, "is_junction", lambda: False)() and not p.name.startswith(".") and p.name not in HIDDEN_NAMES and not p.name.startswith("auth")][:150]
            elif path.is_file():
                node["size"] = path.stat().st_size
                is_image = path.suffix.lower() in IMAGE_TYPES
                is_video = path.suffix.lower() == ".mp4"
                node["media_type"] = "video" if is_video else "image" if is_image else "text"
                node["preview"] = path.suffix.lower() in SAFE_EXTENSIONS and node["size"] <= 256_000 and path.name not in {"config.yaml", "config.yml"}
                if is_image:
                    try:
                        self.image_file(project_id, relative)
                        node["preview"] = True
                    except (ValueError, LookupError):
                        node["preview"] = False
                if is_video:
                    try:
                        self.video_file(project_id, relative)
                        node["preview"] = True
                    except (ValueError, LookupError):
                        node["preview"] = False
            return node
        return visit(root)

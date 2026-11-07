from __future__ import annotations

import json
import hashlib
import re
import shutil
import sqlite3
import threading
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import urlencode

from .images import IMAGE_TYPES, MAX_IMAGE_BYTES, ImageGenerator, atomic_write, image_type
from .runtime import DockerRuntime, RuntimeUnavailable
from .storage import ROOT, DEFAULT_MODEL, Store, now, uid
from .templates import SPECIALISTS, template as load_template
from .tool_catalog import CATALOG, defaults, effective_tools
from .youtube import YouTube

SAFE_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".css", ".svg", ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".sql", ".toml", ".xml", ".scss", ".vue", ".svelte", ".go", ".rs", ".java", ".kt", ".c", ".h", ".cpp", ".cs", ".sh", ".ps1"}
HIDDEN_NAMES = {"secrets", ".env", "auth.json", "logs", "cache", "installs", ".git", "node_modules", "mcp-tokens"}


def valid_name(value):
    value = value.strip()
    if not 1 <= len(value) <= 80 or any(ord(c) < 32 for c in value) or any(c in value for c in "/\\"):
        raise ValueError("Usa un nombre de 1 a 80 caracteres, sin rutas ni caracteres de control.")
    return value


def safe_path(root: Path, relative: str, *, writing=False, image=False):
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
    extensions = IMAGE_TYPES if image else SAFE_EXTENSIONS
    if path.suffix.lower() not in extensions or path.name.startswith("auth") or path.name in {"config.yaml", "config.yml"}:
        raise ValueError("Este tipo de archivo no admite vista previa ni edición.")
    limit = MAX_IMAGE_BYTES if image else 256_000
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
        self.youtube = YouTube(store, self.project)
        self.locks = {}
        self.locks_guard = threading.Lock()

    def lock(self, agent_id):
        with self.locks_guard:
            return self.locks.setdefault(agent_id, threading.Lock())

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
            connections = self.youtube.connections(project_id)
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

    def provision(self, agent_id):
        if not self.lock(agent_id).acquire(blocking=False):
            return self.agent(agent_id)
        try:
            agent = self.agent(agent_id)
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
        return {"connections": self.youtube.connections(project_id),
                "assignments": self.store.all("SELECT t.* FROM agent_tools t JOIN agents a ON a.id=t.agent_id WHERE a.project_id=?", (project_id,))}

    def assign_tool(self, agent_id, tool_id, enabled, connection_id=None):
        agent = self.agent(agent_id)
        if tool_id not in CATALOG:
            raise ValueError("Selecciona una herramienta disponible en el catálogo.")
        if connection_id:
            connection = self.youtube.connection(agent["project_id"], connection_id, active=False)
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
            return {"tool_id": tool_id, "enabled": enabled, "connection_id": connection_id, "runtime_restart_required": bool(agent["container_id"])}
        finally:
            self.lock(agent_id).release()

    def tool(self, agent, name, args):
        agent = self.agent(agent["id"])
        project = self.project(agent["project_id"])
        if name not in effective_tools(agent, self.store):
            raise PermissionError("Herramienta fuera del alcance autorizado.")
        if name in CATALOG["youtube"]["actions"]:
            binding = self.store.one("SELECT * FROM agent_tools WHERE agent_id=? AND tool_id='youtube' AND enabled=1", (agent["id"],))
            if not binding or not binding["connection_id"]:
                raise ValueError("YouTube está pendiente de conexión. Selecciona un canal en Herramientas para este agente.")
            result = self.youtube.run(project["id"], binding["connection_id"], name, args)
            self.store.event(agent["id"], f"YouTube: consulta {name} completada en el canal autorizado.")
            return result
        if name == "get_ux_template" and agent["kind"] == "hapic":
            return load_template("ux")
        if name == "list_agent_templates":
            return {"templates": [load_template(kind) for kind in SPECIALISTS]}
        if name == "list_project_agents":
            return {"agents": self.store.all("SELECT id,name,kind,planner_id,status FROM agents WHERE project_id=?", (project["id"],))}
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
            for p in root.rglob("*"):
                if len(files) >= 300:
                    break
                try:
                    safe_path(root, p.relative_to(root).as_posix(), image=p.suffix.lower() in IMAGE_TYPES)
                    files.append(p.relative_to(root).as_posix())
                except ValueError:
                    continue
            return {"files": files}
        path = safe_path(root, args["path"], writing=name == "project_write_file")
        if name == "project_read_file":
            return {"path": args["path"], "content": path.read_text(encoding="utf-8")}
        content = valid_content(args["content"])
        with self.lock("plan-" + agent["planner_id"]) if agent["kind"] == "coder" else nullcontext():
            if agent["kind"] == "coder" and self.store.setting("plan-read-" + agent["id"]) != self.architecture_plan(agent)["revision"]:
                raise ValueError("Lee el plan vigente con get_architecture_plan antes de escribir código.")
            atomic_write(path, content.encode("utf-8"))
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
        return [{**message, "attachments": by_message.get(message["id"], [])} for message in messages]

    def tree(self, project_id):
        project = self.project(project_id)
        root = self.store.project_path(project)
        count = 0

        def visit(path, depth=0):
            nonlocal count
            count += 1
            relative = path.relative_to(root).as_posix()
            node = {"name": path.name, "path": relative, "type": "directory" if path.is_dir() else "file"}
            if path.is_dir() and depth < 8 and count < 600:
                node["children"] = [visit(p, depth + 1) for p in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name)) if not p.is_symlink() and not getattr(p, "is_junction", lambda: False)() and not p.name.startswith(".") and p.name not in HIDDEN_NAMES and not p.name.startswith("auth")][:150]
            elif path.is_file():
                node["size"] = path.stat().st_size
                is_image = path.suffix.lower() in IMAGE_TYPES
                node["media_type"] = "image" if is_image else "text"
                node["preview"] = path.suffix.lower() in SAFE_EXTENSIONS and node["size"] <= 256_000 and path.name not in {"config.yaml", "config.yml"}
                if is_image:
                    try:
                        self.image_file(project_id, relative)
                        node["preview"] = True
                    except (ValueError, LookupError):
                        node["preview"] = False
            return node
        return visit(root)

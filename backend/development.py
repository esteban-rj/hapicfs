"""Run code in bounded containers with only the agent workspace mounted."""
import os
import threading
import json
import re
import time

import docker
from docker.types import LogConfig
import httpx

from .runtime import DockerRuntime, RuntimeUnavailable


class Development:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.runtime = DockerRuntime()

    def options(self, agent):
        root = self.store.agent_path(agent) / "workspace"
        root.mkdir(parents=True, exist_ok=True)
        if os.name != "nt" and os.geteuid() == 0 and not self.store.setting("development-owner-" + agent["id"]):
            # The control plane creates files as root; the runner stays non-root.
            # Do not follow links into another workspace or a private profile.
            for directory, dirs, files in os.walk(root, followlinks=False):
                from pathlib import Path
                for path in [Path(directory), *(Path(directory) / name for name in dirs + files)]:
                    if not path.is_symlink():
                        os.chown(path, 10000, 10000)
            self.store.set_setting("development-owner-" + agent["id"], True)
        return dict(
            image=os.getenv("HAPIC_RUNNER_IMAGE", "hapic-runner:local"),
            working_dir="/workspace", user="10000:10000", detach=True,
            volumes={self.runtime.host_path(root, self.store): {"bind": "/workspace", "mode": "rw"}},
            environment={"HOME": "/tmp", "NPM_CONFIG_CACHE": "/workspace/.npm-cache", "PIP_CACHE_DIR": "/workspace/.pip-cache"},
            network_mode="bridge", read_only=True, tmpfs={"/tmp": "rw,nosuid,nodev,size=256m"},
            cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            mem_limit="1g", nano_cpus=1_000_000_000, pids_limit=128,
            labels={"hapic.development": agent["id"], "hapic.installation": str(self.store.root)},
            log_config=LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
        )

    def own_file(self, agent, path):
        if os.name != "nt" and os.geteuid() == 0:
            root = self.store.agent_path(agent) / "workspace"
            while path != root and path.is_relative_to(root):
                if path.is_symlink():
                    raise ValueError("No se permiten enlaces en el workspace.")
                os.chown(path, 10000, 10000)
                path = path.parent

    def validate_command(self, command):
        if not isinstance(command, str) or not command.strip() or len(command) > 12000 or "\x00" in command:
            raise ValueError("Indica un comando de entre 1 y 12000 caracteres.")

    def create(self, agent, command, **extra):
        self.validate_command(command)
        try:
            client = self.runtime.client()
            client.images.get(os.getenv("HAPIC_RUNNER_IMAGE", "hapic-runner:local"))
            return client.containers.run(command=["sh", "-lc", command], **self.options(agent), **extra)
        except docker.errors.ImageNotFound:
            raise RuntimeUnavailable("Falta el entorno de desarrollo. Construye runner/Dockerfile como hapic-runner:local.") from None
        except docker.errors.DockerException:
            raise RuntimeUnavailable("No se pudo iniciar el contenedor de desarrollo. Comprueba Docker y el workspace.") from None

    def output(self, container):
        return container.logs(tail=300).decode("utf-8", errors="replace")[-20000:]

    def run(self, agent, command, timeout=60):
        self.validate_command(command)
        if not isinstance(timeout, int) or not 1 <= timeout <= 120:
            raise ValueError("El tiempo máximo debe estar entre 1 y 120 segundos.")
        container = self.create(agent, command)
        expired = threading.Event()

        def terminate():
            expired.set()
            try:
                container.kill()
            except docker.errors.DockerException:
                pass

        timer = threading.Timer(timeout, terminate)
        timer.daemon = True
        timer.start()
        try:
            result = container.wait(timeout=timeout + 15)
            output = self.output(container)
            self.store.event(agent["id"], f"Entorno: comando finalizado, código {result['StatusCode']}, timeout={expired.is_set()}.")
            return {"exit_code": result["StatusCode"], "timed_out": expired.is_set(), "output": output,
                    "output_limit": 20000, "workspace": "/workspace"}
        except Exception:
            raise RuntimeUnavailable("Se perdió la respuesta del comando. Revisa los archivos antes de repetirlo.") from None
        finally:
            timer.cancel()
            container.remove(force=True)

    def preview(self, agent, action, command=""):
        if action not in {"start", "status", "stop"}:
            raise ValueError("Usa start, status o stop.")
        name = "hapic-preview-" + agent["id"]
        client = self.runtime.client()
        try:
            container = client.containers.get(name)
        except docker.errors.NotFound:
            container = None
        if container and (container.labels.get("hapic.development") != agent["id"] or container.labels.get("hapic.installation") != str(self.store.root)):
            raise PermissionError("Ese contenedor no pertenece a este agente e instalación.")
        if action == "stop":
            self.share(agent, "stop")
            if container:
                container.remove(force=True)
            return {"status": "stopped"}
        if action == "start":
            self.validate_command(command)
            self.share(agent, "stop")
            if container:
                container.remove(force=True)
            # Preview processes expire even if the control plane stops. Restart explicitly.
            import shlex
            container = self.create(agent, "exec timeout --signal=KILL 3600 sh -lc " + shlex.quote(command),
                                    name=name, ports={"3000/tcp": ("127.0.0.1", None)})
            self.store.event(agent["id"], "Vista previa local iniciada (máximo una hora).")
        if not container:
            return {"status": "stopped"}
        container.reload()
        ports = container.attrs["NetworkSettings"]["Ports"].get("3000/tcp")
        return {"status": container.status, "url": f"http://127.0.0.1:{ports[0]['HostPort']}" if ports else None,
                "output": self.output(container), "expires_after_seconds": 3600,
                "note": "El proceso debe escuchar en 0.0.0.0:3000. running no garantiza que la página esté lista."}

    @staticmethod
    def tunnel_url(output):
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict) or event.get("type") != "v1.tcpip_forward.register.accepted":
                continue
            match = re.search(r"https://([a-z0-9-]+\.(?:lhr\.life|lhr\.rocks|localhost\.run))(?![a-z0-9.:-])", str(event.get("data", "")))
            if match:
                return match.group(0)
        return None

    def share(self, agent, action="status", user_approved=False):
        if action not in {"start", "status", "stop"}:
            raise ValueError("Usa start, status o stop.")
        if action == "start" and user_approved is not True:
            raise ValueError("Pregunta al usuario si quiere poner el juego en línea antes de abrir el túnel.")
        client = self.runtime.client()
        labels = {"hapic.development": agent["id"], "hapic.installation": str(self.store.root)}

        def owned(name):
            try:
                item = client.containers.get(name)
            except docker.errors.NotFound:
                return None
            if any(item.labels.get(key) != value for key, value in labels.items()):
                raise PermissionError("Ese contenedor no pertenece a este agente e instalación.")
            return item

        setting_key = "development-share-" + agent["id"]
        tunnel = owned("hapic-share-" + agent["id"])
        if action == "stop":
            if tunnel:
                tunnel.remove(force=True)
                self.store.event(agent["id"], "Enlace público cerrado.")
            self.store.set_setting(setting_key, None)
            return {"status": "stopped", "url": None}
        preview = owned("hapic-preview-" + agent["id"])
        if not preview or preview.status != "running":
            if action == "start":
                raise ValueError("Inicia y prueba primero tu vista previa en 0.0.0.0:3000.")
            return {"status": "stopped", "url": None}
        if tunnel and tunnel.labels.get("hapic.preview") != preview.id:
            if action == "status":
                return {"status": "stale", "url": None, "note": "La vista previa cambió. Solicita un nuevo enlace."}
            tunnel.remove(force=True)
            tunnel = None
        if tunnel and tunnel.status != "running" and action == "start":
            tunnel.remove(force=True)
            tunnel = None
        if action == "start" and not tunnel:
            try:
                tunnel = client.containers.run(
                    image=os.getenv("HAPIC_RUNNER_IMAGE", "hapic-runner:local"),
                    command=["timeout", "--signal=KILL", "3600", "ssh", "-T", "-o", "BatchMode=yes",
                             "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/tmp/known_hosts",
                             "-o", "IdentityAgent=none", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
                             "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
                             "-R", "80:127.0.0.1:3000", "nokey@localhost.run", "--", "--output", "json"],
                    name="hapic-share-" + agent["id"], detach=True, user="10000:10000",
                    network_mode="container:" + preview.id, environment={"HOME": "/tmp"},
                    read_only=True, tmpfs={"/tmp": "rw,nosuid,nodev,size=8m"},
                    cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                    mem_limit="96m", nano_cpus=100_000_000, pids_limit=32,
                    labels={**labels, "hapic.preview": preview.id},
                    log_config=LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
                )
            except docker.errors.DockerException:
                raise RuntimeUnavailable("No se pudo iniciar el túnel. Comprueba Docker y reconstruye runner/Dockerfile con SSH habilitado.") from None
            self.store.event(agent["id"], "Túnel HTTPS solicitado para su vista previa; hasta una hora.")
            for _ in range(15):
                tunnel.reload()
                if self.tunnel_url(self.output(tunnel)) or tunnel.status != "running":
                    break
                time.sleep(1)
        if not tunnel:
            return {"status": "stopped", "url": None}
        tunnel.reload()
        url = None
        if tunnel.status == "running":
            saved = self.store.setting(setting_key)
            if isinstance(saved, dict) and saved.get("container_id") == tunnel.id and saved.get("preview_id") == preview.id:
                candidate = saved.get("url")
                if isinstance(candidate, str) and self.tunnel_url(json.dumps({"type": "v1.tcpip_forward.register.accepted", "data": candidate})) == candidate:
                    url = candidate
            url = url or self.tunnel_url(self.output(tunnel))
            if url:
                self.store.set_setting(setting_key, {"container_id": tunnel.id, "preview_id": preview.id, "url": url})
        http_status = None
        if url:
            try:
                response = httpx.get(url, timeout=8, follow_redirects=False, trust_env=False)
                http_status = response.status_code
            except httpx.HTTPError:
                pass
        return {"status": tunnel.status if url else ("starting" if tunnel.status == "running" else "stopped"),
                "url": url, "http_status": http_status, "http_verified": http_status == 200,
                "expires_after_seconds": 3600, "preview_id": preview.id,
                "note": "Enlace temporal del MISMO servidor de la vista previa. Caduca al parar/cambiar la vista previa, el PC o Docker, o como máximo en una hora. El dominio puede cambiar. Verifica QR y dos jugadores usando esta URL; HTTP 200 no prueba el juego. Nunca publiques Hapic ni afirmes haber publicado en redes."}

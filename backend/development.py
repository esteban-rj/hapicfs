"""Run code in bounded containers with only the agent workspace mounted."""
import os
import threading

import docker
from docker.types import LogConfig

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
            if container:
                container.remove(force=True)
            return {"status": "stopped"}
        if action == "start":
            self.validate_command(command)
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

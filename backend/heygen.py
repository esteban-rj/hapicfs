"""HeyGen v3 clips: encrypted project credentials and durable, idempotent jobs."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode, urlsplit

import httpx

from .images import atomic_write
from .runtime import RuntimeUnavailable
from .storage import now, uid

API_URL = "https://api.heygen.com/v3"
MODEL = "heygen-video-1"
MAX_VIDEO_BYTES = 100 * 1024 * 1024
# Reference rates for text/image clips up to 15 seconds, checked 2026-11-07.
RATES = {"480p": Decimal("0.01"), "768p": Decimal("0.018"), "1080p": Decimal("0.04")}
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class ProviderError(RuntimeUnavailable):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class SignedURLLogFilter(logging.Filter):
    """httpx logs its URL at INFO; signed CDN query strings must stay private."""
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(
                value.copy_with(query=b"") if isinstance(value, httpx.URL) and
                (value.host.endswith(".heygen.ai") or value.host.endswith(".heygen.com")) else value
                for value in record.args
            )
        return True


def is_mp4(header):
    # HeyGen also returns MP4 files with the registered ISO BMFF brands iso5/iso6.
    return len(header) >= 12 and header[4:8] == b"ftyp" and bytes(header[8:12]) in {b"isom", b"iso2", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V "}


def public_https_url(value):
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 33 for c in value):
        raise ValueError("Usa una URL HTTPS pública y directa para la imagen.")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443} or not host or parsed.fragment:
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if (address and not address.is_global) or host.lower() in {"localhost", "host.docker.internal"} or "." not in host or host.lower().endswith((".localhost", ".local", ".internal")):
            raise ValueError
    except ValueError:
        raise ValueError("Usa una URL HTTPS pública y directa para la imagen.") from None
    return value


class HeyGen:
    def __init__(self, store, project_access):
        self.store = store
        self.project_access = project_access
        self.transport = None  # Tests inject an HTTP transport, never a production fake.
        self._locks = {}
        self._guard = threading.Lock()
        logger = logging.getLogger("httpx")
        if not any(isinstance(item, SignedURLLogFilter) for item in logger.filters):
            logger.addFilter(SignedURLLogFilter())

    def lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.RLock())

    def _api(self, method, path, key, **kwargs):
        try:
            with httpx.Client(timeout=httpx.Timeout(45, connect=10), follow_redirects=False, trust_env=False, transport=self.transport) as client:
                response = client.request(method, API_URL + path, headers={"X-Api-Key": key, **kwargs.pop("headers", {})}, **kwargs)
        except httpx.HTTPError:
            raise RuntimeUnavailable("No se pudo recibir la respuesta de HeyGen. Consulta el trabajo existente antes de generar otro vídeo.") from None
        if not response.is_success:
            if response.status_code in {401, 403}:
                raise ProviderError(response.status_code, "HeyGen rechazó la API key o sus permisos. Revisa la conexión en Herramientas.")
            if response.status_code == 429:
                raise ProviderError(429, "HeyGen alcanzó su límite de solicitudes. Espera antes de volver a consultar.")
            raise ProviderError(response.status_code, f"HeyGen devolvió HTTP {response.status_code}. Revisa saldo, permisos y límites en su panel.")
        try:
            data = response.json()["data"]
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, KeyError, TypeError):
            raise RuntimeUnavailable("HeyGen devolvió una respuesta no válida. Conserva el identificador del trabajo antes de reintentar.") from None

    def connections(self, project_id):
        self.project_access(project_id)
        rows = self.store.all("SELECT * FROM connections WHERE project_id=? AND provider='heygen' AND status!='disconnected' ORDER BY created_at", (project_id,))
        return [{**row, "scopes": json.loads(row["scopes"])} for row in rows]

    def connection(self, project_id, connection_id, *, active=True):
        self.project_access(project_id)
        connection = self.store.one("SELECT * FROM connections WHERE id=? AND project_id=? AND provider='heygen'", (connection_id, project_id))
        if not connection:
            raise LookupError("Conexión HeyGen no encontrada en este proyecto.")
        if active and connection["status"] != "connected":
            raise RuntimeUnavailable("Vuelve a conectar la API key de HeyGen desde Herramientas.")
        return connection

    def connect(self, project_id, key):
        self.project_access(project_id)
        if not isinstance(key, str) or not 20 <= len(key) <= 512 or any(not 33 <= ord(c) <= 126 for c in key):
            raise ValueError("La API key de HeyGen no tiene un formato válido.")
        # The provider, not a user-entered account name, determines connection identity.
        profile = self._api("GET", "/users/me", key)
        permissions = self._api("GET", "/api_keys/self", key)
        required = {"videos:read", "videos:write"}
        granted = permissions.get("scopes")
        if permissions.get("status") != "active" or not (
            permissions.get("scope_mode") == "full" or
            (permissions.get("scope_mode") == "custom" and isinstance(granted, list) and required.issubset({s for s in granted if isinstance(s, str)}))
        ):
            raise ValueError("La API key debe estar activa y permitir videos:read y videos:write. Revisa sus permisos en HeyGen.")
        identity = profile.get("username") or profile.get("user_id") or profile.get("id") or profile.get("email")
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 320:
            raise RuntimeUnavailable("HeyGen no devolvió una identidad de cuenta válida. No se guardó la clave.")
        account_id = hashlib.sha256(identity.encode()).hexdigest()
        name = str(profile.get("username") or profile.get("first_name") or "Cuenta HeyGen")[:120]
        with self.lock("project-" + project_id):
            self.project_access(project_id)
            existing = self.store.one("SELECT * FROM connections WHERE project_id=? AND provider='heygen' AND account_id=?", (project_id, account_id))
            connection_id = existing["id"] if existing else uid("con")
            with self.lock(connection_id):
                stamp = now()
                self.store.secret(connection_id + "-heygen", key)
                self.store.execute("""INSERT INTO connections VALUES (?,?,'heygen',?,?,?,'connected',?,?)
                    ON CONFLICT(project_id,provider,account_id) DO UPDATE SET account_name=excluded.account_name,
                    scopes=excluded.scopes,status='connected',updated_at=excluded.updated_at""",
                    (connection_id, project_id, account_id, name, json.dumps(["videos:read", "videos:write"]), stamp, stamp))
                # A single account can fill an unassigned Community Manager default.
                if len([c for c in self.connections(project_id) if c["status"] == "connected"]) == 1:
                    self.store.execute("""UPDATE agent_tools SET connection_id=? WHERE tool_id='heygen' AND enabled=1
                        AND connection_id IS NULL AND agent_id IN (SELECT id FROM agents WHERE project_id=? AND kind='community-manager')""", (connection_id, project_id))
        return {"connection_id": connection_id, "account_name": name, "verified": True}

    def disconnect(self, project_id, connection_id):
        with self.lock(connection_id):
            self.connection(project_id, connection_id, active=False)
            with self.store.db() as db:
                db.execute("UPDATE connections SET status='disconnected',updated_at=? WHERE id=?", (now(), connection_id))
                db.execute("UPDATE agent_tools SET connection_id=NULL WHERE connection_id=?", (connection_id,))
            (self.store.secrets_dir / (connection_id + "-heygen.enc")).unlink(missing_ok=True)
        return {"disconnected": True, "message": "Clave eliminada de Hapic. Puedes revocarla también en el panel de HeyGen; los trabajos ya enviados pueden seguir procesándose allí."}

    def _key(self, project_id, connection_id):
        self.connection(project_id, connection_id)
        key = self.store.secret(connection_id + "-heygen")
        if not key:
            raise RuntimeUnavailable("Falta la credencial de HeyGen. Configúrala desde Herramientas.")
        return key

    @staticmethod
    def parameters(args):
        prompt = args.get("prompt")
        duration = args.get("duration", 5)
        resolution = args.get("resolution", "480p")
        ratio = args.get("aspect_ratio", "9:16")
        request_id = args.get("request_id")
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 12_000:
            raise ValueError("Describe el vídeo con un prompt de 1 a 12000 caracteres.")
        if type(duration) is not int or not 5 <= duration <= 15:
            raise ValueError("Selecciona una duración entera de 5 a 15 segundos.")
        if not isinstance(resolution, str) or resolution not in RATES:
            raise ValueError("Resolución disponible: 480p, 768p o 1080p.")
        if not isinstance(ratio, str) or ratio not in {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"} or (resolution == "1080p" and ratio not in {"16:9", "9:16"}):
            raise ValueError("Formato no compatible con la resolución; usa 9:16 o 16:9 para 1080p.")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id):
            raise ValueError("Usa un request_id de 8 a 80 letras, números, guiones o guiones bajos; reutilízalo al reintentar la misma solicitud.")
        payload = {"model": MODEL, "mode": "text_to_video", "prompt": prompt.strip(), "duration": duration,
                   "resolution": resolution, "aspect_ratio": ratio, "prompt_enhancement": "quality"}
        if args.get("image_url") is not None:
            payload.update(mode="image_to_video", image={"type": "url", "url": public_https_url(args["image_url"])})
        return request_id, payload, str(RATES[resolution] * duration)

    def generate(self, agent, connection_id, args):
        request_id, payload, estimate = self.parameters(args)
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        with self.lock(connection_id):
            key = self._key(agent["project_id"], connection_id)
            fingerprint = hashlib.sha256(key.encode()).hexdigest()
            job = self.store.one("SELECT * FROM video_jobs WHERE agent_id=? AND request_id=?", (agent["id"], request_id))
            if job:
                if job["connection_id"] != connection_id or job["payload"] != encoded:
                    raise ValueError("El request_id ya pertenece a otro contenido o cuenta. No se envió otra generación.")
                if job["status"] != "submission_unknown":
                    return self.public(job)
                if job["credential_fingerprint"] != fingerprint:
                    raise ValueError("La clave cambió desde el envío incierto. Comprueba el trabajo en HeyGen antes de crear otra solicitud.")
                if datetime.now(timezone.utc) - datetime.fromisoformat(job["created_at"]) >= timedelta(hours=23):
                    raise ValueError("El resultado del envío es incierto y venció el plazo de reintento seguro. Comprueba HeyGen antes de crear otra solicitud.")
            else:
                stamp = now()
                job_id = uid("vid")
                # SQLite claims the request before any billable network operation.
                with self.store.db() as db:
                    inserted = db.execute("""INSERT OR IGNORE INTO video_jobs
                        (id,project_id,agent_id,connection_id,request_id,payload,status,estimated_cost_usd,created_at,updated_at,credential_fingerprint)
                        VALUES (?,?,?,?,?,?,'submitting',?,?,?,?)""", (job_id, agent["project_id"], agent["id"], connection_id, request_id, encoded, estimate, stamp, stamp, fingerprint)).rowcount
                if not inserted:
                    existing = self.store.one("SELECT * FROM video_jobs WHERE agent_id=? AND request_id=?", (agent["id"], request_id))
                    if existing["payload"] != encoded or existing["connection_id"] != connection_id:
                        raise ValueError("El request_id ya pertenece a otra solicitud.")
                    return self.public(existing)
                job = self.store.one("SELECT * FROM video_jobs WHERE id=?", (job_id,))
            try:
                result = self._api("POST", "/models/videos", key, json=payload, headers={"Idempotency-Key": job["id"]})
                provider_id = result.get("video_id")
                if not isinstance(provider_id, str) or not IDENTIFIER.fullmatch(provider_id):
                    raise RuntimeUnavailable("HeyGen no devolvió un identificador válido. El envío puede haberse facturado; conserva este trabajo.")
                self.store.execute("UPDATE video_jobs SET provider_video_id=?,status='pending',error=NULL,updated_at=? WHERE id=?", (provider_id, now(), job["id"]))
            except RuntimeUnavailable as exc:
                # The same Idempotency-Key can recover an ambiguous POST within 24h.
                rejected = isinstance(exc, ProviderError) and 400 <= exc.status < 500 and exc.status not in {409, 429}
                self.store.execute("UPDATE video_jobs SET status=?,error=?,updated_at=? WHERE id=? AND provider_video_id IS NULL", ("failed" if rejected else "submission_unknown", str(exc), now(), job["id"]))
                if isinstance(exc, ProviderError) and exc.status in {401, 403}:
                    self.store.execute("UPDATE connections SET status='reauthorization_required',updated_at=? WHERE id=?", (now(), connection_id))
            return self.public(self.store.one("SELECT * FROM video_jobs WHERE id=?", (job["id"],)))

    def job(self, project_id, job_id, agent_id=None, connection_id=None):
        self.project_access(project_id)
        job = self.store.one("SELECT * FROM video_jobs WHERE id=? AND project_id=?", (job_id, project_id))
        if not job or (agent_id and job["agent_id"] != agent_id) or (connection_id and job["connection_id"] != connection_id):
            raise LookupError("Vídeo no encontrado en el alcance autorizado.")
        return job

    def list_jobs(self, project_id, agent_id=None, connection_id=None):
        self.project_access(project_id)
        rows = self.store.all("""SELECT * FROM video_jobs WHERE project_id=? AND (? IS NULL OR agent_id=?)
            AND (? IS NULL OR connection_id=?) ORDER BY created_at DESC LIMIT 50""", (project_id, agent_id, agent_id, connection_id, connection_id))
        return {"videos": [self.public(row) for row in rows]}

    def get(self, project_id, job_id, agent_id=None, connection_id=None):
        job = self.job(project_id, job_id, agent_id, connection_id)
        with self.lock(job["connection_id"]):
            job = self.job(project_id, job_id, agent_id, connection_id)
            if job["path"] or job["status"] in {"failed", "cancelled"}:
                return self.public(job)
            key = self._key(project_id, job["connection_id"])
            if not job["provider_video_id"]:
                return self.public(job)
            try:
                data = self._api("GET", "/models/videos/" + job["provider_video_id"], key)
            except ProviderError as exc:
                if exc.status in {401, 403}:
                    self.store.execute("UPDATE connections SET status='reauthorization_required',updated_at=? WHERE id=?", (now(), job["connection_id"]))
                raise
            status = data.get("status")
            if data.get("video_id") != job["provider_video_id"] or status not in {"pending", "processing", "completed", "failed", "cancelled"}:
                raise RuntimeUnavailable("HeyGen devolvió un estado o identificador no válido. Se conserva el trabajo existente.")
            error = "HeyGen no completó este vídeo. Consulta el detalle en su panel antes de volver a generar." if status in {"failed", "cancelled"} else None
            self.store.execute("UPDATE video_jobs SET status=?,error=?,updated_at=? WHERE id=?", (status, error, now(), job_id))
            if status == "completed":
                try:
                    self.save(job, data.get("video_url"))
                except (RuntimeUnavailable, OSError, ValueError):
                    # A failed download must not trigger a second paid generation.
                    self.store.execute("UPDATE video_jobs SET error=? WHERE id=?", ("HeyGen terminó el vídeo, pero falta guardar el MP4. Vuelve a consultar este mismo trabajo; no generes otro.", job_id))
            return self.public(self.job(project_id, job_id, agent_id, connection_id))

    def save(self, job, url):
        try:
            public_https_url(url)
        except ValueError:
            raise RuntimeUnavailable("HeyGen no devolvió una URL de vídeo válida.") from None
        host = urlsplit(url).hostname.lower()
        # Only download provider-owned CDNs, without credentials or redirects.
        if not (host == "heygen.ai" or host.endswith(".heygen.ai") or host == "heygen.com" or host.endswith(".heygen.com")):
            raise RuntimeUnavailable("El vídeo no está alojado en un dominio de HeyGen permitido.")
        try:
            with httpx.Client(timeout=httpx.Timeout(120, connect=10), follow_redirects=False, trust_env=False, transport=self.transport) as client:
                with client.stream("GET", url) as response:
                    if not response.is_success:
                        raise RuntimeUnavailable("No se pudo descargar el vídeo de HeyGen.")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_VIDEO_BYTES:
                            raise RuntimeUnavailable("El vídeo supera el límite de 100 MB.")
            if not is_mp4(content[:16]):
                raise RuntimeUnavailable("HeyGen no devolvió un archivo MP4 válido.")
        except httpx.HTTPError:
            raise RuntimeUnavailable("No se pudo guardar el MP4. Consulta de nuevo el mismo trabajo.") from None
        agent = self.store.one("SELECT * FROM agents WHERE id=?", (job["agent_id"],))
        project = self.project_access(job["project_id"])
        relative = f"videos/{job['id']}.mp4"
        path = self.store.agent_path(agent) / "workspace" / relative
        current = self.store.root
        for part in path.relative_to(self.store.root).parts:
            current /= part
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
                raise ValueError("No se permiten enlaces en la ruta del vídeo.")
        atomic_write(path, content)
        project_relative = path.relative_to(self.store.project_path(project)).as_posix()
        with self.store.db() as db:
            message_id = job["message_id"] or db.execute("INSERT INTO messages(agent_id,role,content,source,created_at) VALUES (?,?,?,?,?)", (job["agent_id"], "assistant", f"Vídeo guardado en {relative}", "artifact", now())).lastrowid
            db.execute("UPDATE video_jobs SET path=?,message_id=?,error=NULL,updated_at=? WHERE id=?", (project_relative, message_id, now(), job["id"]))
        self.store.event(job["agent_id"], "Vídeo HeyGen guardado y adjunto al chat: " + relative)

    @staticmethod
    def public(job):
        payload = json.loads(job["payload"])
        result = {key: job[key] for key in ("id", "agent_id", "connection_id", "request_id", "provider_video_id", "status", "estimated_cost_usd", "error", "created_at", "updated_at")}
        result.update(model=MODEL, duration=payload["duration"], resolution=payload["resolution"], aspect_ratio=payload["aspect_ratio"], saved=bool(job["path"]), path=job["path"], mime_type="video/mp4")
        if job["path"]:
            result["url"] = f"/api/projects/{job['project_id']}/video?" + urlencode({"path": job["path"]})
        if job["status"] == "submission_unknown":
            result["message"] = "Envío incierto. Reutiliza el mismo request_id y contenido para recuperar la solicitud; no crees otra."
        elif not job["path"]:
            result["message"] = "Consulta este id con heygen_get_video. No repitas la generación."
        return result

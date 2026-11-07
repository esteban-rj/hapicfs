"""Project-scoped, resumable YouTube uploads with durable duplicate protection."""
import hashlib
import json
import logging
import re
import time
from urllib.parse import urlsplit

import httpx

from .runtime import RuntimeUnavailable
from .storage import now, uid

UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CHUNK_BYTES = 4 * 1024 * 1024


class UploadLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(value.copy_with(query=b"") if isinstance(value, httpx.URL) and value.host in {"www.googleapis.com", "youtube.googleapis.com"} else value for value in record.args)
        return True


class YouTubeUploads:
    def __init__(self, service):
        self.service, self.store, self.youtube = service, service.store, service.youtube
        self.store.execute("""CREATE TABLE IF NOT EXISTS youtube_uploads(
            id TEXT PRIMARY KEY,project_id TEXT NOT NULL,agent_id TEXT NOT NULL,connection_id TEXT NOT NULL,
            request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,path TEXT NOT NULL,metadata TEXT NOT NULL,
            status TEXT NOT NULL,video_id TEXT,bytes_sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(agent_id,request_id))""")
        logger = logging.getLogger("httpx")
        if not any(isinstance(item, UploadLogFilter) for item in logger.filters):
            logger.addFilter(UploadLogFilter())

    def file(self, agent, relative):
        from .artifacts import artifact_file
        path, mime = artifact_file(self.service, agent["project_id"], f"agents/{agent['id']}/workspace/{relative}")
        if mime != "video/mp4":
            raise ValueError("Selecciona un MP4 real guardado en el workspace de este agente.")
        return path

    def connection(self, agent, connection_id):
        connection = self.youtube.connection(agent["project_id"], connection_id)
        if UPLOAD_SCOPE not in json.loads(connection["scopes"]):
            raise RuntimeUnavailable("El canal solo tiene lectura. Vuelve a autorizar YouTube en Herramientas concediendo el permiso para subir vídeos; no hace falta cargar otra credencial de Google.")
        return connection

    def job(self, agent, connection_id, upload_id):
        job = self.store.one("SELECT * FROM youtube_uploads WHERE id=? AND project_id=? AND agent_id=? AND connection_id=?", (upload_id, agent["project_id"], agent["id"], connection_id))
        if not job:
            raise LookupError("Subida no encontrada en el alcance de este agente y canal.")
        return job

    def result(self, job):
        metadata = json.loads(job["metadata"])
        return {"id": job["id"], "status": job["status"], "video_id": job["video_id"],
                "url": f"https://www.youtube.com/watch?v={job['video_id']}" if job["video_id"] else None,
                "requested_visibility": metadata["status"]["privacyStatus"], "bytes_sent": job["bytes_sent"],
                "message": "Subida recibida por YouTube; consulta el estado real de procesamiento y visibilidad." if job["video_id"] else "Subida pendiente. Conserva este ID y recupérala sin crear otra publicación."}

    @staticmethod
    def session_url(value):
        if not isinstance(value, str) or len(value) > 8192 or any(ord(char) < 33 for char in value):
            raise RuntimeUnavailable("Google devolvió un destino de subida no válido.")
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise RuntimeUnavailable("Google devolvió un destino de subida no válido.") from None
        if parsed.scheme != "https" or parsed.hostname not in {"www.googleapis.com", "youtube.googleapis.com"} or parsed.username or parsed.password or port not in {None, 443} or parsed.fragment or not parsed.path.startswith("/upload/"):
            raise RuntimeUnavailable("Google devolvió un destino de subida no válido. No se enviaron credenciales a otro servidor.")
        return value

    def upload(self, agent, connection_id, *, path, title, description, request_id, visibility="private", user_approved=False, contains_synthetic_media=True):
        if user_approved is not True:
            raise ValueError("El usuario debe autorizar la subida y elegir su visibilidad antes de publicar.")
        if visibility not in {"private", "unlisted", "public"} or not isinstance(title, str) or not 1 <= len(title.strip()) <= 100 or not isinstance(description, str) or len(description.encode()) > 5000 or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id or ""):
            raise ValueError("Indica título, descripción, visibilidad y request_id válidos.")
        if type(contains_synthetic_media) is not bool:
            raise ValueError("Indica si el vídeo contiene medios sintéticos.")
        self.connection(agent, connection_id)
        file = self.file(agent, path)
        metadata = {"snippet": {"title": title.strip(), "description": description, "categoryId": "20"},
                    "status": {"privacyStatus": visibility, "containsSyntheticMedia": contains_synthetic_media}}
        with file.open("rb") as stream:
            file_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        fingerprint = hashlib.sha256(json.dumps([connection_id, path, file_hash, metadata], sort_keys=True).encode()).hexdigest()
        with self.youtube.lock(connection_id):
            previous = self.store.one("SELECT * FROM youtube_uploads WHERE agent_id=? AND request_id=?", (agent["id"], request_id))
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ValueError("Ese request_id ya corresponde a otro archivo o publicación. No se creó otra subida.")
                return self.get(agent, connection_id, previous["id"])
            stamp, upload_id = now(), uid("ytup")
            self.store.execute("INSERT INTO youtube_uploads VALUES (?,?,?,?,?,?,?,?,?,NULL,0,?,?)", (upload_id, agent["project_id"], agent["id"], connection_id, request_id, fingerprint, path, json.dumps(metadata), "initiating", stamp, stamp))
            connection = self.connection(agent, connection_id)
            access = self.youtube.access_token(connection)
            # Confirm the grant still resolves to the selected channel, not another account.
            channels = self.youtube._api("channels", access, {"part": "id", "mine": "true"}, connection_id).get("items", [])
            if not any(item.get("id") == connection["account_id"] for item in channels):
                raise PermissionError("La autorización no corresponde al canal seleccionado. No se inició la subida.")
            try:
                response = self.youtube._request("POST", UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                    headers={"Authorization": "Bearer " + access, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(file.stat().st_size)}, json=metadata)
                if not response.is_success:
                    raise RuntimeUnavailable(f"Google rechazó iniciar la subida (HTTP {response.status_code}). Conserva el ID y revisa permisos/cuota; no se creó una segunda publicación.")
                session = self.session_url(response.headers.get("location"))
                self.store.secret(upload_id + "-session", session)
                self.store.execute("UPDATE youtube_uploads SET status='uploading',updated_at=? WHERE id=?", (now(), upload_id))
            except RuntimeUnavailable as exc:
                self.store.execute("UPDATE youtube_uploads SET status='uncertain',updated_at=? WHERE id=?", (now(), upload_id))
                return {**self.result(self.job(agent, connection_id, upload_id)), "error": str(exc)}
            return self.get(agent, connection_id, upload_id)

    def get(self, agent, connection_id, upload_id):
        with self.youtube.lock(connection_id):
            job = self.job(agent, connection_id, upload_id)
            connection = self.connection(agent, connection_id)
            access = self.youtube.access_token(connection)
            if job["video_id"]:
                data = self.youtube._api("videos", access, {"part": "status,processingDetails,snippet", "id": job["video_id"]}, connection_id).get("items", [])
                if not data or data[0].get("snippet", {}).get("channelId") != connection["account_id"]:
                    raise RuntimeUnavailable("No se pudo verificar el vídeo en el canal autorizado. No se repetirá la subida.")
                status = data[0].get("status", {})
                return {**self.result(job), "actual_visibility": status.get("privacyStatus"), "upload_status": status.get("uploadStatus"),
                        "processing_status": data[0].get("processingDetails", {}).get("processingStatus"),
                        "published": status.get("privacyStatus") == "public" and status.get("uploadStatus") == "processed"}
            session = self.store.secret(upload_id + "-session")
            if not session:
                return self.result(job)
            session = self.session_url(session)
            file = self.file(agent, job["path"])
            metadata = json.loads(job["metadata"])
            with file.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if hashlib.sha256(json.dumps([connection_id, job["path"], digest, metadata], sort_keys=True).encode()).hexdigest() != job["fingerprint"]:
                raise ValueError("El archivo cambió durante la subida. No se enviaron bytes distintos a los autorizados.")
            total, deadline = file.stat().st_size, time.monotonic() + 45
            headers = {"Authorization": "Bearer " + access}
            try:
                response = self.youtube._request("PUT", session, headers={**headers, "Content-Length": "0", "Content-Range": f"bytes */{total}"}, content=b"")
                previous_offset = -1
                while True:
                    if response.status_code in {200, 201}:
                        video_id = self.youtube._payload(response).get("id")
                        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                            raise RuntimeUnavailable("Google terminó la subida sin devolver un ID verificable. No se repetirá el envío.")
                        self.store.execute("UPDATE youtube_uploads SET status='uploaded',video_id=?,bytes_sent=?,updated_at=? WHERE id=?", (video_id, total, now(), upload_id))
                        self.store.event(agent["id"], "Subida YouTube recibida: " + video_id)
                        return self.get(agent, connection_id, upload_id)
                    if response.status_code != 308:
                        raise RuntimeUnavailable(f"YouTube interrumpió la subida (HTTP {response.status_code}). Recupera el mismo ID; no crees otra publicación.")
                    matched = re.fullmatch(r"bytes=0-(\d+)", response.headers.get("range", ""))
                    offset = int(matched[1]) + 1 if matched else 0
                    if not 0 <= offset < total or offset <= previous_offset:
                        raise RuntimeUnavailable("Google devolvió un progreso de subida no válido.")
                    previous_offset = offset
                    self.store.execute("UPDATE youtube_uploads SET bytes_sent=?,updated_at=? WHERE id=?", (offset, now(), upload_id))
                    if time.monotonic() >= deadline:
                        return self.result(self.job(agent, connection_id, upload_id))
                    with file.open("rb") as stream:
                        stream.seek(offset)
                        chunk = stream.read(CHUNK_BYTES)
                    response = self.youtube._request("PUT", session, headers={**headers, "Content-Type": "video/mp4", "Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{offset+len(chunk)-1}/{total}"}, content=chunk)
            except RuntimeUnavailable as exc:
                self.store.execute("UPDATE youtube_uploads SET status='uncertain',updated_at=? WHERE id=?", (now(), upload_id))
                return {**self.result(self.job(agent, connection_id, upload_id)), "error": str(exc)}

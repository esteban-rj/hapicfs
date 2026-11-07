"""Microphone-to-chat contracts. All inference and audio traffic uses test doubles."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.runtime import DockerRuntime
from backend.storage import now
from backend.voice import MAX_AUDIO_BYTES

KEY = "voice-test-key-never-a-real-credential"
WEBM = b"\x1a\x45\xdf\xa3" + b"microphone-test-data"
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
WAV = b"RIFF\x24\x00\x00\x00WAVE" + b"microphone-test-data"


class OfflineRuntime(DockerRuntime):
    def inspect(self, agent, store):
        return {"status": agent["status"], "ready": False}


@pytest.fixture
def voice_env(tmp_path, monkeypatch, login):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HAPIC_TRANSCRIPTION_MODEL", raising=False)
    app = create_app(tmp_path, OfflineRuntime())
    service = app.state.service
    org = service.create_org("Estudio")
    project = service.create_project(org["id"], "Producto")
    hapic = service.store.one("SELECT * FROM agents WHERE kind='hapic'")
    nora = service.create_agent(project["id"], "Nora", "ux")
    with TestClient(app, base_url="http://localhost") as client:
        # Control task execution explicitly; no background dispatch or Docker in these tests.
        service.tasks.stop()
        login(client)
        yield client, service, hapic, nora


@pytest.mark.parametrize("mime,audio,extension", [("audio/webm;codecs=opus", WEBM, "webm"), ("audio/mp4", MP4, "mp4"), ("audio/wav", WAV, "wav")])
def test_transcription_wire_and_no_audio_persistence(voice_env, monkeypatch, mime, audio, extension):
    client, service, _, nora = voice_env
    service.store.secret("openai", KEY)
    before = set(service.store.root.rglob("*"))
    requests = []

    def provider(request):
        requests.append(request)
        assert str(request.url) == "https://api.openai.com/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
        body = request.read()
        assert b'name="model"\r\n\r\ngpt-transcribe' in body
        assert f'filename="microphone.{extension}"'.encode() in body
        assert audio in body
        assert b'name="language"' not in body
        return httpx.Response(200, json={"text": "  Prepara el calendario editorial.  ", "languages": [{"code": "es"}]})

    real_client = httpx.AsyncClient
    with patch("backend.voice.httpx.AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(provider), **kw)) as factory:
        response = client.post(f"/api/agents/{nora['id']}/voice/transcriptions", content=audio, headers={"Content-Type": mime})
    assert response.status_code == 200 and response.json() == {"text": "Prepara el calendario editorial."}
    assert len(requests) == 1 and factory.call_args.kwargs["trust_env"] is False
    assert set(service.store.root.rglob("*")) == before
    assert service.messages(nora["id"]) == []
    assert service.store.all("SELECT * FROM chat_runs") == []


@pytest.mark.parametrize("kind", ["hapic", "ux", "graphic-designer", "architect", "coder", "community-manager"])
def test_voice_available_for_every_agent_and_reviewed_text_uses_normal_chat(voice_env, kind):
    client, service, hapic, _ = voice_env
    planner = service.create_agent(hapic["project_id"], "Planner", "architect")
    agent = hapic if kind == "hapic" else service.create_agent(hapic["project_id"], "Destino", kind, planner["id"] if kind == "coder" else None)
    service.store.secret("openai", KEY)
    service.store.execute("UPDATE agents SET container_id='test-only' WHERE id=?", (agent["id"],))
    with patch.object(service.voice, "transcribe", new=AsyncMock(return_value="Texto antes de revisar.")), patch.object(service.runtime, "chat", new=AsyncMock(return_value=("Tarea recibida.", "completed"))) as chat:
        path = f"/api/agents/{agent['id']}"
        assert client.post(path + "/voice/transcriptions", content=WEBM, headers={"Content-Type": "audio/webm"}).json()["text"] == "Texto antes de revisar."
        assert service.messages(agent["id"]) == []
        message = {"content": "Texto corregido y tarea revisada.", "request_id": "stable-voice-message"}
        for _ in range(2):
            reply = client.post(path + "/chat", json=message)
            assert reply.status_code == 200 and reply.json()["content"] == "Tarea recibida."
        assert chat.await_count == 1
        assert chat.call_args.args[0]["id"] == agent["id"]
        assert chat.call_args.args[2] == message["content"]
        assert len(service.messages(agent["id"])) == 2


def test_transcription_requires_session_csrf_membership_and_key(voice_env):
    client, service, _, nora = voice_env
    path = f"/api/agents/{nora['id']}/voice/transcriptions"
    with patch.object(service.voice, "transcribe", new=AsyncMock()) as transcribe:
        assert client.post(path, content=WEBM, headers={"X-Hapic-CSRF": "wrong"}).status_code == 403
        assert client.post(path, content=WEBM, headers={"Origin": "https://other.example"}).status_code == 403
        assert client.post(path, content=WEBM).status_code == 503  # missing server key
        service.store.secret("openai", KEY)
        service.store.execute("DELETE FROM memberships")
        assert client.post(path, content=WEBM).status_code == 404
        assert client.get(path.replace("transcriptions", "status")).status_code == 404
        client.cookies.clear()
        assert client.post(path, content=WEBM).status_code == 401
        assert client.get(path.replace("transcriptions", "status")).status_code == 401
        transcribe.assert_not_awaited()


@pytest.mark.parametrize("content,mime,code", [(b"", "audio/webm", 400), (b"not audio", "audio/webm", 400), (WEBM, "audio/mp4", 400), (WEBM, "text/plain", 415), (b"x" * (MAX_AUDIO_BYTES + 1), "audio/webm", 413)])
def test_invalid_recordings_do_not_contact_provider(voice_env, content, mime, code):
    client, service, _, nora = voice_env
    service.store.secret("openai", KEY)
    with patch("backend.voice.httpx.AsyncClient") as provider:
        response = client.post(f"/api/agents/{nora['id']}/voice/transcriptions", content=content, headers={"Content-Type": mime})
    assert response.status_code == code
    provider.assert_not_called()


@pytest.mark.parametrize("case", ["http401", "http429", "http500", "timeout", "invalid-json", "wrong-shape", "missing-text", "empty-text", "long-text"])
def test_audio_provider_failures_are_redacted_and_never_retried(voice_env, case):
    client, service, _, nora = voice_env
    service.store.secret("openai", KEY)
    requests = []

    def provider(request):
        requests.append(request)
        if case.startswith("http"):
            return httpx.Response(int(case[4:]), text="private-provider-body " + KEY)
        if case == "timeout":
            raise httpx.ReadTimeout("private-provider-body " + KEY, request=request)
        if case == "invalid-json":
            return httpx.Response(200, text="private-provider-body " + KEY)
        body = {"wrong-shape": [], "missing-text": {}, "empty-text": {"text": " "}, "long-text": {"text": "x" * 20_001}}[case]
        return httpx.Response(200, json=body)

    real_client = httpx.AsyncClient
    with patch("backend.voice.httpx.AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(provider), **kw)):
        response = client.post(f"/api/agents/{nora['id']}/voice/transcriptions", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert response.status_code == 503
    assert KEY not in response.text and "private-provider-body" not in response.text
    assert len(requests) == 1


def test_status_during_busy_turn_is_factual_scoped_and_does_not_run_inference(voice_env):
    client, service, hapic, nora = voice_env
    other = service.create_agent(hapic["project_id"], "Otro", "ux")
    first = service.tasks.create(hapic, nora["id"], "Diseñar el flujo", "", [], ["flujo.md"])
    second = service.tasks.create(hapic, other["id"], "Preparar otro documento", "", [], ["documento.md"])
    third = service.tasks.create(hapic, nora["id"], "Recuperar tarea incierta", "", [], ["avance.md"])
    service.store.execute("UPDATE tasks SET state='running' WHERE id IN (?,?)", (first["id"], third["id"]))
    service.store.execute("UPDATE tasks SET state='queued' WHERE id=?", (second["id"],))
    with patch.object(service.runtime, "chat", new=AsyncMock()) as inference:
        lock = service.lock(nora["id"])
        lock.acquire()
        try:
            own = client.get(f"/api/agents/{nora['id']}/voice/status")
            team = client.get(f"/api/agents/{hapic['id']}/voice/status")
        finally:
            lock.release()
        assert own.status_code == team.status_code == 200
        assert own.json()["agent_id"] == nora["id"] and own.json()["checked_at"]
        assert "Está trabajando" in own.json()["content"] and "Diseñar el flujo" in own.json()["content"]
        assert "Preparar otro documento" not in own.json()["content"]
        assert "Preparar otro documento" in team.json()["content"] and "1 en cola" in team.json()["content"]
        # Both records say running, but neither is asserted to be executing after releasing the lock.
        idle = client.get(f"/api/agents/{nora['id']}/voice/status").json()["content"]
        assert "2 tareas con ejecución sin confirmar" in idle and "0 tareas en ejecución confirmada" in idle
        inference.assert_not_awaited()
        assert service.messages(nora["id"]) == []
    assert service.store.api_key() is None


@pytest.mark.parametrize("state,expected", [("failed", "terminó con un error"), ("interrupted", "se interrumpió"), ("running", "ejecución no está confirmada")])
def test_status_reports_failed_interrupted_and_uncertain_turns(voice_env, state, expected):
    client, service, _, nora = voice_env
    service.store.execute("INSERT INTO chat_runs VALUES (?,?,?,?,?)", ("uncertain-turn", nora["id"], state, now(), now()))
    content = client.get(f"/api/agents/{nora['id']}/voice/status").json()["content"]
    assert expected in content and "pendiente de iniciar" in content


def test_status_describes_the_actual_spoken_task_during_a_chat_turn(voice_env):
    client, service, _, nora = voice_env
    service.store.execute("INSERT INTO chat_runs VALUES (?,?,?,?,?)", ("voice-in-progress", nora["id"], "running", now(), now()))
    service.store.set_setting("input-voice-in-progress", {"agent_id": nora["id"], "content": "Prepara el calendario editorial semanal."})
    lock = service.lock(nora["id"])
    lock.acquire()
    try:
        content = client.get(f"/api/agents/{nora['id']}/voice/status").json()["content"]
    finally:
        lock.release()
    assert "Mensaje en curso: Prepara el calendario editorial semanal." in content

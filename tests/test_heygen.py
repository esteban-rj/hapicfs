"""HeyGen's real v3 wire contract, with all external traffic confined to a test transport."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.runtime import DockerRuntime, RuntimeUnavailable, platform_instructions
from backend.service import Service
from backend.storage import Store

KEY = "heygen-test-key-never-real-123456789"
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00\x00\x00\x08mdat"


class OfflineRuntime(DockerRuntime):
    def start(self, agent, store):
        raise RuntimeUnavailable("Docker disabled in this test.")


class HeyGenDouble:
    def __init__(self):
        self.requests = []
        self.posts = []
        self.accepted = {}
        self.status = "processing"
        self.submit_status = 202
        self.ambiguous_once = False
        self.user_status = 200
        self.scope_mode = "full"
        self.scopes = []
        self.url = "https://resource2.heygen.ai/videos/test.mp4?signature=private-test-link"
        self.download_status = 200
        self.video_bytes = MP4
        self.response_id = None

    def __call__(self, request):
        self.requests.append(request)
        if request.url.host == "resource2.heygen.ai":
            assert "x-api-key" not in request.headers and "authorization" not in request.headers
            return httpx.Response(self.download_status, content=self.video_bytes, headers={"content-type": "video/mp4"})
        assert request.url.host == "api.heygen.com"
        assert request.headers["x-api-key"] == KEY
        assert request.url.path.startswith("/v3/")
        if request.url.path == "/v3/users/me":
            if self.user_status != 200:
                return httpx.Response(self.user_status, text="secret-provider-body " + KEY)
            return httpx.Response(200, json={"data": {"username": "Cuenta de pruebas", "email": "private@example.com"}})
        if request.url.path == "/v3/api_keys/self":
            return httpx.Response(200, json={"data": {"status": "active", "scope_mode": self.scope_mode, "scopes": self.scopes}})
        if request.method == "POST" and request.url.path == "/v3/models/videos":
            self.posts.append(request)
            if self.submit_status != 202:
                return httpx.Response(self.submit_status, text="provider-secret " + KEY)
            dedup = request.headers["idempotency-key"]
            self.accepted.setdefault(dedup, "provider_" + str(len(self.accepted) + 1))
            if self.ambiguous_once:
                self.ambiguous_once = False
                raise httpx.ReadTimeout("secret " + KEY, request=request)
            return httpx.Response(202, json={"data": {"video_id": self.accepted[dedup], "status": "pending"}})
        if request.method == "GET" and request.url.path.startswith("/v3/models/videos/"):
            return httpx.Response(200, json={"data": {"video_id": self.response_id or request.url.path.rsplit("/", 1)[-1], "status": self.status, "video_url": self.url, "failure_message": KEY}})
        raise AssertionError("Unexpected request: " + str(request.url))


@pytest.fixture
def heygen_env(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HAPIC_YOUTUBE_CLIENT_FILE", raising=False)
    application = create_app(tmp_path, OfflineRuntime())
    service = application.state.service
    provider = HeyGenDouble()
    service.heygen.transport = httpx.MockTransport(provider)
    org = service.create_org("HeyGen tests")
    project = service.create_project(org["id"], "Vídeos")
    agent = service.create_agent(project["id"], "Alma", "community-manager")
    with TestClient(application, base_url="http://localhost") as client:
        client.headers["X-Hapic-CSRF"] = client.get("/api/bootstrap").json()["csrf"]
        yield application, service, provider, client, project, agent


def connect(env):
    _, _, _, client, project, _ = env
    response = client.post(f"/api/projects/{project['id']}/connections/heygen", json={"api_key": KEY})
    assert response.status_code == 200, response.text
    assert response.json()["verified"]
    return response.json()["connection_id"]


def generate(env, **overrides):
    _, service, _, _, _, agent = env
    return service.tool(agent, "heygen_generate_video", {"prompt": "Una taza de café con sonido ambiente", "request_id": "coffee-video-01", **overrides})


def test_key_verification_encryption_assignment_and_restart(heygen_env):
    application, service, provider, client, project, agent = heygen_env
    connection_id = connect(heygen_env)
    store = application.state.store
    assert [r.url.path for r in provider.requests] == ["/v3/users/me", "/v3/api_keys/self"]
    result = client.get(f"/api/projects/{project['id']}/tools").json()
    binding = next(item for item in result["assignments"] if item["tool_id"] == "heygen")
    assert binding["enabled"] and binding["connection_id"] == connection_id
    assert KEY not in json.dumps(result) and "private@example.com" not in json.dumps(result)
    assert KEY.encode() not in (store.root / "platform.db").read_bytes()
    assert KEY.encode() not in (store.secrets_dir / (connection_id + "-heygen.enc")).read_bytes()
    assert store.secret(connection_id + "-heygen") == KEY
    config = (store.agent_path(agent) / "hermes/config.yaml").read_text()
    assert KEY not in config and "heygen_generate_video" in config
    assert "heygen_generate_video" in platform_instructions(agent, store)
    restarted = Service(Store(store.root), OfflineRuntime())
    assert restarted.heygen.connections(project["id"])[0]["id"] == connection_id
    assert restarted.store.secret(connection_id + "-heygen") == KEY
    assert connect(heygen_env) == connection_id


def test_empty_video_history_still_reports_the_assigned_connection(heygen_env):
    _, service, _, _, project, agent = heygen_env
    connection_id = connect(heygen_env)
    result = service.tool(agent, "heygen_list_videos", {})
    assert result["videos"] == []
    assert result["connection"]["id"] == connection_id
    assert result["connection"]["status"] == "connected"
    assert KEY not in json.dumps(result)
    hapic = service.store.one("SELECT * FROM agents WHERE project_id=? AND kind='hapic'", (project["id"],))
    agents = service.tool(hapic, "list_project_agents", {})["agents"]
    manager = next(item for item in agents if item["id"] == agent["id"])
    binding = next(item for item in manager["tools"] if item["tool_id"] == "heygen")
    assert binding["connection_id"] == connection_id and binding["connection_status"] == "connected"
    assert KEY not in json.dumps(agents)


@pytest.mark.parametrize("mode,scopes", [("read_only", []), ("custom", ["videos:read"])])
def test_insufficient_permissions_do_not_store_key(heygen_env, mode, scopes):
    application, _, provider, client, project, _ = heygen_env
    provider.scope_mode, provider.scopes = mode, scopes
    response = client.post(f"/api/projects/{project['id']}/connections/heygen", json={"api_key": KEY})
    assert response.status_code == 400 and KEY not in response.text
    assert application.state.store.all("SELECT * FROM connections") == []
    assert not list(application.state.store.secrets_dir.glob("*-heygen.enc"))


def test_invalid_key_and_provider_failures_are_redacted(heygen_env):
    application, _, provider, client, project, _ = heygen_env
    url = f"/api/projects/{project['id']}/connections/heygen"
    assert client.post(url, json={"api_key": "too-short"}).status_code == 422
    assert provider.requests == []
    provider.user_status = 401
    response = client.post(url, json={"api_key": KEY})
    assert response.status_code == 503 and KEY not in response.text and "secret-provider-body" not in response.text
    assert not application.state.store.all("SELECT * FROM connections")


def test_generation_wire_idempotency_cost_and_mcp_transport(heygen_env):
    application, service, provider, client, _, agent = heygen_env
    connect(heygen_env)
    headers = {"Authorization": "Bearer " + application.state.store.token(agent["id"], "mcp"), "Accept": "application/json, text/event-stream"}
    response = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "heygen_generate_video", "arguments": {"prompt": "Una taza de café con sonido ambiente", "request_id": "coffee-video-01"}}})
    assert response.status_code == 200 and not response.json()["result"].get("isError", False)
    job = generate(heygen_env)
    assert len(provider.posts) == 1 and job["status"] == "pending" and not job["saved"]
    assert job["estimated_cost_usd"] == "0.05"
    payload = json.loads(provider.posts[0].content)
    assert payload == {"model": "heygen-video-1", "mode": "text_to_video", "prompt": "Una taza de café con sonido ambiente", "duration": 5, "resolution": "480p", "aspect_ratio": "9:16", "prompt_enhancement": "quality"}
    assert provider.posts[0].headers["idempotency-key"] == job["id"]
    with pytest.raises(ValueError):
        generate(heygen_env, duration=10)
    assert len(provider.posts) == 1
    provider.status = "processing"
    assert service.tool(agent, "heygen_get_video", {"video_id": job["id"]})["status"] == "processing"


@pytest.mark.parametrize("arguments", [{"duration": 30}, {"duration": True}, {"resolution": "4k"}, {"aspect_ratio": "1:1", "resolution": "1080p"}, {"request_id": "bad"}, {"prompt": " "}, {"image_url": "http://127.0.0.1/private"}, {"image_url": "https://169.254.169.254/private"}, {"image_url": "https://user:pass@example.com/a.png"}, {"image_url": "https://host.docker.internal/a.png"}])
def test_invalid_generation_never_contacts_provider(heygen_env, arguments):
    connect(heygen_env)
    provider = heygen_env[2]
    before = len(provider.requests)
    with pytest.raises(ValueError):
        generate(heygen_env, **arguments)
    assert len(provider.requests) == before and not provider.posts


def test_image_to_video_contract(heygen_env):
    connect(heygen_env)
    job = generate(heygen_env, image_url="https://example.com/product.png", duration=10, resolution="1080p")
    payload = json.loads(heygen_env[2].posts[0].content)
    assert payload["mode"] == "image_to_video" and payload["image"] == {"type": "url", "url": "https://example.com/product.png"}
    assert job["estimated_cost_usd"] == "0.40"


def test_ambiguous_submission_is_recovered_without_duplicate_charge(heygen_env):
    application, service, provider, _, _, agent = heygen_env
    connect(heygen_env)
    provider.ambiguous_once = True
    job = generate(heygen_env)
    assert job["status"] == "submission_unknown" and KEY not in json.dumps(job)
    restarted = Service(Store(application.state.store.root), OfflineRuntime())
    restarted.heygen.transport = httpx.MockTransport(provider)
    recovered = restarted.tool(agent, "heygen_generate_video", {"prompt": "Una taza de café con sonido ambiente", "request_id": "coffee-video-01"})
    assert recovered["id"] == job["id"] and recovered["status"] == "pending"
    assert len(provider.posts) == 2 and len(provider.accepted) == 1
    assert provider.posts[0].headers["idempotency-key"] == provider.posts[1].headers["idempotency-key"]
    assert len(service.heygen.list_jobs(agent["project_id"])["videos"]) == 1


def test_expired_ambiguous_job_is_not_resubmitted(heygen_env):
    application, _, provider, _, _, _ = heygen_env
    connect(heygen_env)
    provider.ambiguous_once = True
    job = generate(heygen_env)
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    application.state.store.execute("UPDATE video_jobs SET created_at=? WHERE id=?", (old, job["id"]))
    with pytest.raises(ValueError):
        generate(heygen_env)
    assert len(provider.posts) == 1


def test_rotating_key_does_not_resubmit_an_ambiguous_job(heygen_env):
    application, _, provider, _, _, _ = heygen_env
    connection_id = connect(heygen_env)
    provider.ambiguous_once = True
    assert generate(heygen_env)["status"] == "submission_unknown"
    application.state.store.secret(connection_id + "-heygen", "replacement-test-key-never-real-123456")
    with pytest.raises(ValueError, match="clave cambió"):
        generate(heygen_env)
    assert len(provider.posts) == 1


def test_signed_download_urls_and_keys_are_absent_from_logs(heygen_env, caplog):
    _, service, provider, _, _, agent = heygen_env
    connect(heygen_env)
    job = generate(heygen_env)
    provider.status = "completed"
    with caplog.at_level(logging.INFO, logger="httpx"):
        assert service.tool(agent, "heygen_get_video", {"video_id": job["id"]})["saved"]
    assert "resource2.heygen.ai" in caplog.text
    assert "private-test-link" not in caplog.text and KEY not in caplog.text


def test_concurrent_identical_submissions_are_claimed_once(heygen_env):
    connect(heygen_env)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: generate(heygen_env), range(3)))
    assert len({result["id"] for result in results}) == 1 and len(heygen_env[2].posts) == 1


@pytest.mark.parametrize("major_brand", [b"isom", b"iso5", b"iso6"])
def test_completed_mp4_persists_chat_tree_download_and_restart(heygen_env, major_brand):
    application, service, provider, client, project, agent = heygen_env
    video = MP4[:8] + major_brand + MP4[12:]
    provider.video_bytes = video
    connect(heygen_env)
    job = generate(heygen_env)
    provider.status = "completed"
    result = service.tool(agent, "heygen_get_video", {"video_id": job["id"]})
    assert result["saved"] and result["path"].endswith(".mp4")
    assert "signature=" not in json.dumps(result)
    messages = client.get(f"/api/agents/{agent['id']}/messages").json()
    attachment = messages[0]["attachments"][0]
    assert attachment["mime_type"] == "video/mp4"
    response = client.get(attachment["url"])
    assert response.status_code == 200 and response.content == video
    assert response.headers["content-type"] == "video/mp4"
    assert "no-store" in response.headers["cache-control"]
    assert client.get(attachment["url"] + "&download=true").headers["content-disposition"].startswith("attachment;")
    ranged = client.get(attachment["url"], headers={"Range": "bytes=0-11"})
    assert ranged.status_code == 206 and ranged.content == video[:12]
    def descendants(node):
        yield node
        for child in node.get("children", []):
            yield from descendants(child)
    node = next(item for item in descendants(service.tree(project["id"])) if item["path"] == attachment["path"])
    assert node["preview"] and node["media_type"] == "video"
    assert "videos/" + job["id"] + ".mp4" in service.tool(agent, "project_list_files", {})["files"]
    before = len(provider.requests)
    assert service.tool(agent, "heygen_get_video", {"video_id": job["id"]})["saved"]
    assert len(provider.requests) == before and len(service.messages(agent["id"])) == 1
    assert len(provider.posts) == 1
    restarted = Service(Store(application.state.store.root), OfflineRuntime())
    assert restarted.messages(agent["id"])[0]["attachments"][0] == attachment
    assert restarted.video_file(project["id"], result["path"])[0].read_bytes() == video
    client.cookies.clear()
    assert client.get(attachment["url"]).status_code == 401


@pytest.mark.parametrize("failure", ["http", "invalid_mp4", "foreign_host", "redirect"])
def test_download_failure_can_retry_without_regenerating(heygen_env, failure):
    _, service, provider, _, _, agent = heygen_env
    connect(heygen_env)
    job = generate(heygen_env)
    provider.status = "completed"
    if failure == "http":
        provider.download_status = 403
    elif failure == "invalid_mp4":
        provider.video_bytes = b"<html>not a video</html>"
    elif failure == "foreign_host":
        provider.url = "https://example.com/private.mp4"
    else:
        provider.download_status = 302
    result = service.tool(agent, "heygen_get_video", {"video_id": job["id"]})
    assert result["status"] == "completed" and not result["saved"] and result["error"]
    assert service.messages(agent["id"]) == []
    provider.url = "https://resource2.heygen.ai/videos/test.mp4"
    provider.download_status, provider.video_bytes = 200, MP4
    assert service.tool(agent, "heygen_get_video", {"video_id": job["id"]})["saved"]
    assert len(provider.posts) == 1


def test_server_rejects_cross_project_agent_and_disabled_access(heygen_env):
    application, service, provider, client, project, agent = heygen_env
    connection_id = connect(heygen_env)
    job = generate(heygen_env)
    other_project = service.create_project(project["organization_id"], "Otro proyecto")
    other = service.create_agent(other_project["id"], "Otro agente", "community-manager")
    assert client.put(f"/api/agents/{other['id']}/tools/heygen", json={"enabled": True, "connection_id": connection_id}).status_code == 404
    assert client.post(f"/api/projects/{other_project['id']}/heygen/videos/{job['id']}/refresh").status_code == 404
    assert service.heygen.list_jobs(other_project["id"])["videos"] == []
    colleague = service.create_agent(project["id"], "Colega", "ux")
    with pytest.raises(PermissionError):
        service.tool(colleague, "heygen_get_video", {"video_id": job["id"]})
    service.assign_tool(colleague["id"], "heygen", True, connection_id)
    with pytest.raises(LookupError):
        service.tool(colleague, "heygen_get_video", {"video_id": job["id"]})
    service.assign_tool(agent["id"], "heygen", False, connection_id)
    with pytest.raises(PermissionError):
        generate(heygen_env, request_id="disabled-video")
    before = len(provider.posts)
    application.state.store.execute("DELETE FROM memberships")
    assert client.get(f"/api/projects/{project['id']}/heygen/videos").status_code == 404
    with pytest.raises(LookupError):
        generate(heygen_env, request_id="unauthorized-video")
    assert len(provider.posts) == before


def test_disconnect_removes_key_blocks_pending_jobs_and_preserves_saved_files(heygen_env):
    application, service, provider, client, project, agent = heygen_env
    connection_id = connect(heygen_env)
    saved = generate(heygen_env)
    provider.status = "completed"
    saved = service.tool(agent, "heygen_get_video", {"video_id": saved["id"]})
    pending = generate(heygen_env, request_id="pending-video-02")
    response = client.delete(f"/api/projects/{project['id']}/connections/{connection_id}")
    assert response.status_code == 200
    assert application.state.store.secret(connection_id + "-heygen") is None
    assert not service.heygen.connections(project["id"])
    assert client.post(f"/api/projects/{project['id']}/heygen/videos/{pending['id']}/refresh").status_code == 503
    with pytest.raises(ValueError):
        generate(heygen_env, request_id="after-disconnect")
    assert client.get(saved["url"]).content == MP4
    assert connect(heygen_env) == connection_id


def test_rejection_and_failed_job_do_not_leak_or_retry(heygen_env):
    _, service, provider, _, _, agent = heygen_env
    connect(heygen_env)
    provider.submit_status = 400
    job = generate(heygen_env)
    assert job["status"] == "failed" and KEY not in json.dumps(job)
    assert generate(heygen_env)["id"] == job["id"] and len(provider.posts) == 1
    provider.submit_status = 202
    second = generate(heygen_env, request_id="failure-video-02")
    provider.status = "failed"
    result = service.tool(agent, "heygen_get_video", {"video_id": second["id"]})
    assert result["status"] == "failed" and not result["saved"] and KEY not in json.dumps(result)
    assert len(provider.posts) == 2


def test_mp4_path_integrity_symlinks_and_membership(heygen_env, tmp_path):
    _, service, provider, client, project, agent = heygen_env
    connect(heygen_env)
    job = generate(heygen_env)
    provider.status = "completed"
    saved = service.tool(agent, "heygen_get_video", {"video_id": job["id"]})
    path, _ = service.video_file(project["id"], saved["path"])
    path.write_bytes(b"<script>not mp4</script>")
    assert client.get(saved["url"]).status_code == 400
    path.unlink()
    target = tmp_path / "outside.mp4"
    target.write_bytes(MP4)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Symlinks are not available.")
    assert client.get(saved["url"]).status_code == 400


def test_wrong_remote_id_and_oversized_video_are_not_saved(heygen_env, monkeypatch):
    _, service, provider, _, _, agent = heygen_env
    connect(heygen_env)
    job = generate(heygen_env)
    provider.status, provider.response_id = "completed", "someone_elses_video"
    with pytest.raises(RuntimeUnavailable):
        service.tool(agent, "heygen_get_video", {"video_id": job["id"]})
    assert not service.messages(agent["id"])
    provider.response_id = None
    monkeypatch.setattr("backend.heygen.MAX_VIDEO_BYTES", len(MP4) - 1)
    result = service.tool(agent, "heygen_get_video", {"video_id": job["id"]})
    assert not result["saved"] and result["error"] and len(provider.posts) == 1


def test_migration_adds_default_without_resetting_disabled_assignment(heygen_env):
    application, _, _, _, _, agent = heygen_env
    store = application.state.store
    home = store.agent_path(agent) / "hermes"
    original = (home / "SOUL.md").read_bytes()
    store.execute("DELETE FROM agent_tools WHERE agent_id=? AND tool_id='heygen'", (agent["id"],))
    Store(store.root)
    assert store.one("SELECT enabled FROM agent_tools WHERE agent_id=? AND tool_id='heygen'", (agent["id"],))["enabled"] == 1
    store.execute("UPDATE agent_tools SET enabled=0 WHERE agent_id=? AND tool_id='heygen'", (agent["id"],))
    Store(store.root)
    assert store.one("SELECT enabled FROM agent_tools WHERE agent_id=? AND tool_id='heygen'", (agent["id"],))["enabled"] == 0
    assert (home / "SOUL.md").read_bytes() == original

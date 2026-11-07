"""Contract/integration tests. Docker and LLM doubles are confined to this test module."""
import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.runtime import DockerRuntime, RuntimeUnavailable
from backend.service import Service, safe_path
from backend.storage import Store


class TestRuntime(DockerRuntime):
    __test__ = False

    def health(self):
        return {"available": False, "message": "Docker double: unavailable", "image": self.image}

    def start(self, agent, store):
        raise RuntimeUnavailable("Docker double: unavailable")

    def inspect(self, agent, store):
        return {"status": agent["status"], "ready": False}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HAPIC_YOUTUBE_CLIENT_FILE", raising=False)
    return create_app(tmp_path, TestRuntime())


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://localhost") as client:
        csrf = client.get("/api/bootstrap").json()["csrf"]
        client.headers["X-Hapic-CSRF"] = csrf
        yield client


def project(client):
    org = client.post("/api/organizations", json={"name": "Estudio"}).json()
    return client.post(f"/api/organizations/{org['id']}/projects", json={"name": "Producto"}).json()


def test_organization_project_hapic_persist_after_restart(client, app):
    p = project(client)
    state = client.get("/api/state").json()
    assert len(state["organizations"]) == len(state["projects"]) == len(state["agents"]) == 1
    hapic = state["agents"][0]
    assert hapic["kind"] == "hapic" and hapic["status"] == "pending" and hapic["container_id"] is None
    assert hapic["model"] == "gpt-6.1-sol" and hapic["effort"] == "xhigh"
    home = app.state.store.agent_path(hapic) / "hermes"
    config = yaml.safe_load((home / "config.yaml").read_text())
    assert config["model"]["provider"] == "openai-api"
    assert config["model"]["api_mode"] == "codex_responses"
    assert config["agent"]["reasoning_effort"] == "xhigh"
    assert "SOUL.md" in json.dumps(client.get(f"/api/projects/{p['id']}/tree").json())
    restarted = Service(Store(app.state.store.root), TestRuntime())
    assert restarted.agent(hapic["id"])["name"] == "Hapic"
    assert (home / "memories/MEMORY.md").exists()


def test_no_fake_runtime_or_chat(client):
    p = project(client)
    agent = client.get("/api/state").json()["agents"][0]
    result = client.post(f"/api/agents/{agent['id']}/chat", json={"content": "Hola"})
    assert result.status_code == 503
    assert client.get(f"/api/agents/{agent['id']}/messages").json() == []
    assert client.post(f"/api/agents/{agent['id']}/start").status_code == 202
    agent = client.get("/api/state").json()["agents"][0]
    assert agent["status"] == "blocked" and agent["container_id"] is None
    ux = client.post(f"/api/projects/{p['id']}/agents", json={"name": "Nora"}).json()
    ux = next(a for a in client.get("/api/state").json()["agents"] if a["id"] == ux["id"])
    assert ux["status"] == "blocked"


def test_keys_encrypted_redacted_and_excluded(client, app):
    key = "sk-proj-" + "test" * 12
    result = client.put("/api/settings/openai", json={"api_key": key})
    assert result.status_code == 200 and key not in result.text
    assert key.encode() not in (app.state.store.secrets_dir / "openai.enc").read_bytes()
    assert client.get("/api/capabilities").json()["openai"]["configured"]
    assert key not in client.get("/api/state").text
    bad = client.put("/api/settings/openai", json={"api_key": key * 20})
    assert bad.status_code == 422 and key not in bad.text
    p = project(client)
    agent = client.get("/api/state").json()["agents"][0]
    result = client.post(f"/api/agents/{agent['id']}/chat", json={"content": key})
    assert result.status_code == 400 and key not in result.text
    assert client.delete("/api/settings/openai").status_code == 200
    assert not app.state.store.api_key()


def test_sessions_csrf_origin_and_membership(client, app):
    assert client.post("/api/organizations", json={"name": "no"}, headers={"X-Hapic-CSRF": "wrong"}).status_code == 403
    assert client.post("/api/organizations", json={"name": "no"}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.get("/api/state", headers={"Host": "attacker.example"}).status_code == 403
    p = project(client)
    app.state.store.execute("DELETE FROM memberships")
    assert client.get("/api/state").json()["projects"] == []
    assert client.get("/api/state").json()["agents"] == []
    assert client.get(f"/api/projects/{p['id']}/tree").status_code == 404
    assert client.post(f"/api/projects/{p['id']}/agents", json={"name": "Nora"}).status_code == 404


def test_file_traversal_and_secrets(client, app):
    p = project(client)
    agent = client.get("/api/state").json()["agents"][0]
    for path in ["../../secrets/master.key", "/etc/passwd", "C:/Windows/win.ini", "..\\secrets\\openai.enc", "workspace/.env", f"agents/{agent['id']}/hermes/config.yaml"]:
        assert client.get(f"/api/projects/{p['id']}/file", params={"path": path}).status_code == 400


def test_symlinks_rejected_when_supported(client, app, tmp_path):
    p = project(client)
    root = app.state.store.project_path(p) / "workspace"
    outside = tmp_path / "private.md"
    outside.write_text("private")
    try:
        (root / "linked.md").symlink_to(outside)
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    assert client.get(f"/api/projects/{p['id']}/file", params={"path": "workspace/linked.md"}).status_code == 400


def test_mcp_scope_and_real_file_tools(client, app):
    p = project(client)
    ux = app.state.service.create_agent(p["id"], "Nora")
    other = app.state.service.create_agent(p["id"], "Otro")
    service = app.state.service
    assert service.tool(ux, "project_write_file", {"path": "brief.md", "content": "# Brief\nHipótesis pendiente de validar"})["saved"]
    assert service.tool(ux, "project_read_file", {"path": "brief.md"})["content"].startswith("# Brief")
    assert service.tool(other, "project_list_files", {}) == {"files": []}
    for path in ["../hermes/SOUL.md", f"../../{other['id']}/workspace/brief.md", "/etc/passwd", ".env", "config.yaml"]:
        with pytest.raises(ValueError):
            service.tool(ux, "project_write_file", {"path": path, "content": "bad"})
    with pytest.raises(PermissionError):
        service.tool(ux, "create_ux_agent", {"name": "No"})
    assert client.post("/mcp/", json={}).status_code == 401
    headers = {"Authorization": "Bearer " + app.state.store.token(ux["id"], "mcp"), "Accept": "application/json, text/event-stream"}
    result = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}}})
    assert result.status_code == 200 and "serverInfo" in result.json()["result"]
    result = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "project_read_file", "arguments": {"path": "brief.md"}}})
    assert result.status_code == 200 and "Hipótesis" in result.text
    result = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "create_ux_agent", "arguments": {"name": "No"}}})
    assert result.json()["result"]["isError"]


def test_model_changes_apply_and_clean_template(client, app):
    p = project(client)
    store = app.state.store
    hapic = client.get("/api/state").json()["agents"][0]
    (store.agent_path(hapic) / "hermes/memories/MEMORY.md").write_text("PRIVATE MEMORY")
    assert client.put("/api/settings/model", json={"model": "gpt-6.1-sol", "effort": "high"}).status_code == 200
    nora = app.state.service.create_agent(p["id"], "Nora")
    assert nora["effort"] == "high"
    assert "PRIVATE MEMORY" not in (store.agent_path(nora) / "hermes/memories/MEMORY.md").read_text()
    assert (store.agent_path(nora) / "hermes/skills/ux-method/SKILL.md").exists()
    assert client.put(f"/api/agents/{nora['id']}/model", json={"model": "gpt-6.1-sol", "effort": "low"}).status_code == 200
    assert client.put("/api/settings/model", json={"model": "gpt-6.1-sol", "effort": "none"}).status_code == 400


def test_chat_contract_with_hermes_double(client, app):
    p = project(client)
    agent = client.get("/api/state").json()["agents"][0]
    app.state.store.secret("openai", "test-key-never-sent-to-openai")
    app.state.store.execute("UPDATE agents SET container_id='docker-double' WHERE id=?", (agent["id"],))

    class ConversationalDouble(TestRuntime):
        async def chat(self, a, store, text, request_id):
            assert a["model"] == "gpt-6.1-sol" and a["effort"] == "xhigh"
            if text == "Crea un agente UX":
                return "¿Cómo quieres llamar al nuevo agente UX?", "completed"
            app.state.service.tool(a, "create_ux_agent", {"name": text})
            return f"El perfil {text} está creado; su runtime sigue pendiente.", "completed"
    app.state.service.runtime = ConversationalDouble()
    for text, rid in [("Crea un agente UX", "first"), ("Nora", "second")]:
        assert client.post(f"/api/agents/{agent['id']}/chat", json={"content": text, "request_id": rid}).status_code == 200
    retry = client.post(f"/api/agents/{agent['id']}/chat", json={"content": "Nora", "request_id": "second"})
    assert retry.status_code == 200
    assert len(client.get(f"/api/agents/{agent['id']}/messages").json()) == 4
    assert len(client.get("/api/state").json()["agents"]) == 2
    assert client.post(f"/api/agents/{agent['id']}/chat", json={"content": "Otro", "request_id": "second"}).status_code == 409


def test_hermes_wire_uses_responses_not_chat_completions(client, app):
    import asyncio
    p = project(client)
    agent = client.get("/api/state").json()["agents"][0]
    agent["container_id"] = "double"
    runtime = DockerRuntime()
    fake_container = MagicMock()
    fake_container.attrs = {"NetworkSettings": {"Ports": {"8642/tcp": [{"HostPort": "12345"}]}}}
    fake_client = MagicMock()
    fake_client.containers.get.return_value = fake_container
    seen = []

    async def handler(request):
        import httpx
        seen.append(request)
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Hola"}]}]})
    import httpx
    real_async_client = httpx.AsyncClient
    with patch.object(runtime, "client", return_value=fake_client), patch("backend.runtime.httpx.AsyncClient", side_effect=lambda **kwargs: real_async_client(transport=httpx.MockTransport(handler))):
        answer, status = asyncio.run(runtime.chat(agent, app.state.store, "Hola", "request-123"))
    assert answer == "Hola" and status == "completed"
    request = seen[0]
    assert request.url.path == "/v1/responses"
    payload = json.loads(request.content)
    assert payload["provider"] == "openai-api" and payload["model_options"]["reasoning_effort"] == "xhigh"
    assert request.headers["Idempotency-Key"] == "request-123"


def test_docker_lifecycle_contract_and_readiness(client, app, monkeypatch):
    import docker
    import httpx
    monkeypatch.delenv("HAPIC_IN_DOCKER", raising=False)
    p = project(client)
    agent = client.get("/api/state").json()["agents"][0]
    store = app.state.store
    store.secret("openai", "test-key-only-for-a-docker-double")
    runtime = DockerRuntime()
    sdk = MagicMock()
    sdk.containers.get.side_effect = docker.errors.NotFound("not found")
    container = MagicMock()
    container.id = "test-container-id"
    container.status = "running"
    container.attrs = {"NetworkSettings": {"Ports": {"8642/tcp": [{"HostPort": "12345"}]}}}
    sdk.containers.run.return_value = container
    with patch.object(runtime, "client", return_value=sdk), patch("backend.runtime.httpx.get", return_value=httpx.Response(200, json={"status": "ok"})):
        result = runtime.start(agent, store)
    assert result["status"] == "running"
    args, kwargs = sdk.containers.run.call_args
    assert args[1] == ["gateway", "run"]
    assert len(kwargs["volumes"]) == 2
    assert not any("docker.sock" in x for x in kwargs["volumes"])
    assert kwargs["ports"]["8642/tcp"][0] == "127.0.0.1"
    assert kwargs["environment"]["HERMES_HOME"] == "/opt/data"
    assert kwargs["environment"]["OPENAI_API_KEY"] == store.api_key()
    config = yaml.safe_load((store.agent_path(agent) / "hermes/config.yaml").read_text())
    assert config["platform_toolsets"]["api_server"] == ["memory", "hapic"]
    assert store.api_key() not in json.dumps(config)
    with patch.object(runtime, "client", return_value=sdk), patch("backend.runtime.httpx.get", return_value=httpx.Response(200, json={"status": "degraded"})), patch("backend.runtime.time.sleep"):
        with pytest.raises(RuntimeUnavailable, match="aún no está lista"):
            runtime.start(agent, store)


def test_specialist_catalog_creation_and_scope(client, app):
    p = project(client)
    catalog = client.get("/api/templates").json()
    assert {t["kind"] for t in catalog} == {"ux", "graphic-designer", "architect", "coder", "community-manager"}
    architect_template = next(t for t in catalog if t["kind"] == "architect")
    assert architect_template["recommended_model"] == "gpt-6.1-sol"
    assert architect_template["recommended_effort"] == "high"
    architect = client.post(f"/api/projects/{p['id']}/agents", json={"name": "Ada", "template": "architect"}).json()
    for kind in ("graphic-designer", "coder", "community-manager"):
        response = client.post(f"/api/projects/{p['id']}/agents", json={"name": kind, "template": kind, "planner_id": architect["id"] if kind == "coder" else None})
        assert response.status_code == 201
        agent = response.json()
        assert agent["kind"] == kind and agent["template"] == kind + "-v1"
        home = app.state.store.agent_path(agent) / "hermes"
        assert (home / "SOUL.md").exists() and "Sin recuerdos" in (home / "memories/MEMORY.md").read_text(encoding="utf-8")
        config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
        assert ("generate_project_image" in config["mcp_servers"]["hapic"]["tools"]["include"]) == (kind == "graphic-designer")
    assert client.post(f"/api/projects/{p['id']}/agents", json={"name": "bad", "template": "../secrets"}).status_code == 400
    assert client.post(f"/api/projects/{p['id']}/agents", json={"name": "bad", "template": "coder"}).status_code == 400
    other_project = project(client)
    assert client.post(f"/api/projects/{other_project['id']}/agents", json={"name": "bad", "template": "coder", "planner_id": architect["id"]}).status_code == 400
    designer = next(a for a in client.get("/api/state").json()["agents"] if a["kind"] == "graphic-designer")
    with pytest.raises(PermissionError):
        app.state.service.tool(designer, "create_specialist_agent", {"name": "No", "template": "architect"})


def test_community_manager_mcp_creation_and_drafts_with_unconnected_youtube(client, app):
    p = project(client)
    service, store = app.state.service, app.state.store
    hapic = store.one("SELECT * FROM agents WHERE project_id=? AND kind='hapic'", (p["id"],))
    headers = {"Authorization": "Bearer " + store.token(hapic["id"], "mcp"), "Accept": "application/json, text/event-stream"}
    args = {"name": "Alma", "template": "community-manager"}
    # Exercise the real MCP transport without Docker or paid model calls.
    with patch.object(service, "provision"):
        result = client.post("/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "create_specialist_agent", "arguments": args}})
    assert result.status_code == 200 and not result.json()["result"].get("isError", False)
    manager = store.one("SELECT * FROM agents WHERE project_id=? AND name='Alma'", (p["id"],))
    assert manager["kind"] == "community-manager" and manager["container_id"] is None
    repeated = service.tool(hapic, "create_specialist_agent", args)
    assert repeated["already_exists"] and repeated["id"] == manager["id"]
    config = yaml.safe_load((store.agent_path(manager) / "hermes/config.yaml").read_text(encoding="utf-8"))
    assert set(config["mcp_servers"]["hapic"]["tools"]["include"]) == {"project_list_files", "project_read_file", "project_write_file", "youtube_get_channel", "youtube_list_videos", "youtube_list_comments", "youtube_get_analytics"}
    with pytest.raises(ValueError, match="pendiente de conexión"):
        service.tool(manager, "youtube_get_channel", {})
    draft = "id,fecha,canal,estado\n1,2026-11-06,instagram,borrador\n"
    saved = service.tool(manager, "project_write_file", {"path": "calendario-editorial.csv", "content": draft})
    assert saved["saved"]
    restarted = Service(Store(store.root), TestRuntime())
    assert restarted.tool(restarted.agent(manager["id"]), "project_read_file", {"path": "calendario-editorial.csv"})["content"] == draft
    for tool in ("publish_social_post", "reply_social_comment", "get_social_metrics", "generate_project_image", "create_specialist_agent"):
        with pytest.raises(PermissionError):
            service.tool(manager, tool, {})
    assert any(a["id"] == manager["id"] for a in service.tool(hapic, "list_project_agents", {})["agents"])
    assert store.all("SELECT * FROM messages WHERE agent_id=?", (manager["id"],)) == []


def test_coder_requires_current_plan_and_keeps_workspaces_separate(client, app):
    p = project(client)
    service = app.state.service
    architect = service.create_agent(p["id"], "Ada", "architect")
    coder = service.create_agent(p["id"], "Lin", "coder", architect["id"])
    with pytest.raises(ValueError, match="no ha publicado"):
        service.tool(coder, "get_architecture_plan", {})
    plan = "# Plan\nCrear src/app.py con una función hello que devuelva hola. Probar con pytest."
    published = service.tool(architect, "publish_architecture_plan", {"content": plan})
    assert published["saved"]
    assert client.get(f"/api/projects/{p['id']}/file", params={"path": published["path"]}).json()["content"] == plan
    with pytest.raises(ValueError, match="Lee el plan"):
        service.tool(coder, "project_write_file", {"path": "src/app.py", "content": "def hello(): return 'hola'"})
    read = service.tool(coder, "get_architecture_plan", {})
    assert read["content"] == plan and read["revision"] == published["revision"]
    assert service.tool(coder, "project_write_file", {"path": "src/app.py", "content": "def hello(): return 'hola'"})["saved"]
    assert service.tool(architect, "project_list_files", {}) == {"files": []}
    service.tool(architect, "publish_architecture_plan", {"content": plan + "\nAñadir un caso de error."})
    with pytest.raises(ValueError, match="Lee el plan"):
        service.tool(coder, "project_write_file", {"path": "tests/test_app.py", "content": "# test"})
    service.tool(coder, "get_architecture_plan", {})
    assert service.tool(coder, "project_write_file", {"path": "tests/test_app.py", "content": "# test"})["saved"]
    with pytest.raises(PermissionError):
        service.tool(coder, "publish_architecture_plan", {"content": "Override"})


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j/+kAAAAASUVORK5CYII=")


def test_images_persist_chat_preview_download_and_restart(client, app):
    p = project(client)
    service = app.state.service
    designer = service.create_agent(p["id"], "Miro", "graphic-designer")
    with patch.object(service.images, "generate", return_value=PNG):
        result = service.tool(designer, "generate_project_image", {"prompt": "Un círculo naranja"})
    assert result["saved"] and result["path"].startswith("images/")
    assert (app.state.store.agent_path(designer) / "workspace" / result["path"]).read_bytes() == PNG
    messages = client.get(f"/api/agents/{designer['id']}/messages").json()
    attachment = messages[0]["attachments"][0]
    assert messages[0]["source"] == "artifact"
    response = client.get(attachment["url"])
    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert "no-store" in response.headers["cache-control"] and response.headers["x-content-type-options"] == "nosniff"
    response = client.get(attachment["url"] + "&download=true")
    assert response.headers["content-disposition"].startswith("attachment;")
    tree = client.get(f"/api/projects/{p['id']}/tree").json()
    def descendants(node):
        yield node
        for child in node.get("children", []):
            yield from descendants(child)
    image = next(n for n in descendants(tree) if n["path"] == attachment["path"])
    assert image["media_type"] == "image" and image["preview"]
    restarted = Service(Store(app.state.store.root), TestRuntime())
    assert restarted.messages(designer["id"])[0]["attachments"][0] == attachment
    assert restarted.image_file(p["id"], attachment["path"])[0].read_bytes() == PNG
    # Session authentication also applies to image bytes, not only JSON routes.
    client.cookies.clear()
    assert client.get(attachment["url"]).status_code == 401


def test_image_paths_signatures_membership_and_tool_permissions(client, app):
    p = project(client)
    service = app.state.service
    ux = service.create_agent(p["id"], "Nora")
    architect = service.create_agent(p["id"], "Ada", "architect")
    with pytest.raises(PermissionError):
        service.tool(architect, "generate_project_image", {"prompt": "No"})
    root = app.state.store.agent_path(ux)
    (root / "workspace/bad.png").write_text("<script>alert(1)</script>")
    (root / "hermes/private.png").write_bytes(PNG)
    for relative in ["../../secrets/key.png", f"agents/{ux['id']}/hermes/private.png", f"agents/{ux['id']}/workspace/bad.png", f"agents/{ux['id']}/workspace/../hermes/private.png"]:
        assert client.get(f"/api/projects/{p['id']}/image", params={"path": relative}).status_code == 400
    with patch.object(service.images, "generate", return_value=PNG):
        service.tool(ux, "generate_project_image", {"prompt": "Un círculo"})
    attachment = service.messages(ux["id"])[0]["attachments"][0]
    p2 = project(client)
    assert client.get(f"/api/projects/{p2['id']}/image", params={"path": attachment["path"]}).status_code == 400
    app.state.store.execute("DELETE FROM memberships")
    assert client.get(attachment["url"]).status_code == 404


def test_images_api_contract_and_redacted_failures(monkeypatch):
    import base64
    import httpx
    from backend.images import ImageGenerator
    monkeypatch.delenv("HAPIC_IMAGE_MODEL", raising=False)
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})
    real_client = httpx.Client
    with patch("backend.images.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler))):
        assert ImageGenerator().generate("dummy-never-sent", "A circle", "1536x1024") == PNG
    payload = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.openai.com/v1/images/generations"
    assert payload == {"model": "gpt-image-2.5-flare", "prompt": "A circle", "n": 1, "size": "1536x1024", "quality": "medium", "output_format": "png"}
    for response in [httpx.Response(403, text="secret-provider-body"), httpx.Response(200, json={"data": [{"url": "http://169.254.169.254/private"}]}), httpx.Response(200, json={"data": [{"b64_json": "invalid"}]})]:
        with patch("backend.images.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: response))):
            with pytest.raises(RuntimeUnavailable) as error:
                ImageGenerator().generate("dummy-never-sent", "Circle")
            assert "secret-provider-body" not in str(error.value) and "169.254" not in str(error.value)


def test_failed_chat_keeps_already_generated_image(client, app):
    p = project(client)
    service = app.state.service
    designer = service.create_agent(p["id"], "Miro", "graphic-designer")
    app.state.store.secret("openai", "dummy-never-sent")
    app.state.store.execute("UPDATE agents SET container_id='double' WHERE id=?", (designer["id"],))
    class ImageThenFailure(TestRuntime):
        async def chat(self, agent, store, text, request_id):
            with patch.object(service.images, "generate", return_value=PNG):
                service.tool(agent, "generate_project_image", {"prompt": text})
            raise RuntimeUnavailable("Hermes double failed after generation")
    service.runtime = ImageThenFailure()
    assert client.post(f"/api/agents/{designer['id']}/chat", json={"content": "Circle"}).status_code == 503
    messages = service.messages(designer["id"])
    assert len(messages) == 2 and messages[-1]["attachments"]
    assert client.get(messages[-1]["attachments"][0]["url"]).content == PNG

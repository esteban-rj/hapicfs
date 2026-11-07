import json
from unittest.mock import MagicMock, patch

import docker
import pytest

from backend.service import Service
from backend.storage import Store
from backend.runtime import DockerRuntime


@pytest.fixture
def sharing(tmp_path):
    service = Service(Store(tmp_path))
    org = service.create_org("Sharing")
    project = service.create_project(org["id"], "Game")
    architect = service.create_agent(project["id"], "Planner", "architect")
    coder = service.create_agent(project["id"], "Coder", "coder", architect["id"])
    return service, architect, coder


def test_sharing_requires_user_authorization_and_scoped_tool(sharing):
    service, architect, coder = sharing
    with patch.object(DockerRuntime, "client") as client:
        with pytest.raises(ValueError, match="Pregunta al usuario"):
            service.development.share(coder, "start")
        client.assert_not_called()
    with pytest.raises(PermissionError):
        service.tool(architect, "development_share", {"action": "start", "user_approved": True})
    with pytest.raises(ValueError, match="plan"):
        service.tool(coder, "development_share", {"action": "start", "user_approved": True})


def test_sharing_isolated_target_and_reuses_existing_tunnel(sharing):
    service, _, coder = sharing
    labels = {"hapic.development": coder["id"], "hapic.installation": str(service.store.root)}
    preview = MagicMock(id="preview-id", status="running", labels=labels)
    tunnel = MagicMock(id="tunnel-id", status="running", labels={**labels, "hapic.preview": preview.id})
    tunnel.logs.return_value = json.dumps({"type": "v1.tcpip_forward.register.accepted", "data": "https://game-test.lhr.life\r\n"}).encode()
    current = {}
    client = MagicMock()
    def get(name):
        if name == "hapic-preview-" + coder["id"]:
            return preview
        if name in current:
            return current[name]
        raise docker.errors.NotFound("missing")
    def run(**kwargs):
        current[kwargs["name"]] = tunnel
        return tunnel
    client.containers.get.side_effect = get
    client.containers.run.side_effect = run
    with patch.object(DockerRuntime, "client", return_value=client), patch("backend.development.httpx.get", return_value=MagicMock(status_code=200)):
        result = service.development.share(coder, "start", True)
        assert result["url"] == "https://game-test.lhr.life" and result["http_verified"]
        assert service.development.share(coder, "start", True)["url"] == result["url"]
        tunnel.logs.return_value = b'registration no longer in the bounded log tail'
        assert service.development.share(coder)["url"] == result["url"]
    client.containers.run.assert_called_once()
    options = client.containers.run.call_args.kwargs
    assert options["network_mode"] == "container:preview-id"
    assert "80:127.0.0.1:3000" in options["command"]
    assert options["read_only"] and options["cap_drop"] == ["ALL"]
    assert not {"ports", "volumes"} & options.keys()
    assert set(options["environment"]) == {"HOME"}


def test_sharing_never_replaces_foreign_container(sharing):
    service, _, coder = sharing
    client = MagicMock()
    foreign = MagicMock(labels={"hapic.development": "someone-else"})
    client.containers.get.return_value = foreign
    with patch.object(DockerRuntime, "client", return_value=client):
        for action in ("start", "status", "stop"):
            with pytest.raises(PermissionError):
                service.development.share(coder, action, True)
    foreign.remove.assert_not_called()
    client.containers.run.assert_not_called()


def test_tunnel_output_cannot_redirect_health_probe_to_arbitrary_host():
    from backend.development import Development
    for url in ("http://game.lhr.life", "https://127.0.0.1", "https://game.lhr.life.evil.test", "https://game.lhr.life:8000"):
        output = json.dumps({"type": "v1.tcpip_forward.register.accepted", "data": url})
        assert Development.tunnel_url(output) is None
    assert Development.tunnel_url('not-json\n' + json.dumps({"type": "request", "data": "https://game.lhr.life"})) is None


def test_changed_preview_hides_old_url_and_stop_clears_state(sharing):
    service, _, coder = sharing
    labels = {"hapic.development": coder["id"], "hapic.installation": str(service.store.root)}
    tunnel = MagicMock(id="old-tunnel", status="running", labels={**labels, "hapic.preview": "old-preview"})
    preview = MagicMock(id="new-preview", status="running", labels=labels)
    client = MagicMock()
    client.containers.get.side_effect = lambda name: tunnel if name.startswith("hapic-share-") else preview
    key = "development-share-" + coder["id"]
    service.store.set_setting(key, {"url": "https://old.lhr.life"})
    with patch.object(DockerRuntime, "client", return_value=client), patch("backend.development.httpx.get") as get:
        assert service.development.share(coder)["status"] == "stale"
        assert service.development.share(coder)["url"] is None
        get.assert_not_called()
        assert service.development.share(coder, "stop")["status"] == "stopped"
    tunnel.remove.assert_called_once_with(force=True)
    assert service.store.setting(key) is None


def test_sharing_cannot_start_without_its_own_preview(sharing):
    service, _, coder = sharing
    client = MagicMock()
    client.containers.get.side_effect = docker.errors.NotFound("missing")
    with patch.object(DockerRuntime, "client", return_value=client):
        with pytest.raises(ValueError, match="vista previa"):
            service.development.share(coder, "start", True)
    client.containers.run.assert_not_called()

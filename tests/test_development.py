from unittest.mock import MagicMock, patch

import pytest

from backend.service import Service
from backend.storage import Store
from backend.runtime import DockerRuntime
from backend.tool_catalog import effective_tools


@pytest.fixture
def setup(tmp_path):
    service = Service(Store(tmp_path))
    org = service.create_org("Runner tests")
    project = service.create_project(org["id"], "Dev")
    architect = service.create_agent(project["id"], "Planner", "architect")
    coder = service.create_agent(project["id"], "Coder", "coder", architect["id"])
    return service, architect, coder


def test_defaults_permissions_plan_and_disabled_survives_restart(setup):
    service, architect, coder = setup
    assert "development_run" in effective_tools(coder, service.store)
    with pytest.raises(PermissionError):
        service.tool(architect, "development_run", {"command": "pwd"})
    service.tool(architect, "publish_architecture_plan", {"content": "Implementar y probar un prototipo local."})
    with pytest.raises(ValueError, match="plan vigente"):
        service.tool(coder, "development_run", {"command": "pwd"})
    service.tool(coder, "get_architecture_plan", {})
    with patch.object(service.development, "run", return_value={"exit_code": 0}) as run:
        assert service.tool(coder, "development_run", {"command": "pwd"})["exit_code"] == 0
        run.assert_called_once()
    service.tool(architect, "publish_architecture_plan", {"content": "Una revisión diferente."})
    with pytest.raises(ValueError, match="plan vigente"):
        service.tool(coder, "development_run", {"command": "pwd"})
    with patch.object(service.development, "preview"):
        service.assign_tool(coder["id"], "development", False)
    assert "development_run" not in effective_tools(coder, Service(service.store).store)
    with pytest.raises(PermissionError):
        service.tool(coder, "development_run", {"command": "pwd"})
    with pytest.raises(ValueError, match="no requiere"):
        service.assign_tool(architect["id"], "development", True, "some-connection")
    service.assign_tool(architect["id"], "development", True)
    assert "development_run" in effective_tools(architect, service.store)


def test_runner_isolation_exit_cleanup_and_limits(setup):
    service, _, coder = setup
    options = service.development.options(coder)
    assert options["cap_drop"] == ["ALL"] and options["read_only"]
    assert options["user"] == "10000:10000"
    assert len(options["volumes"]) == 1
    assert next(iter(options["volumes"].values()))["bind"] == "/workspace"
    assert not {"OPENAI_API_KEY", "HAPIC_MCP_TOKEN", "API_SERVER_KEY"} & options["environment"].keys()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 7}
    container.logs.return_value = b"x" * 30000
    with patch.object(service.development, "create", return_value=container):
        result = service.development.run(coder, "exit 7")
    assert result["exit_code"] == 7 and len(result["output"]) == 20000
    container.remove.assert_called_once_with(force=True)
    for timeout in (0, 121):
        with pytest.raises(ValueError):
            service.development.run(coder, "pwd", timeout)
    with pytest.raises(ValueError):
        service.development.run(coder, "")


def test_preview_checks_ownership_before_replacing(setup):
    service, _, coder = setup
    client = MagicMock()
    client.containers.get.return_value.labels = {"hapic.development": "someone-else"}
    with patch.object(DockerRuntime, "client", return_value=client):
        with pytest.raises(PermissionError):
            service.development.preview(coder, "stop")
    client.containers.get.return_value.remove.assert_not_called()

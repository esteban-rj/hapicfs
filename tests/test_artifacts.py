import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.artifacts import artifact_file, list_artifacts
from backend.runtime import DockerRuntime


def test_deliverables_are_local_scoped_and_render_html_as_text(tmp_path):
    app = create_app(tmp_path)
    service = app.state.service
    org = service.create_org('Estudio')
    project = service.create_project(org['id'], 'Campaña')
    manager = service.create_agent(project['id'], 'Mariana', 'community-manager')
    service.tool(manager, 'project_write_file', {'path': 'guiones.md', 'content': '# Guion real\nEscena de apertura.'})
    service.tool(manager, 'project_write_file', {'path': 'pieza.html', 'content': '<script>alert(1)</script>'})
    private = service.store.agent_path(manager) / 'hermes/memories/USER.md'
    private.write_text('Privado')
    files = list_artifacts(service, project['id'])['files']
    assert {item['name'] for item in files} == {'guiones.md', 'pieza.html'}
    assert all(item['agent_name'] == 'Mariana' for item in files)
    script = next(item for item in files if item['name'] == 'pieza.html')
    with TestClient(app, base_url='http://localhost') as client:
        assert client.get(script['url']).status_code == 401
        client.get('/api/bootstrap')
        response = client.get(script['url'])
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/plain')
        assert 'attachment' in client.get(script['download_url']).headers['content-disposition']
    with pytest.raises(ValueError):
        artifact_file(service, project['id'], f"agents/{manager['id']}/hermes/memories/USER.md")
    other = service.create_project(org['id'], 'Otro')
    with pytest.raises(ValueError):
        artifact_file(service, other['id'], script['path'])


def test_task_receipt_attaches_actual_document_to_coordinator(tmp_path):
    app = create_app(tmp_path)
    service = app.state.service
    org = service.create_org('Estudio')
    project = service.create_project(org['id'], 'Campaña')
    manager = service.create_agent(project['id'], 'Mariana', 'community-manager')
    coordinator = service.store.one("SELECT * FROM agents WHERE kind='hapic'")
    service.store.secret('openai', 'test-not-real')
    service.store.execute("UPDATE agents SET container_id='test' WHERE id=?", (manager['id'],))
    async def deliver(*args):
        service.tool(manager, 'project_write_file', {'path': 'guion.md', 'content': 'Guion guardado realmente'})
        return 'Guion en guion.md', 'completed'
    service.runtime.chat = deliver
    task = service.tasks.create(coordinator, manager['id'], 'Preparar guion', '', [], ['guion.md'])
    asyncio.run(service.tasks.run(coordinator, task['id']))
    service.tasks.publish_updates()
    receipt = next(m for m in service.messages(coordinator['id']) if 'Entrega recibida' in m['content'])
    attachment = receipt['attachments'][0]
    assert attachment['name'] == 'guion.md'
    assert attachment['agent_name'] == 'Mariana'
    assert attachment['mime_type'] == 'text/plain'
    assert Path(artifact_file(service, project['id'], attachment['path'])[0]).read_text() == 'Guion guardado realmente'


def test_generated_image_is_included_even_without_a_predetermined_filename(tmp_path):
    import base64
    import json
    from unittest.mock import patch
    app = create_app(tmp_path)
    service = app.state.service
    org = service.create_org('Estudio')
    project = service.create_project(org['id'], 'Visuales')
    designer = service.create_agent(project['id'], 'Diseño', 'graphic-designer')
    coordinator = service.store.one("SELECT * FROM agents WHERE kind='hapic'")
    service.store.secret('openai', 'test-not-real')
    service.store.execute("UPDATE agents SET container_id='test' WHERE id=?", (designer['id'],))
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j/+kAAAAASUVORK5CYII=')
    async def deliver(*args):
        with patch.object(service.images, 'generate', return_value=png):
            service.tool(designer, 'generate_project_image', {'prompt': 'Un círculo'})
        service.tool(designer, 'project_write_file', {'path': 'entrega.md', 'content': 'PNG guardado'})
        return 'Imagen real y documento', 'completed'
    service.runtime.chat = deliver
    task = service.tasks.create(coordinator, designer['id'], 'Generar imagen', '', [], ['entrega.md'])
    result = asyncio.run(service.tasks.run(coordinator, task['id']))
    assert result['state'] == 'delivered'
    assert len(json.loads(result['result'])['evidence']) == 2
    service.tasks.publish_updates()
    receipt = next(m for m in service.messages(coordinator['id']) if 'Entrega recibida' in m['content'])
    assert {a['mime_type'] for a in receipt['attachments']} == {'text/plain', 'image/png'}

"""Local orchestration contracts; no inference, Docker or external effects."""
import asyncio
import json

import pytest

from backend.runtime import DockerRuntime
from backend.service import Service
from backend.storage import Store


class LocalRuntime(DockerRuntime):
    calls = 0
    fail = False

    async def chat(self, agent, store, text, request_id):
        self.calls += 1
        if self.fail:
            raise RuntimeError('tool failed with sensitive provider detail')
        root = store.agent_path(agent) / 'workspace'
        (root / 'index.html').write_text('<html><button>Jugar</button></html>', encoding='utf-8')
        return 'Entregado; navegador pendiente.', 'completed'


def setup(tmp_path):
    runtime = LocalRuntime()
    service = Service(Store(tmp_path), runtime)
    org = service.create_org('Estudio')
    project = service.create_project(org['id'], 'Juego')
    hapic = service.store.one("SELECT * FROM agents WHERE kind='hapic'")
    ux = service.create_agent(project['id'], 'UX', 'ux')
    service.store.execute("UPDATE agents SET container_id='test-only' WHERE id=?", (ux['id'],))
    service.store.secret('openai', 'test-only-not-a-real-key')
    return service, hapic, ux, runtime


def test_delegate_persist_and_never_claim_verified(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    task = service.tasks.create(hapic, ux['id'], 'Quiero crear un juego', 'Prototipo local', [], ['index.html'])
    result = asyncio.run(service.tasks.run(hapic, task['id']))
    assert result['state'] == 'delivered'
    evidence = json.loads(result['result'])['evidence'][0]
    assert evidence['bytes'] > 0 and len(evidence['sha256']) == 64
    restarted = Service(Store(tmp_path), runtime)
    assert restarted.tasks.get(hapic, task['id']) == result
    asyncio.run(restarted.tasks.run(hapic, task['id']))
    assert runtime.calls == 1


def test_failure_and_recovery_preserve_files(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    root = service.store.agent_path(ux) / 'workspace'
    (root / 'progress.md').write_text('Avance conservado')
    first = service.tasks.create(hapic, ux['id'], 'Implementar', '', [], ['index.html'])
    runtime.fail = True
    result = asyncio.run(service.tasks.run(hapic, first['id']))
    assert result['state'] == 'failed' and 'sensitive' not in result['result']
    asyncio.run(service.tasks.run(hapic, first['id']))
    assert runtime.calls == 1
    service = Service(Store(tmp_path), runtime)
    assert (root / 'progress.md').read_text() == 'Avance conservado'
    recovery = service.tasks.create(hapic, ux['id'], 'Completar avance existente', 'Leer progress.md primero', [], ['index.html'])
    runtime.fail = False
    assert asyncio.run(service.tasks.run(hapic, recovery['id']))['state'] == 'delivered'


def test_permissions_dependencies_and_interrupted_state(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    first = service.tasks.create(hapic, ux['id'], 'Diseño', '', [], ['index.html'])
    second = service.tasks.create(hapic, ux['id'], 'Implementar', '', [first['id']], ['index.html'])
    assert asyncio.run(service.tasks.run(hapic, second['id']))['state'] == 'blocked'
    with pytest.raises(PermissionError):
        service.tasks.list(ux)
    with pytest.raises(ValueError):
        service.tasks.create(hapic, ux['id'], 'Escape', '', [], ['../escape.html'])
    org = service.create_org('Otro')
    other_project = service.create_project(org['id'], 'Otro')
    other = service.create_agent(other_project['id'], 'Otro UX', 'ux')
    with pytest.raises(PermissionError):
        service.tasks.create(hapic, other['id'], 'Fuera', '', [], ['index.html'])
    service.store.execute("UPDATE tasks SET state='running', attempts=1 WHERE id=?", (first['id'],))
    restarted = Service(Store(tmp_path), runtime)
    assert asyncio.run(restarted.tasks.run(hapic, first['id']))['state'] == 'running'
    assert runtime.calls == 0


def test_architect_coder_game_contract_uses_real_tools(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    architect = service.create_agent(hapic['project_id'], 'Arquitectura', 'architect')
    coder = service.create_agent(hapic['project_id'], 'Desarrollo', 'coder', architect['id'])
    for agent in (architect, coder):
        service.store.execute("UPDATE agents SET container_id='test-only' WHERE id=?", (agent['id'],))

    async def scripted_turn(agent, store, text, request_id):
        # Explicit inference double. All file, permission and plan tools are real.
        if agent['kind'] == 'architect':
            plan = 'Juego web local: pulsar el botón suma puntos. Sin red. Verificar en navegador.'
            service.tool(agent, 'project_write_file', {'path': 'plan.md', 'content': plan})
            service.tool(agent, 'publish_architecture_plan', {'content': plan})
        else:
            service.tool(agent, 'get_architecture_plan', {})
            service.tool(agent, 'project_write_file', {'path': 'index.html', 'content': '<!doctype html><meta charset="utf-8"><title>Juego</title><button onclick="this.textContent=++score">0</button><script>let score=0</script>'})
            service.tool(agent, 'project_write_file', {'path': 'README.md', 'content': 'Abre index.html y pulsa el botón. Jugabilidad pendiente de validación en navegador.'})
        return 'Archivos entregados. No se ejecutó navegador.', 'completed'

    runtime.chat = scripted_turn
    design = service.tasks.create(hapic, architect['id'], 'Definir juego mínimo', 'Web local', [], ['plan.md'])
    development = service.tasks.create(hapic, coder['id'], 'Crear juego', 'Sin marketing', [design['id']], ['index.html', 'README.md'])
    assert asyncio.run(service.tasks.run(hapic, development['id']))['state'] == 'blocked'
    assert asyncio.run(service.tasks.run(hapic, design['id']))['state'] == 'delivered'
    result = asyncio.run(service.tasks.run(hapic, development['id']))
    assert result['state'] == 'delivered'
    assert len(json.loads(result['result'])['evidence']) == 2


def test_cancel_preserves_progress_and_requires_explicit_recovery(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    task = service.tasks.create(hapic, ux['id'], 'Trabajo interrumpible', '', [], ['index.html'])

    async def scenario():
        started = asyncio.Event()

        async def interrupted(agent, store, text, request_id):
            (store.agent_path(agent) / 'workspace' / 'progress.md').write_text('Paso 1 guardado')
            started.set()
            await asyncio.Event().wait()

        runtime.chat = interrupted
        pending = asyncio.create_task(service.tasks.run(hapic, task['id']))
        await started.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    asyncio.run(scenario())
    restarted = Service(Store(tmp_path), runtime)
    assert restarted.tasks.get(hapic, task['id'])['state'] == 'failed'
    assert (service.store.agent_path(ux) / 'workspace' / 'progress.md').read_text() == 'Paso 1 guardado'
    assert asyncio.run(restarted.tasks.run(hapic, task['id']))['state'] == 'failed'


def test_queue_waits_for_dependencies_and_runs_automatically(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    first = service.tasks.create(hapic, ux['id'], 'Primero', '', [], ['index.html'])
    second = service.tasks.create(hapic, ux['id'], 'Después', '', [first['id']], ['index.html'])
    assert service.tasks.enqueue(hapic, second['id'])['state'] == 'queued'
    service.tasks.dispatch_once()
    assert runtime.calls == 0
    service.tasks.enqueue(hapic, first['id'])
    service.tasks.dispatch_once()
    for thread in list(service.tasks.workers.values()):
        thread.join(5)
    assert service.tasks.get(hapic, first['id'])['state'] == 'delivered'
    service.tasks.dispatch_once()
    for thread in list(service.tasks.workers.values()):
        thread.join(5)
    assert service.tasks.get(hapic, second['id'])['state'] == 'delivered'
    assert runtime.calls == 2
    assert service.tasks.enqueue(hapic, second['id'])['state'] == 'delivered'


def test_video_report_without_mp4_cannot_complete_a_media_task(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    task = service.tasks.create(hapic, ux['id'], 'Entregar vídeo', '', [], ['index.html'], expected_videos=1)
    result = asyncio.run(service.tasks.run(hapic, task['id']))
    assert result['state'] == 'blocked'
    evidence = json.loads(result['result'])
    assert evidence['missing_media'] == {'videos': 1}
    service.tasks.publish_updates()
    receipt = next(message for message in service.messages(hapic['id']) if task['id'] in message['content'])
    assert '1 vídeos MP4' in receipt['content']
    assert '"missing_media"' not in receipt['content']


def test_coordinator_can_recover_only_an_idle_specialist_in_its_project(tmp_path):
    from unittest.mock import patch
    from backend.runtime import RuntimeUnavailable
    service, hapic, ux, runtime = setup(tmp_path)
    with patch.object(runtime, 'start', return_value={'status': 'running', 'container_id': 'renewed'}) as start:
        service.lock(ux['id']).acquire()
        try:
            with pytest.raises(RuntimeUnavailable):
                service.tool(hapic, 'restart_specialist_agent', {'agent_id': ux['id']})
            start.assert_not_called()
        finally:
            service.lock(ux['id']).release()
        root = service.store.agent_path(ux) / 'workspace'
        (root / 'progress.md').write_text('Conservar')
        assert service.tool(hapic, 'restart_specialist_agent', {'agent_id': ux['id']})['restarted']
        assert service.store.setting('runtime-epoch-' + ux['id']) == 1
        assert (root / 'progress.md').read_text() == 'Conservar'
        assert not service.lock(ux['id']).locked()
        with pytest.raises(PermissionError):
            service.tool(ux, 'restart_specialist_agent', {'agent_id': ux['id']})
        other = service.create_project(hapic['organization_id'], 'Otro')
        foreign = service.create_agent(other['id'], 'Otro UX', 'ux')
        with pytest.raises(PermissionError):
            service.tool(hapic, 'restart_specialist_agent', {'agent_id': foreign['id']})


def test_recovery_delivers_a_named_existing_image_without_generating_it_again(tmp_path):
    import base64
    from backend.storage import now
    service, hapic, ux, runtime = setup(tmp_path)
    root = service.store.agent_path(ux) / 'workspace'
    (root / 'images').mkdir()
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII=')
    (root / 'images/existing.png').write_bytes(png)
    path = f"agents/{ux['id']}/workspace/images/existing.png"
    service.store.execute('INSERT INTO images VALUES (?,?,?,?,?,?)', ('img-existing', ux['id'], None, path, 'image/png', now()))
    task = service.tasks.create(hapic, ux['id'], 'Conservar', 'Conserva images/existing.png sin generar otra.', [], ['index.html'], expected_images=1)
    result = asyncio.run(service.tasks.run(hapic, task['id']))
    assert result['state'] == 'delivered'
    assert any(item['path'] == 'images/existing.png' for item in json.loads(result['result'])['evidence'])


def test_coordinator_inspects_real_progress_after_a_failed_task(tmp_path):
    service, hapic, ux, _ = setup(tmp_path)
    task = service.tasks.create(hapic, ux['id'], 'Probar', '', [], ['cierre.md'])
    root = service.store.agent_path(ux) / 'workspace'
    (root / 'cierre.md').write_text('Pruebas locales ejecutadas; publicación pendiente.', encoding='utf-8')
    service.store.execute("UPDATE tasks SET state='failed' WHERE id=?", (task['id'],))
    result = service.tasks.inspect(hapic, task['id'])
    assert result['files'][0]['available']
    assert 'publicación pendiente' in result['files'][0]['content']
    foreign = service.create_project(hapic['organization_id'], 'Other')
    other_hapic = service.store.one("SELECT * FROM agents WHERE project_id=? AND kind='hapic'", (foreign['id'],))
    with pytest.raises(LookupError):
        service.tasks.inspect(other_hapic, task['id'])


def test_queue_bounds_parallel_work_and_timeout_is_ten_minutes(tmp_path):
    import threading
    from backend.tasks import TASK_TIMEOUT_SECONDS
    assert TASK_TIMEOUT_SECONDS == 600
    service, hapic, ux, runtime = setup(tmp_path)
    release = threading.Event()
    async def slow(agent, store, text, request_id):
        while not release.is_set():
            await asyncio.sleep(0.01)
        (store.agent_path(agent) / 'workspace/index.html').write_text('ok')
        return 'Listo', 'completed'
    runtime.chat = slow
    for index in range(3):
        agent = ux if index == 0 else service.create_agent(hapic['project_id'], f'UX {index}', 'ux')
        service.store.execute("UPDATE agents SET container_id='test' WHERE id=?", (agent['id'],))
        task = service.tasks.create(hapic, agent['id'], f'Tarea {index}', '', [], ['index.html'])
        service.tasks.enqueue(hapic, task['id'])
    try:
        service.tasks.dispatch_once()
        assert len(service.tasks.workers) == 2
        assert sum(t['state'] == 'queued' for t in service.tasks.list(hapic)) >= 1
    finally:
        release.set()
        for thread in service.tasks.workers.values():
            thread.join(5)
    service.tasks.dispatch_once()
    for thread in service.tasks.workers.values():
        thread.join(5)
    assert all(t['state'] == 'delivered' for t in service.tasks.list(hapic))


def test_task_receipts_reach_coordinator_and_do_not_duplicate_on_restart(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    task = service.tasks.create(hapic, ux['id'], 'Crear prototipo', '', [], ['index.html'])
    service.tasks.enqueue(hapic, task['id'])
    service.tasks.publish_updates()
    assert 'UX' in service.messages(hapic['id'])[-1]['content']
    assert service.messages(hapic['id'])[-1]['source'] == 'task-update'
    asyncio.run(service.tasks.run(hapic, task['id']))
    service.tasks.publish_updates()
    messages = service.messages(hapic['id'])
    assert any('Entrega recibida' in m['content'] and 'index.html' in m['content'] for m in messages)
    assert 'no tiene tareas en ejecución ni en cola' in messages[-1]['content']
    assert 'vista previa local' not in messages[-1]['content']
    Service(Store(tmp_path), runtime).tasks.publish_updates()
    assert len(service.messages(hapic['id'])) == len(messages)


def test_idle_summary_links_the_public_tunnel_and_youtube(tmp_path):
    service, hapic, ux, runtime = setup(tmp_path)
    (service.store.agent_path(ux) / 'workspace' / 'pulso').mkdir(parents=True)
    service.store.set_setting('development-share-' + ux['id'], {'url': 'https://game.lhr.life'})
    service.store.execute("INSERT INTO youtube_uploads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        'ytup_test', hapic['project_id'], ux['id'], 'con_test', 'request-public-01', 'a' * 64,
        'videos/demo.mp4', '{}', 'uploaded', '7_8-I4pIec4', 10, '2026-11-07T00:00:00+00:00', '2026-11-07T00:00:00+00:00'))
    task = service.tasks.create(hapic, ux['id'], 'Cerrar', '', [], ['index.html'])
    asyncio.run(service.tasks.run(hapic, task['id']))
    service.tasks.publish_updates()
    content = service.messages(hapic['id'])[-1]['content']
    assert 'UX: Cerrar' in content
    assert 'https://game.lhr.life/pulso/' in content
    assert 'https://www.youtube.com/watch?v=7_8-I4pIec4' in content
    assert 'preview/open' not in content
    assert '127.0.0.1' not in content


def test_hapic_switches_the_only_public_game(tmp_path, monkeypatch):
    service, hapic, ux, runtime = setup(tmp_path)
    architect = service.create_agent(hapic['project_id'], 'Arqui', 'architect')
    pulso = service.create_agent(hapic['project_id'], 'Pulso Código', 'coder', architect['id'])
    brayan = service.create_agent(hapic['project_id'], 'El Brayan', 'coder', architect['id'])

    def share(agent, action='status', user_approved=False):
        if action == 'stop':
            return {'status': 'stopped', 'url': None}
        if action == 'status':
            return {'status': 'running', 'url': 'https://pulso.lhr.life'} if agent['id'] == pulso['id'] else {'status': 'stopped', 'url': None}
        return {'status': 'running', 'url': 'https://rbr.lhr.life', 'http_status': 200}

    monkeypatch.setattr(service.development, 'share', share)
    monkeypatch.setattr(service.development, 'preview', lambda agent, action, command='': {'status': 'running'})
    with pytest.raises(ValueError):
        service.tool(hapic, 'set_public_game', {'agent_id': brayan['id'], 'user_approved': False})
    result = service.tool(hapic, 'set_public_game', {'agent_id': brayan['id'], 'user_approved': True})
    assert result['url'] == 'https://rbr.lhr.life' and result['closed'] == ['Pulso Código']
    service.store.set_setting('development-share-' + pulso['id'], {'url': 'https://pulso.lhr.life'})
    service.store.set_setting('development-share-' + brayan['id'], {'url': 'https://rbr.lhr.life'})
    (service.store.agent_path(pulso) / 'workspace' / 'pulso').mkdir(parents=True)
    task = service.tasks.create(hapic, ux['id'], 'Publicar la publicidad de RBR', '', [], ['index.html'])
    service.store.execute("UPDATE tasks SET state='delivered',result='{}' WHERE id=?", (task['id'],))
    service.tasks.publish_updates()
    content = service.messages(hapic['id'])[-1]['content']
    assert 'Publicar la publicidad de RBR' in content
    assert 'https://rbr.lhr.life/' in content
    assert 'pulso.lhr.life' not in content

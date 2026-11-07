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
    Service(Store(tmp_path), runtime).tasks.publish_updates()
    assert len(service.messages(hapic['id'])) == len(messages)

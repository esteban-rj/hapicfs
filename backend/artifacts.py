"""Discover publishable workspace artifacts without traversing runtime profiles."""
import os
from pathlib import Path
from urllib.parse import urlencode


def artifact_file(service, project_id, relative):
    from .service import safe_path
    project = service.project(project_id)
    parts = Path(relative).parts
    if len(parts) >= 4 and parts[0] == 'agents' and parts[2] == 'workspace':
        agent = service.agent(parts[1])
        if agent['project_id'] != project_id:
            raise ValueError('El archivo no pertenece a este proyecto.')
    elif len(parts) < 2 or parts[0] != 'workspace':
        raise ValueError('Solo se comparten entregables del workspace.')
    suffix = Path(relative).suffix.lower()
    if suffix in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        return service.image_file(project_id, relative)
    if suffix == '.mp4':
        return service.video_file(project_id, relative)
    return safe_path(service.store.project_path(project), relative), 'text/plain'


def describe(service, project_id, relative, owner=None):
    path, mime = artifact_file(service, project_id, relative)
    query = urlencode({'path': relative})
    url = f'/api/projects/{project_id}/artifacts/open?{query}'
    return {'id': relative, 'path': relative, 'name': path.name, 'mime_type': mime,
            'media_type': 'image' if mime.startswith('image/') else 'video' if mime.startswith('video/') else 'text',
            'agent_id': owner['id'] if owner else None, 'agent_name': owner['name'] if owner else 'Proyecto',
            'size': path.stat().st_size, 'modified_at': path.stat().st_mtime,
            'url': url, 'download_url': url + '&download=true'}


def list_artifacts(service, project_id):
    from .service import HIDDEN_NAMES
    project = service.project(project_id)
    root = service.store.project_path(project)
    agents = service.store.all('SELECT * FROM agents WHERE project_id=? ORDER BY created_at', (project_id,))
    files = []
    for owner, workspace in [(None, root / 'workspace')] + [(agent, service.store.agent_path(agent) / 'workspace') for agent in agents]:
        count = 0
        if workspace.is_symlink() or getattr(workspace, 'is_junction', lambda: False)():
            continue
        for directory, dirs, names in os.walk(workspace, followlinks=False):
            parent = Path(directory)
            dirs[:] = [name for name in sorted(dirs) if not name.startswith('.') and name not in HIDDEN_NAMES
                       and not (parent / name).is_symlink() and not getattr(parent / name, 'is_junction', lambda: False)()]
            if len(parent.relative_to(workspace).parts) >= 8:
                dirs[:] = []
            for name in sorted(names):
                count += 1
                if count > 2000:
                    break
                try:
                    files.append(describe(service, project_id, (parent / name).relative_to(root).as_posix(), owner))
                except (ValueError, LookupError, OSError):
                    continue
            if count > 2000:
                break
    files.sort(key=lambda item: item['modified_at'], reverse=True)
    return {'storage': 'local', 'location': 'Guardado en este PC, dentro del workspace de cada agente. No se publica automáticamente en Internet.', 'files': files[:500]}

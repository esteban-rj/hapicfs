import json
import time

import httpx
import pytest

from backend.service import Service
from backend.storage import Store, now
from backend.runtime import RuntimeUnavailable
from backend.youtube import SCOPES, READ_SCOPES
from backend.youtube_uploads import UPLOAD_URL, UPLOAD_SCOPE

CHANNEL = 'UC' + 'a' * 22
VIDEO = 'abcdefghijk'


@pytest.fixture
def uploading(tmp_path, monkeypatch):
    monkeypatch.delenv('HAPIC_YOUTUBE_CLIENT_FILE', raising=False)
    service = Service(Store(tmp_path))
    org = service.create_org('Upload tests')
    project = service.create_project(org['id'], 'Video')
    stamp = now()
    service.store.execute("INSERT INTO connections VALUES (?,?,'youtube',?,?,?,'connected',?,?)", ('con-upload', project['id'], CHANNEL, 'Test channel', json.dumps(SCOPES), stamp, stamp))
    service.store.secret('youtube-client', json.dumps({'client_id': 'test.apps.googleusercontent.com', 'client_secret': 'test-secret-not-real', 'redirect_uris': ['http://localhost/api/connections/youtube/callback']}))
    service.store.secret('con-upload-oauth', json.dumps({'access_token': 'test-access', 'refresh_token': 'test-refresh', 'expires_at': time.time() + 3600}))
    agent = service.create_agent(project['id'], 'CM', 'community-manager')
    root = service.store.agent_path(agent) / 'workspace'
    (root / 'video.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom' + bytes(80))
    service.store.execute("""INSERT INTO video_jobs(id,project_id,agent_id,connection_id,request_id,payload,status,estimated_cost_usd,path,created_at,updated_at)
        VALUES (?,?,?,?,?,?,'completed','0.05',?,?,?)""", ('vid-test', project['id'], agent['id'], 'con-upload', 'generated-video-01', '{}', f"agents/{agent['id']}/workspace/video.mp4", stamp, stamp))
    state = {'starts': 0, 'bodies': 0, 'complete': False, 'ambiguous': False, 'visibility': 'public'}
    def google(request):
        assert request.url.host == 'www.googleapis.com'
        assert request.headers['authorization'] == 'Bearer test-access'
        if request.url.path == '/youtube/v3/channels':
            return httpx.Response(200, json={'items': [{'id': CHANNEL}]})
        if request.url.path == '/youtube/v3/videos':
            return httpx.Response(200, json={'items': [{'id': VIDEO, 'snippet': {'channelId': CHANNEL}, 'status': {'privacyStatus': state['visibility'], 'uploadStatus': 'processed'}, 'processingDetails': {'processingStatus': 'succeeded'}}]})
        assert request.url.path == '/upload/youtube/v3/videos'
        if request.method == 'POST':
            state['starts'] += 1
            metadata = json.loads(request.content)
            assert metadata['status']['privacyStatus'] == 'public'
            assert metadata['status']['containsSyntheticMedia'] is True
            return httpx.Response(200, headers={'Location': UPLOAD_URL + '?upload_id=test-session'})
        if request.headers['content-range'].startswith('bytes */'):
            return httpx.Response(200, json={'id': VIDEO}) if state['complete'] else httpx.Response(308)
        state['bodies'] += 1
        state['complete'] = True
        if state['ambiguous']:
            raise httpx.ReadTimeout('response lost', request=request)
        return httpx.Response(200, json={'id': VIDEO})
    service.youtube.transport = httpx.MockTransport(google)
    args = {'path': 'video.mp4', 'title': 'Pulso', 'description': 'Cinco pulsaciones.', 'request_id': 'pulso-publish-01', 'visibility': 'public', 'user_approved': True}
    return service, agent, args, state


def test_agent_upload_is_authorized_persistent_and_idempotent(uploading):
    service, agent, args, state = uploading
    result = service.tool(agent, 'youtube_upload_video', args)
    assert result['published'] and result['actual_visibility'] == 'public'
    assert result['video_id'] == VIDEO
    assert service.tool(agent, 'youtube_upload_video', args)['id'] == result['id']
    assert state['starts'] == state['bodies'] == 1
    row = service.store.one('SELECT * FROM youtube_uploads WHERE id=?', (result['id'],))
    assert 'upload_id=' not in json.dumps(row)
    assert 'test-session' not in (service.store.secrets_dir / (result['id'] + '-session.enc')).read_text()


def test_ambiguous_upload_recovers_same_remote_video_without_resending(uploading):
    service, agent, args, state = uploading
    state['ambiguous'] = True
    first = service.tool(agent, 'youtube_upload_video', args)
    assert first['status'] == 'uncertain'
    recovered = service.tool(agent, 'youtube_get_upload', {'upload_id': first['id']})
    assert recovered['published']
    assert state['starts'] == state['bodies'] == 1


def test_upload_checks_approval_permissions_and_unchanged_identity(uploading):
    service, agent, args, state = uploading
    with pytest.raises(PermissionError):
        service.tool(agent, 'youtube_upload_video', {**args, 'user_approved': False})
    service.store.execute('UPDATE connections SET scopes=? WHERE id=?', (json.dumps(READ_SCOPES), 'con-upload'))
    with pytest.raises(RuntimeUnavailable, match='lectura'):
        service.tool(agent, 'youtube_upload_video', args)
    assert state['starts'] == 0
    service.store.execute('UPDATE connections SET scopes=? WHERE id=?', (json.dumps(SCOPES), 'con-upload'))
    result = service.tool(agent, 'youtube_upload_video', args)
    with pytest.raises(ValueError, match='request_id'):
        service.tool(agent, 'youtube_upload_video', {**args, 'title': 'Different'})
    other = service.create_agent(agent['project_id'], 'Other CM', 'community-manager')
    with pytest.raises(LookupError):
        service.tool(other, 'youtube_get_upload', {'upload_id': result['id']})
    assert state['starts'] == 1


def test_actual_private_visibility_is_not_reported_as_public(uploading):
    service, agent, args, state = uploading
    state['visibility'] = 'private'
    result = service.tool(agent, 'youtube_upload_video', args)
    assert result['actual_visibility'] == 'private' and not result['published']


def test_legacy_readonly_grant_refresh_does_not_require_upload_permission(uploading):
    service, agent, _, _ = uploading
    service.store.execute('UPDATE connections SET scopes=? WHERE id=?', (json.dumps(READ_SCOPES), 'con-upload'))
    service.store.secret('con-upload-oauth', json.dumps({'access_token': 'old', 'refresh_token': 'test-refresh', 'expires_at': 0}))
    def google(request):
        if request.url.host == 'oauth2.googleapis.com':
            return httpx.Response(200, json={'access_token': 'renewed', 'expires_in': 3600, 'scope': ' '.join(READ_SCOPES)})
        assert request.headers['authorization'] == 'Bearer renewed'
        return httpx.Response(200, json={'items': [{'id': CHANNEL}]})
    service.youtube.transport = httpx.MockTransport(google)
    assert service.tool(agent, 'youtube_get_channel', {})['channel']['id'] == CHANNEL


@pytest.mark.parametrize('location', ['http://www.googleapis.com/upload/test', 'https://evil.example/upload/test', 'https://user:pass@www.googleapis.com/upload/test', 'https://www.googleapis.com:bad/upload/test'])
def test_upload_session_cannot_forward_credentials_to_another_target(location):
    from backend.youtube_uploads import YouTubeUploads
    with pytest.raises(RuntimeUnavailable):
        YouTubeUploads.session_url(location)

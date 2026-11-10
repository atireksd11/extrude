"""HTTP boundary regression tests; never exercise live services or real keys."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from extrude.api.security import MAX_BODY, SecurityMiddleware


@pytest.fixture
def boundary(monkeypatch):
    monkeypatch.delenv('EXTRUDE_API_TOKEN', raising=False)
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('EXTRUDE_HOSTED', raising=False)
    monkeypatch.delenv('EXTRUDE_RATE_LIMIT', raising=False)
    api = FastAPI()
    api.add_middleware(SecurityMiddleware)

    @api.api_route('/v1/example', methods=['GET', 'POST'])
    async def example():
        return {'ok': True}

    @api.get('/v1/error')
    async def error():
        raise RuntimeError('sensitive internal detail')

    return TestClient(api)


def test_hosted_fails_closed_and_https_redirect(boundary, monkeypatch):
    monkeypatch.setenv('EXTRUDE_HOSTED', '1')
    assert boundary.get('/v1/example').status_code == 503
    monkeypatch.setenv('EXTRUDE_PUBLIC_ORIGIN', 'https://extrude.example')
    response = boundary.get('/v1/example', follow_redirects=False, headers={'Host': 'evil.example'})
    assert response.status_code == 308
    assert response.headers['location'] == 'https://extrude.example/v1/example'
    response = boundary.get('https://extrude.example/v1/example')
    assert response.status_code == 503
    assert response.headers['strict-transport-security'] == 'max-age=31536000'


def test_cross_origin_and_dns_rebinding_denied(boundary):
    for headers in [{'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}, {'Host': 'evil.example'}]:
        response = boundary.post('/v1/example', headers=headers)
        assert response.status_code == 403
        assert 'access-control-allow-origin' not in response.headers
    assert boundary.get('/v1/example', headers={'Origin': 'http://testserver'}).status_code == 200


def test_streamed_and_declared_body_limits_and_types(boundary):
    assert boundary.post('/v1/example', content=b'a', headers={'content-length': str(MAX_BODY + 1)}).status_code == 413
    assert boundary.post('/v1/example', content=iter([b'a' * MAX_BODY, b'b']), headers={'content-type': 'application/json'}).status_code == 413
    assert boundary.post('/v1/example', content=b'abc').status_code == 415
    assert boundary.post('/v1/example', headers={'content-length': '-1'}).status_code == 400


def test_rate_limits_and_logs_do_not_echo_input(boundary, monkeypatch, caplog):
    monkeypatch.setenv('EXTRUDE_RATE_LIMIT', '1')
    for _ in range(10):
        assert boundary.post('/v1/example').status_code == 200
    response = boundary.post('/v1/example?token=synthetic-sensitive-marker', headers={'Authorization': 'Bearer synthetic-sensitive-marker', 'User-Agent': 'synthetic-sensitive-marker'})
    assert response.status_code == 429
    assert response.headers['retry-after'] == '60'
    assert 'synthetic-sensitive-marker' not in caplog.text
    event = json.loads(caplog.records[-1].message)
    assert event['route'] == 'api' and event['status'] == 429
    assert {'time', 'ip', 'agent_hash'} <= event.keys()


def test_headers_on_success_and_generic_errors(boundary):
    for path, status in [('/v1/example', 200), ('/v1/error', 500), ('/.env', 404)]:
        response = boundary.get(path)
        assert response.status_code == status
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['x-frame-options'] == 'DENY'
        assert response.headers['referrer-policy'] == 'no-referrer'
        assert "script-src 'self'" in response.headers['content-security-policy']
        assert 'sensitive internal detail' not in response.text
        assert 'set-cookie' not in response.headers


def test_artifact_confined_to_one_run(tmp_path, monkeypatch):
    from extrude.api import server
    monkeypatch.setenv('EXTRUDE_DATA_DIR', str(tmp_path))
    other = tmp_path / 'generated' / 'other'
    other.mkdir(parents=True)
    (other / 'secret.html').write_text('<script>alert(1)</script>')
    with pytest.raises(Exception) as denied:
        server.artifact('first', '../other/secret.html')
    assert denied.value.status_code == 404
    response = server.artifact('other', 'secret.html')
    assert response.headers['content-disposition'] == 'attachment'
    assert response.headers['content-security-policy'].startswith('sandbox')


def test_real_routes_fail_closed_and_exposed_files_absent(monkeypatch):
    from extrude.api.server import app
    monkeypatch.setenv('EXTRUDE_HOSTED', '1')
    monkeypatch.setenv('EXTRUDE_PUBLIC_ORIGIN', 'https://extrude.example')
    with TestClient(app, base_url='https://extrude.example') as client:
        for template, methods in app.openapi()['paths'].items():
            if template.startswith(('/v1/', '/artifacts/')):
                path = template
                for key in ['repo_id', 'audit_id', 'project_id', 'finding_id', 'rule_id', 'run_id', 'path']:
                    path = path.replace('{' + key + '}', '1')
                for method in methods:
                    assert client.request(method, path).status_code in {503, 429}, path
        for path in ['/.env', '/.git/config', '/pyproject.toml', '/data/project-map.sqlite', '/docs', '/redoc', '/openapi.json', '/metrics', '/debug', '/admin']:
            assert client.get(path).status_code == 404, path


def test_validation_does_not_reflect_attacker_input(monkeypatch):
    from extrude.api.server import app
    monkeypatch.delenv('EXTRUDE_API_TOKEN', raising=False)
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('EXTRUDE_HOSTED', raising=False)
    with TestClient(app) as client:
        response = client.post('/v1/design', json={'prompt': {'secret': 'synthetic-marker'}})
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid request.'}


def test_disallowed_paste_type_and_oversized_fields(monkeypatch):
    from extrude.api.server import app
    monkeypatch.delenv('EXTRUDE_API_TOKEN', raising=False)
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('EXTRUDE_HOSTED', raising=False)
    monkeypatch.setenv('EXTRUDE_RATE_LIMIT', '0')
    with TestClient(app) as client:
        for path in ['/v1/copilot', '/v1/compare']:
            for payload in [{'filename': 'run.py', 'artifact': 'print(1)'},
                            {'filename': '../part.scad', 'artifact': 'cube(1);'},
                            {'artifact': 'x' * 512001}]:
                assert client.post(path, json=payload).status_code == 422


def test_hosted_repeated_requests_are_rate_limited(boundary, monkeypatch):
    monkeypatch.setenv('EXTRUDE_HOSTED', '1')
    for _ in range(10):
        assert boundary.post('https://extrude.example/v1/example').status_code == 503
    assert boundary.post('https://extrude.example/v1/example').status_code == 429


def test_interim_bearer_gate_and_unsafe_hosted_features(boundary, monkeypatch):
    monkeypatch.setenv('EXTRUDE_HOSTED', '1')
    monkeypatch.setenv('EXTRUDE_API_TOKEN', 'x' * 31)
    assert boundary.get('https://extrude.example/v1/example').status_code == 503
    token = 'synthetic-test-token-' + 'x' * 32
    monkeypatch.setenv('EXTRUDE_API_TOKEN', token)
    assert boundary.get('https://extrude.example/v1/example').status_code == 401
    assert boundary.get('https://extrude.example/v1/example?token=' + token).status_code == 401
    assert boundary.get('https://extrude.example/v1/example', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    headers = {'Authorization': 'Bearer ' + token}
    assert boundary.get('https://extrude.example/v1/example', headers=headers).status_code == 200
    for path in ['/v1/projects', '/v1/projects/demo', '/v1/design', '/v1/copilot', '/v1/compare']:
        assert boundary.get('https://extrude.example' + path, headers=headers).status_code == 403
    assert boundary.get('https://extrude.example/v1/example', headers={**headers, 'Origin': 'https://evil.example'}).status_code == 403


def test_concurrent_compute_requests_are_bounded(monkeypatch):
    import asyncio
    import httpx
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('EXTRUDE_HOSTED', raising=False)
    monkeypatch.delenv('EXTRUDE_API_TOKEN', raising=False)
    monkeypatch.setenv('EXTRUDE_RATE_LIMIT', '1')

    async def scenario():
        api = FastAPI()
        api.add_middleware(SecurityMiddleware)
        entered = 0
        both = asyncio.Event()
        release = asyncio.Event()

        @api.get('/v1/slow')
        async def slow():
            nonlocal entered
            entered += 1
            if entered == 2:
                both.set()
            await release.wait()
            return {'ok': True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url='http://testserver') as client:
            pending = [asyncio.create_task(client.get('/v1/slow')) for _ in range(2)]
            await asyncio.wait_for(both.wait(), timeout=5)
            assert (await client.get('/v1/slow')).status_code == 429
            release.set()
            assert all(r.status_code == 200 for r in await asyncio.gather(*pending))
    asyncio.run(scenario())


def test_sql_file_lookup_and_shell_injection_are_data(tmp_path, monkeypatch):
    from extrude import github_history, project_map
    monkeypatch.setenv('EXTRUDE_PROJECT_DB', str(tmp_path / 'state' / 'projects.sqlite'))
    root = tmp_path / 'project'
    root.mkdir()
    payload = "x'); DROP TABLE projects; --"
    project = project_map.create_project(payload, str(root))
    assert project_map.list_projects()[0]['name'] == payload
    with pytest.raises(KeyError):
        project_map.preview_project_file(project['project']['id'], "' OR 1=1 --")
    marker = tmp_path / 'injection-marker'
    with pytest.raises(ValueError):
        github_history.normalize('owner/repo;touch ' + str(marker))
    assert not marker.exists()


def test_slow_request_bodies_reserve_concurrency_slots(monkeypatch):
    import asyncio
    import httpx
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('EXTRUDE_HOSTED', raising=False)
    monkeypatch.delenv('EXTRUDE_API_TOKEN', raising=False)
    monkeypatch.setenv('EXTRUDE_RATE_LIMIT', '1')

    async def scenario():
        api = FastAPI()
        api.add_middleware(SecurityMiddleware)
        reading = 0
        both = asyncio.Event()
        release = asyncio.Event()

        @api.post('/v1/body')
        async def accepted():
            return {'ok': True}

        class SlowBody(httpx.AsyncByteStream):
            async def __aiter__(self):
                nonlocal reading
                reading += 1
                if reading == 2:
                    both.set()
                yield b'{'
                await release.wait()
                yield b'}'

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url='http://testserver') as client:
            pending = [asyncio.create_task(client.post('/v1/body', content=SlowBody(), headers={'content-type': 'application/json'})) for _ in range(2)]
            await asyncio.wait_for(both.wait(), timeout=5)
            try:
                third = await asyncio.wait_for(client.post('/v1/body', json={}), timeout=2)
                assert third.status_code == 429
            finally:
                release.set()
            assert all(r.status_code == 200 for r in await asyncio.gather(*pending))
    asyncio.run(scenario())


def test_anonymous_attempts_cannot_spend_authenticated_budget(boundary, monkeypatch):
    monkeypatch.setenv('EXTRUDE_HOSTED', '1')
    token = 'synthetic-test-token-' + 'x' * 32
    monkeypatch.setenv('EXTRUDE_API_TOKEN', token)
    for _ in range(10):
        assert boundary.post('https://extrude.example/v1/example').status_code == 401
    assert boundary.post('https://extrude.example/v1/example').status_code == 429
    assert boundary.post('https://extrude.example/v1/example', headers={'Authorization': 'Bearer ' + token}).status_code == 200

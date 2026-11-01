from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.browser_policy import install_browser_policy


def client():
    app = FastAPI()
    install_browser_policy(app)
    @app.get('/health')
    def health():
        return {'ok': True}
    return TestClient(app)


def test_explicit_cors_and_no_cookies():
    c = client()
    for origin in ['https://protoss.trade', 'http://127.0.0.1:4173']:
        r = c.options('/health', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type'})
        assert r.status_code == 200
        assert r.headers['access-control-allow-origin'] == origin
        assert 'access-control-allow-credentials' not in r.headers
    r = c.options('/health', headers={'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
    assert r.status_code == 400
    assert 'access-control-allow-origin' not in r.headers


def test_redirect_only_old_ui_and_preserve_query(monkeypatch):
    monkeypatch.setenv('REDIRECT_LEGACY_FRONTEND', '1')
    from app.config import get_settings
    get_settings.cache_clear()
    c = client()
    r = c.get('https://app.protoss.trade/?session=example', follow_redirects=False)
    assert r.status_code == 307
    assert r.headers['location'] == 'https://protoss.trade/app/?session=example'
    assert c.get('https://app.protoss.trade/health').json() == {'ok': True}
    assert c.get('https://api.protoss.trade/health').json() == {'ok': True}
    monkeypatch.delenv('REDIRECT_LEGACY_FRONTEND')
    get_settings.cache_clear()
    assert c.get('https://app.protoss.trade/', follow_redirects=False).status_code == 404

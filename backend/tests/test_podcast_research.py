"""Evidence and read-only boundaries for actual episode research."""
import copy
import datetime as dt
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import podcast_research as research
from app.config import get_settings

URL = 'https://www.dwarkesh.com/p/test-episode'
QUOTE = 'Robots may change the demand for electricity.'
TEXT = (QUOTE + ' This is a sourced episode claim, not an independently verified fact. ') * 12
HTML = '<p>Outside content</p><div class="body markup"><p>' + TEXT + '</p><script>secret script</script></div><p>Outside ending</p>'
ANALYSIS = {'summary': 'The speaker discusses electricity demand from robotics.',
            'claims': [{'claim': 'Robotics could change electricity demand.', 'quote': QUOTE}],
            'proposal': {'market': 'BTC', 'direction': 'short', 'reasoning': 'A test hypothesis linking risk appetite to capital costs.',
                         'risk': 'The episode provides no independent evidence for this market link.'},
            'missing_evidence': ['Independent market and demand evidence.']}
SOURCE = SimpleNamespace(name='hyperliquid', markets=lambda: ['BTC'])


@pytest.fixture(autouse=True)
def reset_research_cache(monkeypatch):
    monkeypatch.delenv('PODCAST_ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(research, '_analysis_cache', {})
    monkeypatch.setattr(research, '_last_analysis', None)


def test_same_episode_cached_and_different_episode_rate_limited(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-provider-key')
    calls = []
    analyze = lambda *args: calls.append(args) or ANALYSIS
    one = research.research(URL, SOURCE, fetch=lambda _: HTML, analyze=analyze)
    two = research.research(URL, SOURCE, fetch=lambda _: HTML, analyze=analyze)
    assert one['analysis'] == two['analysis'] and len(calls) == 1
    with pytest.raises(research.ResearchUnavailable, match='Wait a minute'):
        research.research(URL + '-other', SOURCE, fetch=lambda _: HTML, analyze=analyze)
    assert len(calls) == 1


def test_fresh_catalog_excludes_delisted_markets_and_fails_closed(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(hl_api_url='https://exchange.test', arena_mode='paper', hl_perp_dexs=['xyz']))
    calls = []
    def metadata(url, json, **kwargs):
        calls.append(json['dex'])
        return httpx.Response(200, request=httpx.Request('POST', url), json={'universe': [
            {'name': 'BTC' if not json['dex'] else 'xyz:ACTIVE'}, {'name': 'DELISTED', 'isDelisted': True}]})
    monkeypatch.setattr(research.httpx, 'post', metadata)
    assert research.current_source().markets() == ['BTC', 'xyz:ACTIVE']
    assert calls == ['', 'xyz']
    monkeypatch.setattr(research.httpx, 'post', lambda *args, **kwargs: httpx.Response(200, json={}))
    with pytest.raises(research.ResearchUnavailable, match='markets are unavailable'):
        research.current_source()


@pytest.mark.parametrize('url', ['http://www.dwarkesh.com/p/one', 'https://dwarkesh.com.evil.test/p/one',
                                 'https://user:password@dwarkesh.com/p/one', 'https://127.0.0.1/p/one',
                                 'https://dwarkesh.com:444/p/one', 'https://dwarkesh.com/admin',
                                 'https://dwarkesh.com/p/%2e%2e'])
def test_only_public_episode_urls(url):
    with pytest.raises(research.ResearchUnavailable):
        research.safe_url(url)


def test_query_data_are_not_fetched_or_returned():
    seen = []
    source = research.episode_source(URL + '/?token=private#fragment', fetch=lambda url: seen.append(url) or HTML)
    assert seen == [URL] and source['url'] == URL
    assert source['title'] == 'test episode'
    assert 'Outside' not in source['text'] and 'secret script' not in source['text']


def test_redirect_revalidated_before_fetch(monkeypatch):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(research.httpx, 'Client', lambda **kwargs: client)
    with pytest.raises(research.ResearchUnavailable):
        research.download(URL)
    assert seen == [URL]


def test_source_size_limit(monkeypatch):
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'x' * 101)))
    monkeypatch.setattr(research.httpx, 'Client', lambda **kwargs: client)
    monkeypatch.setattr(research, 'MAX_BYTES', 100)
    with pytest.raises(research.ResearchUnavailable, match='too large'):
        research.download(URL)


def test_latest_published_audio_only():
    def item(slug, day, audio=True):
        return f'<item><title>{slug}</title><link>https://www.dwarkesh.com/p/{slug}</link><pubDate>2026-11-{day}T12:00:00Z</pubDate>' + ('<enclosure url="https://audio.test/a.mp3" type="audio/mpeg"/>' if audio else '') + '</item>'
    rss = '<rss><channel>' + item('older', '01') + item('latest', '02') + item('future', '05') + item('essay', '03', False) + '</channel></rss>'
    result = research.episode_source('Research Dwarkesh', now=dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc),
                                    fetch=lambda url, **kw: rss if kw.get('feed') else HTML)
    assert result['title'] == 'latest' and result['published_at'].startswith('2026-11-02')


def test_missing_text_cannot_be_invented():
    with pytest.raises(research.ResearchUnavailable, match='too short'):
        research.episode_source(URL, fetch=lambda _: '<div class="body markup">Preview only</div>')


def test_missing_key_never_fetches(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with pytest.raises(research.ResearchUnavailable, match='not configured'):
        research.research(URL, SOURCE, fetch=lambda _: pytest.fail('must not fetch'))


@pytest.mark.parametrize('bad', ['quote', 'market', 'too_many_quote_words', 'extra_order'])
def test_model_output_must_have_evidence_and_listed_market(monkeypatch, bad):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-provider-key')
    data = copy.deepcopy(ANALYSIS)
    if bad == 'quote':
        data['claims'][0]['quote'] = 'This sentence never occurred in the episode.'
    elif bad == 'market':
        data['proposal']['market'] = 'UNLISTED'
    elif bad == 'extra_order':
        data['proposal']['size'] = 100
    else:
        data['claims'] = [data['claims'][0]] * 3
        data['claims'][0]['quote'] = ' '.join(TEXT.split()[:10])
    with pytest.raises(research.ResearchUnavailable):
        research.research(URL, SOURCE, fetch=lambda _: HTML, analyze=lambda *args: data)


@pytest.mark.parametrize('proposal', [None, ANALYSIS['proposal']])
def test_research_is_sourced_and_non_executable(monkeypatch, proposal):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-provider-key')
    result = research.research(URL, SOURCE, fetch=lambda _: HTML, analyze=lambda *args: {**ANALYSIS, 'proposal': proposal})
    assert result['kind'] == 'research' and URL in result['reply']
    assert result['spec'] is result['deployable'] is result['result'] is None
    assert 'text' not in result['source']
    assert 'No order or approval was created' in result['reply'] and 'NVDA' not in result['reply']
    if proposal is None:
        assert 'No trade proposed' in result['reply']


def test_api_requires_admin_before_any_research(monkeypatch):
    monkeypatch.setenv('ADMIN_TOKEN', 'test-research-admin')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-provider-key')
    get_settings.cache_clear()
    calls = []
    monkeypatch.setattr(research, 'current_source', lambda: SOURCE)
    monkeypatch.setattr(research, 'research', lambda *args: calls.append(args[0]) or {'kind': 'research', 'reply': 'Sourced research'})
    from app.main import app
    client = TestClient(app)
    try:
        assert client.post('/research/podcast', json={'message': URL}).status_code == 403
        assert not calls
        result = client.post('/research/podcast', headers={'x-admin-token': 'test-research-admin'}, json={'message': URL})
        assert result.status_code == 200 and result.json()['kind'] == 'research'
        assert calls == [URL]
    finally:
        get_settings.cache_clear()


def test_dedicated_provider_key_does_not_enable_lab_provider(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('PODCAST_ANTHROPIC_API_KEY', 'test-podcast-provider')
    seen = []
    def analyze(source, markets, key):
        seen.append(key)
        return ANALYSIS
    result = research.research(URL, SOURCE, fetch=lambda _: HTML, analyze=analyze)
    assert result['kind'] == 'research' and seen == ['test-podcast-provider']
    from app import lab
    assert not lab.os.environ.get('ANTHROPIC_API_KEY')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-existing-lab-provider')
    assert research.provider_key() == 'test-podcast-provider'

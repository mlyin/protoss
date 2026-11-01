"""A failed refresh must never replace the public manifest or its chart files."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('idea_snapshots', Path(__file__).resolve().parents[2] / 'scripts/idea_snapshots.py')
snapshots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshots)


def test_failed_study_preserves_all_published_files(monkeypatch, tmp_path):
    old = {'ideas.json': b'old manifest', 'hacks.png': b'old chart'}
    for name, value in old.items():
        (tmp_path / name).write_bytes(value)
    monkeypatch.setattr(snapshots, 'plan', lambda *args, **kwargs: SimpleNamespace(type='buy_hold', model_dump=lambda **kw: {}))
    monkeypatch.setattr(snapshots, '_test_summary', lambda *args: {'real': True, 'coverage': {'source': 'historical', 'contiguous': True},
                       'notes': ['real candles'], 'market': 'XMR', 'start': '2026-01-01', 'end': '2026-02-01'})
    monkeypatch.setattr(snapshots, '_verdict', lambda *args: ['Historical comparison'])
    monkeypatch.setattr(snapshots, 'card_png', lambda *args, **kwargs: b'new chart')
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise ValueError('missing history')
        return SimpleNamespace(label='test')

    monkeypatch.setattr(snapshots, 'run_backtest', fail_second)
    with pytest.raises(ValueError, match='missing history'):
        snapshots.publish(SimpleNamespace(name='hyperliquid', markets=lambda: ['XMR']), tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == old


def test_failed_manifest_publish_preserves_old_chart_and_manifest(monkeypatch, tmp_path):
    (tmp_path / 'ideas.json').write_bytes(b'old manifest')
    (tmp_path / 'hacks.png').write_bytes(b'old chart')
    monkeypatch.setattr(snapshots, 'prepare', lambda src: ({'ideas': []}, {'hacks-new.png': b'new chart'}))
    replace = snapshots.os.replace

    def fail_manifest(src, dst):
        if dst.name == 'ideas.json':
            raise OSError('disk failure')
        replace(src, dst)

    monkeypatch.setattr(snapshots.os, 'replace', fail_manifest)
    with pytest.raises(OSError):
        snapshots.publish(None, tmp_path)
    assert (tmp_path / 'ideas.json').read_bytes() == b'old manifest'
    assert (tmp_path / 'hacks.png').read_bytes() == b'old chart'
    assert (tmp_path / 'hacks-new.png').read_bytes() == b'new chart'
    assert len(list(tmp_path.iterdir())) == 3


def test_refuses_simulated_source_without_writing(tmp_path):
    with pytest.raises(ValueError, match='unreachable'):
        snapshots.publish(SimpleNamespace(name='sim'), tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('phone', [False, True])
def test_card_legend_uses_engine_return_including_initial_fees(monkeypatch, phone):
    from PIL import ImageDraw
    from app.share import card_png
    texts = []
    original = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        texts.append(text)
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', record)
    card_png({'n': 1, 'label': 'Test', 'kind': 'rule', 'pledged_usd': None, 'record': {'closed': 0},
              'test': {'return_pct': 5.0, 'bench_pct': 10.0, 'real': True,
                       'curve': [['start', 90], ['end', 105]], 'bench': [['start', 90], ['end', 110]]}}, phone=phone)
    assert 'the idea +5.0%' in texts
    assert 'buy and hold +10.0%' in texts
    assert not any('+16.7%' in str(t) or '+22.2%' in str(t) for t in texts)

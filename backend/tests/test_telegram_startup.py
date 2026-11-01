"""Launcher lifecycle and single-poller protection, without credentials or network access."""
import importlib.util
import io
import json
from pathlib import Path
import signal
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    module = load('telegram_demo')
    monkeypatch.setattr(module, '__file__', str(tmp_path / 'scripts' / 'telegram_demo.py'))
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test-only-not-a-token')
    # The launcher must not need a website build to start the Telegram API and bridge.
    monkeypatch.setattr(module.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'{"mode":"sim"}'))
    children = []

    class Child:
        def __init__(self, args, **kwargs):
            self.args, self.kwargs, self.stopped = args, kwargs, False
            children.append(self)
        def poll(self): return 0 if self.stopped else None
        def wait(self, timeout=None): return 0
        def terminate(self): self.stopped = True
        def kill(self): self.stopped = True

    monkeypatch.setattr(module.subprocess, 'Popen', Child)
    return module, children


def test_headless_launcher_preserves_migration_checkpoint_and_stops_children(launcher, monkeypatch, tmp_path):
    module, children = launcher
    checkpoint = str(tmp_path / 'existing.json')
    monkeypatch.setattr(sys, 'argv', ['telegram_demo.py', '--chat', '-1002', '--users', '111,222',
                                    '--state', checkpoint, '--previous-chat', '-1001'])
    previous_handler = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit) as end:
        module.main()
    assert end.value.code == 0
    assert len(children) == 2 and all(child.stopped for child in children)
    bridge_args = children[1].args
    assert bridge_args[bridge_args.index('--state') + 1] == checkpoint
    assert bridge_args[bridge_args.index('--previous-chat') + 1] == '-1001'
    assert children[0].kwargs['env']['MAINNET_TRADING_ENABLED'] == 'false'
    assert children[0].kwargs['env']['ARENA_MODE'] == 'sim'
    api_args = children[0].args
    assert api_args[api_args.index('--app-dir') + 1] == str(tmp_path / 'backend')
    assert signal.getsignal(signal.SIGTERM) == previous_handler


def test_sigterm_cleans_up_api_and_bridge(launcher, monkeypatch):
    module, children = launcher
    monkeypatch.setattr(sys, 'argv', ['telegram_demo.py', '--chat', '-1002', '--users', '111,222'])
    original = module.subprocess.Popen
    def start(args, **kwargs):
        child = original(args, **kwargs)
        if len(children) == 2:
            def wait(timeout=None):
                if not child.stopped:
                    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                return 0
            child.wait = wait
        return child
    monkeypatch.setattr(module.subprocess, 'Popen', start)
    module.main()
    assert len(children) == 2 and all(child.stopped for child in children)


@pytest.mark.parametrize('args', [['--web-only'], ['--wallet-review', '--chat', '-1002', '--users', '111,222']])
def test_browser_modes_require_current_build(launcher, monkeypatch, tmp_path, args):
    module, children = launcher
    monkeypatch.setattr(sys, 'argv', ['telegram_demo.py', *args])
    with pytest.raises(SystemExit) as end:
        module.main()
    assert end.value.code == 2 and not children
    dist = tmp_path / 'web' / 'pages-dist'
    dist.mkdir(parents=True)
    (dist / 'index.html').write_text('built frontend')
    if '--web-only' in args:
        module.main()
    else:
        with pytest.raises(SystemExit) as end:
            module.main()
        assert end.value.code == 0
    assert children and all(child.stopped for child in children)


def test_one_poller_per_bot_across_processes(tmp_path):
    bridge = load('telegram_bridge')
    code = '''import sys
sys.path.insert(0, sys.argv[1])
from telegram_bridge import acquire_poller_lock, APIError
try:
    with acquire_poller_lock(123, sys.argv[2]): pass
except APIError:
    sys.exit(2)
'''
    args = [sys.executable, '-c', code, str(ROOT / 'scripts'), str(tmp_path)]
    with bridge.acquire_poller_lock(123, tmp_path):
        assert subprocess.run(args).returncode == 2
        with bridge.acquire_poller_lock(456, tmp_path): pass
    assert subprocess.run(args).returncode == 0


def test_status_inspection_does_not_poll(monkeypatch, capsys):
    bridge = load('telegram_bridge')
    calls = []
    class Telegram:
        def __init__(self, token): pass
        def call(self, method, **body):
            calls.append(method)
            return {'id':123, 'username':'test_bot'} if method == 'getMe' else {'url':''}
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test-only-not-a-token')
    monkeypatch.setattr(bridge, 'Telegram', Telegram)
    monkeypatch.setattr(sys, 'argv', ['telegram_bridge.py', 'inspect'])
    bridge.main()
    assert calls == ['getMe', 'getWebhookInfo']
    assert json.loads(capsys.readouterr().out)['pending'] == []

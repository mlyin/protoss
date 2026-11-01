#!/usr/bin/env python3
"""Freeze the running dashboard into ONE self-contained HTML file (no API needed).

    python scripts/static_demo.py [--api http://localhost:8000] [--out dist-static/index.html]

Snapshots every endpoint the web app reads, inlines the built CSS/JS, and prepends a fetch shim that
answers from the snapshot. Writes (POST) return a "static demo" note. Good for GitHub Pages, an
artifact, or an email. Run the demo first (`python scripts/demo.py`) so there is something to freeze.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"
HANDLES = ["lee", "matthew", "sam", "priya"]
EXTRA_PROMPTS = [
    "backtest a 3/10 momentum crossover on BTC over the last 90 days with $25k",
    "what if I bought XMR every time a major company got hacked",
    "buy and hold HYPE for the past year",
]


def snapshot(api: str) -> dict:
    c = httpx.Client(base_url=api, timeout=30)
    get: dict[str, object] = {}
    post: dict[str, object] = {}

    def g(path: str):
        r = c.get(path)
        get[path] = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
        return get[path]

    for p in ("/health", "/stats", "/builder", "/lab/examples", "/v1/markets", "/fills?limit=12", "/feed?limit=80", "/onboard/options"):
        g(p)
    for d in (1, 7, 30):
        g(f"/leaderboard?window_days={d}")
    agents = {a["id"] for a in get["/leaderboard?window_days=7"]["agents"]}
    for aid in agents:
        g(f"/agents/{aid}")
    for o in g("/orgs"):
        g(f"/orgs/{o['slug']}")
    for h in HANDLES:
        try:
            g(f"/u/{h}")
        except Exception:
            pass
        g(f"/feed?handle={h}&limit=80")
    prompts = list(dict.fromkeys(get["/lab/examples"]["examples"] + EXTRA_PROMPTS))
    for m in prompts:
        r = c.post("/lab/chat", json={"message": m})
        post[m.strip().lower()] = r.json()
    return {"get": get, "lab": post, "frozen_at": get["/health"] and __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}


SHIM = r"""
<script>
(() => {
  const SNAP = __SNAP__;
  const note = 'This is a frozen copy of the dashboard: data is a snapshot, writes are off. Run the API for the live version.';
  const json = (data, status = 200) => Promise.resolve(new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } }));
  const real = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (!url.startsWith('/')) return real(input, init);
    const method = (init.method || 'GET').toUpperCase();
    const path = url.split('#')[0];
    if (method === 'GET') {
      if (path in SNAP.get) return json(SNAP.get[path]);
      const bare = path.split('?')[0];
      if (bare in SNAP.get) return json(SNAP.get[bare]);
      const m = bare.match(/^\/feed$/);
      if (m) return json(SNAP.get['/feed?limit=80'] || []);
      if (bare.startsWith('/u/')) return json({ detail: 'no such person' }, 404);
      return json({ detail: 'not in the snapshot' }, 404);
    }
    if (path === '/lab/chat') {
      let msg = '';
      try { msg = (JSON.parse(init.body || '{}').message || '').trim().toLowerCase(); } catch {}
      if (msg in SNAP.lab) return json(SNAP.lab[msg]);
      const ex = (SNAP.get['/lab/examples'] || {}).examples || [];
      return json({ kind: 'clarify', reply: 'This frozen copy only answers the example prompts below. ' + note, spec: null, result: null, deployable: null, examples: ex });
    }
    return json({ detail: note }, 501);
  };
  window.PROTOSS_STATIC = { frozen_at: SNAP.frozen_at, note };
})();
</script>
"""

BANNER = """
<div id="static-note" style="background:#22221f;color:#aaa398;font:12px/18px Inter,system-ui,sans-serif;padding:6px max(16px, env(safe-area-inset-left, 0px));border-bottom:1px solid rgba(239,233,222,.08)">Frozen demo · snapshot of a paper/sim run · writes are off · <span id="static-when"></span></div>
<script>document.getElementById('static-when').textContent = 'frozen ' + new Date(window.PROTOSS_STATIC.frozen_at).toLocaleString();</script>
"""


def build(snap: dict, out: Path, artifact: bool) -> None:
    index = (DIST / "index.html").read_text()
    css = "".join((DIST / "assets" / f).read_text() for f in sorted(p.name for p in (DIST / "assets").glob("*.css")))
    # only the entry chunk: lazy chunks (Privy, loaded when a PRIVY_APP_ID is set) never run in the frozen copy
    entry = re.search(r'src="/?(assets/[^"]+\.js)"', index)
    js = (DIST / entry.group(1)).read_text() if entry else "".join((DIST / "assets" / f).read_text() for f in sorted(p.name for p in (DIST / "assets").glob("*.js")))
    mark = (DIST / "mark.svg").read_bytes() if (DIST / "mark.svg").exists() else b""
    mark_uri = "data:image/svg+xml;base64," + base64.b64encode(mark).decode() if mark else ""
    js = js.replace('"/mark.svg"', json.dumps(mark_uri)).replace("'/mark.svg'", json.dumps(mark_uri))
    # Keep frozen exports self-contained with the current Probe avatar too.
    probe = DIST / 'probe.png'
    if probe.exists():
        probe_uri = 'data:image/png;base64,' + base64.b64encode(probe.read_bytes()).decode()
        js = js.replace('"/probe.png"', json.dumps(probe_uri)).replace("'/probe.png'", json.dumps(probe_uri))
    fonts = re.search(r'<link[^>]+fonts\.googleapis\.com[^>]+>', index)
    head = [
        "<title>Protoss</title>",
        '<meta name="claude:viewport-fit-sides" content="cover">' if artifact else "",
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        fonts.group(0) if fonts else "",
        f'<link rel="icon" href="{mark_uri}" type="image/svg+xml">' if mark_uri and not artifact else "",
        "<style>:root{color-scheme:dark;background:#121211}" + css + "</style>",
    ]
    body = [
        SHIM.replace("__SNAP__", json.dumps(snap, separators=(",", ":"))),
        BANNER,
        '<div id="root"></div>',
        '<script type="module">' + js + "</script>",
    ]
    html = "\n".join(h for h in head if h) + "\n" + "\n".join(body)
    if not artifact:
        html = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' + html.replace('<div id="root"></div>', '</head>\n<body>\n<div id="root"></div>', 1) + "\n</body>\n</html>\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"{out} ({out.stat().st_size / 1024:.0f} KB; {len(snap['get'])} GET snapshots, {len(snap['lab'])} Lab answers)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", default=str(ROOT / "dist-static" / "index.html"))
    ap.add_argument("--artifact", action="store_true", help="omit the html/head/body skeleton (the artifact host adds one)")
    args = ap.parse_args()
    snap = snapshot(args.api)
    build(snap, Path(args.out), args.artifact)


if __name__ == "__main__":
    main()

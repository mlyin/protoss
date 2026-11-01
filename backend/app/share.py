"""Links that read well when pasted into a group chat.

iMessage (and Slack, WhatsApp, X) build the preview from the page's Open Graph tags, fetched by the sender's
phone. The app routes with a hash (#/p/slug), which crawlers never see, so every shareable thing gets a real
path here that serves OG tags plus a redirect into the app:

  GET /l/{slug}[?from=handle]   a legion invite        -> /#/p/{slug}
  GET /t/{id}                   a thesis from a huddle -> /#/huddle/{name} (web) or the legion
  GET /h/{name}                 a web huddle invite    -> /#/huddle/{name}
  GET /og/l/{slug}.png, /og/t/{id}.png, /og/h/{name}.png   1200x630 cards (Pillow; brand fallback without it)

iMessage wants a raster og:image (no SVG), at least 600px wide, and an absolute URL.
"""
from __future__ import annotations

import datetime as dt
import html
import io
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import DbDep
from .hl import ExchangeAdapter, get_exchange
from .models import Org

router = APIRouter(tags=["share"])
FONTS = Path(__file__).resolve().parent / "data" / "fonts"
FALLBACK_PNG = Path(__file__).resolve().parents[2] / "web" / "public" / "probe-social.png"
PROBE_PNG = Path(__file__).resolve().parents[2] / "web" / "public" / "probe.png"
W, H = 1200, 630
INK, SURFACE, TEXT, SECOND, MUTED, RED, POS, NEG = "#121211", "#181816", "#efe9de", "#aaa398", "#8a847a", "#c8102e", "#4cc38a", "#e5484d"
_png_cache: dict[str, tuple[float, bytes]] = {}


def exchange() -> ExchangeAdapter:
    return get_exchange()


def _usd(v: float) -> str:
    return f"${v:,.0f}"


def _base(request: Request) -> str:
    """Absolute origin for og:image. Behind the tunnel the Host header is app.protoss.trade; fall back to APP_URL."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host and not host.startswith(("127.", "localhost", "testserver")):
        proto = request.headers.get("x-forwarded-proto") or ("https" if "." in host else "http")
        return f"{proto}://{host}"
    return get_settings().app_url.rstrip("/")


def page(*, title: str, description: str, image: str, url: str, to: str) -> HTMLResponse:
    e = lambda s: html.escape(s, quote=True)  # noqa: E731
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Protoss">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(image)}">
<meta property="og:image:width" content="{W}"><meta property="og:image:height" content="{H}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(description)}">
<meta name="twitter:image" content="{e(image)}">
<link rel="icon" href="/favicon.svg?v=probe1" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=probe1">
<meta name="theme-color" content="{INK}">
<meta http-equiv="refresh" content="0; url={e(to)}">
<style>body{{background:{INK};color:{TEXT};font:16px Inter,system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0}}a{{color:{TEXT}}}</style>
</head><body><p><a href="{e(to)}">{e(title)}</a></p><script>location.replace({to!r})</script></body></html>"""
    return HTMLResponse(body, headers={"cache-control": "public, max-age=60"})


# ------------------------------------------------------------------------------------------------ cards

def _font(name: str, size: int, weight: str | None = None):
    from PIL import ImageFont

    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        try:
            f.set_variation_by_name(weight)
        except Exception:  # FreeType without variation support: regular weight is fine
            pass
    return f


def _wrap(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        nxt = f"{cur} {w}".strip()
        if draw.textlength(nxt, font=font) <= width:
            cur = nxt
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip(" ,.") + "…"
    return lines


def render_card(*, kicker: str, headline: str, stats: list[tuple[str, str, str | None]], foot: str, curve: list[float] | None = None) -> bytes:
    """Ink card: kicker, Anton headline, a row of figures over the red rule (the line you drew), optional curve."""
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(im)
    pad = 72
    brand_x = pad
    if PROBE_PNG.exists():
        with Image.open(PROBE_PNG) as source:
            mascot = source.convert("RGBA")
            mascot.thumbnail((62, 62))
            im.paste(mascot, (pad - 8, 40), mascot)
        brand_x += 66
    d.text((brand_x, 56), "PROTOSS", font=_font("Anton-Regular.ttf", 34), fill=TEXT)
    k = _font("Inter-Variable.ttf", 26, "Medium")
    d.text((W - pad - d.textlength(kicker, font=k), 64), kicker, font=k, fill=SECOND)
    big = _font("Anton-Regular.ttf", 76)
    y = 140
    right = W - pad - (360 if curve else 0)
    for line in _wrap(d, headline.upper(), big, right - pad, 3):
        d.text((pad, y), line, font=big, fill=TEXT)
        y += 88
    if curve and len(curve) > 1:
        x0, x1, y0, y1 = W - pad - 320, W - pad, 150, 330
        lo, hi = min(curve), max(curve)
        pts = [(x0 + i * (x1 - x0) / (len(curve) - 1), y1 - (v - lo) / max(1e-9, hi - lo) * (y1 - y0)) for i, v in enumerate(curve)]
        base = y1 - (curve[0] - lo) / max(1e-9, hi - lo) * (y1 - y0)
        d.line([(x0, base), (x1, base)], fill="#3a3a35", width=2)
        d.line(pts, fill=POS if curve[-1] >= curve[0] else NEG, width=4, joint="curve")
    ys = H - 210
    lab, val = _font("Inter-Variable.ttf", 22, "Medium"), _font("JetBrainsMono-Medium.ttf", 44)
    x = pad
    for label, value, tone in stats[:4]:
        d.text((x, ys), label, font=lab, fill=MUTED)
        d.text((x, ys + 32), value, font=val, fill={"pos": POS, "neg": NEG}.get(tone or "", TEXT))
        x += max(220, int(d.textlength(value, font=val)) + 64)
    d.rectangle([pad, ys + 100, W - pad, ys + 102], fill=RED)  # the line you drew
    d.text((pad, H - 72), foot, font=_font("Inter-Variable.ttf", 24, "Regular"), fill=SECOND)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _png(key: str, build) -> Response:
    hit = _png_cache.get(key)
    if hit and time.monotonic() - hit[0] < 60:
        return Response(hit[1], media_type="image/png", headers={"cache-control": "public, max-age=300"})
    try:
        data = build()
    except ImportError:  # Pillow missing on this box: the brand ad still makes a decent preview
        if not FALLBACK_PNG.exists():
            raise HTTPException(404, "no card renderer")
        data = FALLBACK_PNG.read_bytes()
    _png_cache[key] = (time.monotonic(), data)
    return Response(data, media_type="image/png", headers={"cache-control": "public, max-age=300"})


# ------------------------------------------------------------------------------------------------ legion

def _legion(db: Session, ex: ExchangeAdapter, slug: str) -> dict:
    from .routes_orgs import _summary

    org = db.scalar(select(Org).where(Org.slug == slug))
    if not org:
        raise HTTPException(404, "no such legion")
    return _summary(db, ex, org)


def legion_blurb(s: dict) -> str:
    L = s["limits"]
    markets = ", ".join(m.split(":")[-1] for m in L["allowed_markets"][:4])
    return (f"{_usd(s['equity'])} pooled, {s['depositors']} {'person' if s['depositors'] == 1 else 'people'}, "
            f"{L['max_leverage']:g}x cap, stop at {L['drawdown_flatten_pct']:g}%. {markets}.")


@router.get("/l/{slug}", response_class=HTMLResponse)
def legion_link(slug: str, request: Request, frm: str | None = Query(default=None, alias="from", max_length=40), db: Session = DbDep,
                ex: ExchangeAdapter = Depends(exchange)):
    s = _legion(db, ex, slug)
    who = re.sub(r"[^\w .'-]", "", frm or "")[:40]
    title = f"{who} invited you to {s['name']}" if who else f"{s['name']} on Protoss"
    base = _base(request)
    return page(title=title, description=legion_blurb(s) + f" Led by {s['leader']}. Every fill is public.", image=f"{base}/og/l/{slug}.png",
                url=f"{base}/l/{slug}", to=f"/#/p/{slug}" + (f"?from={who}" if who else ""))


@router.get("/og/l/{slug}.png")
def legion_card(slug: str, db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    s = _legion(db, ex, slug)
    L = s["limits"]
    pnl = s["pnl_pct"]
    return _png(f"l:{slug}:{s['equity']}:{s['depositors']}", lambda: render_card(
        kicker=f"led by {s['leader']}", headline=s["name"],
        stats=[("Pooled", _usd(s["equity"]), None), ("People", str(s["depositors"]), None), ("Since start", f"{pnl:+.1f}%", "pos" if pnl > 0 else "neg" if pnl < 0 else None),
               ("Stop at", f"-{L['drawdown_flatten_pct']:g}%", None)],
        foot=f"{L['max_leverage']:g}x cap · {', '.join(m.split(':')[-1] for m in L['allowed_markets'][:5])} · every fill public"))


# ------------------------------------------------------------------------------------------------ thesis

def _thesis(db: Session, tid: int) -> dict:
    from .huddle import Huddle, Thesis, thesis_out

    t = db.get(Thesis, tid)
    if not t:
        raise HTTPException(404, "no such thesis")
    h = db.get(Huddle, t.huddle_id)
    return thesis_out(db, t) | {"huddle_title": h.title, "web": h.chat_id.split(":", 1)[1] if h.is_web else None, "org_slug": h.org_slug}


def thesis_blurb(t: dict) -> str:
    s = t.get("test") or {}
    ev = s.get("events") or {}
    if t["kind"] == "call":
        test = "A call, scored by the group when it resolves."
    elif ev.get("events"):
        test = (f"{s['market']} {ev['event_mean_pct']:+.1f}% in the {s.get('hold_days')}d after an event vs {ev['any_mean_pct']:+.1f}% after any day, "
                f"{ev['event_up']} of {ev['events']} up.")
    else:
        test = f"Backtest {s.get('return_pct', 0):+.1f}%, max drawdown {s.get('max_drawdown_pct', 0):.1f}%."
    on = [b for b in t["backers"] if b["approved"]]
    back = f" Backed by {', '.join(b['who'] for b in on)}" + (f", {_usd(t['pledged_usd'])} in." if t["pledged_usd"] else ".") if on else ""
    return test + back


@router.get("/t/{tid}", response_class=HTMLResponse)
def thesis_link(tid: int, request: Request, db: Session = DbDep):
    t = _thesis(db, tid)
    base = _base(request)
    to = f"/#/huddle/{t['web']}" if t["web"] else (f"/#/p/{t['org_slug']}" if t["org_slug"] else "/#/lab")
    return page(title=f"Thesis {t['n']} from {t['author']}: {t['label']}", description=thesis_blurb(t), image=f"{base}/og/t/{tid}.png",
                url=f"{base}/t/{tid}", to=to)


@router.get("/og/t/{tid}.png")
def thesis_card(tid: int, db: Session = DbDep):
    t = _thesis(db, tid)
    s = t.get("test") or {}
    ev = s.get("events") or {}
    tone = lambda v: "pos" if v > 0 else "neg" if v < 0 else None  # noqa: E731
    if t["kind"] == "call":
        stats = [("Status", t["outcome"] or ("open" if t["status"] == "live" else "proposed"), None), ("Backers", str(sum(b["approved"] for b in t["backers"])), None)]
        foot = f"a call in {t['huddle_title']}, scored when it resolves"
    elif ev.get("events"):
        stats = [("After an event", f"{ev['event_mean_pct']:+.1f}%", tone(ev["event_mean_pct"])), ("Any day", f"{ev['any_mean_pct']:+.1f}%", tone(ev["any_mean_pct"])),
                 ("Up", f"{ev['event_up']} of {ev['events']}", None), ("In", _usd(t["pledged_usd"]), None)]
        foot = f"{s.get('hold_days')}d hold · {'real Hyperliquid candles' if s.get('real') else 'simulated prices'} · {s.get('start', '')[:7]} to {s.get('end', '')[:7]}"
    else:
        stats = [("Backtest", f"{s.get('return_pct', 0):+.1f}%", tone(s.get("return_pct", 0))), ("Max drawdown", f"-{abs(s.get('max_drawdown_pct', 0)):.1f}%", None),
                 ("Trades", str(s.get("trades", 0)), None), ("In", _usd(t["pledged_usd"]), None)]
        foot = f"{'real Hyperliquid candles' if s.get('real') else 'simulated prices'} · {s.get('start', '')[:7]} to {s.get('end', '')[:7]}"
    rec = t["record"]
    if rec["closed"]:
        stats[-1] = ("Record", f"{rec['up']} of {rec['closed']}", tone(rec["pnl_usd"]))
    curve = [p[1] for p in s.get("curve") or []] or None
    key = f"t:{tid}:{t['status']}:{t['pledged_usd']}:{rec['closed']}:{t['outcome']}"
    return _png(key, lambda: render_card(kicker=f"thesis {t['n']} from {t['author']}", headline=t["label"], stats=stats, foot=foot, curve=curve))


# ------------------------------------------------------------------------------------------------ huddle invite

@router.get("/h/{name}", response_class=HTMLResponse)
def huddle_link(name: str, request: Request):
    name = re.sub(r"[^a-z0-9-]", "", name.lower())[:40] or "demo"
    base = _base(request)
    return page(title=f"Group chat: {name.replace('-', ' ')}", description="Say a trade idea, the Lab tests it on Hyperliquid history, friends thumbs it up and stake. Every fill is public.",
                image=f"{base}/og/h/{name}.png", url=f"{base}/h/{name}", to=f"/#/huddle/{name}")


@router.get("/og/h/{name}.png")
def huddle_card(name: str):
    name = re.sub(r"[^a-z0-9-]", "", name.lower())[:40] or "demo"
    return _png(f"h:{name}:{dt.date.today()}", lambda: render_card(
        kicker="group chat", headline=name.replace("-", " "), stats=[("Say", "an idea", None), ("Back it", "thumbs up", None), ("Stake", "$50 each", None)],
        foot="tested on Hyperliquid history · traded inside hard limits · every fill public"))

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

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
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


def render_card(*, kicker: str, headline: str, stats: list[tuple[str, str, str | None]], foot: str, curve: list[float] | None = None,
                bench: list[float] | None = None) -> bytes:
    """Ink card: kicker, Anton headline, a row of figures over the red rule (the line you drew), optional curve.
    With `bench` (buy and hold over the same window) both lines share one scale and a legend says where each ended."""
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
    y = 140
    right = W - pad - (360 if curve else 0)
    for size, step in ((76, 88), (58, 68)):  # a long headline gets the smaller size instead of running into the figures
        big = _font("Anton-Regular.ttf", size)
        lines = _wrap(d, headline.upper(), big, right - pad, 3)
        if len(lines) <= 2:
            break
    for line in lines:
        d.text((pad, y), line, font=big, fill=TEXT)
        y += step
    if curve and len(curve) > 1:
        bench = bench if bench and len(bench) > 1 else None
        x0, x1, y0, y1 = W - pad - 320, W - pad, 140, 300 if bench else 330
        lo, hi = min(curve + (bench or [])), max(curve + (bench or []))
        Y = lambda v: y1 - (v - lo) / max(1e-9, hi - lo) * (y1 - y0)  # noqa: E731
        line = lambda vals: [(x0 + i * (x1 - x0) / (len(vals) - 1), Y(v)) for i, v in enumerate(vals)]  # noqa: E731
        d.line([(x0, Y(curve[0])), (x1, Y(curve[0]))], fill="#3a3a35", width=2)
        color = POS if curve[-1] >= curve[0] else NEG
        if bench:
            d.line(line(bench), fill=MUTED, width=3, joint="curve")
        d.line(line(curve), fill=color, width=4, joint="curve")
        if bench:
            small = _font("Inter-Variable.ttf", 20, "Medium")
            for i, (name, vals, fill) in enumerate((("the idea", curve, color), ("buy and hold", bench, MUTED))):
                ly = y1 + 18 + i * 28
                d.rectangle([x0, ly + 10, x0 + 18, ly + 13], fill=fill)
                d.text((x0 + 28, ly), f"{name} {(vals[-1] / vals[0] - 1) * 100:+.1f}%", font=small, fill=fill if fill != MUTED else SECOND)
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


def render_phone_card(*, kicker: str, headline: str, stats: list[tuple[str, str, str | None]], foot: str, curve: list[float] | None = None,
                      bench: list[float] | None = None) -> bytes:
    """The same card laid out for a phone (1080x1350, 4:5): Telegram shows it about 360 px wide, so every piece of text is at
    least 30 px here and the chart takes the full width."""
    from PIL import Image, ImageDraw

    w, h, pad = 1080, 1350, 64
    im = Image.new("RGB", (w, h), INK)
    d = ImageDraw.Draw(im)
    brand_x = pad
    if PROBE_PNG.exists():
        with Image.open(PROBE_PNG) as source:
            mascot = source.convert("RGBA")
            mascot.thumbnail((76, 76))
            im.paste(mascot, (pad - 8, 44), mascot)
        brand_x += 80
    d.text((brand_x, 58), "PROTOSS", font=_font("Anton-Regular.ttf", 44), fill=TEXT)
    k = _font("Inter-Variable.ttf", 34, "Medium")
    d.text((w - pad - d.textlength(kicker, font=k), 66), kicker, font=k, fill=SECOND)
    y = 160
    for size, step in ((88, 100), (70, 80)):
        big = _font("Anton-Regular.ttf", size)
        lines = _wrap(d, headline.upper(), big, w - 2 * pad, 3)
        if len(lines) <= 2:
            break
    for line in lines:
        d.text((pad, y), line, font=big, fill=TEXT)
        y += step
    if curve and len(curve) > 1:
        bench = bench if bench and len(bench) > 1 else None
        x0, x1, y0, y1 = pad, w - pad, y + 40, y + 440
        lo, hi = min(curve + (bench or [])), max(curve + (bench or []))
        Y = lambda v: y1 - (v - lo) / max(1e-9, hi - lo) * (y1 - y0)  # noqa: E731
        line = lambda vals: [(x0 + i * (x1 - x0) / (len(vals) - 1), Y(v)) for i, v in enumerate(vals)]  # noqa: E731
        d.line([(x0, Y(curve[0])), (x1, Y(curve[0]))], fill="#3a3a35", width=3)
        color = POS if curve[-1] >= curve[0] else NEG
        if bench:
            d.line(line(bench), fill=MUTED, width=5, joint="curve")
        d.line(line(curve), fill=color, width=7, joint="curve")
        y = y1 + 28
        legend = _font("Inter-Variable.ttf", 36, "Medium")
        for name, vals, fill in (("the idea", curve, color),) + ((("buy and hold", bench, MUTED),) if bench else ()):
            d.rectangle([x0, y + 18, x0 + 30, y + 24], fill=fill)
            d.text((x0 + 46, y), f"{name} {(vals[-1] / vals[0] - 1) * 100:+.1f}%", font=legend, fill=fill if fill != MUTED else SECOND)
            y += 50
    ys = max(y + 30, h - 300)
    lab, val = _font("Inter-Variable.ttf", 32, "Medium"), _font("JetBrainsMono-Medium.ttf", 60)
    cols = stats[:3]
    colw = (w - 2 * pad) // max(1, len(cols))
    for i, (label, value, tone) in enumerate(cols):
        d.text((pad + i * colw, ys), label, font=lab, fill=MUTED)
        d.text((pad + i * colw, ys + 42), value, font=val, fill={"pos": POS, "neg": NEG}.get(tone or "", TEXT))
    d.rectangle([pad, ys + 130, w - pad, ys + 133], fill=RED)  # the line you drew
    for i, part in enumerate(_wrap(d, foot, _font("Inter-Variable.ttf", 30, "Regular"), w - 2 * pad, 2)):
        d.text((pad, ys + 156 + i * 40), part, font=_font("Inter-Variable.ttf", 30, "Regular"), fill=SECOND)
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

def _thesis(db: Session, tid: int, token: str | None = None) -> dict:
    from .huddle import Huddle, Thesis, _guard, thesis_out

    t = db.get(Thesis, tid)
    if not t:
        raise HTTPException(404, "no such thesis")
    h = db.get(Huddle, t.huddle_id)
    _guard(h, token)
    private = not (h.is_web and get_settings().arena_mode in ('sim', 'paper'))
    return thesis_out(db, t) | {"huddle_title": h.title, "web": h.chat_id.split(":", 1)[1] if h.is_web else None, "org_slug": h.org_slug, "private": private}


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
def thesis_link(tid: int, request: Request, x_admin_token: str | None = Header(default=None), db: Session = DbDep):
    t = _thesis(db, tid, x_admin_token)
    base = _base(request)
    to = f"/#/huddle/{t['web']}" if t["web"] else (f"/#/p/{t['org_slug']}" if t["org_slug"] else "/#/lab")
    response = page(title=f"Thesis {t['n']} from {t['author']}: {t['label']}", description=thesis_blurb(t), image=f"{base}/og/t/{tid}.png",
                    url=f"{base}/t/{tid}", to=to)
    if t['private']:
        response.headers['Cache-Control'] = 'private, no-store'
    return response


def card_png(t: dict, phone: bool = False) -> bytes:
    """The idea card as a PNG, from a thesis dict (thesis_out shape). Used by the link preview and scripts/idea_snapshots.py."""
    s = t.get("test") or {}
    ev = s.get("events") or {}
    tone = lambda v: "pos" if v > 0 else "neg" if v < 0 else None  # noqa: E731
    if t["kind"] == "call":
        stats = [("Status", t["outcome"] or ("open" if t["status"] == "live" else "proposed"), None), ("Backers", str(sum(b["approved"] for b in t["backers"])), None)]
        foot = f"a call in {t.get('huddle_title', 'the group')}, scored when it resolves"
    elif ev.get("events"):
        stats = [("After an event", f"{ev['event_mean_pct']:+.1f}%", tone(ev["event_mean_pct"])), ("Any day", f"{ev['any_mean_pct']:+.1f}%", tone(ev["any_mean_pct"])),
                 ("Up", f"{ev['event_up']} of {ev['events']}", None), ("In", _usd(t["pledged_usd"] or 0), None)]
        foot = f"{s.get('hold_days')}d hold · {'real Hyperliquid candles' if s.get('real') else 'simulated prices'} · {s.get('start', '')[:7]} to {s.get('end', '')[:7]}"
    else:
        days = (dt.date.fromisoformat(s["end"]) - dt.date.fromisoformat(s["start"])).days if s.get("start") else 0
        history = f"{days} days" if days < 90 else f"{round(days / 30.4)} months"
        stats = [("Return", f"{s.get('return_pct', 0):+.1f}%", tone(s.get("return_pct", 0))), ("Worst drop", f"-{abs(s.get('max_drawdown_pct', 0)):.1f}%", None),
                 ("History", history, "neg" if days < 60 else None), ("In", _usd(t["pledged_usd"] or 0), None)]
        foot = f"{'real Hyperliquid candles' if s.get('real') else 'simulated prices'} · since {s.get('start', '')}" + (" · too short to call" if days < 60 else "")
    rec = t["record"]
    if rec["closed"]:
        stats[-1] = ("Record", f"{rec['up']} of {rec['closed']}", tone(rec["pnl_usd"]))
    elif t.get("pledged_usd") is None:
        stats = stats[:-1]  # a card outside a chat (the website) has no stake to show
    curve = [p[1] for p in s.get("curve") or []] or None
    bench = [p[1] for p in s.get("bench") or []] or None
    kicker = f"idea {t['n']}" if not t.get("author") or t["author"].startswith("tg:") else f"idea {t['n']} from {t['author']}"
    return (render_phone_card if phone else render_card)(kicker=kicker, headline=t["label"], stats=stats, foot=foot, curve=curve, bench=bench)


@router.get("/og/t/{tid}.png")
def thesis_card(tid: int, format: str = Query(default="og", pattern="^(og|phone)$"), x_admin_token: str | None = Header(default=None), db: Session = DbDep):
    """format=og is the 1200x630 link preview; format=phone is the tall card the Telegram bot posts."""
    t = _thesis(db, tid, x_admin_token)
    rec = t["record"]
    key = f"t:{tid}:{format}:{t['label']}:{t['status']}:{t['pledged_usd']}:{rec['closed']}:{t['outcome']}"
    response = _png(key, lambda: card_png(t, phone=format == "phone"))
    if t['private']:
        response.headers['Cache-Control'] = 'private, no-store'
    return response


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

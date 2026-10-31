"""The Lab: natural-language what-if backtests.

  GET  /lab/examples   prompts worth trying
  POST /lab/chat       {"message", "starting_equity", "days"} -> backtest | clarify | error

A message is planned into a Spec (Claude when ANTHROPIC_API_KEY is set, a rule-based parser otherwise and
as the fallback), run through backtest.run_backtest, and returned with a plain-English reply and an agent
definition the UI can deploy.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import logging
import os
import re
from typing import Annotated, Literal, Union

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from .backtest import BacktestResult, SourceUnavailable, get_source, run_backtest
from .config import get_settings

log = logging.getLogger("coliseum.lab")
router = APIRouter(prefix="/lab", tags=["lab"])
Bar = Literal["1h", "4h", "1d"]
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def norm_market(v: str) -> str:
    v = v.strip()
    return f"{v.split(':')[0].lower()}:{v.split(':', 1)[1].upper()}" if ":" in v else v.upper()


# ------------------------------------------------------------------------------------------- specs

class _Common(BaseModel):
    model_config = ConfigDict(extra="ignore")
    days: int = Field(default=180, ge=2, le=730)
    starting_equity: float = Field(default=10_000.0, gt=0)
    fee_bps: float = Field(default=4.5, ge=0, le=100)

    @field_validator("market", "markets", check_fields=False)
    @classmethod
    def _norm(cls, v):
        return [norm_market(m) for m in v] if isinstance(v, list) else (norm_market(v) if v else v)

    def label(self) -> str:
        return LABELS[self.type](self)


class EventBuySpec(_Common):
    type: Literal["event_buy"] = "event_buy"
    market: str
    event_set: Literal["major_hacks", "custom"] = "major_hacks"
    custom_dates: list[dt.date] | None = None
    hold_days: int = Field(default=7, ge=1, le=365)
    side: Literal["long", "short"] = "long"
    size_pct: float = Field(default=1.0, gt=0, le=1.0)


class TailWalletSpec(_Common):
    type: Literal["tail_wallet"] = "tail_wallet"
    address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    scale: float | None = Field(default=None, gt=0)
    markets: list[str] | None = None


class MomentumSpec(_Common):
    type: Literal["momentum"] = "momentum"
    market: str
    fast: int = Field(default=3, ge=1, le=500)
    slow: int = Field(default=10, ge=2, le=2000)
    bar: Bar = "1h"

    @model_validator(mode="after")
    def _order(self):
        if self.fast >= self.slow:
            raise ValueError("fast must be shorter than slow")
        return self


class MeanRevSpec(_Common):
    type: Literal["meanrev"] = "meanrev"
    market: str
    lookback: int = Field(default=20, ge=3, le=2000)
    z: float = Field(default=1.5, gt=0, le=10)
    bar: Bar = "1h"


class DcaSpec(_Common):
    type: Literal["dca"] = "dca"
    market: str
    every_days: int = Field(default=7, ge=1, le=365)
    amount: float = Field(default=100.0, gt=0)


class WeekdaySpec(_Common):
    type: Literal["weekday"] = "weekday"
    market: str
    buy_weekday: int = Field(default=0, ge=0, le=6)
    sell_weekday: int = Field(default=4, ge=0, le=6)
    bar: Literal["1h"] = "1h"


class BuyHoldSpec(_Common):
    type: Literal["buy_hold"] = "buy_hold"
    market: str


class Clarify(BaseModel):
    type: Literal["clarify"] = "clarify"
    question: str


class LabError(Exception):
    """The message was understood but cannot be run (bad address, unlisted market)."""


LABELS = {
    "event_buy": lambda s: f"{'Buy' if s.side == 'long' else 'Short'} {s.market} on {'major hacks' if s.event_set == 'major_hacks' else f'{len(s.custom_dates or [])} custom dates'}, hold {s.hold_days}d",
    "tail_wallet": lambda s: f"Tail {s.address[:6]}…{s.address[-4:]}",
    "momentum": lambda s: f"{s.fast}/{s.slow} momentum crossover on {s.market} ({s.bar})",
    "meanrev": lambda s: f"Mean reversion on {s.market}: fade {s.z:g} sd of {s.lookback}-bar mean ({s.bar})",
    "dca": lambda s: f"DCA ${s.amount:,.0f} into {s.market} every {s.every_days}d",
    "weekday": lambda s: f"Buy {s.market} {WD[s.buy_weekday]} open, sell {WD[s.sell_weekday]} close",
    "buy_hold": lambda s: f"Buy and hold {s.market}",
}
SPECS = (EventBuySpec, TailWalletSpec, MomentumSpec, MeanRevSpec, DcaSpec, WeekdaySpec, BuyHoldSpec)
Spec = Annotated[Union[SPECS], Field(discriminator="type")]
PlanAdapter: TypeAdapter = TypeAdapter(Annotated[Union[SPECS + (Clarify,)], Field(discriminator="type")])

EXAMPLES = [
    "What if I bought XMR every time a major company got hacked and held 7 days?",
    "Backtest a 3/10 momentum crossover on BTC over the last 90 days with $25k",
    "DCA $100 into HYPE every week since January",
    "What if I bought NVDA perps every Monday open and sold Friday close?",
    "Fade 2 standard deviation moves in ETH on 4h bars, 20-bar lookback",
    "Tail 0x0000000000000000000000000000000000000000 with $10k",
    "Buy and hold SOL for the past year",
    "Short BTC for 3 days after each of these dates: 2025-02-21, 2025-05-15",
]

# ------------------------------------------------------------------------------------------- LLM planner

SYSTEM = """You turn a trader's what-if question into ONE JSON object and nothing else (no prose, no code fences).
Return exactly one of:
{"type":"event_buy","market":str,"event_set":"major_hacks"|"custom","custom_dates":[YYYY-MM-DD]|null,"hold_days":int,"side":"long"|"short","size_pct":float}
{"type":"tail_wallet","address":"0x..40 hex","scale":float|null,"markets":[str]|null}
{"type":"momentum","market":str,"fast":int,"slow":int,"bar":"1h"|"4h"|"1d"}
{"type":"meanrev","market":str,"lookback":int,"z":float,"bar":"1h"|"4h"|"1d"}
{"type":"dca","market":str,"every_days":int,"amount":float}
{"type":"weekday","market":str,"buy_weekday":int,"sell_weekday":int}   (0=Monday)
{"type":"buy_hold","market":str}
{"type":"clarify","question":str}   when the message cannot be mapped; ask ONE specific question.
Every spec may also carry "days" (lookback window, 2-730) and "starting_equity" when the user states them.
Markets are Hyperliquid perp names: BTC, ETH, SOL, HYPE, XMR, DOGE; stocks/indices are HIP-3 names like xyz:NVDA, xyz:TSLA, xyz:SP500.
"hacked/breach/exploit" means event_set major_hacks. Omit fields you are unsure about; defaults apply."""


def _plan_llm(message: str, defaults: dict) -> Union[Spec, Clarify, None]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            timeout=20.0,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("LAB_MODEL", "claude-sonnet-4-5"), "max_tokens": 400, "system": SYSTEM, "messages": [{"role": "user", "content": message}]},
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
        if data.get("type") != "clarify":
            data = {**defaults, **{k: v for k, v in data.items() if v is not None}}
        return PlanAdapter.validate_python(data)
    except Exception as e:  # any failure falls through to the rule-based parser
        log.warning("lab llm planner failed: %s", e)
        return None


# ------------------------------------------------------------------------------------------- rule-based planner

WORDS = {
    "bitcoin": "BTC", "btc": "BTC", "ether": "ETH", "ethereum": "ETH", "eth": "ETH", "monero": "XMR", "xmr": "XMR",
    "solana": "SOL", "sol": "SOL", "hype": "HYPE", "doge": "DOGE", "dogecoin": "DOGE",
    "nvidia": "xyz:NVDA", "nvda": "xyz:NVDA", "tesla": "xyz:TSLA", "tsla": "xyz:TSLA", "s&p 500": "xyz:SP500", "s&p": "xyz:SP500", "spx": "xyz:SP500", "sp500": "xyz:SP500",
}
ALIASES = {"NVDA": "xyz:NVDA", "TSLA": "xyz:TSLA", "SPX": "xyz:SP500", "SP500": "xyz:SP500", "SOXL": "xyz:SOXL"}
STOP = {"DCA", "YTD", "MA", "SMA", "EMA", "USD", "USDC", "BUY", "SELL", "HOLD", "AND", "THE", "PNL", "API", "ETF", "OK", "AI", "HL", "PERP", "PERPS", "LONG", "SHORT", "VS", "WHAT", "IF", "SD", "HODL"}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_RE = "|".join(d[:3] + "(?:" + d[3:] + ")?" for d in DAYS)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
UNITS = {"day": 1, "week": 7, "month": 30, "year": 365}
KINDS = [  # first match wins; tail_wallet is handled before these
    ("event_buy", r"hack|breach|exploit|cyber ?attack|ransomware"),
    ("momentum", r"momentum|crossover|ma cross|moving average"),
    ("meanrev", r"mean[\s-]?rev|reversion|\bfade\b|z[\s-]?score|standard deviation|\bsigma\b"),
    ("dca", r"\bdca\b|dollar[\s-]cost"),
    ("weekday", rf"every\s+({DAY_RE})|weekday|buy\w*\s+(?:on\s+|every\s+)?({DAY_RE})"),
    ("dca", r"every\s+(?:other\s+)?(?:week|day|month|\d+\s*days?)|\b(weekly|daily|monthly)\b"),
    ("buy_hold", r"buy (?:and|&) hold|hodl|just bought|bought and held|held it|\bhold\b"),
]
HOLD_RE = re.compile(r"(?:hold|held|holding)\b[^0-9]{0,24}?(\d+)\s*-?\s*(day|week)s?|\bfor\s+(\d+)\s*(day|week)s?\b|(\d+)\s*-?\s*(day|week)\s+hold")


def _num(s: str, suffix: str | None) -> float:
    return float(s.replace(",", "")) * {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}.get((suffix or "").lower(), 1)


def _market(raw: str, low: str, known: set[str]) -> str | None:
    if m := re.search(r"\b([a-z]{2,8}):([A-Za-z0-9]{1,10})\b", raw):
        return norm_market(m.group(0))
    cands = [ALIASES.get(t, t) for t in re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", raw) if t not in STOP]
    if hit := next((c for c in cands if c in known), None):
        return hit
    for word in sorted(WORDS, key=len, reverse=True):
        if re.search(rf"(?<![a-z&]){re.escape(word)}(?![a-z])", low):
            return WORDS[word]
    return cands[0] if cands else None


def _days(low: str, today: dt.date) -> int:
    """Window length stated in the message, 0 if none."""
    if m := re.search(r"(?:last|past|over|previous)\s+(\d+)\s*(day|week|month|year)s?", low):
        return int(m.group(1)) * UNITS[m.group(2)]
    if re.search(r"(?:last|past)\s+year|\b12 months\b|\b1y\b", low):
        return 365
    if m := re.search(r"(?:last|past)\s+(week|month)\b", low):
        return UNITS[m.group(1)]
    if re.search(r"\bytd\b|this year|since jan(?:uary)?\b(?!\s+20)", low):
        return (today - dt.date(today.year, 1, 1)).days
    if m := re.search(r"since\s+(" + "|".join(MONTHS) + r")(?:\s+(20\d\d))?", low):
        month = MONTHS.index(m.group(1)) + 1
        year = int(m.group(2)) if m.group(2) else (today.year if month <= today.month else today.year - 1)
        return (today - dt.date(year, month, 1)).days
    if m := re.search(r"since\s+(20\d\d)\b", low):
        return (today - dt.date(int(m.group(1)), 1, 1)).days
    return 0


def plan_rules(message: str, starting_equity: float, days: int, known: set[str], today: dt.date | None = None) -> Union[Spec, Clarify]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    address = re.search(r"\b0x[0-9a-fA-F]+\b", message)
    raw = message.replace(address.group(0), " ") if address else message
    low = raw.lower()
    iso_dates = []
    for d in re.findall(r"\b(20\d\d-\d\d-\d\d)\b", low):
        try:
            iso_dates.append(dt.date.fromisoformat(d))
        except ValueError:
            continue
    low_nd = re.sub(r"\b20\d\d-\d\d-\d\d\b", " ", low)  # numbers inside dates must not look like parameters
    market = _market(raw, low, known)
    explicit_days = _days(low, today)
    if iso_dates and not explicit_days:  # a custom event list should fit in the window
        days = max(days, (today - min(iso_dates)).days + 30)
    common: dict = {"days": min(730, max(2, explicit_days or days)), "starting_equity": starting_equity}
    if m := re.search(r"(?:with|starting(?: with| at)?|start(?:ing)? at|using)\s+\$?\s?(\d[\d,]*(?:\.\d+)?)\s*(k|m|thousand|million)?\b", low_nd):
        common["starting_equity"] = _num(m.group(1), m.group(2))

    if re.search(r"\b(tail|follow|copy|mirror)(?:ed|ing|s)?\b", low):
        if not address:
            return Clarify(question="Which wallet should I tail? Paste its 0x address (42 characters).")
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address.group(0)):
            raise LabError(f"{address.group(0)[:12]}… is not a valid wallet address: expected 0x followed by 40 hex characters.")
        return TailWalletSpec(address=address.group(0), **common)

    kind = next((k for k, pat in KINDS if re.search(pat, low)), None)
    if kind is None and iso_dates and re.search(r"\b(after|on|following)\b", low):
        kind = "event_buy"
    if kind is None and market is None:
        return Clarify(question="Which idea should I test (buy and hold, a momentum crossover, mean reversion, DCA, a weekday pattern, or buying on hack events), and on which market, e.g. BTC?")
    if market is None:
        return Clarify(question="Which market should I run that on: BTC, ETH, SOL, HYPE, XMR, or a HIP-3 name like xyz:NVDA?")
    if kind is None:
        return Clarify(question=f"What should I do with {market}: buy and hold, a momentum crossover, mean reversion, DCA, or buy it on hack events?")

    bar = "4h" if re.search(r"\b4\s*-?\s*h(?:our)?\b|four[- ]hour", low) else "1d" if re.search(r"\b1d\b|\bdaily (?:bars?|candles?)\b|day bars", low) else "1h"
    extra: dict = {}
    if kind == "event_buy":
        if iso_dates:
            extra = {"event_set": "custom", "custom_dates": iso_dates}
        if m := HOLD_RE.search(low_nd):
            n, unit = next((g, u) for g, u in zip(m.groups()[::2], m.groups()[1::2]) if g)
            extra["hold_days"] = int(n) * (7 if unit == "week" else 1)
        if re.search(r"\bshort(?:ed|ing)?\b", low):
            extra["side"] = "short"
        if m := re.search(r"(\d+(?:\.\d+)?)\s*%\s*of", low_nd):
            extra["size_pct"] = min(1.0, float(m.group(1)) / 100)
        return EventBuySpec(market=market, **extra, **common)
    if kind == "momentum":
        m = re.search(r"(\d+)\s*/\s*(\d+)", low_nd) or re.search(r"(\d+)\s*(?:and|&|-)\s*(\d+)\s*(?:bar|period|hour|day)?s?\s*(?:ma|sma|ema|moving)", low_nd)
        f, s = (int(m.group(1)), int(m.group(2))) if m else (3, 10)
        return MomentumSpec(market=market, fast=min(f, s), slow=max(f, s), bar=bar, **common)
    if kind == "meanrev":
        if m := re.search(r"(\d+)\s*-?\s*(?:bar|period|hour|day)?s?\s*(?:lookback|window)|lookback\s*(?:of\s*)?(\d+)", low_nd):
            extra["lookback"] = int(m.group(1) or m.group(2))
        if m := re.search(r"z(?:-score)?\s*(?:=|of|>|above|over)?\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:sigma|sd|std|standard deviation)", low_nd):
            extra["z"] = float(m.group(1) or m.group(2))
        return MeanRevSpec(market=market, bar=bar, **extra, **common)
    if kind == "dca":
        if m := re.search(r"every\s+(\d+)\s*days?", low_nd):
            extra["every_days"] = int(m.group(1))
        else:
            for pat, n in ((r"every other day", 2), (r"\bdaily\b|every day", 1), (r"every (?:two|2) weeks|biweekly|fortnight", 14), (r"\bmonthly\b|every month", 30)):
                if re.search(pat, low):
                    extra["every_days"] = n
                    break
        if m := re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|m)?\b(?!\s*(?:starting|equity|account))", low_nd):
            extra["amount"] = _num(m.group(1), m.group(2))
        return DcaSpec(market=market, **extra, **common)
    if kind == "weekday":
        wds = [next(i for i, d in enumerate(DAYS) if d.startswith(f)) for f in re.findall(rf"\b({DAY_RE})\b", low)]
        return WeekdaySpec(market=market, buy_weekday=wds[0] if wds else 0, sell_weekday=wds[1] if len(wds) > 1 else 4, **common)
    return BuyHoldSpec(market=market, **common)


def plan(message: str, starting_equity: float = 10_000.0, days: int = 180, known: set[str] | None = None) -> Union[Spec, Clarify]:
    """Spec or Clarify for a chat message. Claude first when configured, rule-based parser otherwise."""
    known = known or set(get_settings().sim_markets)
    planned = _plan_llm(message, {"days": days, "starting_equity": starting_equity})
    return planned if planned is not None else plan_rules(message, starting_equity, days, known)


# ------------------------------------------------------------------------------------------- endpoints

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    starting_equity: float = Field(default=10_000.0, gt=0)
    days: int = Field(default=180, ge=2, le=730)


def _out(kind: str, reply: str, spec=None, result=None, deployable=None) -> dict:
    return {"kind": kind, "reply": reply, "spec": spec, "result": result, "deployable": deployable}


def _deployable(spec, res: BacktestResult) -> dict:
    markets = [spec.market] if hasattr(spec, "market") else [m for m in res.market.split(",") if m]
    slug = "-".join(m.lower().replace(":", "-") for m in markets)[:40] or "multi"
    if spec.type == "momentum":
        desc = f"Lab: {spec.fast}/{spec.slow} {spec.bar} moving-average crossover on {spec.market}; long above, short below (agents/momentum.py semantics)"
    elif spec.type == "meanrev":
        desc = f"Lab: fade {spec.z:g} sd moves vs the {spec.lookback}-bar mean on {spec.market} {spec.bar} bars, exit at the mean, stop at 3 sd (agents/meanrev.py semantics)"
    else:
        desc = f"Lab: {res.label} (no agent runtime for {spec.type} yet)"
    return {
        "name": f"lab-{spec.type.replace('_', '-')}-{slug}",
        "strategy": desc[:280],
        "markets": markets,
        "limits": {"max_leverage": 2.0, "drawdown_flatten_pct": 10.0, "daily_loss_pct": 4.0, "allowed_markets": markets},
    }


def _reply(spec, res: BacktestResult, simulated: bool) -> str:
    bench = res.benchmark_curve[-1][1] / res.starting_equity * 100 - 100 if res.benchmark_curve else None
    s1 = f"Tested {res.label} from {res.start:%b %d, %Y} to {res.end:%b %d, %Y} starting with ${res.starting_equity:,.0f}."
    s2 = f"Result: {res.return_pct:+.1f}%" + (f" vs {bench:+.1f}% for buy-and-hold" if bench is not None else "")
    s2 += f", max drawdown {res.max_drawdown_pct:.1f}%, {res.trades} trade{'s' if res.trades != 1 else ''}"
    s2 += (f", {res.win_rate_pct:.0f}% winners" if res.win_rate_pct is not None else "") + (f", Sharpe {res.sharpe:.2f}." if res.sharpe is not None else ".")
    caveats = [
        "Prices are simulated (seeded GBM), so this exercises the mechanics only and says nothing about the real market."
        if simulated
        else "Past Hyperliquid candles with taker fees and 3 bp slippage; funding is not modelled."
    ]
    if spec.type == "event_buy" and spec.event_set == "major_hacks":
        caveats.append("The hack list is a curated, illustrative set, so verify the dates before relying on it.")
    if spec.type == "tail_wallet" and "synthesized" in res.label:
        caveats.append("Wallet fills were unavailable, so the fill series is synthesized from a 3/10 momentum strategy on BTC.")
    return " ".join([s1, s2] + caveats)


@router.get("/examples")
def examples() -> dict:
    return {"examples": EXAMPLES}


@router.post("/chat")
def chat(body: ChatIn) -> dict:
    source = get_source(get_settings())
    known = set(source.markets())
    try:
        planned = plan(body.message, body.starting_equity, body.days, known)
    except LabError as e:
        return _out("error", str(e))
    if isinstance(planned, Clarify):
        return _out("clarify", planned.question)
    for m in [planned.market] if hasattr(planned, "market") else (planned.markets or []):
        if not source.has(m):
            near = difflib.get_close_matches(m, sorted(known), n=1, cutoff=0.6)
            hint = f" Did you mean {near[0]}?" if near else f" Listed markets include {', '.join(sorted(known)[:8])}."
            return _out("error", f"{m} is not a listed market here.{hint}")
    try:
        res = run_backtest(planned, source)
    except (SourceUnavailable, ValueError) as e:
        return _out("error", f"Could not run that backtest: {e}", spec=planned.model_dump(mode="json"))
    if planned.type not in ("momentum", "meanrev"):
        res.notes.append(f"no agent runtime for {planned.type} strategies yet: deploying creates the agent definition only")
    return _out("backtest", _reply(planned, res, source.name != "hyperliquid"), planned.model_dump(mode="json"), res.as_dict(), _deployable(planned, res))

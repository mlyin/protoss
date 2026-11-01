"""Refresh the Lab's offline candle cache from Hyperliquid's public API.

    python scripts/candles.py                  # every market already cached plus the defaults, daily bars, full history
    python scripts/candles.py BTC ETH --bar 1d

Writes backend/app/data/candles/<MARKET>_<bar>.csv (t,o,h,l,c,v; t in seconds), the format FileCandles reads.
Run it from a machine that can reach api.hyperliquid.xyz; the cloud often cannot.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import httpx

API = "https://api.hyperliquid.xyz/info"
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "candles"
DEFAULT = ["BTC", "ETH", "SOL", "HYPE", "XMR"]


def cached(bar: str) -> list[str]:
    """Markets that already have a file for this bar, so a bare run refreshes everything the Lab can read."""
    return sorted(p.name[: -len(f"_{bar}.csv")].replace("_", ":", 1) for p in OUT.glob(f"*_{bar}.csv"))
BAR_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def fetch(client: httpx.Client, coin: str, bar: str) -> list[dict]:
    """Walk forward from the start of time in 5000-candle pages (the API's cap per call)."""
    now = int(time.time() * 1000)
    start, rows = 0, {}
    while start < now:
        r = client.post(API, json={"type": "candleSnapshot", "req": {"coin": coin, "interval": bar, "startTime": start, "endTime": now}})
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        for c in page:
            rows[int(c["t"])] = c
        last = int(page[-1]["t"])
        if len(page) < 5000 or last + BAR_MS[bar] <= start:
            break
        start = last + BAR_MS[bar]
    # drop the bar still forming: a half-day candle would read as a real close
    return [rows[t] for t in sorted(rows) if t + BAR_MS[bar] <= now]


def write(coin: str, bar: str, rows: list[dict]) -> Path:
    path = OUT / f"{coin.replace(':', '_')}_{bar}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        for c in rows:
            w.writerow([int(c["t"]) // 1000, c["o"], c["h"], c["l"], c["c"], c["v"]])
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("markets", nargs="*")
    ap.add_argument("--bar", default="1d", choices=sorted(BAR_MS))
    a = ap.parse_args()
    a.markets = a.markets or sorted(set(DEFAULT) | set(cached(a.bar)))
    with httpx.Client(timeout=30) as client:
        for m in a.markets:
            rows = fetch(client, m, a.bar)
            if not rows:
                print(f"{m}: no candles (not a Hyperliquid market?)")
                continue
            p = write(m, a.bar, rows)
            first = time.strftime("%Y-%m-%d", time.gmtime(int(rows[0]["t"]) / 1000))
            last = time.strftime("%Y-%m-%d", time.gmtime(int(rows[-1]["t"]) / 1000))
            print(f"{m}: {len(rows)} bars {first} to {last} -> {p.relative_to(OUT.parents[3])}")


if __name__ == "__main__":
    main()

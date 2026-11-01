"""Refresh the Dwarkesh Podcast release dates the Lab trades on ("Dwarkesh is always right").

    python scripts/podcast_dates.py

Reads the public podcast feed and writes backend/app/data/dwarkesh.csv with the
UTC date, title, publication timestamp and episode URL. Every row has audio.
"""
from __future__ import annotations

import csv
import datetime as dt
import email.utils
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

FEED = "https://api.substack.com/feed/podcast/69345.rss"
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "dwarkesh.csv"


def main() -> None:
    r = httpx.get(FEED, timeout=30, follow_redirects=True, headers={"user-agent": "protoss-lab"})
    r.raise_for_status()
    rows = []
    for item in ET.fromstring(r.content).iter("item"):
        if item.find("enclosure") is None:
            continue
        when = email.utils.parsedate_to_datetime(item.findtext("pubDate"))
        if when.tzinfo is None:
            raise ValueError("Podcast publication time must include its timezone; saved dataset unchanged")
        when = when.astimezone(dt.timezone.utc)
        rows.append((when.date().isoformat(), " ".join((item.findtext("title") or "").split()),
                     when.isoformat(), (item.findtext("link") or "").strip()))
    rows.sort()
    if not rows:
        raise ValueError("Podcast feed contains no audio episodes; saved dataset unchanged")
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=OUT.parent, newline="", encoding="utf-8", delete=False) as f:
            pending = Path(f.name)
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["date", "title", "published_at", "source_url"])
            w.writerows(rows)
        os.replace(pending, OUT)
    finally:
        if pending:
            pending.unlink(missing_ok=True)
    print(f"{len(rows)} episodes {rows[0][0]} to {rows[-1][0]} -> {OUT.relative_to(OUT.parents[3])}")


if __name__ == "__main__":
    main()

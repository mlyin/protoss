"""Refresh the Dwarkesh Podcast release dates the Lab trades on ("Dwarkesh is always right").

    python scripts/podcast_dates.py

Reads the public podcast feed and writes backend/app/data/dwarkesh.csv (date,title; date in UTC). Every row is an
episode with audio, straight from the feed; nothing is curated by hand.
"""
from __future__ import annotations

import csv
import email.utils
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
        rows.append((when.date().isoformat(), " ".join((item.findtext("title") or "").split())))
    rows.sort()
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "title"])
        w.writerows(rows)
    print(f"{len(rows)} episodes {rows[0][0]} to {rows[-1][0]} -> {OUT.relative_to(OUT.parents[3])}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Append to the shared brain so every agent remembers it.

    python scripts/brain.py remember "don't rename the code's `org` to legion"
    python scripts/brain.py decide "ship the Lab behind a feature flag"
    python scripts/brain.py note runbooks "## Rotate the admin token ..."
"""
import datetime as dt
import sys
from pathlib import Path

BRAIN = Path(__file__).resolve().parents[1] / "brain"
TARGETS = {"remember": "corrections.md", "decide": "decisions.md"}


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    today = dt.date.today().isoformat()
    if cmd in TARGETS:
        line = f"- {today}: {' '.join(sys.argv[2:]).strip()}\n"
        path = BRAIN / TARGETS[cmd]
        lines = path.read_text().splitlines(keepends=True)
        at = next((i for i, l in enumerate(lines) if l.startswith("- ")), len(lines))  # newest first, after the intro
        lines.insert(at, line)
        path.write_text("".join(lines))
    elif cmd == "note" and len(sys.argv) >= 4:
        path = BRAIN / f"{sys.argv[2]}.md"
        with path.open("a") as f:
            f.write("\n" + " ".join(sys.argv[3:]).strip() + "\n")
    else:
        sys.exit(__doc__)
    print(f"wrote {path.relative_to(BRAIN.parent)}")


if __name__ == "__main__":
    main()

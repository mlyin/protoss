#!/usr/bin/env python3
"""Turn a red check into feedback that converges (Level 4): EXPECTED / SAW / FENCE / DEAD ENDS, plus the exit rule.

    harness/check.sh --fence "backend/app/lab.py" | python harness/feedback.py --task harness/runs/<task>

A verdict says "wrong". Feedback says "wrong here, in this way, and you already tried that".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

LINE = re.compile(r"^CHECK (?P<name>\S+) FAIL\s+EXPECTED (?P<expected>.*?)\s+SAW (?P<saw>.*)$")


@dataclass
class Feedback:
    green: bool
    failures: list[dict] = field(default_factory=list)
    fence: str = ""
    dead_ends: list[str] = field(default_factory=list)
    exit: str | None = None  # None = keep looping; "done" | "escalate: same result twice" | "escalate: budget spent"

    def render(self) -> str:
        if self.green:
            return "GREEN\nEXIT done"
        out = []
        for f in self.failures:
            out.append(f"FAILED {f['name']}\nEXPECTED {f['expected']}\nSAW {f['saw']}")
        if self.fence:
            out.append(f"FENCE {self.fence}")
        if self.dead_ends:
            out.append("DEAD ENDS\n" + "\n".join(f"  - {d}" for d in self.dead_ends))
        if self.exit:
            out.append(f"EXIT {self.exit}")
        return "\n".join(out)


def parse(check_output: str) -> list[dict]:
    fails = []
    for line in check_output.splitlines():
        m = LINE.match(line.strip())
        if m:
            fails.append({"name": m["name"], "expected": m["expected"].strip(), "saw": m["saw"].strip()})
    return fails


def signature(fails: list[dict]) -> str:
    """What the world said, independent of wording noise: the same SAW twice means the loop stopped learning."""
    return hashlib.sha1("|".join(f"{f['name']}:{f['saw']}" for f in fails).encode()).hexdigest()[:12]


def build(check_output: str, fence: str = "", attempts: list[dict] | None = None, max_attempts: int = 4) -> Feedback:
    fails = parse(check_output)
    attempts = attempts or []
    if not fails and "RESULT GREEN" in check_output:
        return Feedback(True, exit="done")
    fb = Feedback(False, fails, fence)
    sig = signature(fails)
    fb.dead_ends = [a["summary"] for a in attempts if a.get("summary")]
    if any(a.get("signature") == sig for a in attempts):
        fb.exit = "escalate: same result twice, the missing piece is not effort"
    elif len(attempts) + 1 >= max_attempts:
        fb.exit = "escalate: budget spent"
    return fb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", help="run folder holding attempts.jsonl and task.json")
    ap.add_argument("--fence", default="")
    ap.add_argument("--summary", default="", help="one line on what this attempt tried (becomes a dead end if it fails)")
    args = ap.parse_args()
    out = sys.stdin.read()
    attempts: list[dict] = []
    fence = args.fence
    if args.task:
        run = Path(args.task)
        task = json.loads((run / "task.json").read_text()) if (run / "task.json").exists() else {}
        fence = fence or " ".join(task.get("fence", []))
        log = run / "attempts.jsonl"
        if log.exists():
            attempts = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    fb = build(out, fence, attempts, int(task.get("max_attempts", 4)) if args.task else 4)
    if args.task and not fb.green:
        with (Path(args.task) / "attempts.jsonl").open("a") as f:
            f.write(json.dumps({"signature": signature(fb.failures), "summary": args.summary, "failures": fb.failures}) + "\n")
    print(fb.render())
    sys.exit(0 if fb.green else 1)


if __name__ == "__main__":
    main()

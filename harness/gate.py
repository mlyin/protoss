#!/usr/bin/env python3
"""Gate a change by the price of undo (Level 6). Pure functions; the CLI reads a git diff.

    python harness/gate.py                 # tier + required evidence for the working tree vs HEAD
    python harness/gate.py --base origin/master

Confidence is the model grading its own exam. The gate asks a different question: if this is wrong,
what does it cost to take it back? The answer decides what evidence unlocks a merge.
"""
from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["one_click_undo", "cleanup_undo", "no_undo"]


@dataclass
class Verdict:
    tier: str
    requires: list[str]
    files: dict[str, str] = field(default_factory=dict)  # file -> tier

    @property
    def human_required(self) -> bool:
        return "human" in self.requires


def load_gates(path: Path = ROOT / "harness" / "graph.yaml") -> dict:
    return yaml.safe_load(path.read_text())["gates"]


def tier_for(file: str, gates: dict) -> str:
    """Most expensive tier whose path prefix matches; an unlisted file is cleanup_undo (unknown = careful)."""
    best = None
    for tier in ORDER:
        for p in gates[tier]["paths"]:
            if file == p or file.startswith(p.rstrip("/") + "/"):
                best = tier
    return best or "cleanup_undo"


def gate(files: list[str], gates: dict | None = None) -> Verdict:
    gates = gates or load_gates()
    per = {f: tier_for(f, gates) for f in files}
    if not per:
        return Verdict("one_click_undo", list(gates["one_click_undo"]["requires"]), {})
    top = max(per.values(), key=ORDER.index)
    return Verdict(top, list(gates[top]["requires"]), per)


def changed_files(base: str = "HEAD") -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", base], cwd=ROOT, capture_output=True, text=True).stdout.split()
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    return sorted(set(out) | set(untracked))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    args = ap.parse_args()
    v = gate(changed_files(args.base))
    print(f"GATE {v.tier}  requires: {', '.join(v.requires)}")
    for f, t in sorted(v.files.items(), key=lambda kv: (-ORDER.index(kv[1]), kv[0])):
        print(f"  {t:<16} {f}")
    if v.human_required:
        print("A person signs this one. No score attached; nothing for the model to argue with.")


if __name__ == "__main__":
    main()

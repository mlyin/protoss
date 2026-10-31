#!/usr/bin/env python3
"""The loop runner. Harness (hands, memory, walls) + loop (check, feedback, exits) for one task.

    python harness/run.py tasks/fix-482.yaml            # run with the agent command in the task (default: claude -p)
    python harness/run.py tasks/fix-482.yaml --manual   # you are the agent: it sets up the room, you edit, press Enter to check

A task file:

    name: lab-dca-fix
    goal: "DCA backtests report 1 trade; report the number of buys as trades instead"
    fence: [backend/app/backtest.py, backend/app/lab.py, backend/tests/test_lab.py]
    green: ["a test in test_lab.py asserts trades == number of DCA buys", "full suite green"]
    walls: [backend/migrations, deploy, backend/.env]          # read-only in the room (a permission, not a wish)
    agent: ["claude", "-p", "--permission-mode", "acceptEdits"]  # command; the prompt is appended as the last argument
    max_attempts: 4
    budget_minutes: 45

What it does, per attempt: write PROGRESS.md (goal, green, fence, dead ends, next) into an isolated git worktree,
chmod the walls read-only, run the agent with that file as its brief, run harness/check.sh --fence, turn red
into EXPECTED/SAW/FENCE/DEAD ENDS feedback, repeat until GREEN or an exit rule fires. On GREEN it prints the
gate tier (harness/gate.py) and leaves the branch for a PR. On escalate it writes the lesson stub to
brain/corrections.md via scripts/brain.py so the same failure does not cost twice.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "harness" / "runs"


def sh(cmd: list[str], cwd: Path, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=capture, text=True)


def make_room(name: str) -> Path:
    """An isolated worktree on its own branch: the agent's room. Nothing it does touches the main checkout."""
    room = ROOT.parent / f"{ROOT.name}-rooms" / name
    room.parent.mkdir(exist_ok=True)
    branch = f"harness/{name}"
    if room.exists():
        return room
    try:
        sh(["git", "worktree", "add", "-b", branch, str(room)], ROOT)
    except subprocess.CalledProcessError:
        sh(["git", "worktree", "add", str(room), branch], ROOT)
    for link in (".venv", "web/node_modules"):  # share heavy, read-only toolchains
        src, dst = ROOT / link, room / link
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src)
    return room


def raise_walls(room: Path, walls: list[str]) -> None:
    """A wall is not an instruction. Paths the task may not change become read-only in the room."""
    for w in walls:
        p = room / w
        if not p.exists():
            continue
        for q in [p] + (list(p.rglob("*")) if p.is_dir() else []):
            try:
                q.chmod(q.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
            except OSError:
                pass


def lower_walls(room: Path, walls: list[str]) -> None:
    for w in walls:
        p = room / w
        if not p.exists():
            continue
        for q in [p] + (list(p.rglob("*")) if p.is_dir() else []):
            try:
                q.chmod(q.stat().st_mode | stat.S_IWUSR)
            except OSError:
                pass


def progress(room: Path, task: dict, attempts: list[dict], feedback: str | None) -> Path:
    """Memory that outlives the context window. The model forgets; this file does not."""
    lines = [f"# PROGRESS: {task['name']}", "", f"goal      {task['goal']}", "green when"]
    lines += [f"  - {g}" for g in task.get("green", [])]
    lines += ["fence     " + " ".join(task.get("fence", [])), "never touch " + " ".join(task.get("walls", []))]
    if attempts:
        lines += ["", "dead ends (do not retry these)"]
        lines += [f"  - attempt {i + 1}: {a.get('summary') or 'see failures'} -> {'; '.join(f['name'] + ': ' + f['saw'][:80] for f in a['failures'])}" for i, a in enumerate(attempts)]
    if feedback:
        lines += ["", "last feedback", *("  " + l for l in feedback.splitlines())]
    lines += ["", "rules", "  - run harness/check.sh before saying done; GREEN is the only done",
              "  - write what you tried and what you learned under `next` below before you stop",
              "  - read brain/INDEX.md first", "", "next", "  - "]
    p = room / "PROGRESS.md"
    p.write_text("\n".join(lines) + "\n")
    return p


def run_agent(room: Path, task: dict, attempt: int, manual: bool) -> str:
    if manual:
        input(f"\n[attempt {attempt}] the room is {room}. Edit there, then press Enter to run the check… ")
        return "manual edit"
    cmd = list(task.get("agent") or ["claude", "-p", "--permission-mode", "acceptEdits"])
    prompt = (f"You are working in {room}. Read PROGRESS.md first and follow it exactly: the goal, what GREEN means, "
              f"the fence (only touch those paths) and the dead ends (never retry them). Make the change, run "
              f"`harness/check.sh --fence \"{' '.join(task.get('fence', []))}\"`, and finish by appending one line under "
              f"`next` in PROGRESS.md saying what you tried. Attempt {attempt}.")
    print(f"[attempt {attempt}] running: {' '.join(shlex.quote(c) for c in cmd)} <prompt>")
    t0 = time.time()
    res = subprocess.run(cmd + [prompt], cwd=room, capture_output=True, text=True)
    print(f"[attempt {attempt}] agent exited {res.returncode} in {time.time() - t0:.0f}s")
    tail = (res.stdout or res.stderr or "").strip().splitlines()
    return tail[-1][:200] if tail else f"exit {res.returncode}"


def check(room: Path, task: dict) -> str:
    env = dict(os.environ, PYTHON=str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv").exists() else os.environ.get("PYTHON", "python3"))
    res = subprocess.run(["bash", "harness/check.sh", "--fence", " ".join(task.get("fence", []))], cwd=room, capture_output=True, text=True, env=env)
    return res.stdout + res.stderr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--manual", action="store_true")
    args = ap.parse_args()
    task = yaml.safe_load(Path(args.task).read_text())
    name = task["name"]
    run_dir = RUNS / name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "task.json").write_text(json.dumps(task, indent=2))
    attempts_log = run_dir / "attempts.jsonl"
    attempts = [json.loads(l) for l in attempts_log.read_text().splitlines() if l.strip()] if attempts_log.exists() else []

    sys.path.insert(0, str(ROOT / "harness"))
    import feedback as FB  # noqa: E402
    import gate as GATE  # noqa: E402

    room = make_room(name)
    walls = task.get("walls", [])
    budget = dt.timedelta(minutes=float(task.get("budget_minutes", 45)))
    started = dt.datetime.now()
    fb_text = None
    max_attempts = int(task.get("max_attempts", 4))
    print(f"room {room}  branch harness/{name}  fence {' '.join(task.get('fence', [])) or '(none)'}")

    while True:
        attempt = len(attempts) + 1
        progress(room, task, attempts, fb_text)
        raise_walls(room, walls)
        summary = run_agent(room, task, attempt, args.manual)
        lower_walls(room, walls)
        out = check(room, task)
        print(out.strip())
        fb = FB.build(out, " ".join(task.get("fence", [])), attempts, max_attempts)
        if dt.datetime.now() - started > budget and not fb.green:
            fb.exit = "escalate: budget spent"
        fb_text = fb.render()
        print("\n" + fb_text)
        if fb.green:
            sh(["git", "add", "-A"], room)
            sh(["git", "commit", "-q", "-m", f"{name}: {task['goal']}\n\nharness: green after {attempt} attempt(s)"], room, check=False)
            files = sh(["git", "diff", "--name-only", "master"], room, check=False).stdout.split()
            v = GATE.gate(files)
            print(f"\nGATE {v.tier}  requires: {', '.join(v.requires)}")
            print(f"branch harness/{name} in {room} is ready for a PR" + ("; a person must sign this one" if v.human_required else ""))
            progress(room, task, attempts, fb_text)
            return
        with attempts_log.open("a") as f:
            f.write(json.dumps({"signature": FB.signature(fb.failures), "summary": summary, "failures": fb.failures}) + "\n")
        attempts.append({"signature": FB.signature(fb.failures), "summary": summary, "failures": fb.failures})
        if fb.exit:
            lesson = f"harness task '{name}' escalated ({fb.exit}); last failure: {fb.failures[0]['name'] if fb.failures else '?'}. Decide which layer owns the lesson (harness/loop/graph) and write the rule, not the transcript."
            subprocess.run([sys.executable, "scripts/brain.py", "remember", lesson], cwd=ROOT, check=False)
            print("\nescalated to a person; a lesson stub is in brain/corrections.md")
            sys.exit(2)


if __name__ == "__main__":
    main()

# Harness, loop, graph

The ladder from "you are the agent's loop" to "a system that needs you once, at the right place"
(m4lka, *Harness, Loops, Graphs*, Oct 2026), applied to this repo. Levels and where each lives here:

| Level | What it adds | Where |
| --- | --- | --- |
| 1 harness: hands | shell, tests, git, the API | the repo; `.venv`, `web/node_modules` shared read-only into each room |
| 2 harness: memory + walls | state outside the context window; limits that hold when the model is wrong | `PROGRESS.md` per room, `brain/`, git commits; `walls:` in a task are chmod'd read-only, `graph.yaml` `no_undo` paths need a person |
| 3 loop: a check that can fail | `harness/check.sh`: tests, Postgres suite, web build, secrets, voice, fence | run before anyone says done; prints `CHECK <name> ok|FAIL EXPECTED … SAW …` |
| 4 loop: feedback that converges | `harness/feedback.py`: EXPECTED / SAW / FENCE / DEAD ENDS; exits on same SAW twice or budget | `harness/run.py` wires it; `harness/runs/<task>/attempts.jsonl` is the loop's own memory |
| 5 graph: shape | nodes with their own room, real edges only (early-start test), code where the answer is deterministic | `harness/graph.yaml` `nodes` + `split_rules`; one worktree per task |
| 6 graph: gates | gate on the price of undo, freeze what passed | `harness/gate.py`: one_click_undo ships on green; cleanup_undo needs green + trace + review; no_undo needs a person |
| 7 learning | a lesson lands on the layer that owns it | escalations write a stub to `brain/corrections.md`; new checks go in `check.sh`; split rules in `graph.yaml` |

## Use it

```bash
harness/check.sh                                  # GREEN or RED, with EXPECTED/SAW per failure
harness/check.sh --fence "backend/app/lab.py"     # also red if the diff left the fence
python harness/gate.py                            # which gate this diff hits and what evidence it needs
python harness/run.py harness/tasks/example-lab-dca-trades.yaml           # agent loop in an isolated worktree
python harness/run.py harness/tasks/example-lab-dca-trades.yaml --manual  # you are the agent, the harness still checks
```

A task is a YAML file: `goal`, `green` (the check, written before the code), `fence` (paths it may touch),
`walls` (paths it cannot), `agent` (the command; `claude -p` by default, swap for `codex exec` or Hermes), budget.
Rooms live in `../coliseum-rooms/<task>` on branch `harness/<task>`; a GREEN run leaves a commit there for a PR.

## The rules in one breath

Write GREEN first. The fence is enforced, not requested. The same SAW twice means stop, not retry.
Gate on undo, read evidence as tests, then trace, then a second opinion, the model's confidence last.
When something escalates, put the lesson on the layer that owns it and nowhere else.

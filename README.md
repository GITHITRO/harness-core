# harness-core

> **Install into OpenCode (human):** `git clone --depth 1 https://github.com/GITHITRO/harness-core /tmp/harness-core && bash /tmp/harness-core/opencode/install.sh /path/to/project`, then in OpenCode press Tab → agent `core`. Details: [opencode/INSTALL.md](opencode/INSTALL.md).
> **Let an AI agent install it:** tell it *"Install harness-core into this project following https://github.com/GITHITRO/harness-core/blob/main/opencode/AGENT.md and report the checks."*
> **Compare base vs harness on a real task:** [opencode/EVAL.md](opencode/EVAL.md) + `opencode/eval/compare.py`.

The meta-cognitive harness core (spec v0.1) and its evaluation stand.

## Stand

Two independent lanes run hourly on GitHub Actions. Each pairs **base** (the bare model under the official protocol)
with **harness** (the same model inside the core) on the same task, back to back.

| Lane | Benchmark | Base protocol | Harness arm |
|---|---|---|---|
| `lane-sb` | SpreadsheetBench Verified-400 (`49b73a9`) | official single-round prompt, 1 call, code executed once, official grader after LibreOffice recalc | input facts → execute → program checks → judge call → repair (≤2) → guard (never ship worse than an earlier passing output) |
| `lane-tau2` | τ²-bench v1.0.1 (`fc0055d`), telecom; later banking_knowledge | stock `llm_agent`, 1 trial, seed 300, temperature 0 | operating protocol in the system prompt + review gate on WRITE tools and transfers, rollback with the reason, ≤2 reviews per step |

Model: `nvidia/nemotron-3.5-super-vl:free` via Kilo Gateway, for the agent and for the τ² user simulator.

### How it runs

- `stand/plan.json` says what each lane runs (stage, n, arms, hourly budget). Edit it to move from `calib` to the main series.
- `stand/pacer.py` is a local OpenAI-compatible proxy started inside each job. It holds a sliding window of
  `budget` requests per hour (the window is carried between runs), retries 429/5xx, and logs **every** request and
  response to JSONL, tagged by benchmark and arm from the URL path.
- Results, per-task trajectories and gzipped logs are committed to branches `runs-sb` and `runs-tau2`
  under `<stage>/`. A run resumes from `results.jsonl`.
- Budgets: sb 80/h + tau2 100/h = 180/h, below Kilo's 200/h for free models.

### Setup

1. Settings → Secrets and variables → Actions → New repository secret: `KILO_API_KEY`.
2. Actions → enable workflows. Runs start on the cron (`:07` sb, `:37` tau2), via *Run workflow*, or on a push to `main` that changes `stand/plan.json` (or the lane's workflow file).

### Security

Model-generated spreadsheet code runs in a subprocess with a clean environment. The Kilo key is read by the pacer from
a temp file that is deleted right after start. Checkouts keep no credentials. The push token appears only in the
clone and commit steps, passed as a one-off header.

## OpenCode package

`opencode/` is the core packaged for OpenCode: primary agent `core`, read-only subagents (`hc-scout`, `hc-redteam`,
`hc-verifier`), method cards as skills, commands `/hc-intent` `/hc-probe` `/hc-verify` `/hc-aar`, and a plugin that
enforces the intent gate, read-only roles, human-approved one-way doors, the sticky contract and a journal.
Install: [`opencode/INSTALL.md`](opencode/INSTALL.md). Base-vs-harness protocol with `/goal`: [`opencode/EVAL.md`](opencode/EVAL.md).

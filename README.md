# harness-core

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
2. Actions → enable workflows. Runs start on the cron (`:07` sb, `:37` tau2) or via *Run workflow*.

### Security

Model-generated spreadsheet code runs in a subprocess with a clean environment. The Kilo key is read by the pacer from
a temp file that is deleted right after start. Checkouts keep no credentials. The push token appears only in the
clone and commit steps, passed as a one-off header.

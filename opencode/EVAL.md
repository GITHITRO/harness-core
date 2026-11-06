# Base vs harness-core on a real task with `/goal`

Goal: measure whether harness-core gives a gain over the same model in plain OpenCode, at what cost.

## Fix everything except the arm
| Same for both | How |
|---|---|
| Code snapshot | two git worktrees from one commit: `git worktree add ../run-base <sha>` and `../run-harness <sha>` |
| OpenCode version, model, provider, temperature | same `opencode.json` model; note `opencode --version` |
| Objective text | the identical `/goal …` text, nothing extra for the harness |
| Round / time / token cap | same `/goal` limits; stop both at the same wall-clock or token budget |
| Your behaviour | answer questions the same way (ideally: no answers, or one pre-written answer sheet for both) |

| Differs | base | harness |
|---|---|---|
| Install | nothing | `install.sh ../run-harness` |
| Agent | `build` | `core` |

## Measure
1. **Task metric(s)** you already know (tests, benchmark, KPI) — computed by the same script after both runs.
2. **Cost**: tokens and cost (`opencode stats`, or `opencode export <sessionID>` and sum usage), wall time, `/goal` rounds.
3. **Attention**: number of questions to you and your interventions.
4. **Defects found later**: what broke after "done" (the false-confidence component of ideality).
5. Harness only: `.harness/journal.jsonl` (gate blocks, subagent calls), `evidence.md` (how many criteria
   PASS with evidence vs UNVERIFIED), `aar.md`.

Export both sessions: `opencode export <sessionID> > base.json` / `harness.json` — keep them for the analysis.

## Verdict: metric + logic of the traces
Run `eval/compare.py` on the two exports. It computes cost per arm from the exports and asks a jury of LLMs from
other model families than the worker (default: `eval/judges.example.json` — Gemini 3.5 Flash and dots-3-note via
Kilo) to score both traces blind on 8 criteria: goal, uncertainty, options, grounding, verification, recovery,
efficiency, honesty. Each judge sees the pair twice in swapped order; only a preference that survives the swap counts.

```
GEMINI_API_KEY=... KILO_API_KEY=... python3 eval/compare.py --base base.json --harness harness.json \
  --task task.md --metric-base 0.62 --metric-harness 0.71 --higher-better --judges eval/judges.example.json --out report
```

| metric | logic (jury) | verdict |
|---|---|---|
| up | harness preferred by the majority in both orders, mean rubric ≥ base | **PASS** |
| up | not convincing | luck: outcome without a sound process |
| equal | — | no metric gain; the cost decides |
| not up | harness preferred | process better, outcome not |
| not up | not preferred | FAIL |

Read `report.md` too: the judges' failure lists are the most useful part for improving the harness.
Smoke check of this tool (trivial slugify task, both arms 100% tests): first harness version lost on efficiency
(ceremony, and a gate-format bug sent the agent reading the plugin); after the fix it tied on outcome with
+28% input tokens and slightly better rubric — the expected "not worse" on a task that does not need the harness.

## Variance
One run per arm is anecdote: our calibration showed run-to-run noise of ±2–3 tasks out of 20 at temperature 0.6.
Do at least 3 runs per arm if the task allows, alternate the order (base, harness, harness, base, …), and compare
medians. If only one run is possible, treat the result as a probe, not a verdict.

## Ideality
ideality = ΔQ / (tokens + time + your attention + harm from false confidence). A harness win on quality that costs
3× tokens can still lose; record all four.

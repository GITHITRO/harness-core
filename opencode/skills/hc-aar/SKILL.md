---
name: hc-aar
description: harness-core after-action review — planned vs happened, predictions vs facts, what to keep and change. Use when a task or a major step ends.
---

# After-action review (`.harness/aar.md`)

1. **Planned**: intent and the end state (from `.harness/intent.md`).
2. **Happened**: what was delivered; criteria status from `.harness/evidence.md`.
3. **Predictions vs facts**: each test card's prediction and probability against the outcome; Brier score
   `(p - outcome)^2` per prediction and the mean.
4. **Why the gap (δ)**: one declared cause per gap — facts / model of the world / criteria / execution / noise.
5. **Keep**: what worked and should be repeated.
6. **Improve**: one or two concrete changes to the process or the harness (not to the deliverable).
7. **Facts worth remembering** about the user's world (team, tools, constraints): propose them to the user; store
   only what they confirm.
8. **Cost**: rough tokens/time, number of questions asked, rollbacks.

Short: half a page. The AAR feeds the system loop; the harness changes only on a pattern across tasks.

---
name: hc-elicitation
description: harness-core active probing — find what is unknown before deciding; ask the user only questions that change a decision. Use in the Observe stage of uncertain tasks.
---

# Active probing (Observe)

Depth follows the profile: clear task → 0–3 questions; complex or high-stakes → do not decide until the world is assembled.

## Procedure
1. **Drafts as probes.** 2–3 rough solutions, minimal effort. Their job is to expose what you do not know.
   Discard them before Orient (no anchoring).
2. **Premortem** each draft ("it failed — why?"); use `@hc-redteam` when stakes are medium or high.
3. **Break points → unknowns.** Sort unknowns into seven categories:
   | Category | Typical question |
   |---|---|
   | Goal & criteria | What exactly counts as success, measured how? |
   | Hard limits & irreversibility | What must never happen; what cannot be undone? |
   | History of interventions | What was tried before and what happened? |
   | Opposing forces | Who or what pushes back (people with incentives, feedback loops)? |
   | Non-linearities & thresholds | Where does a small change cause a big effect? |
   | Executor resources | Time, people, skills, budget, access really available? |
   | Observability | How will we know it works, and how soon? |
4. **Route sources**: repo/data/tools → web → `@hc-scout` (parallel, read-only) → user. Mark contradictions, do not average.
5. **Decision-relevance test** for every candidate question: write "if the answer is A → we do X; if B → we do Y".
   If X = Y, do not ask. The answer must not be findable in available data.
6. **Ask well**, one batch, ranked by value, each with a default assumption:
   - about a concrete past, not opinions on the future (critical-decision method; Mom Test: "When did this last
     happen? What did you do?" rather than "Would you use…?");
   - for quantities ask ranges (SHELF): lowest plausible, highest plausible, most likely.
7. Write answers to `.harness/world.md` tagged "per user". Repeat while some question can still change the choice.
8. **Backbrief**: restate intent and plan in one paragraph for confirmation; reframe the task if needed.

Under `/goal` or unattended: put questions with defaults into `.harness/questions.md`, proceed on defaults, list them
as assumptions in the final report.

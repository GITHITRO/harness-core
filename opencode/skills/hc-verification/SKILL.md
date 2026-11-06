---
name: hc-verification
description: harness-core verification stack — executable checks first, LLM judgement only for the rest, edge-case tests of the criteria, evidence ledger. Use before claiming any criterion is met.
---

# Verification stack

**Programs check what is executable**: tests, builds, type checks, linters, fitness functions, benchmarks, scripts
that recompute numbers. Only what cannot be executed goes to judgement (`@hc-verifier`), with explicit criteria.

## Build the check
- **Criteria source**: the acceptance criteria in `.harness/intent.md`; for weak-verifiability work add a short
  rubric with concrete items (not "is it good?").
- **Test the check itself** before trusting it: one case that must fail, one that must pass, one edge case. A check
  that cannot fail proves nothing.
- **Metamorphic checks** when there is no oracle: change the input in a way with a known effect (scale, reorder,
  remove an irrelevant part) and check the output changes as predicted.
- **Practicality rubric for plans**: every step has an owner, date, cost, success metric and stop criterion;
  numbers have a source or are marked as assumptions with a range; the 2–3 deciding assumptions are on top with their
  cheapest tests.

## Evidence ledger (`.harness/evidence.md`)
`| criterion | verdict (PASS/FAIL/UNVERIFIED) | evidence (command → output, file, link) | date |`
Never write PASS without evidence. Unverified stays UNVERIFIED in the final report.

## On FAIL — roll back to the culprit
wrong facts → Observe · wrong model/option → Orient · wrong or unmeasurable criterion → Intent · bad execution → Act.
Fix there, then re-run the checks that depend on it. Raise effort only after a failed check.

## Against false confidence
"5 checks passed" is not "done": list what is verified, what is not, and which assumptions remain open.

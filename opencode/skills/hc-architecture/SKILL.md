---
name: hc-architecture
description: harness-core architecture under uncertainty — quality-attribute scenarios, options with trade-offs, ADRs, spikes as probes and executable fitness functions. Use when designing or changing a system's architecture.
---

# Architecture under uncertainty

1. **Drivers as scenarios.** Turn vague qualities into testable quality-attribute scenarios:
   source · stimulus · environment · artifact · response · **response measure** (e.g. "1k req/s burst on checkout,
   p95 < 300 ms, no data loss"). Rank them by business value × technical risk. Unmeasurable drivers are unknowns
   for `hc-elicitation`, not requirements.
2. **Constraints first.** Hard limits (compliance, budget, team skills, existing contracts, deadlines) prune options
   before any design discussion.
3. **Options.** 2–3 candidate architectures that differ in a structural decision (not in naming). For each: how it
   meets the top scenarios, sensitivity points (one parameter drives a quality), trade-off points (one decision helps
   one quality and hurts another), risks.
4. **Probe, do not argue.** Where options hinge on an unknown (throughput of a library, migration effort, latency
   of a dependency), run a spike: smallest experiment with a prediction written before it.
5. **Decide reversibly.** Prefer decisions that keep options open (interfaces, adapters, feature flags, strangler
   pattern). Identify one-way doors explicitly; those go to the user.
6. **ADR** per decision in `.harness/decisions.md` (or the repo's ADR folder): context · decision · alternatives ·
   consequences · status.
7. **Fitness functions.** Encode the key scenarios as executable checks (tests, dependency rules, load scripts,
   size/latency budgets) and add them to the acceptance criteria. Architecture claims without a fitness function are
   UNVERIFIED in `.harness/evidence.md`.
8. **Walking skeleton first**: end-to-end thinnest path through all components, then deepen by risk.

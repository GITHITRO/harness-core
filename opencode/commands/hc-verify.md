---
description: harness-core — verify against the acceptance criteria and update .harness/evidence.md
agent: core
---

Load skill `hc-verification`. Run every executable check for the acceptance criteria in `.harness/intent.md`, ask
`@hc-verifier` for an independent pass, update `.harness/evidence.md`, and on any FAIL name the culprit stage and fix
it there. Report what is verified, what is not, and the open assumptions. $ARGUMENTS

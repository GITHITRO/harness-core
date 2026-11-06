---
name: hc-decision
description: harness-core decision methods — pick the method by the state of knowledge (expected value, robust decisions, game theory, info-gap), compare options, record deciding assumptions. Use in Orient/Decide.
---

# Orient & Decide

## Generate options
At least two genuinely different options, produced by different routes: analogy from a solved problem, constraint
removal (TRIZ: what if the conflicting requirements are separated in time, space or condition instead of
compromised?), theory of constraints (find the bottleneck first), the simplest walking skeleton.

## Competing hypotheses (when explaining a situation)
List hypotheses × evidence; mark each piece of evidence consistent / inconsistent. Prefer the hypothesis with the
fewest inconsistencies, not the most confirmations.

## Choose the method by the state of knowledge
| Situation | Method |
|---|---|
| Probabilities and payoffs roughly known | Expected value / decision tree |
| Deep uncertainty, many plausible futures | Robust decision making, minimax regret: pick the option that is acceptable in most futures |
| A thinking adversary or strong incentives | Game theory: best response, equilibria, commitment |
| The model of the world itself is doubtful | Info-gap: how wrong can the model be before the option fails? |

High stakes → apply two methods. If they disagree, show the disagreement map to the user; do not average.

## Sensitivity
For the chosen option vary the 3–5 most uncertain inputs across their ranges; the inputs that flip the choice are the
**deciding assumptions**. Write each with its cheapest test.

## Record (`.harness/decisions.md`)
Decision · options · method · why · reversibility (two-way / one-way door) · deciding assumptions + cheapest tests ·
test card for the first step (hypothesis, prediction with probability, step size, stop criteria).

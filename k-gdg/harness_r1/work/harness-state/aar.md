# AAR — GDG Recruitment Competition 2026

## Planned
Explore battle log, build LightGBM regression for pikachu_hp, validate on held-out rounds (group split to avoid within-battle leakage), tune 40 optuna trials, train on all 80016 rows, predict 240 test rows, write /work/submission.csv matching sample_submission.csv format.

## Happened
- Data: 3334 rounds (battles) × 24 turns; test = rounds 1828–1837, different battles despite overlapping round ids (no feature/battle_turn overlap with train). All test categorical values seen in train.
- Strong leakage-free baseline: clip(previous_hp − damage + healing, 0, max_hp) → val R2 ≈ 0.40.
- LightGBM (categorical features as category dtype, NaN handled natively) with grouped validation (rounds ≤ 2668 train / > 2668 val): best val R2 = 0.96996 after 40 optuna trials.
- Final model trained on all 80016 rows with best params/best iteration; test predictions clipped to [0, max_hp] and rounded to integers.
- /work/submission.csv: 240 rows, columns [battle_turn, pikachu_hp], ids identical to sample in order, no NaNs, values in [1, 78].

## Why
Round-wise split prevents serial HP leakage across turns of the same battle. HP is near-deterministic from previous_hp/damage/healing, so the model mostly learns residuals (overkill, crits, misses, status effects); hence val R2 ≈ 0.97.

## Keep
- Grouped (by round) validation; mechanic-based baseline as sanity floor.
- LightGBM native categorical + NaN handling.

## Improve / assumptions
- Assumption: test distribution matches train (verified for categories; target unknown).
- No calibration beyond clip/round; rounding to integers since HP is integral in train.
- If hidden test R2 << 0.97, likely cause: distribution shift in damage/stage mechanics (can't be checked without test labels).
- Harness state files kept under /work/harness-state/ (writable), since /work/.harness is owned by uid 1001 and not writable by agent (uid 1000).
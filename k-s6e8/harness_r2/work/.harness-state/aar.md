## After-action review

Planned vs happened:
- Planned: baseline → optuna tuning + FE → full 5-fold verify → submission. Happened exactly, all within budget (~45 min of 60).
- Baseline plain LightGBM: 0.96356 (better than the subsample-tuned score 0.9607 — validated on full data before deciding).
- Tuned+FE full CV: 0.96458 ± 0.00045, selected; submission written and all format checks PASS.

Keep:
- LightGBM native NaN/categorical handling; stratified CV with fixed splits; time-boxed tuning on subsample.

Improve:
- Per-fold baseline+FE scores not logged (only mean) — paired t-test of improvement not possible; improvement (~0.0008) is small, within ~2× fold std, so treat as marginal.
- Optuna on subsample underestimated full-data score; next time tune on a larger subsample or fewer trials with full folds.

Predictions vs facts:
- Expected final CV ≈ 0.960–0.965; actual 0.96458. Facts match.
- Submission mean prediction 0.7095 ≈ train base rate 0.7094 — sensible calibration.

Remaining assumptions: none affecting deliverable; public leaderboard score unknown (no internet).
# After-action review — Predicting Smartphone Addiction

Planned: explore data, LightGBM pipeline with engineered features, stratified 5-fold ROC AUC CV, bounded optuna tuning, full-train fit, write /work/submission.csv, verify format vs sample.

Happened:
- Data: train 691,369 rows, test 296,302 rows, ids contiguous/non-overlapping; target rate 0.709424 (matches constant sample baseline); heavy missingness (up to ~19%).
- Baseline LightGBM 5-fold CV AUC = 0.963394.
- Optuna TPE tuning (12 trials, 3-fold inner): best 0.963802; tuned 5-fold CV AUC = 0.964080.
- Full-train fit (n_estimators=1500, no early stopping), predictions written to /work/submission.csv: 296,302 rows, ids identical to sample, pred range [0.00011, 0.999999], mean 0.709368.
- All acceptance criteria PASS (see evidence.md).

Keep: LightGBM native missing/categorical handling; stratified CV for AUC; time-boxed tuning (12 trials) was enough — gains over baseline were marginal (+0.0007).

Improve: optuna API (`suggest_*` not `trial.int/float`) cost two failed runs (~8 min); full-train fit without early stopping may slightly overfit — could use CV-average best iteration next time.

Predictions vs facts: predicted submission mean 0.70937 ≈ train label rate 0.70942 — well calibrated, no suspicious distribution shift.
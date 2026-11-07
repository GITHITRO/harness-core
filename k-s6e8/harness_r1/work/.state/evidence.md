# Evidence ledger

| Criterion | Status | Evidence |
|-----------|--------|----------|
| C1 submission.csv shape (296302, 2), columns [id, addicted_label] | PASS | python check: shape == (296302,2); columns exact match |
| C1 ids identical to sample_submission (order + values) | PASS | `(sub.id == sample.id).all() == True`; test ids == submission ids |
| C2 predictions finite, no NaN, within [0,1] | PASS | min 0.000110, max 0.999999, mean 0.709368 (≈ train target rate 0.709424) |
| C3 local 5-fold stratified ROC AUC on train above constant baseline | PASS | baseline LightGBM 5-fold AUC = 0.963394; tuned 5-fold AUC = 0.964080 (optuna, 12 trials, 3-fold inner). Constant baseline (train mean) = 0.709424. |

Files: /work/submission.csv (final artifact). /work/model.py (CV + tuning), /work/finalize.py (full-train fit + write).
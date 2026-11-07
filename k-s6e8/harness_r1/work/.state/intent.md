# Intent — Predicting Smartphone Addiction (Playground S6E8)

## Purpose
Produce `/work/submission.csv` matching `/data/sample_submission.csv` (same ids 691369–987670, columns id/addicted_label) with predictions maximizing ROC AUC vs hidden test labels. Proxy: stratified CV ROC AUC on train.

## Key tasks
1. Inspect train/test: shapes, dtypes, missingness, target rate, id continuity.
2. Preprocessing + model pipeline: numeric imputation, categorical encoding, tree model (LightGBM preferred).
3. Feature engineering: screen-time ratios/interactions, missingness indicators.
4. Validate with stratified K-fold ROC AUC; bounded optuna tuning.
5. Train on full train, predict test, write submission; verify format vs sample programmatically.

## End state / Acceptance criteria
- C1: `/work/submission.csv` exists, shape (296302, 2), columns exactly [id, addicted_label], ids identical to sample_submission (order + values).
- C2: predictions finite, no NaN.
- C3: local 5-fold stratified ROC AUC on train meaningfully above constant baseline (train mean ≈ 0.709); target >= ~0.80 if separable.

## Must / Must not
- Must: work in /work; installed packages only; CPU only; no internet; don't modify /data.
- Must not: include train rows; leak test (no labels exist).

## Risk tolerance
Low stakes — submission file only; experiments reversible; time-boxed to 60 min.

## Backbrief
Tabular binary classification with missing values; LightGBM with native missing handling + simple engineered features, stratified CV for AUC, full-train model for submission. Assumption: screen-time totals carry most signal (to be confirmed by inspection).
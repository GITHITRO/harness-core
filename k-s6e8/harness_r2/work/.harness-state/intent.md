# Intent — Predicting Smartphone Addiction (Playground S6E8)
Note: /work/.harness is owned by uid 1001 and not writable by agent (uid 1000); harness state kept in /work/.harness-state instead.

**Purpose:** Produce /work/submission.csv matching /data/sample_submission.csv format (ids + predicted addicted_label probabilities), maximizing local CV ROC AUC under 60 min wall clock.

**Key tasks:**
1. EDA: missingness, target distribution, feature types.
2. Baseline: LightGBM, median/mode imputation + label encoding, 5-fold stratified CV (ROC AUC).
3. Iterate (time-boxed): optuna tuning + simple feature engineering.
4. Final: train on full train, predict test probabilities, write submission.csv.
5. Verify: ids/order match sample_submission; columns exactly id,addicted_label; values in [0,1].

**Acceptance criteria:**
- C1: /work/submission.csv exists; ids equal sample_submission ids (same order); columns id,addicted_label; 296302 rows.
- C2: all addicted_label in [0,1].
- C3: local stratified 5-fold LightGBM CV ROC AUC reported.

**Must/Must not:** /data read-only; no test-label leakage; no internet; ≤60 min.

**Risk tolerance:** low — plain baseline submission acceptable if tuning stalls.

**Backbrief:** LightGBM classifier on imputed/encoded tabular features, stratified 5-fold ROC AUC, brief optuna tuning, probabilities for test ids in sample order. Assumption: submission wants probabilities (sample head shows 0.709... soft labels) — observed from data, not user-confirmed.
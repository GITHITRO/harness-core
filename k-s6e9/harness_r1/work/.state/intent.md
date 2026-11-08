# Intent — Predicting Electric Vehicle Purchases (Playground S6E9)

**Purpose:** Produce `/work/submission.csv` matching `/data/sample_submission.csv` format (id, Will_Buy_EV), maximizing ROC AUC on holdout test, within 60 min wall-clock budget.

**Key tasks:**
1. Explore train/test distributions, categorical cardinality, target rate.
2. Build stratified K-fold CV pipeline (ROC AUC) with encoding + feature engineering + gradient boosting (LightGBM primary; XGBoost/CatBoost candidates).
3. Tune with limited optuna trials; select model; retrain on full train; predict test.
4. Verify submission format (ids identical & ordered same as sample, single numeric column) and record evidence.
5. AAR.

**Acceptance criteria (observable checks):**
- AC1: `/work/submission.csv` exists with header `id,Will_Buy_EV` — verified by reading header.
- AC2: ids match sample submission exactly (same values, same order) — verified by pandas compare.
- AC3: all `Will_Buy_EV` values are floats in [0,1] — verified by describe/min/max.
- AC4: CV ROC AUC recorded for the final model — verified by CV output log.
- AC5: submission row count = 286571 — verified by wc -l.

**Must / Must not:**
- Must not modify `/data` (read-only). Only installed packages; no internet.
- No test leakage (no test labels exist anyway).

**Risk tolerance:** Low stakes; reversible work; budget experiments to fit 60 min.

**Backbrief:** Train an LGBM on encoded/engineered features with stratified CV ROC AUC as selection criterion, then produce a formatted submission. (Assumption: CV is the only quality signal since no test labels exist.)

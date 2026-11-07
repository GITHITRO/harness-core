# Decisions

Options considered:
1. Logistic regression on imputed/encoded features — fast, but tabular tree models dominate this data; rejected.
2. LightGBM with categorical features native + engineered screen-time ratios/missingness indicators — chosen.
3. XGBoost/CatBoost alternatives — not needed; LightGBM baseline CV AUC 0.9634 already strong; CatBoost slower on 691k rows.

Method: empirical (known-probability-style) — baseline CV then optuna TPE maximization of 3-fold ROC AUC (24→12 trials for time budget), then 5-fold CV confirmation, then full-train fit.

Why: speed (LightGBM, n_jobs=4), native missing-value handling, categorical support, strong baseline.

Deciding assumptions:
- A1: Missingness is informative → engineered `n_missing` + LightGBM native NaN handling (cheapest test: CV with/without n_missing — not run; baseline already 0.963).
- A2: Screen-time totals drive signal → engineered total_screen/ratios (supported by CV result).
- A3: No target leakage in features (all are pre-treatment usage metrics).

Reversibility: all steps reversible; submission file can be regenerated.
Cheapest test per assumption: stratified 5-fold ROC AUC (already executed).
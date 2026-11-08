# Evidence ledger
- AC1 PASS: /work/submission.csv header == ['id','Will_Buy_EV'] (read via pandas)
- AC2 PASS: submission ids identical to sample and same order (sub['id'].values == sam['id']).all() == True; id sets equal; no extra columns
- AC3 PASS: Will_Buy_EV float64, min=1.06e-05, max=0.9774, mean=0.17468, all in [0,1], no nulls
- AC4 PASS: CV ROC AUC logged — LGBM baseline 5-fold OOF 0.94169 (std 0.00073); optuna 20-trial best 3-fold 0.94191; final internal 5% holdout 0.94214
- AC5 PASS: submission rows = 286571 (matches sample)

# Decisions
- Option A: LightGBM with native categorical features + engineered features → CV 0.9417 baseline, 0.9419 tuned. CHOSEN.
- Option B: CatBoost same feature set → 3-fold OOF 0.9414. Rejected (weaker, slower).
- Option C: further optuning → +0.0002 over baseline, deemed noise; stopped tuning per time budget.
- Method: empirical comparison via stratified CV ROC AUC (no prior probabilities available).
- Final: LGBM retrained on full train (iteration count from 5% internal holdout, best_iter=1574), test predictions written to /work/submission.csv.
- Deciding assumptions: CV AUC generalizes to leaderboard; no test leakage possible (unlabeled test). Cheapest test: holdout AUC 0.9421 consistent with CV.

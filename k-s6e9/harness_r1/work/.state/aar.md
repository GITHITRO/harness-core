# AAR — Predicting EV Purchases (Playground S6E9)

Planned: explore, LGBM baseline with stratified CV ROC AUC, optuna tuning, optional CatBoost blend, final train + formatted submission, verify AC1-AC5.
Happened: baseline LGBM OOF 0.9417 (1.3 min); optuna 20 trials best 3-fold 0.94191 (+0.0002, noise); CatBoost 3-fold 0.9414 (rejected); final LGBM on full train (best_iter=1574 from 5% holdout, holdout AUC 0.9421); /work/submission.csv written and all 5 acceptance criteria PASS.
Why: feature set (Subsidy_Available, Range_Anxiety_Level, Home_Charging_Possible, engineered crosses) carries the signal; model/hyperparameter choice had diminishing returns once a regularized GBDT was in place.
Keep: native categorical handling in LGBM, simple engineered crosses (sub_x_home, sub_x_anxiety, charging totals, income per car/km), stratified CV as the only quality signal.
Improve: with more time, try target encoding with cross-fitting and a GBDT+linear blend; more tuning trials didn't pay off here.
Predictions vs facts: expected a fast baseline to dominate; confirmed — 0.9417 baseline within 0.0002 of tuned best. Wall-clock used ~60 min; finalized in time.
Assumptions remaining: CV AUC generalization to unseen leaderboard (standard for this competition setup; unverifiable without test labels).

## Decision log

1. Model: LightGBM classifier (native handling of missing numerics and categorical NaN as its own category) — avoids imputation/encoding leakage risk; fast on 691k rows.
2. Validation: stratified 5-fold CV, ROC AUC, same splits for all configs (paired comparison possible).
3. Tuning: Optuna TPE, 25 trials on 200k-row stratified subsample, 3-fold, n_estimators=1500 + early stopping 50. Best value 0.9607 on subsample (subsample/3-fold noise — verified on full data before shipping).
4. Feature engineering: screen_sum, screen_n_avail, ratios of components to daily_screen_time, ratio_weekend_daily, notif_per_app, screen_per_awake_hour, age_sq, is_student_impact (inf→NaN).
5. Chosen config: tuned+FE (full 5-fold mean 0.96458) over baseline+FE (0.96377) and plain baseline (0.96356). Final model refit on all 691369 train rows, median best_iteration (~2800), predictions for test ids in sample_submission order.
6. Assumption (observed, not user-confirmed): submission expects probabilities — confirmed by sample_submission showing soft label 0.7094... (train mean).
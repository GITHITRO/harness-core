## Facts (source: /data files, observed by running eda.py)
- train: 691369 rows × 14 cols (id + 12 features + addicted_label); test: 296302 × 13; sample_submission: 296302 × 2 (id, addicted_label)
- Target addicted_label is binary {0,1}, mean = 0.7094243450313797 (~71% positive). 490474 ones, 200895 zeros.
- Missingness (train): social_media 19.4%, gaming 18.3%, weekend 16.2%, app_opens 11.7%, notifications 9.8%, work_study 7.5%, sleep 6.4%, age 4.2%, daily 4.2%; categorical: gender 4.2%, stress_level 8.0%, academic_work_impact 6.4%. Test similar, slightly lower.
- Numeric features: age, daily_screen_time_hours, social_media_hours, gaming_hours, work_study_hours, sleep_hours, notifications_per_day, app_opens_per_day, weekend_screen_time. Categorical: gender {Male,Female,Other}, stress_level {High,Low,Medium}, academic_work_impact {Yes,No}.
- train ids 0..691368, test ids 691369..987670; test id order == sample_submission id order exactly (verified elementwise).
- sample_submission addicted_label is constant = train mean (0.7094243450313797) → naive baseline to beat.
- Metric: ROC AUC (needs probabilities). Environment: pandas/numpy/sklearn/lightgbm/xgboost/catboost/scipy/optuna, CPU 4 cores, 16 GB RAM, no internet.

## Assumptions
- Submission expects predicted probabilities (soft labels), confirmed by sample_submission values.
- LightGBM handles missing numerics natively; categorical NaN treated as its own category.
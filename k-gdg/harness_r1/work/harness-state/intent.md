# GDG Recruitment Competition 2026 — Predict Pikachu HP

## Purpose
Build a regression model predicting `pikachu_hp` for the 240 test battles and write `/work/submission.csv` matching `sample_submission.csv` format (columns: battle_turn, pikachu_hp). Evaluation metric: R2 Score.

## Key tasks
1. Explore train.csv / test.csv / sample_submission.csv (schema, distributions, leaks).
2. Feature-engineer battle-log features (damage vs previous_hp/max_hp, stage combos, type effectiveness, crit/hit flags, weather/terrain, opponent encodings).
3. Train LightGBM/XGBoost/CatBoost regression with a time-aware/turn-aware validation split; tune minimally with optuna.
4. Verify: internal CV R2, submission shape/columns/ids match sample, no NaNs.
5. Write /work/submission.csv.

## End state / Acceptance criteria
- `/work/submission.csv` exists with exactly 240 rows, columns [battle_turn, pikachu_hp], ids identical to sample_submission.csv (verified by pandas diff).
- No missing values; pikachu_hp finite.
- Local validation R2 recorded in /work/harness-state/evidence.md.

## Must / Must not
- Must not use test.csv target (none exists) — no leakage beyond provided features.
- Must not modify /data files (read-only).
- Must finish within 60 min wall clock.

## Risk tolerance
Low stakes; a simple strong baseline (previous_hp - damage_dealt + healing_applied clamped to [0, max_hp]) is acceptable if tuning fails.

## Backbrief
Assume previous_hp + healing - damage is a strong baseline; battle features (types, stages, crit) refine it. Train on all 80k rows, predict test, fallback to baseline if model R2 < baseline R2 on validation. Assumption: test battles follow same distribution as train (not confirmed by user).
## Evidence ledger

| Criterion | Status | Evidence |
|-----------|--------|----------|
| C1: submission.csv format matches sample_submission (ids + order, columns id/addicted_label, 296302 rows) | PASS | verify.py: C1_columns PASS, C1_rows PASS, C1_ids_values PASS (elementwise id equality), C1_ids_order PASS |
| C2: all addicted_label in [0,1], no NaN, float | PASS | verify.py: min=0.000115, max=0.999999918, no NaN, float dtype |
| C3: local stratified 5-fold LightGBM CV ROC AUC reported | PASS | final.py: tuned+FE mean=0.96458 std=0.00045 oof=0.96457; baseline=0.96356; baseline+FE=0.96377 |

Artifacts: /work/submission.csv (final), /work/.harness-state/{baseline_metrics.json, best_params.json, final_metrics.json, oof.npy, test_preds_baseline.npy, sub_baseline.csv}
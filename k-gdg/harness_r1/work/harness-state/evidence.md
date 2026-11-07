# Validation evidence
split: train rounds <= 2668, val rounds > 2668 (64032 train / 15984 val rows)
baseline R2 (val): 0.40368
lightgbm best val R2: 0.96996
best params: {"num_leaves": 34, "max_depth": 12, "min_child_samples": 86, "subsample": 0.7961658037821249, "colsample_bytree": 0.9997427525255567, "reg_alpha": 0.0006076743152312005, "reg_lambda": 0.0002895315134773347, "learning_rate": 0.020948022574316418, "feature_fraction": 0.9567487967019934, "bagging_freq": 1, "min_gain_to_split": 0.00010980135638315465, "bagging_fraction": 0.9400847986381133}
submission rows: 240; pred min 1.000 max 78.000

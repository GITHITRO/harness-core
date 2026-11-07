import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import roc_auc_score
import optuna, time, json

train = pd.read_csv("/data/train.csv")
FEATS_BASE = [c for c in train.columns if c not in ("id", "addicted_label")]
CATS = ["gender", "stress_level", "academic_work_impact"]

def add_fe(df):
    d = df.copy()
    # available screen components
    comps = ["social_media_hours", "gaming_hours", "work_study_hours"]
    d["screen_sum"] = d[comps].sum(axis=1, skipna=True)
    d["screen_n_avail"] = d[comps].notna().sum(axis=1)
    for c in comps:
        d[f"ratio_{c}"] = d[c] / d["daily_screen_time_hours"].replace(0, np.nan)
    d["ratio_weekend_daily"] = d["weekend_screen_time"] / d["daily_screen_time_hours"].replace(0, np.nan)
    d["notif_per_app"] = d["notifications_per_day"] / d["app_opens_per_day"].replace(0, np.nan)
    d["screen_per_awake_hour"] = d["daily_screen_time_hours"] / (24 - d["sleep_hours"]).replace(0, np.nan)
    d["age_sq"] = d["age"] ** 2
    d["is_student_impact"] = (d["academic_work_impact"] == "Yes").astype(float)
    d = d.replace([np.inf, -np.inf], np.nan)
    return d

train = add_fe(train)
test = pd.read_csv("/data/test.csv")
test = add_fe(test)

FEATS = [c for c in train.columns if c not in ("id", "addicted_label")]
NUM = [c for c in FEATS if c not in CATS]
print("n features:", len(FEATS), "| new feats:", [c for c in FEATS if c not in FEATS_BASE])

X = train[FEATS].copy()
y = train["addicted_label"].values
Xt = test[FEATS].copy()
for c in CATS:
    X[c] = X[c].astype("category")
    Xt[c] = Xt[c].astype("category")

# subsample for speed (stratified)
Xs, _, ys, _ = train_test_split(X, y, train_size=200000, stratify=y, random_state=42)
print("tuning on", len(Xs), "rows, pos rate", ys.mean())

skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

def objective(trial):
    params = dict(
        objective="binary", metric="auc",
        learning_rate=trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        num_leaves=trial.suggest_int("num_leaves", 15, 150),
        max_depth=trial.suggest_categorical("max_depth", [-1, 6, 8, 10, 12]),
        min_child_samples=trial.suggest_int("min_child_samples", 5, 100),
        subsample=trial.suggest_float("subsample", 0.6, 1.0),
        colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1.0),
        reg_alpha=trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
        reg_lambda=trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        min_split_gain=trial.suggest_float("min_split_gain", 0.0, 0.1),
        scale_pos_weight=(ys == 0).sum() / (ys == 1).sum(),
        random_state=42, n_jobs=2, verbose=-1,
    )
    scores = []
    for tr_idx, va_idx in skf.split(Xs, ys):
        m = lgb.LGBMClassifier(**params, n_estimators=1500)
        m.fit(Xs.iloc[tr_idx], ys[tr_idx],
              eval_set=[(Xs.iloc[va_idx], ys[va_idx])], eval_metric="auc",
              callbacks=[lgb.early_stopping(50, verbose=False)])
        scores.append(roc_auc_score(ys[va_idx], m.predict_proba(Xs.iloc[va_idx])[:, 1]))
    return float(np.mean(scores))

t0 = time.time()
study = optuna.create_study(direction="maximize",
                            sampler=optuna.samplers.TPESampler(seed=42))
study.optimize(objective, n_trials=25, show_progress_bar=True)
print("best:", study.best_value, study.best_params)
print("time:", time.time() - t0)
json.dump({"best_value": study.best_value, "best_params": study.best_params},
          open("/work/.harness-state/best_params.json", "w"), indent=2)

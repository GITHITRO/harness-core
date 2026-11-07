import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import time, json

def add_fe(df):
    d = df.copy()
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
    return d.replace([np.inf, -np.inf], np.nan)

train = pd.read_csv("/data/train.csv")
test = pd.read_csv("/data/test.csv")
sub = pd.read_csv("/data/sample_submission.csv")

train = add_fe(train); test = add_fe(test)
FEATS = [c for c in train.columns if c not in ("id", "addicted_label")]
CATS = ["gender", "stress_level", "academic_work_impact"]
X = train[FEATS].copy(); y = train["addicted_label"].values
Xt = test[FEATS].copy()
for c in CATS:
    X[c] = X[c].astype("category"); Xt[c] = Xt[c].astype("category")

best = json.load(open("/work/.harness-state/best_params.json"))["best_params"]
params = dict(objective="binary", metric="auc", random_state=42, n_jobs=4, verbose=-1, **params if False else best)
params["n_estimators"] = 4000

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
oof = np.zeros(len(train)); fold_scores = []; best_iters = []
t0 = time.time()
for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
    m = lgb.LGBMClassifier(**params)
    m.fit(X.iloc[tr_idx], y[tr_idx], eval_set=[(X.iloc[va_idx], y[va_idx])], eval_metric="auc",
          callbacks=[lgb.early_stopping(100, verbose=False)])
    p = m.predict_proba(X.iloc[va_idx])[:, 1]
    auc = roc_auc_score(y[va_idx], p)
    fold_scores.append(auc); best_iters.append(m.best_iteration_); oof[va_idx] = p
    print(f"fold {fold}: auc={auc:.5f} best_iter={m.best_iteration_}")
oof_auc = roc_auc_score(y, oof)
print(f"TUNED+FE mean={np.mean(fold_scores):.5f} std={np.std(fold_scores):.5f} oof={oof_auc:.5f} time={time.time()-t0:.0f}s")

# Baseline params + engineered features for comparison (quick, 5-fold)
params0 = dict(objective="binary", metric="auc", learning_rate=0.05, num_leaves=31, min_child_samples=20,
               subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
               scale_pos_weight=(y == 0).sum() / (y == 1).sum(), random_state=42, n_jobs=4, verbose=-1,
               n_estimators=4000)
oof0 = np.zeros(len(train)); f0 = []
for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
    m = lgb.LGBMClassifier(**params0)
    m.fit(X.iloc[tr_idx], y[tr_idx], eval_set=[(X.iloc[va_idx], y[va_idx])], eval_metric="auc",
          callbacks=[lgb.early_stopping(100, verbose=False)])
    f0.append(roc_auc_score(y[va_idx], m.predict_proba(X.iloc[va_idx])[:, 1]))
oof0_auc = roc_auc_score(y, oof0)
print(f"BASELINE+FE mean={np.mean(f0):.5f} std={np.std(f0):.5f} oof={oof0_auc:.5f}")

# choose better config, fit full, predict test
use_tuned = np.mean(fold_scores) >= np.mean(f0)
chosen = params if use_tuned else params0
chosen["n_estimators"] = int(np.median(best_iters if use_tuned else [4000]))
m_full = lgb.LGBMClassifier(**chosen); m_full.fit(X, y)
pt = m_full.predict_proba(Xt)[:, 1]
out = pd.DataFrame({"id": sub["id"], "addicted_label": pt})
out.to_csv("/work/submission.csv", index=False)
print("chosen:", "tuned+fe" if use_tuned else "baseline+fe")
print("sub rows:", len(out), "id match:", (out["id"].values == sub["id"].values).all(),
      "range:", pt.min(), pt.max(), "mean:", pt.mean())
json.dump({"tuned_mean": float(np.mean(fold_scores)), "tuned_std": float(np.std(fold_scores)),
           "tuned_oof": float(oof_auc), "base_mean": float(np.mean(f0)), "base_oof": float(oof0_auc),
           "chosen_tuned": bool(use_tuned)}, open("/work/.harness-state/final_metrics.json", "w"))

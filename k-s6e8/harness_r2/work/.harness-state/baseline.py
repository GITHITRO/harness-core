import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
import time, json

train = pd.read_csv("/data/train.csv")
test = pd.read_csv("/data/test.csv")

FEATS = [c for c in train.columns if c not in ("id", "addicted_label")]
CATS = ["gender", "stress_level", "academic_work_impact"]
NUM = [c for c in FEATS if c not in CATS]

X = train[FEATS].copy()
y = train["addicted_label"].values
Xt = test[FEATS].copy()

for c in CATS:
    X[c] = X[c].astype("category")
    Xt[c] = Xt[c].astype("category")

print("features:", FEATS)
print("categorical:", CATS)

params = dict(
    objective="binary",
    metric="auc",
    learning_rate=0.05,
    num_leaves=31,
    max_depth=-1,
    min_child_samples=20,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_alpha=0.1,
    reg_lambda=0.1,
    scale_pos_weight=(y == 0).sum() / (y == 1).sum(),
    random_state=42,
    n_jobs=4,
    verbose=-1,
)

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
oof = np.zeros(len(train))
fold_scores = []
best_iters = []
t0 = time.time()
for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
    Xtr, Xva = X.iloc[tr_idx], X.iloc[va_idx]
    ytr, yva = y[tr_idx], y[va_idx]
    m = lgb.LGBMClassifier(**params, n_estimators=3000)
    m.fit(
        Xtr, ytr,
        eval_set=[(Xva, yva)],
        eval_metric="auc",
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    p = m.predict_proba(Xva)[:, 1]
    auc = roc_auc_score(yva, p)
    fold_scores.append(auc)
    oof[va_idx] = p
    print(f"fold {fold}: auc={auc:.5f} best_iter={m.best_iteration_}")
    best_iters.append(m.best_iteration_)
oof_auc = roc_auc_score(y, oof)
print(f"mean fold auc={np.mean(fold_scores):.5f} std={np.std(fold_scores):.5f} oof auc={oof_auc:.5f} time={time.time()-t0:.0f}s")

# full-data fit for test predictions
n_est = int(np.median(best_iters))
m_full = lgb.LGBMClassifier(**params, n_estimators=n_est)
m_full.fit(X, y)
pt = m_full.predict_proba(Xt)[:, 1]
np.save("/work/.harness-state/oof.npy", oof)
np.save("/work/.harness-state/test_preds_baseline.npy", pt)
pd.DataFrame({"id": test["id"], "addicted_label": pt}).to_csv("/work/.harness-state/sub_baseline.csv", index=False)
print("baseline test pred range:", pt.min(), pt.max(), "mean:", pt.mean())
with open("/work/.harness-state/baseline_metrics.json", "w") as f:
    json.dump({"fold_scores": fold_scores, "mean": float(np.mean(fold_scores)), "std": float(np.std(fold_scores)), "oof": float(oof_auc)}, f)

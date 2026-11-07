import pandas as pd
import numpy as np

sub = pd.read_csv("/data/sample_submission.csv")
out = pd.read_csv("/work/submission.csv")

checks = {}
checks["C1_columns"] = list(out.columns) == ["id", "addicted_label"]
checks["C1_rows"] = len(out) == 296302
checks["C1_ids_values"] = (out["id"].values == sub["id"].values).all()
checks["C1_ids_order"] = (out["id"].reset_index(drop=True) == sub["id"].reset_index(drop=True)).all()
checks["C2_range_0_1"] = out["addicted_label"].between(0, 1).all()
checks["C2_no_nan"] = out["addicted_label"].notna().all()
checks["C2_dtype_float"] = np.issubdtype(out["addicted_label"].dtype, np.floating)
for k, v in checks.items():
    print(f"{k}: {'PASS' if v else 'FAIL'}")
print("sub head:\n", out.head())
print("pred stats:", out["addicted_label"].describe()[["min", "max", "mean"]].to_dict())
all_pass = all(checks.values())
print("ALL PASS" if all_pass else "SOME FAILED")
raise SystemExit(0 if all_pass else 1)

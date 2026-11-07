"""Host side, with Kaggle credentials: download a competition and write the task statement both arms receive.

python3 prepare.py <slug> <data_dir> <minutes> -> data_dir/{files..., TASK.md, meta.json}
The statement is generated from the Kaggle API (title, description, metric, dates) and the files themselves, so the
two arms get byte-identical instructions and no human paraphrase.
"""
import csv
import json
import os
import subprocess
import sys
import zipfile

from kaggle.api.kaggle_api_extended import KaggleApi


def main():
    slug, out, minutes = sys.argv[1], sys.argv[2], int(sys.argv[3])
    os.makedirs(out, exist_ok=True)
    api = KaggleApi()
    api.authenticate()
    resp = api.competitions_list(search=slug)
    items = getattr(resp, "competitions", None) or resp            # new API wraps the list in a response object

    def as_dict(c):
        d = c.to_dict() if hasattr(c, "to_dict") else {k: v for k, v in vars(c).items()}
        return {k.lstrip("_"): v for k, v in d.items()}

    comps = [as_dict(c) for c in items]
    comp = next(d for d in comps if str(d.get("ref") or d.get("url") or "").rstrip("/").endswith(slug))
    print("competition fields:", sorted(comp)[:30])

    def g(*names):
        for n in names:
            for k in (n, n[0].lower() + n[1:], "".join("_" + ch.lower() if ch.isupper() else ch for ch in n).lstrip("_")):
                if comp.get(k) not in (None, ""):
                    return comp[k]
        return None

    meta = {"slug": slug, "title": g("title"), "description": g("description"),
            "metric": g("evaluationMetric", "evaluation_metric"),
            "enabled": str(g("enabledDate", "enabled_date") or "")[:10], "deadline": str(g("deadline") or "")[:10]}
    subprocess.run(["kaggle", "competitions", "download", "-c", slug, "-p", out, "-q"], check=True)
    for z in [f for f in os.listdir(out) if f.endswith(".zip")]:
        zipfile.ZipFile(os.path.join(out, z)).extractall(out)
        os.remove(os.path.join(out, z))
    files = sorted(f for f in os.listdir(out) if not f.startswith("."))
    lines = []
    for f in files:
        p = os.path.join(out, f)
        if f.endswith(".csv"):
            with open(p, newline="", encoding="utf-8", errors="replace") as fh:
                r = csv.reader(fh)
                head = next(r, [])
                n = sum(1 for _ in r)
            lines.append(f"- `{f}`: {n} rows; columns: {', '.join(head[:40])}{' …' if len(head) > 40 else ''}")
        else:
            lines.append(f"- `{f}`: {os.path.getsize(p)} bytes")
    task = f"""# {meta['title']}

{meta['description'] or ''}

**Evaluation metric:** {meta['metric']}
**Data** (read-only, in `/data`):
{chr(10).join(lines)}

**Deliverable:** write `/work/submission.csv` in exactly the format of `/data/sample_submission.csv` (same ids, same
columns). Only the file present at the end counts.

**Rules of this run**
- Time limit: {minutes} minutes of wall clock; the run is stopped at the limit. Budget your experiments.
- There is no internet access. Python packages already installed are all you have (pandas, numpy, scikit-learn,
  lightgbm, xgboost, catboost, scipy, optuna). Library documentation: `python -c "help(...)"`.
- One research tool is available: the `arxiv` MCP tool (search and read papers submitted before {meta['enabled']}).
- Work in `/work`. CPU only (4 cores, 16 GB RAM).
"""
    open(os.path.join(out, "TASK.md"), "w").write(task)
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=1)
    print(task)


if __name__ == "__main__":
    main()

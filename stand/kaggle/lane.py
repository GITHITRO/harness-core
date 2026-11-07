"""Kaggle lane, host side. One call = one unit (next arm × repeat of the active stage), then submit and record.

python3 lane.py --stage-dir <state>/<stage> --slug S --arms base,harness --repeats 2 --minutes 60 --calls 150
Order is interleaved (base#1, harness#1, base#2, harness#2) so time-of-day effects hit both arms alike.
Writes results.jsonl rows and status.json {"remaining": n}. A unit that fails twice is skipped.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def redact(t):
    import re
    return re.sub(r"KGAT_[A-Za-z0-9]+|[0-9a-f]{32}|(bearer|token|key)\s*[=:]?\s*\S{16,}", "[REDACTED]", t or "", flags=re.I)


def validate(sub, sample):
    """Same columns, same ids, no missing values. Returns (ok, message)."""
    try:
        with open(sample, newline="") as f:
            r = csv.reader(f); sh = next(r); sids = [row[0] for row in r]
        with open(sub, newline="") as f:
            r = csv.reader(f); h = next(r); rows = list(r)
    except Exception as e:
        return False, f"unreadable: {e}"
    if [c.strip() for c in h] != [c.strip() for c in sh]:
        return False, f"columns {h[:5]} != {sh[:5]}"
    if len(rows) != len(sids) or set(r[0] for r in rows) != set(sids):
        return False, f"ids differ: {len(rows)} rows vs {len(sids)}"
    if any(len(r) != len(sh) or any(v.strip() == "" for v in r) for r in rows):
        return False, "missing values"
    return True, "ok"


def submit(slug, path, msg):
    subprocess.run(["kaggle", "competitions", "submit", "-c", slug, "-f", path, "-m", msg], check=True,
                   capture_output=True, text=True)
    for _ in range(40):                       # up to ~20 min for scoring
        time.sleep(30)
        out = subprocess.run(["kaggle", "competitions", "submissions", "-c", slug, "--csv"], capture_output=True,
                             text=True).stdout
        for row in csv.DictReader(out.splitlines()):
            if row.get("description") == msg:
                st = (row.get("status") or "").lower()
                if "complete" in st:
                    return {"public": row.get("publicScore"), "private": row.get("privateScore"), "status": st}
                if "error" in st:
                    return {"status": st, "error": row.get("errorDescription")}
    return {"status": "timeout"}


def main():
    ap = argparse.ArgumentParser()
    for k in ("stage-dir", "slug", "arms"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--calls", type=int, default=150)
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    os.makedirs(a.stage_dir, exist_ok=True)
    res = os.path.join(a.stage_dir, "results.jsonl")
    rows = [json.loads(l) for l in open(res)] if os.path.exists(res) else []
    units = [(rep, arm) for rep in range(1, a.repeats + 1) for arm in a.arms.split(",")]
    tries = {}
    for r in rows:
        tries[(r["rep"], r["arm"])] = tries.get((r["rep"], r["arm"]), 0) + (0 if "error" not in r else 1)
    done = {(r["rep"], r["arm"]) for r in rows if "error" not in r} | {k for k, n in tries.items() if n >= 2}
    todo = [u for u in units if u not in done]
    if todo:
        rep, arm = todo[0]
        meta = json.load(open(os.path.join(a.data, "meta.json")))
        out = os.path.join(a.stage_dir, f"{arm}_r{rep}")
        shutil.rmtree(out, ignore_errors=True)
        t0 = time.time()
        p = subprocess.run(["bash", os.path.join(HERE, "run_arm.sh"), arm, a.data, out, str(a.minutes), str(a.calls),
                            meta["enabled"] or meta["deadline"], f"kaggle-{a.slug}"[:60]], capture_output=True, text=True)
        row = {"slug": a.slug, "arm": arm, "rep": rep, "wall_s": round(time.time() - t0), "runner": redact(p.stdout)[-300:]}
        try:
            row["pacer"] = json.load(open(os.path.join(out, "logs", "pacer_stats.json")))
        except Exception:
            pass
        sub = os.path.join(out, "work", "submission.csv")
        if not os.path.exists(sub):
            row["error"] = "no submission.csv" + (f" | {redact(p.stderr)[-300:]}" if p.returncode else "")
        else:
            ok, msg = validate(sub, os.path.join(a.data, "sample_submission.csv"))
            row["valid"] = msg
            if not ok:
                row["score"] = {"status": "invalid"}           # a real outcome of the arm, not an infra error
            else:
                shutil.copy(sub, os.path.join(out, "submission.csv"))
                try:
                    row["score"] = submit(a.slug, sub, f"harness-core {arm} r{rep} {int(t0)}")
                except subprocess.CalledProcessError as e:
                    row["error"] = "submit failed: " + redact(e.stderr)[-300:]
        shutil.rmtree(os.path.join(out, "work"), ignore_errors=True)   # data copies are not kept; logs are
        with open(res, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False)[:600])
    tries = {}
    for r in rows:
        tries[(r["rep"], r["arm"])] = tries.get((r["rep"], r["arm"]), 0) + (0 if "error" not in r else 1)
    done = {(r["rep"], r["arm"]) for r in rows if "error" not in r} | {k for k, n in tries.items() if n >= 2}
    json.dump({"remaining": sum(u not in done for u in units)}, open(os.path.join(a.stage_dir, "status.json"), "w"))


if __name__ == "__main__":
    main()

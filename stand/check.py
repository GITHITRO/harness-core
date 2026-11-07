"""Stand status page + self-healing, run at the end of every lane job (no LLM, stdlib only).

python3 stand/check.py --out STATUS.md [--dispatch]
  - per lane: active run?, remaining, last run conclusion
  - metrics from runs-<lane>/<stage>/results.jsonl: SB accuracy per arm on common tasks, sign test vs base;
    tau2 pass per arm on pairs
  - --dispatch (needs GH_TOKEN): restart a lane that is idle while remaining > 0
"""
import argparse
import base64
import json
import math
import os
import urllib.request

sys_path = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, sys_path)
import active as ACTIVE  # noqa: E402

REPO = os.environ.get("GITHUB_REPOSITORY", "GITHITRO/harness-core")
API = f"https://api.github.com/repos/{REPO}"
TOKEN = os.environ.get("GH_TOKEN", "")


def get(url, raw=False):
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = "Bearer " + TOKEN
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
            data = r.read()
        return data.decode() if raw else json.loads(data)
    except Exception:
        return None


def content(branch, path):
    d = get(f"{API}/contents/{path}?ref={branch}")
    if d and d.get("content"):
        return base64.b64decode(d["content"]).decode()
    if d and d.get("download_url"):             # files > 1 MB
        return get(d["download_url"], raw=True)
    return None


def sign_p(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="STATUS.md")
    ap.add_argument("--dispatch", action="store_true")
    a = ap.parse_args()
    plan = json.load(open(os.path.join(os.path.dirname(__file__), "plan.json")))
    runs = (get(f"{API}/actions/runs?per_page=30") or {}).get("workflow_runs", [])
    md = ["# Stand status", "", "| lane | stage | active | remaining | last run |", "|---|---|---|---|---|"]
    detail = []
    for lane in ("sb", "tau2"):
        cur, _ = ACTIVE.active(plan, lane)
        cfg = cur or ACTIVE.stages(plan, lane)[-1]
        mine = [r for r in runs if r["name"] == f"lane-{lane}"]
        own_id = os.environ.get("GITHUB_RUN_ID")
        active = [r for r in mine if r["status"] in ("in_progress", "queued", "pending", "waiting") and str(r["id"]) != own_id]
        last = next((r for r in mine if r["status"] == "completed"), None)
        st = content(f"runs-{lane}", f"{cfg['stage']}/status.json")
        rem = json.loads(st)["remaining"] if st else ("not started" if cur else 0)
        action = ""
        # restart only OTHER lanes (a lane re-dispatching itself after a crash would loop)
        if a.dispatch and cur and not active and lane != os.environ.get("LANE") and TOKEN:
            req = urllib.request.Request(f"{API}/actions/workflows/{lane}.yml/dispatches", data=b'{"ref":"main"}',
                                         method="POST", headers={"Authorization": "Bearer " + TOKEN,
                                                                 "Accept": "application/vnd.github+json"})
            try:
                urllib.request.urlopen(req, timeout=30)
                action = " → restarted"
            except Exception as e:
                action = f" → restart failed: {e}"
        md.append(f"| {lane} | {cfg['stage']} | {len(active)} | {rem}{action} | "
                  f"{(last or {}).get('conclusion', '—')} {(last or {}).get('updated_at', '')[:16]} |")
        res = content(f"runs-{lane}", f"{cfg['stage']}/results.jsonl")
        rows = [json.loads(l) for l in (res or "").splitlines() if l.strip()]
        rows = [r for r in rows if "error" not in r]
        md_stage = cfg["stage"]
        if lane == "sb" and cfg.get("script") == "lhaw":
            summ = content(f"runs-{lane}", f"{cfg['stage']}/summary.json")
            detail += ["", "## SpreadsheetBench, underspecified (LHAW: output location removed, asking allowed)", "",
                       "```", summ or "no summary yet", "```"]
        elif lane == "sb":
            cur = {"harness": "sb-h2"}
            by = {}
            for r in rows:
                if r["arm"] in cur and r.get("harness_version") != cur[r["arm"]]:
                    continue
                by.setdefault(r["arm"], {})[r["id"]] = r
            base = by.get("base", {})
            detail += ["", "## SpreadsheetBench (Verified-400, first 100 of the stratified order)", "",
                       "| arm | n | correct | vs base on common tasks (+/−, sign p) | calls/task |", "|---|---|---|---|---|"]
            for arm, d in by.items():
                ids = [i for i in d if i in base]
                plus = sum(d[i]["correct"] and not base[i]["correct"] for i in ids)
                minus = sum(base[i]["correct"] and not d[i]["correct"] for i in ids)
                acc = sum(r["correct"] for r in d.values())
                cpt = sum(r.get("calls", 0) for r in d.values()) / max(1, len(d))
                vs = "—" if arm == "base" else f"+{plus}/−{minus}, p={sign_p(minus, plus + minus):.3f} (n={len(ids)})"
                detail.append(f"| {arm} | {len(d)} | {acc} ({acc / max(1, len(d)):.0%}) | {vs} | {cpt:.2f} |")
        else:
            by = {}
            for r in rows:
                if r["arm"] == "harness" and r.get("harness_version") != "tau2-h2":
                    continue
                by.setdefault(r["arm"], {})[r["idx"]] = r["reward"] >= 0.999
            b, h = by.get("base", {}), by.get("harness", {})
            ids = [i for i in h if i in b]
            detail += ["", f"## τ² {cfg.get('domain', '')}", "",
                       f"pairs {len(ids)}: base {sum(b[i] for i in ids)} · harness {sum(h[i] for i in ids)} · "
                       f"harness-only {sum(h[i] and not b[i] for i in ids)} · base-only {sum(b[i] and not h[i] for i in ids)}"]
    md += detail + ["", f"_updated by stand/check.py; plan: stand/plan.json_"]
    open(a.out, "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()

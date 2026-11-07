"""Which stage of a lane runs now: the first stage in plan.json (current + queue) whose results are not complete.

python3 stand/active.py <lane>              -> key=value lines for $GITHUB_OUTPUT (enabled, stage, n, arms, ...)
python3 stand/active.py <lane> --has-work   -> prints 1 if any stage of the lane still has work, else 0
A stage is complete when runs-<lane>/<stage>/status.json says remaining == 0. Not started -> has work.
"""
import base64
import json
import os
import sys
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "GITHITRO/harness-core")
HERE = os.path.dirname(os.path.abspath(__file__))


def remaining(lane, stage):
    h = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    url = f"https://api.github.com/repos/{REPO}/contents/{stage}/status.json?ref=runs-{lane}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return json.loads(base64.b64decode(json.load(r)["content"]))["remaining"]
    except Exception:
        return None                                   # not started (or unreadable): treat as work to do


def stages(plan, lane):
    cur = {k: v for k, v in plan[lane].items() if k != "queue"}
    return [cur] + [dict(cur, **q) for q in plan[lane].get("queue", [])]


def active(plan, lane):
    if not plan[lane].get("enabled", True):
        return None, 0
    for s in stages(plan, lane):
        rem = remaining(lane, s["stage"])
        if rem is None or rem != 0:
            return s, rem
    return None, 0


def main():
    lane = sys.argv[1]
    plan = json.load(open(os.path.join(HERE, "plan.json")))
    s, rem = active(plan, lane)
    if "--has-work" in sys.argv:
        print(1 if s else 0)
        return
    if not s:
        print("enabled=false")
        return
    print("enabled=true")
    print(f"model={plan['model']}")
    for k, v in s.items():                      # every scalar setting of the stage
        if isinstance(v, (str, int, float, bool)) and k != "enabled":
            print(f"{k}={v}")
    print(f"script={s.get('script', 'run')}")


if __name__ == "__main__":
    main()

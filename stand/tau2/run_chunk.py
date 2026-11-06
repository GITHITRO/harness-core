"""Paired tau2 runs through the pacer: for each task, base (stock llm_agent) then harness, back to back.

<tau2 venv python> -I stand/tau2/run_chunk.py --domain telecom --n 5 --out runs/tau2/calib --deadline <epoch>

Task order: seeded shuffle (seed 0) of the domain's base split, so any prefix is a fair sample.
Each (task, arm) is one `tau2 run` with 1 trial, seed 300, concurrency 1. The full tau2 results.json
(trajectory, reward breakdown) is copied to <out>/<arm>/<idx>.json; one summary row goes to results.jsonl.
Agent and user simulator are the same model; user traffic is tagged arm "<arm>-user" in the pacer log.
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PACER = os.environ.get("PACER", "http://127.0.0.1:8787").rstrip("/")
MODEL = os.environ.get("MODEL", "nvidia/nemotron-3.5-super-vl:free")
AGENTS = {"base": "llm_agent", "harness": "harness_agent"}
HARNESS_VERSION = "tau2-h2"


def task_ids(domain, seed=0):
    from tau2.registry import registry
    loader = registry.get_tasks_loader(domain)
    try:
        tasks = loader("base")
    except TypeError:
        tasks = loader()
    ids = [t.id for t in tasks]
    random.Random(seed).shuffle(ids)
    return ids


def llm_args(bench, arm):
    return json.dumps({"api_base": f"{PACER}/b/{bench}/a/{arm}/v1", "api_key": "via-pacer",
                       "temperature": 0.0, "num_retries": 1})


def run_one(domain, tid, arm, idx, out, timeout_s):
    from tau2.utils.utils import DATA_DIR
    name = f"hc_{domain}_{arm}_{idx:03d}_{int(time.time())}"
    bench = f"tau2-{domain}"
    cmd = [sys.executable, "-I", os.path.join(HERE, "launch.py"), "run", "--domain", domain,
           "--agent", AGENTS[arm], "--agent-llm", f"openai/{MODEL}", "--agent-llm-args", llm_args(bench, arm),
           "--user-llm", f"openai/{MODEL}", "--user-llm-args", llm_args(bench, arm + "-user"),
           "--task-ids", tid, "--num-trials", "1", "--max-concurrency", "1", "--seed", "300",
           "--save-to", name, "--timeout", str(timeout_s), "--log-level", "WARNING"]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    src = os.path.join(DATA_DIR, "simulations", name, "results.json")
    row = {"idx": idx, "task_id": tid, "arm": arm, "model": MODEL, "rc": p.returncode,
           "harness_version": HARNESS_VERSION if arm == "harness" else None,
           "wall_s": round(time.time() - t0, 1)}
    if not os.path.exists(src):
        row["error"] = (p.stderr or p.stdout)[-600:]
        return row
    os.makedirs(os.path.join(out, arm), exist_ok=True)
    shutil.copy(src, os.path.join(out, arm, f"{idx:03d}.json"))
    res = json.load(open(src))
    sims = res.get("simulations") or []
    if not sims:
        row["error"] = "no simulation in results.json"
        return row
    s = sims[0]
    ri = s.get("reward_info") or {}
    msgs = s.get("messages") or []
    row.update({"reward": ri.get("reward"), "termination": s.get("termination_reason"),
                "n_messages": len(msgs),
                "agent_calls": sum(1 for m in msgs if m.get("role") == "assistant"),
                "agent_cost": s.get("agent_cost"), "user_cost": s.get("user_cost")})
    if row["reward"] is None:
        row["error"] = f"no reward (termination={row['termination']})"
    return row


def _current(r):
    """Base rows always count; harness rows only for the current harness version."""
    return r["arm"] != "harness" or r.get("harness_version") == HARNESS_VERSION


def summarize(out):
    path = os.path.join(out, "results.jsonl")
    rows = [json.loads(l) for l in open(path)] if os.path.exists(path) else []
    rows = [r for r in rows if "error" not in r and _current(r)]
    s = {"harness_version": HARNESS_VERSION}
    for arm in sorted({r["arm"] for r in rows if r["arm"] != "harness_version"}):
        rs = [r for r in rows if r["arm"] == arm]
        s[arm] = {"n": len(rs), "pass": sum(r["reward"] >= 0.999 for r in rs),
                  "pass_rate": round(sum(r["reward"] >= 0.999 for r in rs) / len(rs), 3),
                  "mean_messages": round(sum(r["n_messages"] for r in rs) / len(rs), 1)}
    by = {}
    for r in rows:
        by.setdefault(r["idx"], {})[r["arm"]] = r["reward"] >= 0.999
    pairs = [v for v in by.values() if "base" in v and "harness" in v]
    s["paired"] = {"n": len(pairs), "harness_only": sum(v["harness"] and not v["base"] for v in pairs),
                   "base_only": sum(v["base"] and not v["harness"] for v in pairs)}
    json.dump(s, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print(json.dumps(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="telecom")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--arms", default="base,harness")
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=0)
    ap.add_argument("--timeout", type=int, default=2400, help="per-simulation wall clock limit, s")
    ap.add_argument("--max-attempts", type=int, default=2, help="per (task, arm) before it is marked failed")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "results.jsonl")
    rows = [json.loads(l) for l in open(path)] if os.path.exists(path) else []
    done = {(r["idx"], r["arm"]) for r in rows if "error" not in r and _current(r)}
    tries = {}
    for r in rows:
        if not _current(r):
            continue
        tries[(r["idx"], r["arm"])] = tries.get((r["idx"], r["arm"]), 0) + 1
    ids = task_ids(a.domain)[: a.n]
    arms = a.arms.split(",")
    stop = False
    for idx, tid in enumerate(ids):
        for arm in arms:
            key = (idx, arm)
            if key in done or tries.get(key, 0) >= a.max_attempts:
                continue
            if a.deadline and time.time() > a.deadline:
                print("deadline reached, stopping")
                stop = True
                break
            row = run_one(a.domain, tid, arm, idx, a.out, a.timeout)
            with open(path, "a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{idx:03d} {arm:<8} reward={row.get('reward')} msgs={row.get('n_messages')} "
                  f"{row['wall_s']}s {row.get('error', '')[:160]}", flush=True)
        if stop:
            break
    final = [json.loads(l) for l in open(path)] if os.path.exists(path) else []
    ok = {(r["idx"], r["arm"]) for r in final if "error" not in r and _current(r)}
    cnt = {}
    for r in final:
        if not _current(r):
            continue
        cnt[(r["idx"], r["arm"])] = cnt.get((r["idx"], r["arm"]), 0) + 1
    remaining = sum((i, arm) not in ok and cnt.get((i, arm), 0) < a.max_attempts
                    for i in range(len(ids)) for arm in arms)
    json.dump({"remaining": remaining}, open(os.path.join(a.out, "status.json"), "w"))
    summarize(a.out)


if __name__ == "__main__":
    main()

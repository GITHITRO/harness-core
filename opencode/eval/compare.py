#!/usr/bin/env python3
"""Compare a base run and a harness run of the same real task: metric + blind LLM-jury review of the traces.

Decision rule (from the eval protocol):
  metric  PASS  if the harness metric beats base (direction set by --higher-better / --lower-better)
  logic   PASS  if the jury prefers the harness trace in BOTH presentation orders by majority, and its mean
                rubric score is not lower than base's
  verdict PASS only when both pass. Metric up with logic not passing = "luck" (outcome without a sound process).
  Logic passing with metric not up = "process better, outcome not" (look at the task, not at the harness).

Usage
  python3 compare.py --base base.json --harness harness.json --task task.md \
      --metric-base 0.62 --metric-harness 0.71 --higher-better \
      --judges judges.json --out report

  base.json / harness.json : `opencode export <sessionID>` of each arm (several files per arm: repeat the flag)
  judges.json              : [{"name": "...", "url": ".../chat/completions", "model": "...", "key_env": "ENV"}]
Outputs <out>.json and <out>.md. Stdlib only.

Blinding: arms are shown as X / Y in random order and then swapped (position bias cancels); harness-specific names
(.harness/, hc-*, harness-core, "core" agent) are neutralised. Blinding is partial: a structured process is still
visible, which is exactly what is being judged.
"""
import argparse
import json
import random
import re
import sys
import urllib.error
import urllib.request

RUBRIC = [
    ("goal", "Goal and success criteria were made explicit and measurable before or early in the work."),
    ("uncertainty", "Unknowns and assumptions were identified; information was gathered (files, tools, questions) before committing; defaults were stated."),
    ("options", "Alternatives were considered where the task warranted it, with a reason for the choice and attention to reversibility."),
    ("grounding", "Claims and decisions rest on tool outputs actually seen; nothing is fabricated or assumed silently."),
    ("verification", "Real checks were run (tests, builds, metrics); evidence was gathered before declaring done."),
    ("recovery", "Failures and errors were diagnosed to their cause and fixed there, not papered over or retried blindly."),
    ("efficiency", "No wasted loops, ceremony or redundant steps relative to the difficulty of the task."),
    ("honesty", "The final claim matches the evidence; what is unverified or assumed is said plainly."),
]

JUDGE_PROMPT = """You are reviewing two traces of AI coding agents that worked on the same task. Judge the quality
of the PROCESS (reasoning, decisions, checks), not style, length or the tools' names.

<task>
{task}
</task>

<trace id="X">
{x}
</trace>

<trace id="Y">
{y}
</trace>

Score each trace 1-5 on every criterion, citing a short piece of the trace as evidence:
{rubric}

Then give an overall preference.
Return ONLY a JSON object:
{{"X": {{"<criterion>": {{"score": 1-5, "evidence": "..."}}, ...}},
  "Y": {{...}},
  "preference": "X" | "Y" | "tie", "confidence": 0.0-1.0,
  "key_failures": {{"X": ["..."], "Y": ["..."]}}, "summary": "two sentences"}}"""

NEUTRAL = [(r"\.harness/", "notes/"), (r"\bhc-(scout|redteam|verifier)\b", r"helper-\1"), (r"harness-core", "toolkit"),
           (r"\bharness\b", "toolkit"), (r"\bagent[=: ]+\"?core\"?", "agent=main"), (r"<harness_state>", "<notes>")]


def load_export(path):
    raw = open(path, encoding="utf-8").read()
    return json.loads(raw[raw.find("{"):])


def stats(sessions):
    s = {"sessions": len(sessions), "assistant_msgs": 0, "tokens_in": 0, "tokens_out": 0, "tokens_reasoning": 0,
         "tokens_cache_read": 0, "cost": 0.0, "tool_calls": 0, "tool_errors": 0, "subagent_calls": 0,
         "questions": 0, "wall_s": 0.0, "tools": {}}
    for d in sessions:
        t = d["info"].get("time", {})
        if t.get("created") and t.get("updated"):
            s["wall_s"] += (t["updated"] - t["created"]) / 1000
        for m in d["messages"]:
            i = m["info"]
            if i.get("role") == "assistant":
                s["assistant_msgs"] += 1
                tok = i.get("tokens") or {}
                s["tokens_in"] += tok.get("input", 0)
                s["tokens_out"] += tok.get("output", 0)
                s["tokens_reasoning"] += tok.get("reasoning", 0)
                s["tokens_cache_read"] += (tok.get("cache") or {}).get("read", 0)
                s["cost"] += i.get("cost") or 0
            for p in m["parts"]:
                if p.get("type") != "tool":
                    continue
                s["tool_calls"] += 1
                s["tools"][p["tool"]] = s["tools"].get(p["tool"], 0) + 1
                if (p.get("state") or {}).get("status") == "error":
                    s["tool_errors"] += 1
                if p["tool"] == "task":
                    s["subagent_calls"] += 1
                if p["tool"] == "question":
                    s["questions"] += 1
    s["wall_s"] = round(s["wall_s"], 1)
    s["cost"] = round(s["cost"], 4)
    return s


def condense(sessions, limit=45000):
    lines = []
    for k, d in enumerate(sessions):
        if len(sessions) > 1:
            lines.append(f"=== session {k + 1} ===")
        for m in d["messages"]:
            role = m["info"].get("role")
            for p in m["parts"]:
                ty = p.get("type")
                if ty == "text" and (p.get("text") or "").strip() and not p.get("synthetic"):
                    lines.append(f"[{role}] {p['text'].strip()[:700]}")
                elif ty == "tool":
                    st = p.get("state") or {}
                    inp = json.dumps(st.get("input") or {}, ensure_ascii=False)[:300]
                    out = str(st.get("output") or st.get("error") or "")[:400].replace("\n", " | ")
                    lines.append(f"[tool {p['tool']} {st.get('status')}] {inp} -> {out}")
    text = "\n".join(lines)
    for pat, rep in NEUTRAL:
        text = re.sub(pat, rep, text, flags=re.I)
    if len(text) > limit:
        head, tail = text[: limit // 2], text[-limit // 2:]
        text = head + f"\n…[{len(text) - limit} chars of the middle omitted]…\n" + tail
    return text


def call(judge, prompt):
    import os
    body = json.dumps({"model": judge["model"], "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0}).encode()
    req = urllib.request.Request(judge["url"], data=body, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ[judge["key_env"]]})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read()[:200]!r}"
    text = d["choices"][0]["message"].get("content") or ""
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)), None
    except Exception:
        return None, "unparseable: " + text[:200]


def mean_score(side):
    vals = [v.get("score") for v in side.values() if isinstance(v, dict) and isinstance(v.get("score"), (int, float))]
    return sum(vals) / len(vals) if vals else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", action="append", required=True)
    ap.add_argument("--harness", action="append", required=True)
    ap.add_argument("--task", required=True, help="file with the objective given to both arms")
    ap.add_argument("--metric-base", type=float)
    ap.add_argument("--metric-harness", type=float)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--higher-better", action="store_true", default=True)
    g.add_argument("--lower-better", action="store_true")
    ap.add_argument("--judges", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="report")
    a = ap.parse_args()

    base = [load_export(p) for p in a.base]
    harn = [load_export(p) for p in a.harness]
    task = open(a.task, encoding="utf-8").read()
    traces = {"base": condense(base), "harness": condense(harn)}
    rubric = "\n".join(f"- {k}: {v}" for k, v in RUBRIC)
    judges = json.load(open(a.judges))
    rng = random.Random(a.seed)
    first = rng.choice([("base", "harness"), ("harness", "base")])
    orders = [first, first[::-1]]

    reviews = []
    for j in judges:
        for x_arm, y_arm in orders:
            res, err = call(j, JUDGE_PROMPT.format(task=task, x=traces[x_arm], y=traces[y_arm], rubric=rubric))
            rec = {"judge": j["name"], "X": x_arm, "Y": y_arm, "error": err}
            if res:
                pref = res.get("preference")
                rec.update({"preferred": {"X": x_arm, "Y": y_arm}.get(pref, "tie"),
                            "confidence": res.get("confidence"),
                            "mean": {x_arm: mean_score(res.get("X", {})), y_arm: mean_score(res.get("Y", {}))},
                            "scores": {x_arm: res.get("X"), y_arm: res.get("Y")},
                            "key_failures": {x_arm: (res.get("key_failures") or {}).get("X"),
                                             y_arm: (res.get("key_failures") or {}).get("Y")},
                            "summary": res.get("summary")})
            reviews.append(rec)
            print(f"{j['name']:<20} X={x_arm:<8} -> {rec.get('preferred', 'ERROR')} {err or ''}", file=sys.stderr)

    ok = [r for r in reviews if not r["error"]]
    per_judge = {}
    for r in ok:
        per_judge.setdefault(r["judge"], []).append(r["preferred"])
    consistent = {jn: (p[0] if len(p) == 2 and p[0] == p[1] else "inconsistent") for jn, p in per_judge.items()}
    votes = list(consistent.values())
    harness_votes = votes.count("harness")
    means = {arm: [r["mean"][arm] for r in ok if r["mean"].get(arm) is not None] for arm in ("base", "harness")}
    avg = {arm: round(sum(v) / len(v), 2) if v else None for arm, v in means.items()}
    logic_pass = bool(votes) and harness_votes > len(votes) / 2 and (avg["harness"] or 0) >= (avg["base"] or 0)

    metric_pass = None
    tie = a.metric_base is not None and a.metric_base == a.metric_harness
    if a.metric_base is not None and a.metric_harness is not None:
        metric_pass = a.metric_harness < a.metric_base if a.lower_better else a.metric_harness > a.metric_base
    if metric_pass is None:
        verdict = "logic only (no metric given)"
    elif tie:
        verdict = "no metric gain; " + ("process better" if logic_pass else "process not better") + " (the cost decides)"
    elif metric_pass and logic_pass:
        verdict = "PASS"
    elif metric_pass:
        verdict = "luck: metric up, process not convincingly better"
    elif logic_pass:
        verdict = "process better, outcome not"
    else:
        verdict = "FAIL"

    report = {"verdict": verdict, "metric": {"base": a.metric_base, "harness": a.metric_harness, "pass": metric_pass},
              "logic": {"pass": logic_pass, "judge_verdicts": consistent, "mean_rubric": avg},
              "cost": {"base": stats(base), "harness": stats(harn)}, "reviews": reviews}
    json.dump(report, open(a.out + ".json", "w"), ensure_ascii=False, indent=1)

    md = [f"# Base vs harness: {verdict}", "",
          f"Metric: base {a.metric_base} · harness {a.metric_harness} · pass {metric_pass}",
          f"Logic: pass {logic_pass} · judges (consistent across both orders) {consistent} · mean rubric {avg}", "",
          "| | base | harness |", "|---|---|---|"]
    for k in ("tokens_in", "tokens_out", "tokens_reasoning", "cost", "assistant_msgs", "tool_calls", "tool_errors",
              "subagent_calls", "questions", "wall_s"):
        md.append(f"| {k} | {report['cost']['base'][k]} | {report['cost']['harness'][k]} |")
    md += ["", "## Rubric (mean over judges and orders)", "", "| criterion | base | harness |", "|---|---|---|"]
    for k, _ in RUBRIC:
        row = []
        for arm in ("base", "harness"):
            v = [r["scores"][arm][k]["score"] for r in ok
                 if isinstance((r["scores"].get(arm) or {}).get(k), dict) and isinstance(r["scores"][arm][k].get("score"), (int, float))]
            row.append(round(sum(v) / len(v), 2) if v else "—")
        md.append(f"| {k} | {row[0]} | {row[1]} |")
    md += ["", "## Judges"]
    for r in reviews:
        md.append(f"- **{r['judge']}** (X={r['X']}): preferred {r.get('preferred', 'ERROR')}, "
                  f"confidence {r.get('confidence')}. {r.get('summary') or r['error'] or ''}")
        if r.get("key_failures"):
            for arm in ("base", "harness"):
                if r["key_failures"].get(arm):
                    md.append(f"  - {arm} failures: " + "; ".join(map(str, r["key_failures"][arm]))[:500])
    open(a.out + ".md", "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md[:5]))


if __name__ == "__main__":
    main()

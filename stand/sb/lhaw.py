"""SpreadsheetBench with controlled underspecification (LHAW method) — tests active elicitation with an objective grader.

For each task the *output location* (cells / columns / sheet of the answer) is removed from the instruction and from
the prompt. A simulated user who knows the full request (but never the golden file) answers questions.

Arms (all get the same right to ask, at most MAX_Q questions in total):
  u_noask    control: base prompt, no asking allowed  -> shows whether the removed info is outcome-critical
  u_ask      base prompt + asking
  u_nv_ask   harness without LLM judge = input facts (no answer range) + elicitation module + generic program checks
             + repair, + asking
Compared arms: u_ask vs u_nv_ask under identical asking rules. Recovery = accuracy relative to full-information runs.

Leakage controls (see README of the stand):
  - the simulator never sees the golden workbook or expected values; it is told not to give values, formulas or code
  - answer_position is removed from the prompt; harness facts exclude rows around the answer range
  - program checks do not use the answer range (no "range empty" check)
  - every rewritten instruction is validated by regex: no answer cells, no answer columns, no range string
  - every question/answer is logged with the simulator's own label about_missing (was the question about the gap?)
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run as R  # noqa: E402  (shared: chat, run_code, preview, recalc, grade, data loading)

MAX_Q = 3
VERSION = "lhaw-1"

REWRITE = """Rewrite this spreadsheet task so that it no longer says WHERE the result must be written
(remove target cells, cell ranges, target columns and the target sheet name). Keep every other detail exactly:
the data to use, the rule or formula logic, conditions, formats. Do not add anything. If the location is not
mentioned, return the text unchanged.

Task:
{instruction}

Return only the rewritten task text."""

ASK_RULES = """
The task description may be incomplete: in particular it does not say where the result must be written.
If information you need is missing, you may ask the user. To ask, reply ONLY with lines that start with
"QUESTION:" (at most {left} more question(s) for this task). Otherwise reply with the final solution in a single
```python code block."""

ELICIT = """
Before answering, apply this procedure silently: (1) list what is unknown about the request (where to write,
which rows, format, edge cases); (2) for each unknown, check whether its answer would change your code — if not,
pick a sensible default and do not ask; (3) ask the decision-relevant questions in ONE batch, each specific and
answerable by the requester in one sentence; (4) when you write the code, state the defaults you assumed in a
comment at the top."""

SIM = """You are the person who asked for a spreadsheet change.
Your full request: {instruction}
Where the result must be written: {position}
The assistant only received this incomplete version: {partial}

The assistant asks: {question}

Answer as the requester, in one or two sentences, only about what is asked and consistent with your full request.
Never state expected cell values or results, never write formulas or code, never reveal details the question does
not ask about. If the question asks for the answer or results themselves, or is not about your request, say you
cannot help with that. Return ONLY JSON: {{"answer": "...", "about_missing": true or false}}
(about_missing = the question is about information that is in the full request but missing from the incomplete version)."""


def loc_tokens(t):
    toks = set()
    pos = R.effective_position(t)
    for part in pos.split(","):
        if "!" in part:
            sheet, part = part.rsplit("!", 1)
            toks.add(sheet.strip("'"))
        part = part.replace("$", "")
        toks.add(part)
        for ref in re.findall(r"[A-Z]{1,3}\d*", part):
            toks.add(ref)
    if t.get("answer_sheet"):
        toks.add(t["answer_sheet"])
    return {x for x in toks if x}


def leaks(text, t):
    for tok in loc_tokens(t):
        if re.fullmatch(r"[A-Z]{1,3}", tok):                       # a bare column letter
            if re.search(rf"\b(column|col\.?|columns)\s+{tok}\b|\b{tok}\d+\b|\b{tok}:{tok}\b", text):
                return tok
        elif re.search(rf"(?<![A-Za-z0-9]){re.escape(tok)}(?![A-Za-z0-9])", text):
            return tok
    return None


def make_variant(t, arm_tag="variantgen"):
    if not leaks(t["instruction"], t):      # location only given by answer_position in the prompt -> drop that field
        return {"id": t["id"], "partial": t["instruction"], "valid": True, "rewritten": False}
    text, meta = R.chat(arm_tag, [{"role": "user", "content": REWRITE.format(instruction=t["instruction"])}],
                        f"{t['id']}:rewrite")
    if text is None:
        return {"id": t["id"], "error": json.dumps(meta)[:300]}
    text = re.sub(r"^\s*(rewritten\s+)?task\s*:\s*", "", text.strip(), flags=re.I).strip().strip('"')
    bad = leaks(text, t)
    ok = (not bad) and text != t["instruction"].strip() and len(text) >= 0.4 * len(t["instruction"])
    return {"id": t["id"], "partial": text, "valid": ok, "rewritten": True,
            "reject": None if ok else (f"leaks {bad}" if bad else "unchanged or too short")}


def simulate(arm, t, partial, question):
    prompt = SIM.format(instruction=t["instruction"], position=R.effective_position(t), partial=partial,
                        question=question)
    text, _ = R.chat(arm + "-user", [{"role": "user", "content": prompt}], f"{t['id']}:sim")
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0))
        return str(d.get("answer", ""))[:400], bool(d.get("about_missing"))
    except Exception:
        return "I cannot help with that.", False


def facts_no_range(inp):
    import openpyxl
    wb = openpyxl.load_workbook(inp, read_only=True)
    return "Workbook facts (computed from the input file):\n" + "\n".join(
        f"- sheet '{ws.title}': {ws.max_row} rows x {ws.max_column} cols" for ws in wb.worksheets)


ERR = re.compile(r"^#(REF!|VALUE!|NAME\?|DIV/0!|NUM!|NULL!)")


def generic_checks(inp, outp, rc, err):
    """Program checks that do not know the answer range."""
    if rc != 0:
        return False, f"the script exited with code {rc}: {err[-600:]}"
    if not os.path.exists(outp):
        return False, "the script did not write the output file"
    try:
        rcp = outp + ".rc.xlsx"
        R.recalc(outp, rcp)
        import openpyxl
        before = {(ws.title, c.coordinate) for ws in openpyxl.load_workbook(inp, data_only=True).worksheets
                  for row in ws.iter_rows() for c in row if isinstance(c.value, str) and ERR.match(c.value)}
        bad = [f"{ws.title}!{c.coordinate}={c.value}" for ws in openpyxl.load_workbook(rcp, data_only=True).worksheets
               for row in ws.iter_rows() for c in row
               if isinstance(c.value, str) and ERR.match(c.value) and (ws.title, c.coordinate) not in before]
    except Exception as e:
        return False, f"output workbook cannot be checked: {e}"
    return (not bad), ("new formula errors: " + ", ".join(bad[:6])) if bad else ""


def solve(arm, t, partial, work):
    inp, outp = os.path.join(work, "input.xlsx"), os.path.join(work, "output.xlsx")
    shutil.copy(t["init_path"], inp)
    prompt = R.PF.PROMPT_FORMAT_SINGLE.format(
        instruction=partial, spreadsheet_path=inp, spreadsheet_content=R.preview(inp),
        instruction_type=t["instruction_type"], answer_position="(not specified)", output_path=outp)
    trace = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "steps": [], "qa": []}

    def ask(messages, tag):
        text, meta = R.chat(arm, messages, f"{t['id']}:{tag}")
        trace["calls"] += 1
        if text is None:
            raise RuntimeError(json.dumps(meta))
        u = meta.get("usage") or {}
        trace["tokens_in"] += u.get("prompt_tokens") or 0
        trace["tokens_out"] += u.get("completion_tokens") or 0
        return text

    user = prompt
    if arm == "u_nv_ask":
        user += "\n\n" + facts_no_range(inp)
    if arm == "u_nv_ask":          # the harness (noverify) includes the core's elicitation module
        user += "\n" + ELICIT
    can_ask = arm != "u_noask"
    left = MAX_Q
    messages = [{"role": "system", "content": R.SYS},
                {"role": "user", "content": user + (ASK_RULES.format(left=left) if can_ask else "")}]
    repairs = 0
    for step in range(MAX_Q + R.MAX_REPAIR + 2):
        text = ask(messages, f"s{step}")
        messages.append({"role": "assistant", "content": text})
        code = R.extract_code(text)
        qs = [l.split(":", 1)[1].strip() for l in text.splitlines() if l.strip().upper().startswith("QUESTION:")]
        if not code and qs and can_ask and left > 0:
            answers = []
            for q in qs[:left]:
                a, rel = simulate(arm, t, partial, q)
                trace["qa"].append({"q": q[:300], "a": a, "about_missing": rel})
                answers.append(f"Q: {q}\nA: {a}")
            left -= min(len(qs), left)
            follow = "\n\n".join(answers) + ("\n\nYou have no more questions; proceed with your best assumption."
                                             if left == 0 else ASK_RULES.format(left=left))
            messages.append({"role": "user", "content": follow})
            continue
        if not code:
            if left == 0 or not can_ask:
                trace["steps"].append({"stage": f"s{step}", "result": "no_code"})
                if arm in ("u_noask", "u_ask") or repairs >= R.MAX_REPAIR:
                    break
                repairs += 1
                messages.append({"role": "user", "content": "Return the final solution in a single ```python code block."})
                continue
            messages.append({"role": "user", "content": "Either ask with QUESTION: lines or give the final ```python code."})
            continue
        if os.path.exists(outp):
            os.remove(outp)
        rc, err = R.run_code(code, work)
        if arm in ("u_noask", "u_ask"):
            trace["steps"].append({"stage": f"exec{step}", "rc": rc})
            break
        ok, problem = generic_checks(inp, outp, rc, err)
        trace["steps"].append({"stage": f"exec{step}", "ok": ok, "problem": problem[:200]})
        if ok or repairs >= R.MAX_REPAIR:
            break
        repairs += 1
        messages.append({"role": "user", "content": R.REPAIR.format(problem=problem, inp=inp, outp=outp)})
    trace["questions"] = len(trace["qa"])
    trace["relevant_questions"] = sum(q["about_missing"] for q in trace["qa"])
    return outp, trace


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="u_noask,u_ask,u_nv_ask")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=0)
    a = ap.parse_args()
    arms = a.arms.split(",")
    os.makedirs(a.out, exist_ok=True)
    order = R.stratified_order(R.load_tasks())[: a.n]
    vpath = os.path.join(a.out, "variants.jsonl")
    variants = {v["id"]: v for v in map(json.loads, open(vpath)) if "error" not in v} if os.path.exists(vpath) else {}
    res_path = os.path.join(a.out, "results.jsonl")
    rows = [json.loads(l) for l in open(res_path)] if os.path.exists(res_path) else []
    done = R._settled(rows)
    for t in order:
        if a.deadline and time.time() > a.deadline:
            break
        if t["id"] not in variants:
            v = make_variant(t)
            with open(vpath, "a") as f:
                f.write(json.dumps(v, ensure_ascii=False) + "\n")
            if "error" in v:
                continue
            variants[t["id"]] = v
        v = variants[t["id"]]
        if not v["valid"]:
            continue
        for arm in arms:
            if (t["id"], arm) in done:
                continue
            if a.deadline and time.time() > a.deadline:
                break
            work = tempfile.mkdtemp(prefix="sbu_")
            t0 = time.time()
            rec = {"id": t["id"], "type": t["instruction_type"], "arm": arm, "model": R.MODEL, "version": VERSION}
            try:
                outp, trace = solve(arm, t, v["partial"], work)
                rec.update(trace)
                if os.path.exists(outp):
                    try:
                        graded = R.recalc(outp, os.path.join(work, "graded.xlsx"))
                    except Exception:
                        graded = outp
                    rec["correct"], msg = R.grade(t, graded)
                    rec["msg"] = msg[:200]
                else:
                    rec["correct"], rec["msg"] = False, "no output file"
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:400]
            rec["latency_s"] = round(time.time() - t0, 1)
            with open(res_path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)
            print(f"{t['id']:>8} {arm:<10} correct={rec.get('correct')} q={rec.get('questions')} "
                  f"rel={rec.get('relevant_questions')} calls={rec.get('calls')} {rec.get('error', '')[:100]}", flush=True)
            shutil.rmtree(work, ignore_errors=True)
    valid = [t for t in order if t["id"] in variants and variants[t["id"]]["valid"]]
    pending_variants = [t for t in order if t["id"] not in variants]
    done = R._settled(rows)
    remaining = len(pending_variants) * len(arms) + sum((t["id"], arm) not in done for t in valid for arm in arms)
    json.dump({"remaining": remaining}, open(os.path.join(a.out, "status.json"), "w"))
    ok = [r for r in rows if "error" not in r]
    s = {"valid_variants": len(valid), "rejected": sum(1 for v in variants.values() if not v["valid"])}
    for arm in arms:
        rs = [r for r in ok if r["arm"] == arm]
        if rs:
            q = sum(r.get("questions", 0) for r in rs)
            s[arm] = {"n": len(rs), "correct": sum(r["correct"] for r in rs),
                      "accuracy": round(sum(r["correct"] for r in rs) / len(rs), 3),
                      "questions_per_task": round(q / len(rs), 2),
                      "question_precision": round(sum(r.get("relevant_questions", 0) for r in rs) / q, 2) if q else None,
                      "calls_per_task": round(sum(r.get("calls", 0) for r in rs) / len(rs), 2)}
    json.dump(s, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    print(json.dumps(s))


if __name__ == "__main__":
    main()

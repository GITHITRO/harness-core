"""SpreadsheetBench Verified-400, two arms through the pacer proxy.

  base     official single-round protocol: PROMPT_FORMAT_SINGLE, one model call, code executed once.
  harness  the core applied to the same prompt (no access to golden files):
             contract  -> extra facts from the INPUT workbook (sheet sizes, rows around the answer range)
             execute   -> external checks: code ran, output exists, target sheet/cells filled, no #REF!/#VALUE!
             verify    -> one judge call sees instruction + code + produced target cells: PASS / FAIL(reason)
             repair    -> rollback to generation with the concrete failure, at most MAX_REPAIR rounds
           Guard "not worse than bare": a repair that breaks the external checks is discarded and the
           earlier output is kept.

python -I stand/sb/run.py --arms base,harness --n 20 --out runs/sb/calib --deadline <epoch>
Env: SB_DATA (extracted verified_400 dir), SB_REPO (SpreadsheetBench checkout), PACER (http://127.0.0.1:8787),
     MODEL (default nvidia/nemotron-3.5-super-vl:free).
"""
import argparse
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SB_DATA = os.environ["SB_DATA"]
SB_REPO = os.environ["SB_REPO"]
PACER = os.environ.get("PACER", "http://127.0.0.1:8787").rstrip("/")
MODEL = os.environ.get("MODEL", "nvidia/nemotron-3.5-super-vl:free")
GEN = {"temperature": 0.6, "top_p": 0.95, "max_tokens": 16000}
MAX_REPAIR = 2
SYS = "Answer in plain text. Put the final solution in a single ```python code block."


def _load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


PF = _load("prompt_format", os.path.join(SB_REPO, "inference", "prompt_format.py"))
OFFICIAL = _load("official_evaluation", os.path.join(SB_REPO, "evaluation", "evaluation.py"))


# ---------------------------------------------------------------- data
def load_tasks():
    ds = json.load(open(os.path.join(SB_DATA, "dataset.json"), encoding="utf-8"))
    out = []
    for d in ds:
        tid = str(d["id"])
        base = os.path.join(SB_DATA, "spreadsheet", tid)
        # Upstream naming is not uniform: 1_<id>_init.xlsx / 1_<id>_golden.xlsx for most tasks, initial.xlsx /
        # golden.xlsx for 13284 32023 32789 56274 58109, and 42930 ships 1_43930_golden.xlsx. Match by suffix.
        files = sorted(os.listdir(base)) if os.path.isdir(base) else []
        pick = lambda want, alt: next((os.path.join(base, f) for f in files if f == want), None) or \
            next((os.path.join(base, f) for f in files if f.endswith(alt)), os.path.join(base, want))
        init = pick(f"1_{tid}_init.xlsx", "_init.xlsx") if f"1_{tid}_init.xlsx" in files or not "initial.xlsx" in files \
            else os.path.join(base, "initial.xlsx")
        gold = pick(f"1_{tid}_golden.xlsx", "_golden.xlsx") if any(f.endswith("_golden.xlsx") for f in files) \
            else os.path.join(base, "golden.xlsx")
        out.append({"id": tid, "instruction": d["instruction"], "instruction_type": d["instruction_type"],
                    "answer_position": d["answer_position"], "answer_sheet": d.get("answer_sheet") or None,
                    "init_path": init, "golden_path": gold})
    return out


def stratified_order(tasks, seed=0):
    """Deterministic order whose every prefix keeps the cell/sheet proportion of the full set."""
    rng = random.Random(seed)
    strata = {}
    for t in tasks:
        strata.setdefault(t["instruction_type"], []).append(t)
    for v in strata.values():
        rng.shuffle(v)
    total, taken, order = len(tasks), {k: 0 for k in strata}, []
    while len(order) < total:
        k = min((k for k in strata if taken[k] < len(strata[k])),
                key=lambda k: (taken[k] + 1) / (len(strata[k]) / total))
        order.append(strata[k][taken[k]])
        taken[k] += 1
    return order


def effective_position(t):
    pos, sheet = t["answer_position"], t.get("answer_sheet")
    if not sheet:
        return pos
    return ",".join(p if "!" in p else f"'{sheet}'!{p}" for p in pos.split(","))


def grade(t, pred):
    try:
        ok, msg = OFFICIAL.compare_workbooks(t["golden_path"], pred, t["instruction_type"], effective_position(t))
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return bool(ok), str(msg)


def recalc(src, out, timeout=120):
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as prof:
        subprocess.run(["soffice", f"-env:UserInstallation=file://{prof}", "--headless", "--convert-to", "xlsx",
                        "--outdir", d, src], check=True, capture_output=True, timeout=timeout)
        shutil.copy(os.path.join(d, os.path.basename(src)), out)
    return out


def preview(path, rows=5):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"Sheet: {ws.title}")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= rows:
                break
            out.append(" | ".join("" if v is None else str(v) for v in row))
    return "\n".join(out)


# ---------------------------------------------------------------- model + execution
def chat(arm, messages, tag):
    body = json.dumps(dict(model=MODEL, messages=messages, **GEN)).encode()
    url = f"{PACER}/b/sb/a/{arm}/v1/chat/completions"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "X-Tag": tag})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=3600))
    except urllib.error.HTTPError as e:
        return None, {"http": e.code, "body": e.read()[:300].decode("utf-8", "replace")}
    except Exception as e:
        return None, {"http": 599, "body": f"{type(e).__name__}: {e}"}
    msg = d["choices"][0]["message"]
    return msg.get("content") or "", {"usage": d.get("usage", {}), "finish": d["choices"][0].get("finish_reason")}


def extract_code(text):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", re.S)
    return max(blocks, key=len) if blocks else None


def run_code(code, cwd, timeout=60):
    p = os.path.join(cwd, "solution.py")
    open(p, "w", encoding="utf-8").write(code)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": cwd, "LANG": "C.UTF-8"}
    try:
        r = subprocess.run([sys.executable, "-I", p], cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env)
        return r.returncode, (r.stderr or "")[-1500:]
    except subprocess.TimeoutExpired:
        return -9, "timeout after 60 s"


# ---------------------------------------------------------------- harness pieces (input-only facts, no golden)
def _ranges(t):
    import openpyxl.utils as U
    out = []
    for part in effective_position(t).split(","):
        sheet = None
        if "!" in part:
            sheet, part = part.rsplit("!", 1)
            sheet = sheet.strip("'")
        try:
            c1, r1, c2, r2 = U.range_boundaries(part.replace("$", ""))
        except Exception:
            continue
        out.append((sheet, c1, r1, c2 or c1, r2 or r1))
    return out


def contract_facts(t, inp):
    """Facts about the input workbook the bare prompt does not show (data acquisition stage)."""
    import openpyxl
    wb = openpyxl.load_workbook(inp, data_only=False)
    lines = ["Workbook facts (computed from the input file):"]
    for ws in wb.worksheets:
        lines.append(f"- sheet '{ws.title}': {ws.max_row} rows x {ws.max_column} cols")
    for sheet, c1, r1, c2, r2 in _ranges(t):
        ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.worksheets[0]
        lines.append(f"- answer range on '{ws.title}': rows {r1}-{r2}, cols {c1}-{c2}. Rows around it (formulas shown):")
        for r in range(max(1, r1 - 3), min(ws.max_row, r1 + 3) + 1):
            vals = [ws.cell(r, c).value for c in range(1, min(ws.max_column, c2 + 3) + 1)]
            lines.append(f"  row {r}: " + " | ".join("" if v is None else str(v)[:120] for v in vals))
    return "\n".join(lines)


# #N/A is excluded: it is a legitimate expected value in some tasks (calib: 47933 was broken by a repair).
ERR_RE = re.compile(r"^#(REF!|VALUE!|NAME\?|DIV/0!|NUM!|NULL!)")
HARNESS_VERSION = "sb-h2"


def external_checks(t, out_path, rc, stderr):
    """Program judge. Returns (ok, problems, target_dump). Uses the output only."""
    if rc != 0:
        return False, [f"the script exited with code {rc}: {stderr[-600:]}"], ""
    if not os.path.exists(out_path):
        return False, ["the script did not write the output file"], ""
    try:
        rc_path = out_path + ".recalc.xlsx"
        recalc(out_path, rc_path)
    except Exception as e:
        rc_path = out_path
    import openpyxl
    try:
        wb = openpyxl.load_workbook(rc_path, data_only=True)
    except Exception as e:
        return False, [f"output workbook cannot be opened: {e}"], ""
    problems, dump, filled, total = [], [], 0, 0
    for sheet, c1, r1, c2, r2 in _ranges(t):
        if sheet and sheet not in wb.sheetnames:
            problems.append(f"sheet '{sheet}' is missing in the output")
            continue
        ws = wb[sheet] if sheet else wb.worksheets[0]
        for r in range(r1, r2 + 1):
            row = []
            for c in range(c1, c2 + 1):
                v = ws.cell(r, c).value
                total += 1
                filled += v not in (None, "")
                if isinstance(v, str) and ERR_RE.match(v):
                    problems.append(f"{ws.title}!{ws.cell(r, c).coordinate} evaluates to {v}")
                row.append("" if v is None else (repr(v) if len(str(v)) <= 300 else repr(str(v)[:300]) + "...[display cut]"))
            if len(dump) < 25:
                dump.append(f"row {r}: " + " | ".join(row))
    if total and filled == 0 and t["instruction_type"].startswith("Cell"):
        problems.append("every cell of the answer range is empty after running the script")
    return not problems, problems[:8], "\n".join(dump)


VERIFY = """You are checking a spreadsheet solution before it is delivered.
Instruction: {instruction}
Answer range: {pos}
Script that produced the output:
```python
{code}
```
Values now in the answer range (after recalculation, Python repr; '...[display cut]' marks display truncation only):
{dump}
Input preview:
{preview}

Does the output satisfy the instruction exactly (right cells, right values, right format/type)?
Reply with one line: PASS, or FAIL: <the concrete defect>. Say FAIL only for a defect you can point to."""

REPAIR = """Your previous script had a problem:
{problem}
Fix it. Return the complete corrected script in a single ```python code block. Keep reading from {inp} and writing to {outp}."""


# ---------------------------------------------------------------- arms
def solve(arm, t, work):
    inp, outp = os.path.join(work, "input.xlsx"), os.path.join(work, "output.xlsx")
    shutil.copy(t["init_path"], inp)
    prompt = PF.PROMPT_FORMAT_SINGLE.format(instruction=t["instruction"], spreadsheet_path=inp,
                                            spreadsheet_content=preview(inp), instruction_type=t["instruction_type"],
                                            answer_position=effective_position(t), output_path=outp)
    trace = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "steps": []}

    def ask(messages, tag):
        text, meta = chat(arm, messages, f"{t['id']}:{tag}")
        trace["calls"] += 1
        if text is None:
            raise RuntimeError(json.dumps(meta))
        u = meta.get("usage") or {}
        trace["tokens_in"] += u.get("prompt_tokens") or 0
        trace["tokens_out"] += u.get("completion_tokens") or 0
        return text

    if arm == "base":
        text = ask([{"role": "system", "content": SYS}, {"role": "user", "content": prompt}], "gen")
        code = extract_code(text)
        if code:
            run_code(code, work)
        trace["steps"].append({"stage": "gen", "has_code": bool(code)})
        return outp, trace

    # harness
    messages = [{"role": "system", "content": SYS},
                {"role": "user", "content": prompt + "\n\n" + contract_facts(t, inp)}]
    best = None                       # (outp copy) of the last output that passed external checks
    for rnd in range(MAX_REPAIR + 1):
        text = ask(messages, f"gen{rnd}")
        messages.append({"role": "assistant", "content": text})
        code = extract_code(text)
        if os.path.exists(outp):
            os.remove(outp)
        if not code:
            problem = "no ```python code block was found in your answer"
            trace["steps"].append({"stage": f"gen{rnd}", "result": "no_code"})
        else:
            rc, err = run_code(code, work)
            ok, problems, dump = external_checks(t, outp, rc, err)
            trace["steps"].append({"stage": f"exec{rnd}", "ok": ok, "problems": problems})
            if ok:
                best = os.path.join(work, f"passed_{rnd}.xlsx")
                shutil.copy(outp, best)
                verdict = ask([{"role": "user", "content": VERIFY.format(
                    instruction=t["instruction"], pos=effective_position(t), code=code[:6000], dump=dump,
                    preview=preview(inp))}], f"verify{rnd}").strip()
                v_line = next((l for l in verdict.splitlines()[::-1] if re.match(r"\s*(PASS|FAIL)", l)), verdict[-200:])
                trace["steps"].append({"stage": f"verify{rnd}", "verdict": v_line[:300]})
                if not v_line.strip().startswith("FAIL"):
                    break
                problem = "a reviewer found: " + v_line.strip()[5:].strip(" :")
            else:
                problem = "; ".join(problems)
        if rnd == MAX_REPAIR:
            break
        messages.append({"role": "user", "content": REPAIR.format(problem=problem, inp=inp, outp=outp)})
    if best and (not os.path.exists(outp) or not external_checks(t, outp, 0, "")[0]):
        shutil.copy(best, outp)       # guard: never deliver something worse than an earlier passing output
        trace["steps"].append({"stage": "guard", "restored": os.path.basename(best)})
    return outp, trace


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="base,harness")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", required=True)
    ap.add_argument("--deadline", type=float, default=0, help="epoch seconds; no new task starts after it")
    a = ap.parse_args()
    arms = a.arms.split(",")
    os.makedirs(a.out, exist_ok=True)
    order = stratified_order(load_tasks())[: a.n]
    res_path = os.path.join(a.out, "results.jsonl")
    done = set()
    if os.path.exists(res_path):
        rows = [json.loads(l) for l in open(res_path, encoding="utf-8") if l.strip()]
        old = [r for r in rows if "error" not in r and not _current(r)]
        if old:
            with open(os.path.join(a.out, "results_superseded.jsonl"), "a", encoding="utf-8") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in old)
        keep = [r for r in rows if _current(r)]
        with open(res_path, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in keep)
        done = _settled(keep)
    for t in order:
        for arm in arms:                       # paired: base then harness on the same task, back to back
            if (t["id"], arm) in done:
                continue
            if a.deadline and time.time() > a.deadline:
                print("deadline reached, stopping")
                write_status(a.out, order, arms)
                return summarize(a.out)
            work = tempfile.mkdtemp(prefix="sb_")
            t0 = time.time()
            rec = {"id": t["id"], "type": t["instruction_type"], "arm": arm, "model": MODEL,
                   "harness_version": HARNESS_VERSION if arm == "harness" else None}
            try:
                outp, trace = solve(arm, t, work)
                rec.update(trace)
                if os.path.exists(outp):
                    try:
                        graded = recalc(outp, os.path.join(work, "graded.xlsx"))
                    except Exception as e:
                        graded, rec["recalc_error"] = outp, str(e)[:200]
                    rec["correct"], rec["msg"] = grade(t, graded)
                    rec["msg"] = rec["msg"][:200]
                else:
                    rec["correct"], rec["msg"] = False, "no output file"
            except Exception as e:  # one broken task must not stop the lane; recorded, retried once, then skipped
                rec["error"] = f"{type(e).__name__}: {e}"[:400]
            rec["latency_s"] = round(time.time() - t0, 1)
            with open(res_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            write_status(a.out, order, arms)          # after every task: a cancelled job still leaves a true status
            print(f"{t['id']:>8} {arm:<8} correct={rec.get('correct')} calls={rec.get('calls')} "
                  f"{rec['latency_s']}s {rec.get('error', '')[:120]}", flush=True)
            shutil.rmtree(work, ignore_errors=True)
    write_status(a.out, order, arms)
    summarize(a.out)


def summarize(out):
    rows = [json.loads(l) for l in open(os.path.join(out, "results.jsonl"), encoding="utf-8") if l.strip()]
    rows = [r for r in rows if "error" not in r and _current(r)]
    by = {}
    for r in rows:
        by.setdefault(r["arm"], []).append(r)
    s = {}
    for arm, rs in by.items():
        s[arm] = {"n": len(rs), "correct": sum(r["correct"] for r in rs),
                  "accuracy": round(sum(r["correct"] for r in rs) / len(rs), 3),
                  "calls_per_task": round(sum(r.get("calls", 0) for r in rs) / len(rs), 2),
                  "tokens_in": sum(r.get("tokens_in", 0) for r in rs),
                  "tokens_out": sum(r.get("tokens_out", 0) for r in rs)}
    ids = {}
    for r in rows:
        ids.setdefault(r["id"], {})[r["arm"]] = r["correct"]
    pairs = [v for v in ids.values() if "base" in v and "harness" in v]
    s["harness_version"] = HARNESS_VERSION
    s["paired"] = {"n": len(pairs), "harness_only": sum(v["harness"] and not v["base"] for v in pairs),
                   "base_only": sum(v["base"] and not v["harness"] for v in pairs)}
    json.dump(s, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print(json.dumps(s))
    return s


MAX_ATTEMPTS = 2


def _settled(rows):
    """(id, arm) that need no more work: a graded row, or MAX_ATTEMPTS error rows (then skipped in metrics)."""
    errs = {}
    ok = set()
    for r in rows:
        k = (r["id"], r["arm"])
        if "error" in r:
            errs[k] = errs.get(k, 0) + 1
        else:
            ok.add(k)
    return ok | {k for k, n in errs.items() if n >= MAX_ATTEMPTS}


def _current(r):
    """Base rows always count; harness rows only for the current harness version."""
    return r["arm"] != "harness" or r.get("harness_version") == HARNESS_VERSION


def write_status(out, order, arms):
    path = os.path.join(out, "results.jsonl")
    done = set()
    if os.path.exists(path):
        done = _settled([r for r in map(json.loads, open(path, encoding="utf-8")) if _current(r)])
    remaining = sum((t["id"], a) not in done for t in order for a in arms)
    json.dump({"remaining": remaining}, open(os.path.join(out, "status.json"), "w"))


if __name__ == "__main__":
    main()

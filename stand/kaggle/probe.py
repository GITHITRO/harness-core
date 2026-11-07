"""Probe Kaggle access for the candidate competitions (run in Actions with the Kaggle secret). Writes probe.md."""
import json
import os
import re
import subprocess

SLUGS = ["playground-series-s6e8", "playground-series-s6e9", "playground-series-s6e10", "playground-series-s6e11",
         "recruitment-task-for-ml-gdg", "squares-in-squares", "kaggriculture"]


SECRETS = [v for v in (os.environ.get("KAGGLE_API_TOKEN"), os.environ.get("KAGGLE_KEY")) if v]


def redact(text):
    """Never let a credential reach a log or a published file (an earlier version leaked one via error text)."""
    for v in SECRETS:
        text = text.replace(v, "[REDACTED]")
    return re.sub(r"KGAT_[A-Za-z0-9]+|(bearer|token|key)\s*[=:]?\s*\S{16,}", "[REDACTED]", text, flags=re.I)


def sh(cmd, timeout=300):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.returncode, redact((p.stdout + p.stderr).strip())


def main():
    out = ["# Kaggle probe", ""]
    rc, who = sh("kaggle config view 2>&1 | head -5")
    out += ["auth: " + ("ok" if rc == 0 else "FAILED"), ""]
    out += ["| competition | listed (deadline, entered) | files | download | notes |", "|---|---|---|---|---|"]
    for s in SLUGS:
        rc, lst = sh(f"kaggle competitions list -s {s} --csv")
        row = next((l for l in lst.splitlines()[1:] if s in l), "")
        rc_f, files = sh(f"kaggle competitions files -c {s} --csv")
        nfiles = max(0, len(files.splitlines()) - 1) if rc_f == 0 else 0
        os.makedirs(f"/tmp/k/{s}", exist_ok=True)
        rc_d, dl = sh(f"kaggle competitions download -c {s} -p /tmp/k/{s} -q", timeout=900)
        size = sh(f"du -sh /tmp/k/{s} | cut -f1")[1]
        note = ""
        if rc_d != 0:
            note = dl.splitlines()[-1][:160] if dl else "download failed"
        out.append(f"| {s} | {(row[:150] or lst.splitlines()[-1][:150]).replace(chr(10)," ")} | {nfiles if rc_f == 0 else files[-120:]} | "
                   f"{'ok ' + size if rc_d == 0 else 'NO'} | {note} |")
    rc, env = sh("pip install -q kaggle-environments 2>&1 | tail -1; python3 -c \"from kaggle_environments import make; "
                 "e=make('kaggriculture'); print('kaggriculture env ok', e.configuration.get('episodeSteps'))\" 2>&1 | tail -3",
                 timeout=900)
    out += ["", "kaggle-environments / kaggriculture: " + env.replace("\n", " | ")[:400]]
    text = redact("\n".join(out) + "\n")
    assert not any(v in text for v in SECRETS)
    open("probe.md", "w").write(text)
    print(text)


if __name__ == "__main__":
    main()

"""Pacer proxy: OpenAI-compatible, local, single upstream lane.

Everything a benchmark sends to the model goes through here, so one place enforces the quota and keeps
the full log. Tags come from the URL path, so unmodified clients (litellm inside tau2) can be tagged:

    base_url = http://127.0.0.1:8787/b/<bench>/a/<arm>/v1      -> POST .../v1/chat/completions

Rules
- Sliding window: at most BUDGET upstream attempts per 3600 s (retries count). The window is loaded from /
  saved to STATE_FILE, so consecutive CI runs share it.
- Requests are serialized (one in flight). 429 -> wait (Retry-After or 60 s * 2^n, cap 15 min) and retry;
  5xx / network errors -> backoff retry, at most MAX_RETRY attempts, then the error is passed to the client.
- Every attempt is logged to LOG_DIR/<bench>.<arm>.jsonl: request body, response body, status, latency.
- GET /stats -> JSON counters. Clients use it to decide whether to start another task.

Env: UPSTREAM_BASE, UPSTREAM_KEY_FILE or UPSTREAM_KEY, BUDGET (default 90), STATE_FILE, LOG_DIR, PORT, LANE.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("UPSTREAM_BASE", "https://ai-gateway.kilo.ai/api/v1").rstrip("/")
KEY = os.environ.get("UPSTREAM_KEY") or open(os.environ["UPSTREAM_KEY_FILE"]).read().strip()
BUDGET = int(os.environ.get("BUDGET", "90"))
STATE_FILE = os.environ.get("STATE_FILE", "pacer_state.json")
LOG_DIR = os.environ.get("LOG_DIR", "logs")
PORT = int(os.environ.get("PORT", "8787"))
HOST = os.environ.get("HOST", "127.0.0.1")
# hard per-run cap on upstream calls (equal budget for every arm); 0 = unlimited
MAX_CALLS = int(os.environ.get("MAX_CALLS", "0"))
LANE = os.environ.get("LANE", "kilo")
MAX_RETRY = int(os.environ.get("MAX_RETRY", "6"))
# measured on 529 calls: median 2.3 s, p99 126 s, max 190 s -> 300 s bounds a hung request with margin
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "300"))
WINDOW = 3600.0
PATH_RE = re.compile(r"^/b/([\w.-]+)/a/([\w.-]+)/v1(/.*)$")

os.makedirs(LOG_DIR, exist_ok=True)
_lock = threading.Lock()          # one upstream request at a time
_log_lock = threading.Lock()
_stats = {"lane": LANE, "budget": BUDGET, "attempts": 0, "ok": 0, "http_429": 0, "http_5xx": 0,
          "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "started": time.time()}


def _load_window():
    try:
        ts = json.load(open(STATE_FILE)).get("attempts", [])
        now = time.time()
        return [t for t in ts if now - t < WINDOW]
    except (OSError, ValueError):
        return []


_window = _load_window()


def save_state():
    now = time.time()
    with open(STATE_FILE, "w") as f:
        json.dump({"attempts": [t for t in _window if now - t < WINDOW], "saved": now}, f)


def _take_slot():
    """Block until the sliding window has room, then record an attempt."""
    while True:
        now = time.time()
        while _window and now - _window[0] >= WINDOW:
            _window.pop(0)
        if len(_window) < BUDGET:
            _window.append(now)
            _stats["attempts"] += 1
            save_state()
            return
        time.sleep(min(30.0, WINDOW - (now - _window[0]) + 0.5))


def _log(bench, arm, rec):
    with _log_lock, open(os.path.join(LOG_DIR, f"{bench}.{arm}.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def forward(bench, arm, subpath, body_bytes):
    try:
        req_json = json.loads(body_bytes)
    except ValueError:
        req_json = {"_raw": body_bytes.decode("utf-8", "replace")}
    url = UPSTREAM + subpath
    if MAX_CALLS and _stats["ok"] >= MAX_CALLS:
        _log(bench, arm, {"ts": time.time(), "lane": LANE, "bench": bench, "arm": arm, "status": 429, "budget_exhausted": True})
        return 429, json.dumps({"error": {"message": f"call budget of this run exhausted ({MAX_CALLS} calls). Stop and make sure /work/submission.csv is written.", "type": "budget_exhausted"}}).encode()
    with _lock:
        for attempt in range(MAX_RETRY):
            _take_slot()
            t0 = time.time()
            status, data, retry_after = None, b"", None
            try:
                r = urllib.request.Request(url, data=body_bytes, method="POST", headers={
                    "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
                with urllib.request.urlopen(r, timeout=UPSTREAM_TIMEOUT) as resp:
                    status, data = resp.status, resp.read()
            except urllib.error.HTTPError as e:
                status, data = e.code, e.read()
                retry_after = e.headers.get("Retry-After")
            except Exception as e:  # network / timeout
                status, data = 599, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()
            lat = round(time.time() - t0, 2)
            try:
                resp_json = json.loads(data)
            except ValueError:
                # streaming (SSE): keep the whole stream and read usage from the last chunk that carries it
                raw = data.decode("utf-8", "replace")
                resp_json = {"_stream": raw[:400000]}
                for line in raw.splitlines()[::-1]:
                    if line.startswith("data:") and '"usage"' in line:
                        try:
                            resp_json["usage"] = json.loads(line[5:].strip()).get("usage")
                            break
                        except ValueError:
                            pass
            usage = resp_json.get("usage") if isinstance(resp_json, dict) else None
            if status == 200 and usage:
                _stats["prompt_tokens"] += usage.get("prompt_tokens") or 0
                _stats["completion_tokens"] += usage.get("completion_tokens") or 0
            _log(bench, arm, {"ts": t0, "lane": LANE, "bench": bench, "arm": arm, "attempt": attempt,
                              "status": status, "latency_s": lat, "request": req_json, "response": resp_json})
            if status == 200:
                _stats["ok"] += 1
                return status, data
            if status == 429:
                _stats["http_429"] += 1
                try:
                    wait = float(retry_after)
                except (TypeError, ValueError):
                    wait = 60.0 * (2 ** attempt)
                time.sleep(min(wait, 900.0))
                continue
            if status >= 500:
                _stats["http_5xx"] += 1
                time.sleep(min(15.0 * (2 ** attempt), 300.0))
                continue
            _stats["errors"] += 1
            return status, data          # 4xx other than 429: client's problem, pass through
        _stats["errors"] += 1
        return status, data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, status, data, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/stats"):
            now = time.time()
            s = dict(_stats, in_window=sum(1 for t in _window if now - t < WINDOW))
            return self._send(200, json.dumps(s).encode())
        self._send(404, b"{}")

    def do_POST(self):
        m = PATH_RE.match(self.path)
        if not m:
            return self._send(404, b'{"error":"use /b/<bench>/a/<arm>/v1/..."}')
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        status, data = forward(m.group(1), m.group(2), m.group(3), body)
        self._send(status, data)


def main():
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"pacer lane={LANE} budget={BUDGET}/h window_loaded={len(_window)} port={PORT}", flush=True)
    try:
        srv.serve_forever()
    finally:
        save_state()


if __name__ == "__main__":
    main()

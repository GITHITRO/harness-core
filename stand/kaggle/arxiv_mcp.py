"""arXiv as an MCP tool with an enforced date cut-off (runs in its own container; the agent has no other way out).

Env: CUTOFF=YYYY-MM-DD (competition start; nothing submitted after it is visible), MAX_SEARCH, MAX_READ,
     CACHE_DIR (shared cache, committed for reproducibility), LOG (jsonl of every call).
Tools: arxiv_search(query, max_results<=10) -> id, title, submitted date, abstract (<=1200 chars)
       arxiv_read(paper_id, start=0) -> <=8000 chars of the paper text, only if submitted <= CUTOFF
arXiv API terms: at most one request every 3 seconds; responses are cached.
"""
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from mcp.server.fastmcp import FastMCP

CUTOFF = os.environ["CUTOFF"]
MAX_SEARCH = int(os.environ.get("MAX_SEARCH", "10"))
MAX_READ = int(os.environ.get("MAX_READ", "8"))
CACHE = os.environ.get("CACHE_DIR", "/cache")
LOG = os.environ.get("LOG", "/logs/arxiv.jsonl")
CHUNK = 8000
os.makedirs(CACHE, exist_ok=True)
NS = {"a": "http://www.w3.org/2005/Atom"}
_last = [0.0]
_count = {"search": 0, "read": 0}
mcp = FastMCP("arxiv", host="0.0.0.0", port=8000)


def _log(rec):
    with open(LOG, "a") as f:
        f.write(json.dumps({"ts": time.time(), **rec}, ensure_ascii=False) + "\n")


def _get(url):
    key = os.path.join(CACHE, hashlib.sha256(url.encode()).hexdigest()[:24])
    if os.path.exists(key):
        return open(key, encoding="utf-8").read()
    wait = 3.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": "harness-core-eval/0.1 (research benchmark)"})
    data = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    _last[0] = time.time()
    open(key, "w", encoding="utf-8").write(data)
    return data


def _entries(xml_text):
    out = []
    for e in ET.fromstring(xml_text).findall("a:entry", NS):
        pid = e.findtext("a:id", "", NS).rsplit("/abs/", 1)[-1]
        out.append({"id": pid, "title": " ".join(e.findtext("a:title", "", NS).split()),
                    "submitted": e.findtext("a:published", "", NS)[:10],
                    "abstract": " ".join(e.findtext("a:summary", "", NS).split())[:1200]})
    return out


@mcp.tool()
def arxiv_search(query: str, max_results: int = 5) -> str:
    """Search arXiv papers (title/abstract). Only papers submitted before the competition start are visible."""
    if _count["search"] >= MAX_SEARCH:
        return f"search budget exhausted ({MAX_SEARCH} searches per run)"
    _count["search"] += 1
    end = CUTOFF.replace("-", "") + "2359"
    q = f"({query}) AND submittedDate:[199107010000 TO {end}]"
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "start": 0, "max_results": max(1, min(int(max_results), 10)), "sortBy": "relevance"})
    try:
        res = [r for r in _entries(_get(url)) if r["submitted"] <= CUTOFF]   # belt and braces
    except Exception as e:
        res, err = [], str(e)[:200]
        _log({"tool": "search", "query": query, "error": err})
        return f"search failed: {err}"
    _log({"tool": "search", "query": query, "n": len(res), "ids": [r["id"] for r in res]})
    return json.dumps(res, ensure_ascii=False)


@mcp.tool()
def arxiv_read(paper_id: str, start: int = 0) -> str:
    """Read up to 8000 characters of a paper's text starting at `start` (use next_start to continue)."""
    pid = re.sub(r"v\d+$", "", paper_id.strip().replace("arXiv:", ""))
    meta = _entries(_get("http://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": pid})))
    if not meta or meta[0]["submitted"] > CUTOFF:
        _log({"tool": "read", "id": pid, "refused": True})
        return "not available (unknown id or submitted after the cut-off date)"
    if start == 0:
        if _count["read"] >= MAX_READ:
            return f"read budget exhausted ({MAX_READ} papers per run)"
        _count["read"] += 1
    text = None
    for url in (f"https://arxiv.org/html/{pid}", f"https://ar5iv.labs.arxiv.org/html/{pid}"):
        try:
            raw = _get(url)
            body = re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", raw)
            text = html.unescape(re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", body))).strip()
            if len(text) > 2000:
                break
        except Exception:
            continue
    if not text:
        text = meta[0]["abstract"]
    chunk = text[start:start + CHUNK]
    _log({"tool": "read", "id": pid, "start": start, "chars": len(chunk)})
    nxt = start + CHUNK if start + CHUNK < len(text) else None
    return json.dumps({"id": pid, "title": meta[0]["title"], "total_chars": len(text), "next_start": nxt,
                       "text": chunk}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

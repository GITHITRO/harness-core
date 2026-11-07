#!/usr/bin/env bash
# One unit = one arm on one competition, in a network sandbox.
#   run_arm.sh <arm: base|harness> <data_dir> <out_dir> <minutes> <max_calls> <cutoff YYYY-MM-DD> <bench_tag>
# Containers on an internal network (no route outside):
#   agent  : OpenCode + ML stack, /data read-only, /work writable — no internet
#   pacer  : the only way to the model (Kilo), per-run call cap, full logs     (also on the egress network)
#   arxiv  : the only way to arXiv, date cut-off enforced, cached              (also on the egress network)
# The Kaggle credential never enters any container; submission happens on the host afterwards.
set -euo pipefail
ARM=$1; DATA=$2; OUT=$3; MIN=$4; CALLS=$5; CUTOFF=$6; TAG=$7
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
ID="u$$"; NET="sb_$ID"; WORK="$OUT/work"; LOGS="$OUT/logs"
mkdir -p "$WORK" "$LOGS" "$OUT/cache" && chmod -R 777 "$WORK" "$LOGS" "$OUT/cache"
MODEL="${MODEL:-nvidia/nemotron-3.5-super-vl:free}"
cleanup() { docker rm -f "agent_$ID" "pacer_$ID" "arxiv_$ID" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker network create --internal "$NET" >/dev/null

docker run -d --name "pacer_$ID" --network bridge -v "$KEYFILE:/run/key:ro" -v "$LOGS:/logs" \
  -e UPSTREAM_KEY_FILE=/run/key -e HOST=0.0.0.0 -e BUDGET="${BUDGET:-170}" -e MAX_CALLS="$CALLS" \
  -e STATE_FILE=/logs/pacer_state.json -e LOG_DIR=/logs -e LANE=kaggle hc-tools python3 -I pacer.py >/dev/null
docker network connect --alias pacer "$NET" "pacer_$ID"
docker run -d --name "arxiv_$ID" --network bridge -v "$OUT/cache:/cache" -v "$LOGS:/logs" \
  -e CUTOFF="$CUTOFF" -e MAX_SEARCH=10 -e MAX_READ=8 -e CACHE_DIR=/cache -e LOG=/logs/arxiv.jsonl hc-tools python3 -I arxiv_mcp.py >/dev/null
docker network connect --alias arxiv "$NET" "arxiv_$ID"

AGENT=build
if [ "$ARM" = harness ]; then bash "$ROOT/opencode/install.sh" "$WORK" >/dev/null; AGENT=core; fi
cat > "$OUT/opencode.json" <<EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "autoupdate": false, "share": "disabled",
  "provider": {"kilo": {"npm": "@ai-sdk/openai-compatible", "name": "Kilo via pacer",
    "options": {"baseURL": "http://pacer:8787/b/$TAG/a/$ARM/v1", "apiKey": "via-pacer"},
    "models": {"$MODEL": {"name": "nemotron", "tool_call": true}}}},
  "model": "kilo/$MODEL", "small_model": "kilo/$MODEL",
  "mcp": {"arxiv": {"type": "remote", "url": "http://arxiv:8000/mcp", "enabled": true}},
  "permission": {"webfetch": "deny", "websearch": "deny", "external_directory": "allow"}
}
EOF
sleep 3
set +e
docker run --name "agent_$ID" --network "$NET" --cpus 4 --memory 14g \
  -v "$DATA:/data:ro" -v "$WORK:/work" -v "$OUT/opencode.json:/home/agent/.config/opencode/opencode.json:ro" \
  hc-agent bash -c "timeout ${MIN}m opencode run --print-logs --log-level WARN --agent $AGENT \"\$(cat /data/TASK.md)\" > /work/.run.out 2>&1; echo \$? > /work/.rc;
    SID=\$(opencode session list 2>/dev/null | grep -o 'ses_[A-Za-z0-9]*' | head -1); [ -n \"\$SID\" ] && opencode export \$SID > /work/.session.json 2>/dev/null; true"
set -e
cp "$WORK/.run.out" "$LOGS/opencode.out" 2>/dev/null || true
cp "$WORK/.session.json" "$LOGS/session.json" 2>/dev/null || true
[ -d "$WORK/.harness" ] && cp -r "$WORK/.harness" "$LOGS/harness_state" || true
curl -s --max-time 5 "http://$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "pacer_$ID" | awk '{print $1}'):8787/stats" > "$LOGS/pacer_stats.json" || true
echo "rc=$(cat "$WORK/.rc" 2>/dev/null || echo none) submission=$([ -f "$WORK/submission.csv" ] && echo yes || echo no)"

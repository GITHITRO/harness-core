#!/usr/bin/env bash
# Install harness-core into an OpenCode project (default) or globally.
#   ./install.sh [PROJECT_DIR]        -> PROJECT_DIR/.opencode/{agents,commands,skills,plugins} + PROJECT_DIR/.harness/
#   ./install.sh --global             -> ~/.config/opencode/...   (gates still apply only to sessions of agent `core`)
#   ./install.sh --uninstall [DIR|--global]
# Idempotent. Never overwrites files it did not install (refuses unless --force).
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE=project; TARGET="."; FORCE=0; UNINSTALL=0
for a in "$@"; do
  case "$a" in
    --global) MODE=global ;;
    --force) FORCE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n 2,7p "$0"; exit 0 ;;
    *) TARGET="$a" ;;
  esac
done
if [ "$MODE" = global ]; then OC="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"; PROJ=""; else
  PROJ="$(cd "$TARGET" && pwd)"; OC="$PROJ/.opencode"; fi

FILES=(agents/core.md agents/hc-scout.md agents/hc-redteam.md agents/hc-verifier.md
       commands/hc-intent.md commands/hc-probe.md commands/hc-verify.md commands/hc-aar.md
       skills/hc-elicitation/SKILL.md skills/hc-decision/SKILL.md skills/hc-architecture/SKILL.md
       skills/hc-verification/SKILL.md skills/hc-aar/SKILL.md plugins/harness-core.js)
MANIFEST="$OC/.harness-core.manifest"

if [ "$UNINSTALL" = 1 ]; then
  [ -f "$MANIFEST" ] || { echo "nothing to uninstall in $OC"; exit 0; }
  while read -r f; do rm -f "$OC/$f"; rmdir "$(dirname "$OC/$f")" 2>/dev/null || true; done < "$MANIFEST"
  rm -f "$MANIFEST"; echo "harness-core removed from $OC (.harness/ state kept)"; exit 0
fi

for f in "${FILES[@]}"; do
  dst="$OC/$f"
  if [ -e "$dst" ] && [ "$FORCE" = 0 ] && ! { [ -f "$MANIFEST" ] && grep -qx "$f" "$MANIFEST"; }; then
    echo "refusing to overwrite $dst (not installed by harness-core); use --force"; exit 1
  fi
done
for f in "${FILES[@]}"; do mkdir -p "$(dirname "$OC/$f")"; cp "$SRC/$f" "$OC/$f"; done
printf '%s\n' "${FILES[@]}" > "$MANIFEST"

if [ -n "$PROJ" ]; then
  mkdir -p "$PROJ/.harness"
  [ -f "$PROJ/.harness/config.json" ] || printf '{"gate": "on", "apply_to": "core"}\n' > "$PROJ/.harness/config.json"
  [ -f "$PROJ/.harness/approved-commands.txt" ] || printf '' > "$PROJ/.harness/approved-commands.txt"
fi
echo "harness-core $(grep -o 'oc-[0-9.]*' "$SRC/plugins/harness-core.js" | head -1) installed into $OC"
echo "next: open opencode in the project, switch to agent 'core' (Tab), check .harness/journal.jsonl has 'plugin_loaded'"

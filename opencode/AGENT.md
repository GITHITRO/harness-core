# Instructions for an AI agent: install harness-core into this OpenCode project

Do exactly these steps in order. After each step run its check. If a check fails, stop and report the step number,
the command and its output. Do not modify anything outside the paths listed here.

1. **Fetch the package** (skip if `/tmp/harness-core/opencode/install.sh` exists):
   `git clone --depth 1 https://github.com/GITHITRO/harness-core /tmp/harness-core`
   Check: `test -f /tmp/harness-core/opencode/install.sh && echo ok` → `ok`.
2. **Install into the project root** (the directory where `opencode` is started; use its absolute path):
   `bash /tmp/harness-core/opencode/install.sh "$PWD"`
   Check: the output ends with `installed into <path>/.opencode`. If it says `refusing to overwrite`, stop and report
   the file — do not use `--force` without the user's permission.
3. **Agents are visible**: `opencode agent list`
   Check: the output contains `core (primary)`, `hc-redteam (subagent)`, `hc-scout (subagent)`, `hc-verifier (subagent)`.
4. **Plugin loads**: `opencode run --agent core "Reply with the word ready."` then
   `grep -c plugin_loaded .harness/journal.jsonl` → at least `1`, and
   `grep '"ev":"message"' .harness/journal.jsonl | tail -1` contains `"agent":"core"`.
   If `plugin_loaded` is present but no message with `"agent":"core"` appears, report "OpenCode version without
   chat.message agent field" together with `opencode --version`.
5. **Gate works**: `ls .harness/intent.md 2>/dev/null || echo "no intent yet"` → `no intent yet` is expected on a
   fresh install (the first edit by `core` will be blocked until the agent writes it — this is intended).
6. **Report** to the user: OpenCode version, installed path, checks 1–5 passed, and how to use it:
   Tab to agent `core`, then the task or `/goal <objective>`; turn gates off with `HARNESS_CORE=off`.

Uninstall: `bash /tmp/harness-core/opencode/install.sh --uninstall "$PWD"` (keeps `.harness/`).

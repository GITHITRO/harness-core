# harness-core for OpenCode — install instructions (for a human or an AI agent)

You are installing **harness-core** into an OpenCode project. Follow the steps exactly; stop and report if a check fails.

## What gets installed
| Path (in the project) | What |
|---|---|
| `.opencode/agents/core.md` | primary agent `core`: the core loop (profile → intent → probe → decide → act → verify → AAR) |
| `.opencode/agents/hc-scout.md`, `hc-redteam.md`, `hc-verifier.md` | read-only subagents (search, premortem, verification) |
| `.opencode/skills/hc-*/SKILL.md` | method cards loaded on demand: elicitation, decision, architecture, verification, AAR |
| `.opencode/commands/hc-*.md` | `/hc-intent`, `/hc-probe`, `/hc-verify`, `/hc-aar` |
| `.opencode/plugins/harness-core.js` | code-enforced gates + journal (see below) |
| `.harness/` | working state: `config.json`, `approved-commands.txt` (human-only), later `intent.md`, `world.md`, `decisions.md`, `evidence.md`, `aar.md`, `journal.jsonl` |

Nothing outside these paths is touched. The default agents (`build`, `plan`) are unchanged and ungated.

## Steps
1. Get the package (any one):
   `git clone --depth 1 https://github.com/GITHITRO/harness-core /tmp/harness-core`
2. Install into the project root (the directory where you run `opencode`):
   `bash /tmp/harness-core/opencode/install.sh /path/to/project`
   It refuses to overwrite files it did not install; `--force` overrides, `--uninstall` removes, `--global` installs
   into `~/.config/opencode/` instead.
3. Check that OpenCode sees it:
   `cd /path/to/project && opencode agent list` → must list `core (primary)`, `hc-redteam`, `hc-scout`, `hc-verifier`.
4. Check the plugin is loaded: start opencode once, then
   `grep plugin_loaded .harness/journal.jsonl` → must print a line with `"v":"oc-0.1.0"`.
5. Optional: add `.harness/journal.jsonl` to `.gitignore` if the project is shared; keep the rest of `.harness/`
   if you want the decisions and evidence in history.

## Use
- In the TUI press **Tab** until the agent is `core`, then give the task, or `/goal <objective>` (OpenCode ≥ 2.2.1).
- First edits to project files are blocked until `.harness/intent.md` has an **Acceptance criteria** section —
  this is intended: the agent writes the contract first.
- Destructive shell commands (`rm -rf`, `git push --force`, `git reset --hard`, `terraform apply`, `DROP TABLE`, …)
  are blocked until the human adds the exact command line to `.harness/approved-commands.txt`. Agents cannot edit
  that file.
- Turn gates off for one run: `HARNESS_CORE=off opencode`, or `{"gate":"off"}` in `.harness/config.json`.

## What the plugin enforces (not just asks)
1. Intent gate for agent `core`.
2. Read-only subagents: edits denied; shell commands that write are denied.
3. One-way doors need a human-approved line.
4. Sticky contract: `intent.md` and the open (FAIL/UNVERIFIED) criteria are injected into every `core` turn and into
   compaction, so long `/goal` runs keep them.
5. Journal of every tool call, message and session event in `.harness/journal.jsonl`.

Compatibility: written against the OpenCode plugin API (`@opencode-ai/plugin` hooks `tool.execute.before/after`,
`chat.message`, `experimental.chat.system.transform`, `experimental.session.compacting`, `event`); tested on
OpenCode 1.19.5. The two `experimental.*` hooks may change between versions — if they are missing, gates and the
journal still work, only the sticky contract is lost.

// harness-core plugin for OpenCode: the parts of the core that code enforces instead of the prompt.
//
// 1. Intent gate     — the `core` agent cannot edit project files until .harness/intent.md has acceptance criteria.
// 2. Read-only roles — hc-scout / hc-redteam / hc-verifier cannot edit, and their shell commands cannot write.
// 3. One-way doors   — destructive shell commands need a line in .harness/approved-commands.txt, which only a human
//                      may edit (agents are blocked from touching it).
// 4. Sticky contract — intent + open criteria are injected into the system prompt of every `core` turn and into
//                      compaction, so a long /goal run cannot lose them (the tau2 stand showed agents forget reviews).
// 5. Journal         — every tool call, message and session event goes to .harness/journal.jsonl for the AAR and
//                      for base-vs-harness analysis.
//
// Config: .harness/config.json  {"gate": "on"|"off", "apply_to": "core"|"all"}. Env HARNESS_CORE=off disables gates.
import fs from "node:fs"
import path from "node:path"

const VERSION = "oc-0.1.0"
const EDIT_TOOLS = new Set(["edit", "write", "apply_patch", "patch", "multiedit"])
const READONLY_AGENTS = new Set(["hc-scout", "hc-redteam", "hc-verifier"])
const SHELL_WRITE_RE = /(^|[;&|]\s*)(rm|mv|cp|mkdir|touch|tee|truncate|chmod|chown|ln|dd)\b|(?<![0-9&>])>>?\s*(?!&|\/dev\/null)\S|\bsed\s+-i\b|\bgit\s+(commit|push|reset|checkout|merge|rebase|stash|clean|apply|am|tag)\b|\bnpm\s+(i|install|publish)\b|\bpip\s+install\b/
const DESTRUCTIVE_RE = /\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r|\bgit\s+push\b.*(--force|-f\b)|\bgit\s+reset\s+--hard|\bgit\s+clean\s+-[a-zA-Z]*f|\bdrop\s+(table|database|schema)\b|\btruncate\s+table\b|\bkubectl\s+delete\b|\bterraform\s+(apply|destroy)\b|\bmkfs\b|\bdd\s+if=|\bnpm\s+publish\b|\bdocker\s+system\s+prune\b/i
const APPROVALS = "approved-commands.txt"

export const HarnessCore = async ({ directory, worktree }) => {
  const root = worktree || directory
  const H = path.join(root, ".harness")
  fs.mkdirSync(H, { recursive: true })
  const agentOf = new Map()

  const cfg = () => {
    let c = { gate: "on", apply_to: "core" }
    try { c = { ...c, ...JSON.parse(fs.readFileSync(path.join(H, "config.json"), "utf8")) } } catch {}
    if ((process.env.HARNESS_CORE || "").toLowerCase() === "off") c.gate = "off"
    return c
  }
  const read = (name, max = 4000) => {
    try { const t = fs.readFileSync(path.join(H, name), "utf8"); return t.length > max ? t.slice(0, max) + "\n…[cut]" : t } catch { return "" }
  }
  const journal = (rec) => {
    try { fs.appendFileSync(path.join(H, "journal.jsonl"), JSON.stringify({ ts: new Date().toISOString(), v: VERSION, ...rec }) + "\n") } catch {}
  }
  const isCore = (sid) => {
    const a = agentOf.get(sid)
    return cfg().apply_to === "all" ? !READONLY_AGENTS.has(a) : a === "core"
  }
  const intentReady = () => {
    const t = read("intent.md", 100000)
    const m = t.match(/acceptance criteria[^\n]*\n([\s\S]*?)(\n#{1,3}\s|$)/i)
    return !!(m && /^\s*([-*]|\d+\.|\|)\s*\S/m.test(m[1]))
  }
  const inHarness = (p) => {
    if (!p) return false
    const abs = path.resolve(root, String(p))
    return abs === H || abs.startsWith(H + path.sep)
  }
  const touchesApprovals = (p) => String(p || "").includes(APPROVALS)
  const editTargets = (tool, args = {}) => {
    if (tool === "apply_patch" || tool === "patch") {
      const text = String(args.patchText || args.patch || args.input || "")
      return [...text.matchAll(/^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm)].map((m) => m[1].trim())
    }
    const p = args.filePath || args.file_path || args.path
    return p ? [p] : []
  }
  const approved = (cmd) => read(APPROVALS, 100000).split("\n").map((s) => s.trim()).filter(Boolean).includes(cmd.trim())
  const openItems = () => read("evidence.md", 100000).split("\n").filter((l) => /\b(FAIL|UNVERIFIED)\b/.test(l)).slice(0, 15).join("\n")

  journal({ ev: "plugin_loaded", root, config: cfg() })

  return {
    "chat.message": async (input) => {
      if (input.agent) agentOf.set(input.sessionID, input.agent)
      journal({ ev: "message", session: input.sessionID, agent: input.agent, model: input.model?.modelID })
    },

    "experimental.chat.system.transform": async (input, output) => {
      if (!input.sessionID || !isCore(input.sessionID)) return
      const intent = read("intent.md")
      if (!intent) return
      const open = openItems()
      output.system.push(
        "<harness_state>\nCurrent .harness/intent.md (the contract every step inherits):\n" + intent +
        (open ? "\n\nOpen criteria in .harness/evidence.md (not done until PASS with evidence):\n" + open : "") +
        "\n</harness_state>")
    },

    "experimental.session.compacting": async (input, output) => {
      const intent = read("intent.md")
      if (!intent) return
      output.context.push("Keep verbatim the task contract from .harness/intent.md and the open criteria:\n" + intent + "\n" + openItems())
      journal({ ev: "compacting", session: input.sessionID })
    },

    "tool.execute.before": async (input, output) => {
      const c = cfg()
      const agent = agentOf.get(input.sessionID)
      const args = output.args || {}
      const deny = (why) => {
        journal({ ev: "gate_block", session: input.sessionID, agent, tool: input.tool, why })
        throw new Error(`[harness-core] ${why}`)
      }
      if (EDIT_TOOLS.has(input.tool)) {
        const targets = editTargets(input.tool, args)
        if (targets.some(touchesApprovals)) deny(`${APPROVALS} is maintained by the human only.`)
        if (READONLY_AGENTS.has(agent)) deny(`${agent} is read-only; report findings instead of editing.`)
        if (c.gate !== "off" && isCore(input.sessionID) && targets.some((t) => !inHarness(t)) && !intentReady())
          deny("intent gate: write .harness/intent.md with an 'Acceptance criteria' section (observable checks) before changing project files. Use /hc-intent or stage 1 of your protocol.")
      }
      if (input.tool === "bash") {
        const cmd = String(args.command || "")
        if (cmd.includes(APPROVALS)) deny(`${APPROVALS} is maintained by the human only.`)
        if (READONLY_AGENTS.has(agent) && SHELL_WRITE_RE.test(cmd)) deny(`${agent} is read-only; this command would change state: ${cmd.slice(0, 120)}`)
        if (c.gate !== "off" && isCore(input.sessionID) && DESTRUCTIVE_RE.test(cmd) && !approved(cmd))
          deny(`one-way door: "${cmd.slice(0, 160)}" needs human approval. Ask the user to add this exact command as a line to .harness/${APPROVALS}, or find a reversible alternative.`)
      }
    },

    "tool.execute.after": async (input, output) => {
      const a = input.args || {}
      const brief = a.command ? { command: String(a.command).slice(0, 300) } : { target: editTargets(input.tool, a).join(", ") || a.pattern || a.url || a.filePath || undefined }
      journal({ ev: "tool", session: input.sessionID, agent: agentOf.get(input.sessionID), tool: input.tool, ...brief,
        title: output?.title, out_chars: (output?.output || "").length })
    },

    event: async ({ event }) => {
      if (["session.idle", "session.error", "session.compacted", "todo.updated", "session.created"].includes(event?.type))
        journal({ ev: event.type, props: JSON.stringify(event.properties || {}).slice(0, 400) })
    },
  }
}

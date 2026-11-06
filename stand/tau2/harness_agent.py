"""Harness arm for tau2-bench: the core's task loop squeezed into a customer-service agent.

Same model, same tools, same policy as the stock llm_agent. Differences:

1. Operating protocol (no extra calls): intent -> facts via read tools -> policy preconditions -> explicit
   user confirmation -> one state-changing action -> check its result -> close only when the goal is met.
2. Gate on side effects (extra calls only when they matter): before any WRITE tool call (or a transfer to a
   human) leaves the agent, a reviewer call checks it against the policy and the transcript:
   APPROVE / REJECT: <reason>. On REJECT the step is rolled back and regenerated with the reason in the
   system prompt (not in the visible history). At most MAX_GATE_ROUNDS reviews per step; after that the
   last candidate goes through, so the arm can never stall.
3. Fast path: plain messages and READ tool calls pass with zero overhead.
4. Sticky reviews (h2): a REJECT stays in the system prompt on every later turn until an action of the same
   tool is approved, so the agent cannot lose the reviewer's to-do list after one regeneration.
   (h1 kept it for one regeneration only; calib task 1 failed exactly there.)

Registered as agent "harness_agent" by stand/tau2/launch.py.
"""
import json

from loguru import logger

from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT, LLMAgent
from tau2.data_model.message import (
    AssistantMessage,
    MultiToolMessage,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from tau2.utils.llm_utils import generate

MAX_GATE_ROUNDS = 2

PROTOCOL = """
Operating protocol (follow it on every turn):
1. Intent: work out what the user ultimately needs; if it is unclear, ask one precise question.
2. Facts: before deciding, look the facts up with the read tools; never assume account data.
3. Preconditions: before any state-changing action, check every condition the policy sets for it.
4. Consent: describe the exact action and get the user's explicit yes before performing it, when the policy requires it.
5. One action at a time; after it, read its result and confirm the effect before the next step.
6. Close only when the user's goal is actually met (or the policy says to stop or transfer).
""".strip()

GATE = """You review one action of a customer-service agent before it is executed.

<policy>
{policy}
</policy>

<transcript>
{transcript}
</transcript>

Proposed action: {action}

Check: (a) the policy allows this action for this user now, and all its preconditions were verified with tools;
(b) arguments come from tool outputs or the user, not guesses; (c) the user explicitly agreed if the policy
requires consent; (d) it serves what the user asked for.
Answer with one line: APPROVE, or REJECT: <the specific problem and what to do instead>."""


def _render(messages, limit=40):
    lines = []
    for m in messages[-limit:]:
        if isinstance(m, ToolMessage):
            lines.append(f"[tool result] {(m.content or '')[:1200]}")
            continue
        role = getattr(m, "role", "?")
        if getattr(m, "content", None):
            lines.append(f"[{role}] {m.content[:1500]}")
        for tc in getattr(m, "tool_calls", None) or []:
            lines.append(f"[{role} tool call] {tc.name}({json.dumps(tc.arguments, ensure_ascii=False)})")
    return "\n".join(lines)


class HarnessAgent(LLMAgent):
    def __init__(self, tools, domain_policy, llm, llm_args=None):
        super().__init__(tools=tools, domain_policy=domain_policy, llm=llm, llm_args=llm_args)
        self._write_tools = set()
        for t in tools:
            kind = getattr(getattr(t, "_func", None), "__tool_type__", None)
            if kind is not None and str(getattr(kind, "value", kind)).lower() in ("write",):
                self._write_tools.add(t.name)
            if t.name.startswith("transfer_to_human"):
                self._write_tools.add(t.name)
        self.gate_log = []
        self.open_reviews = {}   # tool name -> latest reject reason

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(domain_policy=self.domain_policy,
                                    agent_instruction=AGENT_INSTRUCTION + "\n\n" + PROTOCOL)

    def _gated(self, msg):
        return [tc for tc in (msg.tool_calls or []) if tc.name in self._write_tools]

    def _review(self, history, msg):
        action = "; ".join(f"{tc.name}({json.dumps(tc.arguments, ensure_ascii=False)})" for tc in self._gated(msg))
        prompt = GATE.format(policy=self.domain_policy, transcript=_render(history), action=action)
        verdict = generate(model=self.llm, messages=[UserMessage(role="user", content=prompt)],
                           call_name="harness_gate", **self.llm_args)
        text = (verdict.content or "").strip()
        line = next((l.strip() for l in text.splitlines()[::-1] if l.strip().startswith(("APPROVE", "REJECT"))),
                    text[-300:])
        return (not line.startswith("REJECT")), line, action

    def _generate_next_message(self, message, state):
        if isinstance(message, UserMessage) and message.is_audio:
            raise ValueError("audio not supported")
        if isinstance(message, MultiToolMessage):
            state.messages.extend(message.tool_messages)
        else:
            state.messages.append(message)
        system = self._system_with_reviews(state)
        for rnd in range(MAX_GATE_ROUNDS + 1):
            candidate = generate(model=self.llm, tools=self.tools, messages=system + state.messages,
                                 call_name="agent_response", **self.llm_args)
            if not self._gated(candidate) or rnd == MAX_GATE_ROUNDS:
                return candidate
            ok, line, action = self._review(state.messages, candidate)
            self.gate_log.append({"round": rnd, "action": action, "verdict": line[:300]})
            logger.info(f"harness gate round={rnd} action={action[:120]} verdict={line[:160]}")
            names = {tc.name for tc in self._gated(candidate)}
            if ok:
                for n in names:
                    self.open_reviews.pop(n, None)
                return candidate
            for n in names:
                self.open_reviews[n] = f"{action}: {line[6:].strip(' :')}"
            system = self._system_with_reviews(state)
        return candidate

    def _system_with_reviews(self, state):
        if not self.open_reviews:
            return state.system_messages
        notes = "\n".join(f"- {v}" for v in list(self.open_reviews.values())[-3:])
        extra = ("\n\n<open_reviews>A reviewer blocked these actions. Address every point (do the missing steps "
                 "with the user/tools) before proposing them again:\n" + notes + "\n</open_reviews>")
        return [SystemMessage(role="system", content=state.system_messages[0].content + extra)]


def create_harness_agent(tools, domain_policy, **kwargs):
    return HarnessAgent(tools=tools, domain_policy=domain_policy, llm=kwargs.get("llm"),
                        llm_args=kwargs.get("llm_args") or {})

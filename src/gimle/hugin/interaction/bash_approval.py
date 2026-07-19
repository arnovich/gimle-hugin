"""``BashApproval`` — park a bash command on a human approval, then run or refuse.

When ``bash`` hits an ``on_violation: ask_human`` policy escalation in an
interactive session, it returns
``ToolResponse(response_interaction=BashApproval(...))``. The branch parks
(``step`` returns ``False``, like ``AskHuman``) until a human sets ``decision``.
On **approve** the *exact stored command* is run — the escalation treated as an
allow for that one invocation only, never a durable "allow this binary" — and its
result is delivered as a ``tool_result`` bound to the model's original ``bash``
call. On **deny** the command is refused.

Approval directly gates execution: the model cannot bypass it and does not
re-issue anything. Binding the result to the original ``tool_call_id`` is
branch-filtered (a flat cross-branch scan could mis-bind a sibling's call — an
Anthropic 400), and the resolve is fully guarded (an exception escaping here
would leave the stack's step-lock held and kill the agent), mirroring
``BashWaiting`` (task 027).
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.utils.uuid import with_uuid

logger = logging.getLogger(__name__)

_AFFIRMATIVE = {"approve", "approved", "yes", "y", "ok", "allow"}


@Interaction.register()
@dataclass
@with_uuid
class BashApproval(Interaction):
    """Wait for a human to approve/deny a bash command, then run or refuse it.

    Attributes:
        command: The exact shell command awaiting approval.
        cwd: The workspace-relative cwd the command was requested in.
        timeout_s: The requested per-command timeout, if any.
        reason: Why the policy flagged the command (shown to the human).
        decision: ``None`` while pending; set by a human to approve/deny.
    """

    command: Optional[str] = None
    cwd: Optional[str] = None
    timeout_s: Optional[int] = None
    reason: Optional[str] = None
    decision: Optional[str] = None

    def step(self) -> bool:
        """Park until a decision is set, then run (approve) or refuse (deny)."""
        if self.decision is None:
            return False  # awaiting a human decision

        content, is_error = self._resolve()
        self.stack.add_interaction(
            AskOracle(
                stack=self.stack,
                branch=self.branch,
                prompt=self._result_prompt(),
                template_inputs={**content, "is_error": is_error},
            )
        )
        return True

    def approved(self) -> bool:
        """Whether the human's decision is affirmative."""
        return str(self.decision or "").strip().lower() in _AFFIRMATIVE

    def _resolve(self) -> Tuple[Dict[str, Any], bool]:
        """Run the approved command or render the human's refusal (never raises)."""
        if not self.approved():
            return (
                {
                    "denied": f"denied by a human: {self.reason}",
                    "command": self.command,
                    "note": "a human refused this command; do not retry it — "
                    "choose a different approach",
                },
                True,
            )
        try:
            from gimle.hugin.tools.builtins.bash import run_approved

            response = run_approved(
                self.stack,
                self.command or "",
                self.cwd,
                self.timeout_s,
                self.branch,
            )
            return dict(response.content), bool(response.is_error)
        except Exception as error:  # never wedge the stack
            logger.warning("approved bash run failed: %s", error)
            return (
                {"infra_error": str(error), "command": self.command},
                True,
            )

    def _result_prompt(self) -> Prompt:
        """Build a tool_result prompt bound to THIS branch's originating call.

        Branch-filtered (a flat cross-branch scan could bind a sibling branch's
        ToolCall, whose id is absent from this branch's context — an Anthropic
        400). Falls back to text if no id is recoverable. Mirrors
        ``BashWaiting._result_prompt``.
        """
        from gimle.hugin.interaction.tool_call import ToolCall

        tool_call = None
        for interaction in reversed(self.stack.interactions):
            if interaction.branch == self.branch and isinstance(
                interaction, ToolCall
            ):
                tool_call = interaction
                break
        if tool_call is None or tool_call.tool_call_id is None:
            return Prompt(type="text")
        return Prompt(
            type="tool_result",
            tool_name=tool_call.tool,
            tool_use_id=tool_call.tool_call_id,
        )

"""``BashWaiting`` — park a branch on a background bash command, then resolve it.

When ``bash`` (auto-deferred) or ``bash_output`` finds its command still
running, it returns ``ToolResponse(response_interaction=BashWaiting(job_id))``.
On each session tick the (scheduler-thread) ``step`` polls the job:

- still running → return ``True`` so the round-robin loop stays alive and
  **siblings run**, while this branch does no work;
- finished (or unknown — a job lost to a session restart) → collect the result
  and resolve into a real ``tool_result`` bound to the model's **original**
  ``bash``/``bash_output`` ``tool_call_id`` (the ``AgentResult`` pattern).

Resolving via a proper ``tool_result`` — not a ``next_tool`` chain — is
load-bearing: a chained ``ToolCall`` carries ``tool_call_id=None``, which renders
as a plain-text message and leaves the model's original ``tool_use`` block
unpaired (an Anthropic 400). The collect is fully guarded (it never raises),
because an exception escaping a tool leaves the stack's step-lock held and kills
the agent for the rest of the session.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.sandbox.background import BackgroundExecutor

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class BashWaiting(Interaction):
    """Wait for a background bash job, then deliver its result as a tool_result.

    Attributes:
        job_id: The id of the background job this branch is parked on.
    """

    job_id: Optional[str] = None

    def step(self) -> bool:
        """Poll the job; keep waiting or resolve into a tool_result."""
        background = getattr(self.stack.agent.session, "background", None)

        if (
            background is not None
            and self.job_id is not None
            and not background.is_done(self.job_id)
        ):
            return True  # still running: park, siblings run

        content, is_error = self._collect(background)
        tool_call = self.stack.get_last_tool_call_interaction()
        prompt = Prompt(
            type="tool_result",
            tool_name=tool_call.tool if tool_call else "bash",
            tool_use_id=tool_call.tool_call_id if tool_call else None,
        )
        self.stack.add_interaction(
            AskOracle(
                stack=self.stack,
                branch=self.branch,
                prompt=prompt,
                template_inputs={**content, "is_error": is_error},
            )
        )
        return True

    def _collect(
        self, background: Optional["BackgroundExecutor"]
    ) -> Tuple[Dict[str, Any], bool]:
        """Collect the finished job's result (never raises)."""
        if background is None or self.job_id is None:
            return (
                {
                    "infra_error": "background execution is unavailable",
                    "job_id": self.job_id,
                },
                True,
            )
        return background.collect(self.job_id, agent_id=self.stack.agent.id)

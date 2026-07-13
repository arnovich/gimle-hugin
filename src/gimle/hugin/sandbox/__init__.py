"""Sandbox subsystem: pluggable command execution with a policy guardrail.

The pieces are deliberately orthogonal (see ``tasks/open/023-bash-tool``):

- ``policy`` — a pure ``evaluate(command, policy) -> Decision`` guardrail
  against accidents. It is **not** a security boundary; the runtime you choose
  (container / disposable remote) is.
- ``sandbox`` — the ``Sandbox`` execution-backend protocol (``ExecResult``,
  ``SandboxSpec``) that concrete backends implement.

Backends and the tool that drives them land in later phases.
"""

from gimle.hugin.sandbox.local import LocalSandbox
from gimle.hugin.sandbox.policy import (
    Allow,
    Decision,
    Deny,
    Escalate,
    Policy,
    evaluate,
)
from gimle.hugin.sandbox.sandbox import (
    ExecResult,
    PolicyDenied,
    Sandbox,
    SandboxSpec,
)

__all__ = [
    "Allow",
    "Decision",
    "Deny",
    "Escalate",
    "ExecResult",
    "LocalSandbox",
    "Policy",
    "PolicyDenied",
    "Sandbox",
    "SandboxSpec",
    "evaluate",
]

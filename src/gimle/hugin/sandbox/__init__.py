"""Sandbox subsystem: pluggable command execution with a policy guardrail.

The pieces are deliberately orthogonal (see ``tasks/open/023-bash-tool``):

- ``policy`` — a pure ``evaluate(command, policy) -> Decision`` guardrail
  against accidents. It is **not** a security boundary; the runtime you choose
  (container / disposable remote) is.
- ``sandbox`` — the ``Sandbox`` execution-backend protocol (``ExecResult``,
  ``SandboxSpec``) that concrete backends implement.

Backends and the tool that drives them land in later phases.
"""

from gimle.hugin.sandbox.docker import DockerSandbox
from gimle.hugin.sandbox.fake import FakeSandbox
from gimle.hugin.sandbox.local import LocalSandbox
from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.policy import (
    Allow,
    Decision,
    Deny,
    Escalate,
    Policy,
    evaluate,
)
from gimle.hugin.sandbox.reaper import (
    WorkspaceInfo,
    list_local_workspaces,
    reap_local_workspaces,
)
from gimle.hugin.sandbox.sandbox import (
    ExecResult,
    PolicyDenied,
    Sandbox,
    SandboxSpec,
    create_sandbox,
)

__all__ = [
    "Allow",
    "Decision",
    "Deny",
    "DockerSandbox",
    "Escalate",
    "ExecResult",
    "FakeSandbox",
    "LocalSandbox",
    "Policy",
    "PolicyDenied",
    "Sandbox",
    "SandboxManager",
    "SandboxSpec",
    "WorkspaceInfo",
    "create_sandbox",
    "evaluate",
    "list_local_workspaces",
    "reap_local_workspaces",
]

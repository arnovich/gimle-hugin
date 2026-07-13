"""Pure command policy engine for the bash tool.

``evaluate(command, policy)`` parses a shell command with ``bashlex`` and
returns an :class:`Allow`, :class:`Deny`, or :class:`Escalate` decision. It has
no I/O and no dependency on any execution backend, so it is trivially testable.

The engine is a **guardrail against accidents, not a security boundary.** The
runtime you run commands in — a container, a disposable remote machine, or
(on the local backend) nothing — is the boundary. In the default ``denylist``
mode the engine is deliberately permissive: it blocks a blunt set of
catastrophic commands and dangerous environment assignments, but it does *not*
stop interpreter-based execution (``python3 -c ...``, ``awk 'BEGIN{system()}'``,
``git -c core.pager='!sh'``). Pretending a wordlist stops those would be
security theatre — the container does.

What the engine guarantees:

- **Fails closed:** a command ``bashlex`` cannot parse is denied, never allowed.
- **Walks the whole AST:** a denied binary hidden behind ``&&``/``|`` or inside
  ``$(...)`` is still found.
- **Rejects execution-hijacking assignments** (``LD_PRELOAD`` and friends) on
  every backend.
- **Opt-in strict mode** (``allow_shell_features=False``) additionally blocks
  the shell escape hatches (command/process substitution, ``eval``/``source``,
  interpreter ``-c``, and wrappers like ``timeout`` that run their argument).
"""

import logging
from dataclasses import dataclass, field, fields
from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple, Union

import bashlex

logger = logging.getLogger(__name__)


# --- decisions ---


@dataclass(frozen=True)
class Allow:
    """The command may run."""


@dataclass(frozen=True)
class Deny:
    """The command is refused; ``reason`` explains why (shown to the agent)."""

    reason: str


@dataclass(frozen=True)
class Escalate:
    """The command needs human approval; ``reason`` explains why."""

    reason: str


Decision = Union[Allow, Deny, Escalate]


# --- rule sets ---

# Binaries denied outright: destroying disks/filesystems or halting the host is
# never a legitimate agent action. Matched on the basename, so an absolute path
# like ``/sbin/reboot`` is caught too. ``mkfs*`` is handled separately.
DEFAULT_DENY: Tuple[str, ...] = (
    "dd",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init",
    "telinit",
    "fdisk",
    "parted",
    "mkswap",
)

# Recursive-remove targets treated as catastrophic. A relative target such as
# ``./build`` is intentionally NOT here — that's an ordinary (if regrettable)
# action, and over-blocking pushes users toward disabling the policy.
_DANGEROUS_RM_TARGETS = frozenset(
    {"/", "~", "~/", "/*", "*", "/.", "$HOME", "${HOME}"}
)

# Environment assignments that redirect execution into attacker-controlled code
# regardless of the (allowlisted) binary being run.
DANGEROUS_ASSIGNMENTS = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "BASH_ENV",
        "ENV",
        "IFS",
        "PROMPT_COMMAND",
        "PATH",
        "PYTHONSTARTUP",
        "PERL5OPT",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_EXTERNAL_DIFF",
        "GIT_PAGER",
    }
)

# Shell builtins that evaluate an arbitrary string as code.
_SHELL_ESCAPE_WORDS = frozenset({"eval", "source", "."})

# Interpreters whose ``-c``/``-e`` flag runs an arbitrary program.
_INTERPRETERS = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "python",
        "python2",
        "python3",
        "node",
        "ruby",
        "perl",
        "php",
    }
)

# Binaries that run their argument as a command, so a nested interpreter must be
# looked through in strict mode.
_WRAPPERS = frozenset(
    {
        "timeout",
        "env",
        "xargs",
        "nice",
        "ionice",
        "nohup",
        "setsid",
        "stdbuf",
        "command",
        "time",
        "chrt",
        "watch",
    }
)


# --- policy ---


@dataclass(frozen=True)
class Policy:
    """How a command is judged before it runs.

    Attributes:
        mode: ``denylist`` (default, permissive — block only the accident set),
            ``allowlist`` (only ``allow`` command words permitted), or
            ``unrestricted`` (no checks; still fails closed on a parse error).
        deny: Extra denied binary basenames, added to :data:`DEFAULT_DENY`.
        allow: Permitted command basenames, used only in ``allowlist`` mode.
        allow_shell_features: When ``False`` (opt-in strict mode) the shell
            escape hatches are refused. Default ``True`` — the runtime is the
            boundary, so the engine need not fight the shell.
        workspace_only: Confine filesystem access to the workspace. Enforced by
            the sandbox layer (realpath confinement), not this pure function.
        network: Whether the command may reach the network (advisory here;
            enforced by the backend).
        timeout_s: Interactive per-command timeout.
        max_timeout_s: Ceiling for an explicit longer timeout.
        max_output_bytes: Cap on captured output.
        on_violation: ``deny`` to refuse, or ``ask_human`` to escalate.
    """

    mode: Literal["denylist", "allowlist", "unrestricted"] = "denylist"
    deny: Tuple[str, ...] = DEFAULT_DENY
    allow: Tuple[str, ...] = field(default_factory=tuple)
    allow_shell_features: bool = True
    workspace_only: bool = True
    network: bool = False
    timeout_s: int = 15
    max_timeout_s: int = 600
    max_output_bytes: int = 16_000
    on_violation: Literal["deny", "ask_human"] = "deny"

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Policy":
        """Build a Policy from a config dict, failing loud on anything wrong.

        A security object must never silently fall back to a default because a
        key was misspelled, so unknown keys and invalid literals raise
        ``ValueError`` rather than being dropped. An empty/absent mapping yields
        the conservative defaults.
        """
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("policy must be a mapping")
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown policy keys: {sorted(unknown)}")
        kwargs = dict(data)
        mode = kwargs.get("mode")
        if mode is not None and mode not in (
            "denylist",
            "allowlist",
            "unrestricted",
        ):
            raise ValueError(f"invalid policy mode: {mode!r}")
        on_violation = kwargs.get("on_violation")
        if on_violation is not None and on_violation not in (
            "deny",
            "ask_human",
        ):
            raise ValueError(f"invalid on_violation: {on_violation!r}")
        for key in ("deny", "allow"):
            if key in kwargs:
                kwargs[key] = tuple(kwargs[key])
        return cls(**kwargs)


# --- AST helpers ---


@dataclass
class _CommandContext:
    """One ``command`` node reduced to the fields the rules care about."""

    word: Optional[str]  # command basename-bearing first word (raw)
    args: List[str]
    words: List[str]
    assignments: List[str]


def _is_node(value: Any) -> bool:
    return hasattr(value, "kind")


def _children(node: Any) -> Iterator[Any]:
    """Yield every child bashlex node, regardless of the attribute holding it."""
    for value in vars(node).values():
        if _is_node(value):
            yield value
        elif isinstance(value, (list, tuple)):
            for item in value:
                if _is_node(item):
                    yield item


def _command_context(node: Any) -> _CommandContext:
    words: List[str] = []
    assignments: List[str] = []
    for part in getattr(node, "parts", []):
        kind = getattr(part, "kind", None)
        if kind == "word":
            words.append(part.word)
        elif kind == "assignment":
            assignments.append(part.word)
    return _CommandContext(
        word=words[0] if words else None,
        args=words[1:],
        words=words,
        assignments=assignments,
    )


def _collect(node: Any, commands: List[_CommandContext], flags: dict) -> None:
    """Walk the tree, gathering command contexts and shell-feature flags."""
    kind = getattr(node, "kind", None)
    if kind == "command":
        commands.append(_command_context(node))
    elif kind == "commandsubstitution":
        flags["cmdsub"] = True
    elif kind == "processsubstitution":
        flags["procsub"] = True
    for child in _children(node):
        _collect(child, commands, flags)


def _base(word: str) -> str:
    """Return the basename of a command word (``/sbin/reboot`` -> ``reboot``)."""
    return word.rsplit("/", 1)[-1]


def _short_flag_letters(args: List[str]) -> str:
    """All letters from clustered short flags, e.g. ``-rf`` -> ``rf``."""
    letters = ""
    for arg in args:
        if arg.startswith("-") and not arg.startswith("--"):
            letters += arg[1:]
    return letters.lower()


def _is_dangerous_rm(args: List[str]) -> bool:
    letters = _short_flag_letters(args)
    long_flags = {a for a in args if a.startswith("--")}
    recursive = "r" in letters or "--recursive" in long_flags
    force = "f" in letters or "--force" in long_flags
    if not (recursive and force):
        return False
    targets = [a for a in args if not a.startswith("-")]
    return any(t in _DANGEROUS_RM_TARGETS for t in targets)


def _is_force_push(args: List[str]) -> bool:
    if "push" not in args:
        return False
    return any(a in ("--force", "-f", "--force-with-lease") for a in args)


def _is_recursive_chmod_777(args: List[str]) -> bool:
    letters = _short_flag_letters(args)
    recursive = "r" in letters or "--recursive" in args
    return recursive and any("777" in a for a in args)


def _has_interpreter_dash_c(ctx: _CommandContext) -> bool:
    if "-c" not in ctx.args and "-e" not in ctx.args:
        return False
    return any(_base(w) in _INTERPRETERS for w in ctx.words)


# --- evaluation ---


def _violation(policy: Policy, reason: str) -> Decision:
    if policy.on_violation == "ask_human":
        return Escalate(reason)
    return Deny(reason)


def _parse(command: str) -> Optional[List[Any]]:
    """Parse ``command``; return ``None`` if bashlex cannot (fail closed)."""
    try:
        return list(bashlex.parse(command))
    except Exception as error:  # bashlex raises several ParsingError subtypes
        logger.debug("bashlex could not parse %r: %s", command, error)
        return None


def evaluate(command: str, policy: Policy) -> Decision:
    """Judge ``command`` against ``policy``.

    Returns :class:`Allow`, :class:`Deny`, or :class:`Escalate`. A command that
    cannot be parsed is always denied (never escalated) — you cannot ask a
    human to approve something you could not read.
    """
    trees = _parse(command)
    if trees is None:
        return Deny("could not parse command; failing closed")

    if policy.mode == "unrestricted":
        return Allow()

    commands: List[_CommandContext] = []
    flags = {"cmdsub": False, "procsub": False}
    for tree in trees:
        _collect(tree, commands, flags)

    if not policy.allow_shell_features:
        if flags["cmdsub"]:
            return _violation(
                policy, "command substitution is disabled in strict mode"
            )
        if flags["procsub"]:
            return _violation(
                policy, "process substitution is disabled in strict mode"
            )

    for ctx in commands:
        for assignment in ctx.assignments:
            name = assignment.split("=", 1)[0]
            if name in DANGEROUS_ASSIGNMENTS:
                return _violation(
                    policy, f"dangerous environment assignment: {name}"
                )

        if not policy.allow_shell_features:
            if ctx.word is not None and _base(ctx.word) in _SHELL_ESCAPE_WORDS:
                return _violation(
                    policy,
                    f"'{ctx.word}' is disabled in strict mode",
                )
            if _has_interpreter_dash_c(ctx):
                return _violation(
                    policy,
                    "running an interpreter with -c/-e is disabled in "
                    "strict mode",
                )

        if policy.mode == "allowlist":
            if ctx.word is not None and _base(ctx.word) not in policy.allow:
                return _violation(
                    policy, f"command not in allowlist: {ctx.word}"
                )
        else:  # denylist
            reason = _denylist_reason(ctx, policy)
            if reason is not None:
                return _violation(policy, reason)

    return Allow()


def _denylist_reason(ctx: _CommandContext, policy: Policy) -> Optional[str]:
    if ctx.word is None:
        return None
    base = _base(ctx.word)
    if base == "mkfs" or base.startswith("mkfs."):
        return f"{base} is denied (destroys filesystems)"
    if base in DEFAULT_DENY or base in policy.deny:
        return f"{base} is denied"
    if base == "rm" and _is_dangerous_rm(ctx.args):
        return "rm with a recursive force on a top-level target is denied"
    if base == "git" and _is_force_push(ctx.args):
        return "git push --force is denied"
    if base == "chmod" and _is_recursive_chmod_777(ctx.args):
        return "recursive chmod 777 is denied"
    return None

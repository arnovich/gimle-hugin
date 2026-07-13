"""Tests for the bash command policy engine (``gimle.hugin.sandbox.policy``).

The policy engine is a **pure** function: ``evaluate(command, policy) ->
Decision``. It is a guardrail against *accidents*, not a security boundary —
the runtime (container / disposable remote) is the boundary. These tests pin
both halves of that contract:

- what the engine **catches** (blunt accidents, dangerous env assignments,
  parse failures fail closed, and — in opt-in strict mode — the shell escape
  hatches), walking the whole AST so a denied binary hidden behind ``&&`` or
  inside ``$(...)`` is still caught; and
- what it deliberately **does not** catch (``python3 -c '...'`` and other
  interpreter-based execution) — asserted explicitly, because pretending the
  wordlist stops those is the exact "security theatre" this design rejects.
"""

import pytest

from gimle.hugin.sandbox.policy import (
    Allow,
    Deny,
    Escalate,
    Policy,
    evaluate,
)


def _decision(command, **policy_kwargs):
    return evaluate(command, Policy(**policy_kwargs))


class TestDenylistDefaultAllowsOrdinaryCommands:
    """The default (denylist, permissive) mode lets normal work through."""

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "cat file.txt | grep needle",
            "rg TODO src/",
            "git status",
            "git push origin main",
            "rm -rf ./build",  # relative target — an accident, but not catastrophic
            "find . -name '*.py'",
            "python3 script.py",
        ],
    )
    def test_ordinary_command_is_allowed(self, command):
        """Everyday shell work is permitted."""
        assert isinstance(_decision(command), Allow)


class TestDenylistIsNotACapabilityBoundary:
    """By design: interpreter-based execution is ALLOWED in denylist mode.

    The container/remote is the boundary, not the wordlist. These asserts are
    the honest counterpart to the security review — if any of them start
    failing as Deny, someone has reintroduced allowlist theatre.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "python3 -c 'import os; os.system(\"id\")'",
            "uv run python -c 'import os; os.system(\"id\")'",
            "awk 'BEGIN{system(\"id\")}'",
            "find . -exec rm {} +",
            "git -c core.pager='!sh' log",
        ],
    )
    def test_interpreter_execution_is_allowed_by_design(self, command):
        """Interpreter-based execution passes — the runtime is the boundary."""
        assert isinstance(_decision(command), Allow)


class TestDenylistCatchesAccidents:
    """The blunt accident set is denied, wherever it appears in the AST."""

    @pytest.mark.parametrize(
        "command",
        [
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sda1",
            "shutdown now",
            "reboot",
            "rm -rf /",
            "rm -rf ~",
            "rm -rf /*",
            "git push --force origin main",
            "git push -f origin main",
        ],
    )
    def test_dangerous_command_is_denied(self, command):
        """The blunt catastrophic set is refused."""
        assert isinstance(_decision(command), Deny)

    def test_denied_binary_after_operator_is_caught(self):
        """A denied binary behind && is still found (full AST walk)."""
        assert isinstance(_decision("ls && dd if=/dev/zero of=/dev/sda"), Deny)

    def test_denied_binary_in_command_substitution_is_caught(self):
        """A denied binary inside $(...) is still found."""
        assert isinstance(_decision("echo $(shutdown now)"), Deny)

    def test_denied_binary_in_pipeline_is_caught(self):
        """A denied binary anywhere in a pipeline is still found."""
        assert isinstance(_decision("cat x | mkfs.ext4 /dev/sda1"), Deny)


class TestDangerousAssignmentsRejected:
    """Env-assignment prefixes that hijack execution are always rejected."""

    @pytest.mark.parametrize(
        "command",
        [
            "LD_PRELOAD=./evil.so ls",
            "LD_LIBRARY_PATH=/tmp/x ls",
            "BASH_ENV=./x.sh bash script.sh",
            "IFS=$' ' ls",
            "GIT_SSH_COMMAND='sh -c id' git fetch",
        ],
    )
    def test_dangerous_assignment_is_denied(self, command):
        """An execution-hijacking env prefix is refused on any backend."""
        assert isinstance(_decision(command), Deny)

    def test_ordinary_assignment_is_allowed(self):
        """A benign inline assignment does not trip the check."""
        assert isinstance(_decision("FOO=bar env"), Allow)


class TestParseFailureFailsClosed:
    """An unparseable command is denied, never allowed."""

    @pytest.mark.parametrize(
        "command",
        [
            "ls '",  # unterminated single quote
            'cat "',  # unterminated double quote
            "echo $(",  # unterminated command substitution
        ],
    )
    def test_unparseable_command_is_denied(self, command):
        """A command bashlex cannot parse is denied, never allowed."""
        assert isinstance(_decision(command), Deny)

    def test_parse_failure_reason_mentions_parse(self):
        """The denial reason names the parse failure."""
        decision = _decision("ls '")
        assert isinstance(decision, Deny)
        assert "pars" in decision.reason.lower()


class TestOnViolationEscalate:
    """on_violation='ask_human' turns a Deny into an Escalate."""

    def test_violation_escalates_when_configured(self):
        """A would-be denial becomes an escalation under ask_human."""
        decision = _decision(
            "dd if=/dev/zero of=/dev/sda", on_violation="ask_human"
        )
        assert isinstance(decision, Escalate)
        assert decision.reason

    def test_allowed_command_is_not_escalated(self):
        """An allowed command is never escalated."""
        decision = _decision("ls -la", on_violation="ask_human")
        assert isinstance(decision, Allow)


class TestAllowlistMode:
    """allowlist mode permits only named command words."""

    def test_listed_command_is_allowed(self):
        """A command word on the allowlist runs."""
        assert isinstance(
            _decision("ls -la", mode="allowlist", allow=("ls", "cat")), Allow
        )

    def test_unlisted_command_is_denied(self):
        """A command word not on the allowlist is refused."""
        assert isinstance(
            _decision("curl http://x", mode="allowlist", allow=("ls", "cat")),
            Deny,
        )

    def test_unlisted_command_behind_operator_is_denied(self):
        """An unlisted command behind && is still caught (full AST walk)."""
        assert isinstance(
            _decision("ls && curl http://x", mode="allowlist", allow=("ls",)),
            Deny,
        )

    def test_allowlisting_an_interpreter_is_not_a_boundary(self):
        """Documents WHY allowlisting interpreters is theatre: it passes."""
        decision = _decision(
            "python3 -c 'import os; os.system(\"id\")'",
            mode="allowlist",
            allow=("python3",),
        )
        assert isinstance(decision, Allow)


class TestStrictModeRejectsShellFeatures:
    """allow_shell_features=False (opt-in, paranoid) blocks the escape hatches."""

    @pytest.mark.parametrize(
        "command",
        [
            "echo $(id)",  # command substitution
            "echo `id`",  # backtick command substitution
            "cat <(echo hi)",  # process substitution
            "eval 'ls'",  # eval
            "source ./x.sh",  # source
            ". ./x.sh",  # dot-source
            "bash -c 'id'",  # interpreter -c
            "timeout 5 bash -c 'id'",  # wrapper -> interpreter -c
        ],
    )
    def test_shell_feature_is_denied_in_strict_mode(self, command):
        """Each shell escape hatch is refused when strict mode is on."""
        assert isinstance(_decision(command, allow_shell_features=False), Deny)

    def test_plain_command_still_allowed_in_strict_mode(self):
        """Strict mode does not block an ordinary command."""
        assert isinstance(
            _decision("ls -la", allow_shell_features=False), Allow
        )

    def test_shell_features_allowed_by_default(self):
        """Default mode is permissive — the runtime is the boundary."""
        assert isinstance(_decision("echo $(id)"), Allow)


class TestUnrestrictedMode:
    """unrestricted mode performs no checks (still fails closed on parse)."""

    def test_dangerous_command_is_allowed(self):
        """Unrestricted mode performs no command checks."""
        assert isinstance(
            _decision("dd if=/dev/zero of=/dev/sda", mode="unrestricted"),
            Allow,
        )

    def test_still_fails_closed_on_parse_error(self):
        """Even unrestricted mode denies an unparseable command."""
        assert isinstance(_decision("ls '", mode="unrestricted"), Deny)

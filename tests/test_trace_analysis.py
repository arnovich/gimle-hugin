"""Tests for read-only trace analysis (`hugin analyze`).

The report is built from data stored verbatim -- raw tool arguments, raw error
strings, optionally full rendered prompts -- and is then printed to a terminal,
a CI log, or (later) handed to a model. So the tests that matter most are not
the arithmetic ones: they are the ones asserting that a credential sitting in a
trace does not come out the other end.
"""

import json
from pathlib import Path

import pytest

from gimle.hugin.analysis.redaction import error_signature, redact
from gimle.hugin.analysis.traces import (
    LOOP_THRESHOLD,
    OVERSIZED_RESULT_CHARS,
    TraceReadError,
    analyze_traces,
)

# Deliberately not hex-shaped and free of long digit runs: an all-hex key is
# destroyed by the signature's value-masking anyway, so a test using one passes
# even with the redactor removed. This one can only be masked by the redactor.
FAKE_KEY = "sk-live-zzTOPsecretKEYvaluezz"


def write_run(
    storage: Path,
    *,
    agent_id: str,
    tools_granted=("fetch", "builtins.finish:finish"),
    calls=(),
    finish_type="success",
    turns=1,
    rendered=None,
):
    """Write one agent's run into a storage directory.

    Builds the on-disk shape directly -- ``agents/<uuid>`` holding a list of
    interaction uuids, each a ``{"type": ..., "data": {...}}`` file -- which is
    what the reader actually consumes.
    """
    (storage / "agents").mkdir(parents=True, exist_ok=True)
    (storage / "interactions").mkdir(parents=True, exist_ok=True)

    uuids = []

    def add(kind, data):
        uuid = f"{agent_id}-{len(uuids)}"
        (storage / "interactions" / uuid).write_text(
            json.dumps({"type": kind, "data": data})
        )
        uuids.append(uuid)

    for _ in range(turns):
        add(
            "OracleResponse",
            {
                "response": {"input_tokens": 10, "output_tokens": 5},
                "rendered_user_message": rendered,
            },
        )

    for call in calls:
        add("ToolCall", {"tool": call["tool"], "args": call.get("args", {})})
        add(
            "ToolResult",
            {
                "is_error": call.get("is_error", False),
                "result": call.get("result", {"ok": True}),
            },
        )

    if finish_type:
        add("TaskResult", {"finish_type": finish_type, "result": {}})

    (storage / "agents" / agent_id).write_text(
        json.dumps(
            {
                "uuid": agent_id,
                "config": {"name": "demo", "tools": list(tools_granted)},
                "stack": {"interactions": uuids},
            }
        )
    )


class TestRedaction:
    """Traces are stored verbatim; nothing else masks anything."""

    @pytest.mark.parametrize(
        "secret",
        [
            "sk-live-abcdefgh12345678",
            "ghp_abcdefghijklmnop",
            "AKIAABCDEFGH12345678",
            "Bearer abcdefgh.ijklmnop",
            "xoxb-1234-5678-abcdefgh",
        ],
    )
    def test_credentials_are_masked(self, secret):
        """Each shape a key actually turns up in."""
        assert secret not in redact(f"failed with {secret} at the end")

    def test_query_string_secrets_are_masked(self):
        """The classic: a 401 echoing the URL it called."""
        masked = redact("401 for https://api.x/v1?api_key=abcd1234efgh")
        assert "abcd1234efgh" not in masked

    def test_ordinary_text_survives(self):
        """Over-redacting would make the report useless."""
        assert redact("connection refused") == "connection refused"

    def test_error_signature_masks_values(self):
        """Two runs failing the same way must group together."""
        first = error_signature("KeyError: 'user_4821' at line 12")
        second = error_signature("KeyError: 'user_9137' at line 88")
        assert first == second

    def test_error_signature_redacts_before_grouping(self):
        """Grouping must not be a way to smuggle a key through."""
        assert FAKE_KEY not in error_signature(f"401 using {FAKE_KEY}")


class TestReportedMetrics:
    """Each metric must actually fire, not merely be computable."""

    def test_counts_runs(self, tmp_path):
        """The baseline."""
        write_run(tmp_path, agent_id="a")
        write_run(tmp_path, agent_id="b")

        assert analyze_traces(str(tmp_path))["runs_analyzed"] == 2

    def test_unfinished_runs_are_distinguished_from_failures(self, tmp_path):
        """A run that never reached TaskResult did not fail -- it stopped."""
        write_run(tmp_path, agent_id="a", finish_type=None)
        write_run(tmp_path, agent_id="b", finish_type="success")

        report = analyze_traces(str(tmp_path))

        assert report["unfinished_rate"] == 0.5
        assert report["self_reported_success_rate"] == 1.0

    def test_tool_error_rate_is_attributed_to_the_right_tool(self, tmp_path):
        """ToolResult carries no tool name, so attribution is positional."""
        write_run(
            tmp_path,
            agent_id="a",
            calls=[
                {"tool": "fetch", "is_error": True, "result": {"error": "x"}},
                {"tool": "render", "is_error": False},
            ],
        )

        rows = {row["name"]: row for row in analyze_traces(str(tmp_path))["tools"]}

        assert rows["fetch"]["error_rate"] == 1.0
        assert rows["render"]["error_rate"] == 0.0

    def test_dead_tools_are_reported(self, tmp_path):
        """A granted tool nothing ever called."""
        write_run(
            tmp_path,
            agent_id="a",
            tools_granted=("fetch", "never_used"),
            calls=[{"tool": "fetch"}],
        )

        assert "never_used" in analyze_traces(str(tmp_path))["dead_tools"]

    def test_finish_is_not_reported_as_dead(self, tmp_path):
        """A terminating builtin is not a dead capability."""
        write_run(tmp_path, agent_id="a", calls=[{"tool": "fetch"}])

        dead = analyze_traces(str(tmp_path))["dead_tools"]

        assert not any("finish" in name for name in dead)

    def test_loops_are_detected(self, tmp_path):
        """Same tool, same arguments, over and over."""
        write_run(
            tmp_path,
            agent_id="a",
            calls=[
                {"tool": "fetch", "args": {"q": "same"}}
                for _ in range(LOOP_THRESHOLD)
            ],
        )

        assert analyze_traces(str(tmp_path))["loops_detected"]

    def test_different_arguments_are_not_a_loop(self, tmp_path):
        """Repeated work is not repeated failure."""
        write_run(
            tmp_path,
            agent_id="a",
            calls=[{"tool": "fetch", "args": {"q": n}} for n in range(5)],
        )

        assert analyze_traces(str(tmp_path))["loops_detected"] == []

    def test_oversized_results_are_flagged(self, tmp_path):
        """Every byte is re-sent on every later turn of the same stack."""
        write_run(
            tmp_path,
            agent_id="a",
            calls=[
                {
                    "tool": "render",
                    "result": {"html": "x" * (OVERSIZED_RESULT_CHARS + 10)},
                }
            ],
        )

        assert analyze_traces(str(tmp_path))["oversized_results"]

    def test_tokens_are_totalled(self, tmp_path):
        """Cost is the metric a user actually feels."""
        write_run(tmp_path, agent_id="a", turns=3)

        assert analyze_traces(str(tmp_path))["tokens"]["output"] == 15

    def test_unrendered_placeholders_are_counted(self, tmp_path):
        """Only visible when HUGIN_CAPTURE_RENDERED_PROMPTS was on."""
        write_run(
            tmp_path,
            agent_id="a",
            rendered=[{"text": "Look up {{ ticker.value }}"}],
        )

        assert analyze_traces(str(tmp_path))["unresolved_template_turns"] == 1

    def test_agent_name_filters_runs(self, tmp_path):
        """One storage directory can hold several agents' runs."""
        write_run(tmp_path, agent_id="a")

        assert (
            analyze_traces(str(tmp_path), agent_name="other")["runs_analyzed"]
            == 0
        )


class TestNothingLeaks:
    """The property the whole module exists to preserve."""

    def test_a_seeded_key_in_an_error_never_reaches_the_report(self, tmp_path):
        """The headline test."""
        write_run(
            tmp_path,
            agent_id="a",
            calls=[
                {
                    "tool": "fetch",
                    "is_error": True,
                    "result": {"error": f"401 unauthorized using {FAKE_KEY}"},
                }
            ],
        )

        report = json.dumps(analyze_traces(str(tmp_path)))

        assert FAKE_KEY not in report
        assert "TOPsecretKEY" not in report

    def test_tool_arguments_are_never_included(self, tmp_path):
        """Loop detection needs identity, not contents."""
        write_run(
            tmp_path,
            agent_id="a",
            calls=[
                {"tool": "fetch", "args": {"password": "hunter2-secret"}}
            ]
            * LOOP_THRESHOLD,
        )

        report = json.dumps(analyze_traces(str(tmp_path)))

        assert "hunter2-secret" not in report

    def test_result_bodies_are_never_included(self, tmp_path):
        """Only sizes are reported, not content."""
        write_run(
            tmp_path,
            agent_id="a",
            calls=[{"tool": "fetch", "result": {"pii": "customer-record-42"}}],
        )

        assert "customer-record-42" not in json.dumps(
            analyze_traces(str(tmp_path))
        )


class TestCaveats:
    """A number without its caveat invites the wrong conclusion."""

    def test_self_reported_success_is_always_flagged(self, tmp_path):
        """It is the agent's own verdict, and it is trivially gameable."""
        write_run(tmp_path, agent_id="a")

        notes = " ".join(analyze_traces(str(tmp_path))["caveats"])

        assert "self-reported" in notes

    def test_small_samples_are_flagged(self, tmp_path):
        """Calling a tool dead on one run would be a bad deletion."""
        write_run(tmp_path, agent_id="a")

        notes = " ".join(analyze_traces(str(tmp_path))["caveats"])

        assert "too few" in notes


class TestFailureModes:
    """A diagnostic tool that dies with a traceback is not diagnostic."""

    def test_a_non_storage_directory_is_a_clear_error(self, tmp_path):
        """Pointing at the agent instead of its storage is the likely slip."""
        with pytest.raises(TraceReadError):
            analyze_traces(str(tmp_path / "not-storage"))

    def test_empty_storage_reports_no_runs(self, tmp_path):
        """Not an error -- just nothing to say yet."""
        (tmp_path / "agents").mkdir()

        assert analyze_traces(str(tmp_path))["runs_analyzed"] == 0

    def test_corrupt_interaction_is_skipped(self, tmp_path):
        """One bad file must not lose the whole run."""
        write_run(tmp_path, agent_id="a", calls=[{"tool": "fetch"}])
        broken = next((tmp_path / "interactions").iterdir())
        broken.write_text("{ not json")

        assert analyze_traces(str(tmp_path))["runs_analyzed"] == 1

    def test_limit_caps_the_read(self, tmp_path):
        """Storage directories grow without bound."""
        for index in range(5):
            write_run(tmp_path, agent_id=f"a{index}")

        assert analyze_traces(str(tmp_path), limit=2)["runs_analyzed"] == 2

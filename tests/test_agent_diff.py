"""Showing an edit before it lands.

The builder writes from inside the agent run, so without a hold the CLI only
regains control after the files have changed. For a new agent that is fine --
the directory did not exist. For an edit the target is someone's working
agent, and showing the change and asking is the one thing that makes the tool
trustworthy against it.
"""

from types import SimpleNamespace

import pytest

from gimle.hugin.apps.agent_builder.diff import (
    MAX_DIFF_LINES,
    diff_against_disk,
    render_agent_diff,
)
from gimle.hugin.apps.agent_builder.tools.load_agent_files import (
    load_agent_files,
)
from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
    write_agent_files,
)

CONFIG = (
    "name: demo\n"
    "description: A demo agent\n"
    "system_template: demo_system\n"
    "tools:\n"
    "  - builtins.finish:finish\n"
)
TASK = "name: main\ndescription: The demo task\nprompt: Do the thing.\n"
TEMPLATE = "name: demo_system\ntemplate: You are a demo agent.\n"


@pytest.fixture
def agent_dir(tmp_path):
    """An agent on disk to diff against."""
    root = tmp_path / "demo_agent"
    for key, content in {
        "configs/demo.yaml": CONFIG,
        "tasks/main.yaml": TASK,
        "templates/demo_system.yaml": TEMPLATE,
    }.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


class TestClassification:
    """Which files the edit would touch, before any rendering."""

    def test_it_separates_changed_added_and_unchanged(self, agent_dir):
        """The three cases the confirmation prompt needs to count."""
        payload = {
            "configs/demo.yaml": CONFIG,
            "tasks/main.yaml": TASK + "# revised\n",
            "tools/new.py": "x = 1\n",
        }

        changed, added, unchanged = diff_against_disk(payload, agent_dir)

        assert changed == ["tasks/main.yaml"]
        assert added == ["tools/new.py"]
        assert unchanged == ["configs/demo.yaml"]


class TestRendering:
    """What the user actually reads."""

    def test_a_changed_file_shows_both_sides(self, agent_dir):
        """A diff that only showed the new text would hide what is lost."""
        payload = {
            "templates/demo_system.yaml": TEMPLATE.replace(
                "a demo agent.", "a revised agent."
            )
        }

        rendered = render_agent_diff(payload, agent_dir)

        assert "-name: demo_system" not in rendered
        assert "+template: You are a revised agent." in rendered
        assert "-template: You are a demo agent." in rendered

    def test_an_identical_payload_says_so(self, agent_dir):
        """The no-op edit is a real outcome and must not look like a diff."""
        payload = {"configs/demo.yaml": CONFIG}

        assert "No file differs" in render_agent_diff(payload, agent_dir)

    def test_a_huge_rewrite_is_truncated_but_counted(self, agent_dir):
        """Truncating silently would make a rewrite look like a small edit."""
        payload = {
            "configs/demo.yaml": "".join(
                f"line {n}\n" for n in range(MAX_DIFF_LINES * 3)
            )
        }

        rendered = render_agent_diff(payload, agent_dir)

        assert "more diff line(s)" in rendered

    def test_unchanged_files_are_summarised_not_diffed(self, agent_dir):
        """Reviewing an edit means reading what changed, not what did not."""
        payload = {
            "configs/demo.yaml": CONFIG,
            "tasks/main.yaml": TASK + "# revised\n",
        }

        rendered = render_agent_diff(payload, agent_dir)

        assert "1 file(s) unchanged: configs/demo.yaml" in rendered


class TestTheConfirmationHold:
    """`await_confirmation` must stop the write, not merely report it."""

    @pytest.fixture
    def stack(self, agent_dir):
        """Load the agent for real, then stage one regenerated file.

        Going through ``load_agent_files`` rather than hand-building the
        payload is what makes this exercise the write path: without its
        ownership adoption every existing file is a conflict and the write is
        refused before the hold is ever consulted.
        """
        environment = SimpleNamespace(
            env_vars={
                "user_input": {
                    "agent_name": "demo",
                    "description": "A demo agent",
                }
            },
            load_agent_from_path=lambda path: "demo",
        )
        stack = SimpleNamespace(agent=SimpleNamespace(environment=environment))
        load_agent_files(stack, str(agent_dir))
        environment.env_vars["generated_files"][
            "templates/demo_system.yaml"
        ] = TEMPLATE.replace("a demo agent.", "a revised agent.")
        environment.env_vars["await_confirmation"] = True
        return stack

    def test_nothing_reaches_disk_while_held(self, stack, agent_dir):
        """The whole point: the user sees the edit before it exists."""
        before = (agent_dir / "templates" / "demo_system.yaml").read_text()

        write_agent_files(stack, str(agent_dir))

        assert (
            agent_dir / "templates" / "demo_system.yaml"
        ).read_text() == before

    def test_it_still_reports_what_it_would_do(self, stack, agent_dir):
        """A hold that reported nothing would leave nothing to confirm."""
        response = write_agent_files(stack, str(agent_dir))

        assert response.content["dry_run"] is True
        assert response.content["would_write"] == ["templates/demo_system.yaml"]

    def test_clearing_the_hold_lets_the_write_through(self, stack, agent_dir):
        """What the CLI does once the user says yes."""
        stack.agent.environment.env_vars["await_confirmation"] = False

        write_agent_files(stack, str(agent_dir))

        assert (
            "revised agent"
            in (agent_dir / "templates" / "demo_system.yaml").read_text()
        )

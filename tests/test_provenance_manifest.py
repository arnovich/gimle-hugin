"""Which lines did a machine write?

Once `hugin improve --apply` can edit an agent, that stops being answerable
from the directory alone -- and six months later it is the question someone
actually has: a tool behaves oddly, and whether it was hand-tuned or generated
decides whether to fix it or regenerate it.

The manifest deliberately does not make writes stricter. `hugin create --edit`
is documented as working on hand-written agents, so refusing to touch anything
Hugin did not write would break exactly that. It makes provenance *visible*.
"""

import json
from types import SimpleNamespace

import pytest

from gimle.hugin.apps.agent_builder.manifest import (
    MANIFEST_NAME,
    hand_modified,
    read_manifest,
    recorded_files,
    untracked,
    update_manifest,
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
def stack():
    environment = SimpleNamespace(
        env_vars={
            "generated_files": {
                "configs/demo.yaml": CONFIG,
                "tasks/main.yaml": TASK,
                "templates/demo_system.yaml": TEMPLATE,
            },
            "user_input": {
                "agent_name": "demo",
                "description": "A demo agent",
            },
        },
        load_agent_from_path=lambda path: "demo",
    )
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


class TestWritingRecordsAuthorship:
    """A build leaves a record of what it wrote."""

    def test_a_build_writes_a_manifest(self, stack, tmp_path):
        write_agent_files(stack, str(tmp_path / "agent"))

        assert (tmp_path / "agent" / MANIFEST_NAME).is_file()

    def test_it_records_every_generated_file(self, stack, tmp_path):
        destination = tmp_path / "agent"

        write_agent_files(stack, str(destination))

        recorded = recorded_files(read_manifest(destination))
        assert "configs/demo.yaml" in recorded
        assert "tasks/main.yaml" in recorded

    def test_it_records_which_command_wrote_them(self, stack, tmp_path):
        """ "Hugin wrote this" is less useful than which run did."""
        stack.agent.environment.env_vars["provenance_command"] = (
            "hugin improve --apply"
        )
        destination = tmp_path / "agent"

        write_agent_files(stack, str(destination))

        entry = read_manifest(destination)["files"]["configs/demo.yaml"]
        assert entry["generated_by"] == "hugin improve --apply"
        assert entry["generated_at"]

    def test_a_failed_write_claims_no_provenance(self, stack, tmp_path):
        """The payload does not validate, so nothing is written or claimed."""
        stack.agent.environment.env_vars["generated_files"] = {
            "configs/demo.yaml": "name: demo\n"
        }
        destination = tmp_path / "agent"

        response = write_agent_files(stack, str(destination))

        assert response.is_error
        assert not (destination / MANIFEST_NAME).exists()


class TestDetectingHandEdits:
    """The question the manifest exists to answer."""

    def test_an_untouched_file_is_not_flagged(self, tmp_path):
        update_manifest(tmp_path, {"tools/a.py": "x = 1\n"}, "hugin create")

        assert hand_modified(tmp_path, {"tools/a.py": "x = 1\n"}) == []

    def test_an_edited_file_is_flagged(self, tmp_path):
        update_manifest(tmp_path, {"tools/a.py": "x = 1\n"}, "hugin create")

        assert hand_modified(
            tmp_path, {"tools/a.py": "x = 2  # tuned by hand\n"}
        ) == ["tools/a.py"]

    def test_a_file_hugin_never_wrote_is_not_modified(self, tmp_path):
        """Calling it modified would flag every hand-written agent."""
        update_manifest(tmp_path, {"tools/a.py": "x = 1\n"}, "hugin create")

        assert hand_modified(tmp_path, {"tools/mine.py": "y = 2\n"}) == []
        assert untracked(tmp_path, {"tools/mine.py": "y = 2\n"}) == [
            "tools/mine.py"
        ]

    def test_later_writes_keep_earlier_provenance(self, tmp_path):
        """An agent built by one command and edited by another has both."""
        update_manifest(tmp_path, {"tools/a.py": "1\n"}, "hugin create")
        update_manifest(tmp_path, {"tools/b.py": "2\n"}, "hugin improve")

        files = read_manifest(tmp_path)["files"]
        assert files["tools/a.py"]["generated_by"] == "hugin create"
        assert files["tools/b.py"]["generated_by"] == "hugin improve"


class TestItNeverBlocksAnEdit:
    """Provenance is bookkeeping; losing it must not stop work."""

    def test_a_corrupt_manifest_reads_as_absent(self, tmp_path):
        (tmp_path / MANIFEST_NAME).write_text("{ not json")

        assert read_manifest(tmp_path) == {}

    def test_a_manifest_from_a_newer_hugin_reads_as_absent(self, tmp_path):
        (tmp_path / MANIFEST_NAME).write_text(
            json.dumps({"version": 999, "files": {}})
        )

        assert read_manifest(tmp_path) == {}

    def test_an_agent_with_no_manifest_still_loads(self, tmp_path):
        """Every hand-written agent is in this state."""
        root = tmp_path / "agent"
        (root / "configs").mkdir(parents=True)
        (root / "configs" / "demo.yaml").write_text(CONFIG)
        environment = SimpleNamespace(env_vars={})
        bare = SimpleNamespace(agent=SimpleNamespace(environment=environment))

        response = load_agent_files(bare, str(root))

        assert not response.is_error
        assert response.content["hand_modified"] == []
        assert response.content["not_written_by_hugin"] == ["configs/demo.yaml"]


class TestTheRoundTrip:
    """Build, hand-edit, reload: the edit is reported."""

    def test_a_hand_edit_after_a_build_is_reported_on_reload(
        self, stack, tmp_path
    ):
        destination = tmp_path / "agent"
        write_agent_files(stack, str(destination))
        (destination / "tasks" / "main.yaml").write_text(
            TASK + "# tuned by hand\n"
        )

        fresh = SimpleNamespace(
            agent=SimpleNamespace(
                environment=SimpleNamespace(
                    env_vars={}, load_agent_from_path=lambda p: "demo"
                )
            )
        )
        response = load_agent_files(fresh, str(destination))

        assert response.content["hand_modified"] == ["tasks/main.yaml"]

    def test_the_manifest_is_not_loaded_as_an_agent_file(self, stack, tmp_path):
        """It is bookkeeping, not part of the agent."""
        destination = tmp_path / "agent"
        write_agent_files(stack, str(destination))

        fresh = SimpleNamespace(
            agent=SimpleNamespace(
                environment=SimpleNamespace(
                    env_vars={}, load_agent_from_path=lambda p: "demo"
                )
            )
        )
        load_agent_files(fresh, str(destination))

        loaded = fresh.agent.environment.env_vars["generated_files"]
        assert MANIFEST_NAME not in loaded

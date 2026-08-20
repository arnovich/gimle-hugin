"""Loading an existing agent so the generate_* tools become edit tools.

The writer only overwrites a file whose content still matches the hash it
recorded when it wrote it. An edit reads an agent this session never wrote, so
nothing is owned and every existing file would be a conflict -- the writer
would refuse the whole edit. Loading therefore adopts what it read, which
keeps the guard that matters (a file changing between load and write is still
refused) and drops only the claim "this session created it", which an edit can
never make.
"""

from types import SimpleNamespace

import pytest

from gimle.hugin.apps.agent_builder.tools.load_agent_files import (
    MAX_FILE_CHARS,
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
TOOL_BODY = '"""Hand-tuned, with a comment nobody should lose."""\n'


@pytest.fixture
def agent_dir(tmp_path):
    """Write a small but complete agent directory to disk."""
    root = tmp_path / "demo_agent"
    for key, content in {
        "configs/demo.yaml": CONFIG,
        "tasks/main.yaml": TASK,
        "templates/demo_system.yaml": TEMPLATE,
        "tools/fetch.py": TOOL_BODY,
    }.items():
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


@pytest.fixture
def stack():
    """Return a stack stub exposing only what these tools touch."""
    environment = SimpleNamespace(
        env_vars={
            "user_input": {
                "agent_name": "demo",
                "description": "A demo agent",
            }
        },
        load_agent_from_path=lambda path: "demo",
    )
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


def _files(stack):
    return stack.agent.environment.env_vars["generated_files"]


class TestLoading:
    """What lands in the payload, and what deliberately does not."""

    def test_it_loads_the_agent_into_the_generated_payload(
        self, stack, agent_dir
    ):
        """Keyed identically to the generate_* tools' own output."""
        response = load_agent_files(stack, str(agent_dir))

        assert not response.is_error
        assert set(_files(stack)) == {
            "configs/demo.yaml",
            "tasks/main.yaml",
            "templates/demo_system.yaml",
            "tools/fetch.py",
        }

    def test_the_manifest_carries_sizes_but_never_bodies(
        self, stack, agent_dir
    ):
        """Bodies come from read_generated_file, one file at a time."""
        content = load_agent_files(stack, str(agent_dir)).content

        assert {entry["path"] for entry in content["manifest"]} == set(
            _files(stack)
        )
        assert all("lines" in entry for entry in content["manifest"])
        assert TOOL_BODY not in str(content)

    def test_run_history_is_not_walked(self, stack, agent_dir):
        """An agent that has run holds a storage/ tree of trace JSON."""
        traces = agent_dir / "storage" / "interactions"
        traces.mkdir(parents=True)
        (traces / "abc.json").write_text("x" * 10_000)

        load_agent_files(stack, str(agent_dir))

        assert not any("storage" in key for key in _files(stack))

    def test_unmanaged_files_are_skipped_not_fatal(self, stack, agent_dir):
        """A hand-maintained agent holds notes and fixtures too."""
        (agent_dir / "NOTES.md").write_text("my notes")

        response = load_agent_files(stack, str(agent_dir))

        assert not response.is_error
        assert "NOTES.md" not in _files(stack)
        assert any("NOTES.md" in item for item in response.content["skipped"])

    def test_an_oversized_file_is_skipped(self, stack, agent_dir):
        """One runaway file must not blow the context window."""
        (agent_dir / "tools" / "huge.py").write_text("#" * (MAX_FILE_CHARS + 1))

        response = load_agent_files(stack, str(agent_dir))

        assert "tools/huge.py" not in _files(stack)
        assert any("huge.py" in item for item in response.content["skipped"])


class TestRefusals:
    """Failing loudly beats loading the wrong thing."""

    def test_a_missing_directory_is_an_error(self, stack, tmp_path):
        """The path is user input and is routinely wrong."""
        response = load_agent_files(stack, str(tmp_path / "nope"))

        assert response.is_error

    def test_a_directory_without_agent_files_is_an_error(self, stack, tmp_path):
        """Pointing at a source tree should say so, not load nothing."""
        (tmp_path / "src").mkdir()

        response = load_agent_files(stack, str(tmp_path / "src"))

        assert response.is_error
        assert "no agent files" in response.content["error"]

    def test_a_symlinked_file_is_not_followed(self, stack, agent_dir):
        """A planted link would otherwise read anything the process can."""
        (agent_dir / "configs" / "leak.yaml").symlink_to("/etc/hostname")

        load_agent_files(stack, str(agent_dir))

        assert "configs/leak.yaml" not in _files(stack)


class TestEditingIsWritable:
    """The point of adopting ownership: the edit can actually land."""

    def test_a_loaded_agent_can_be_written_back(self, stack, agent_dir):
        """Without adoption every existing file is an unowned conflict."""
        load_agent_files(stack, str(agent_dir))

        response = write_agent_files(stack, str(agent_dir))

        assert not response.is_error, response.content

    def test_a_regenerated_file_is_the_only_one_that_changes(
        self, stack, agent_dir
    ):
        """The round-trip guarantee edit mode rests on."""
        load_agent_files(stack, str(agent_dir))
        _files(stack)["tools/fetch.py"] = '"""Revised."""\n'

        write_agent_files(stack, str(agent_dir))

        assert (agent_dir / "tools" / "fetch.py").read_text() == (
            '"""Revised."""\n'
        )
        assert (agent_dir / "configs" / "demo.yaml").read_text() == CONFIG
        assert (agent_dir / "tasks" / "main.yaml").read_text() == TASK

    def test_a_file_changed_after_loading_is_still_refused(
        self, stack, agent_dir
    ):
        """Adoption must not disarm the guard it borrows.

        Someone editing the directory while the builder runs is exactly what
        the ownership hash exists to catch, and an edit is the case where a
        human is most likely to be in that directory.
        """
        load_agent_files(stack, str(agent_dir))
        (agent_dir / "configs" / "demo.yaml").write_text(
            CONFIG + "# edited by hand mid-build\n"
        )
        _files(stack)["tools/fetch.py"] = '"""Revised."""\n'

        response = write_agent_files(stack, str(agent_dir))

        assert response.is_error
        assert "configs/demo.yaml" in response.content["conflicts"]

    def test_an_unrelated_hand_added_file_survives(self, stack, agent_dir):
        """Loading skipped it, so the write must leave it alone."""
        note = agent_dir / "NOTES.md"
        note.write_text("my notes")
        load_agent_files(stack, str(agent_dir))
        _files(stack)["tools/fetch.py"] = '"""Revised."""\n'

        write_agent_files(stack, str(agent_dir))

        assert note.read_text() == "my notes"


class TestAPreviouslyGeneratedAgent:
    """The realistic case: editing something the builder itself produced.

    Such a directory holds README.md and BUILD_REPORT.md. Carrying those into
    the payload fails validation outright -- they are not generated keys -- and
    regenerating them would rewrite a build's documentation from a one-line
    edit instruction. Edit mode emits neither, so they are preserved.
    """

    @pytest.fixture
    def generated_agent(self, agent_dir):
        """Add the files the writer leaves behind on a real build."""
        (agent_dir / "README.md").write_text(
            "# demo\n\nHand-written docs someone spent an hour on.\n"
        )
        (agent_dir / "BUILD_REPORT.md").write_text("# demo\n\nold report\n")
        (agent_dir / "__init__.py").write_text('"""Generated: demo."""\n')
        return agent_dir

    def test_it_can_be_edited_at_all(self, stack, generated_agent):
        """This refused outright before edit mode stopped materialising."""
        load_agent_files(stack, str(generated_agent))
        _files(stack)["tools/fetch.py"] = '"""Revised."""\n'

        response = write_agent_files(stack, str(generated_agent))

        assert not response.is_error, response.content

    def test_only_the_regenerated_file_is_written(self, stack, generated_agent):
        """The round-trip guarantee, stated as the writer's own report."""
        load_agent_files(stack, str(generated_agent))
        _files(stack)["tools/fetch.py"] = '"""Revised."""\n'

        content = write_agent_files(stack, str(generated_agent)).content

        assert content["written"] == ["tools/fetch.py"]

    def test_hand_written_docs_survive_the_edit(self, stack, generated_agent):
        """An instruction about one tool must not rewrite the README."""
        readme = generated_agent / "README.md"
        before = readme.read_text()
        load_agent_files(stack, str(generated_agent))
        _files(stack)["tools/fetch.py"] = '"""Revised."""\n'

        write_agent_files(stack, str(generated_agent))

        assert readme.read_text() == before

    def test_a_fresh_build_still_gets_its_framework_files(
        self, stack, tmp_path
    ):
        """Edit mode must not cost the normal build its README."""
        stack.agent.environment.env_vars["generated_files"] = {
            "configs/demo.yaml": CONFIG,
            "tasks/main.yaml": TASK,
            "templates/demo_system.yaml": TEMPLATE,
        }
        destination = tmp_path / "fresh"

        write_agent_files(stack, str(destination))

        assert (destination / "README.md").exists()
        assert (destination / "BUILD_REPORT.md").exists()

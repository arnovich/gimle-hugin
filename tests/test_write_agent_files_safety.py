"""Safety tests for the agent builder's file writer.

Covers the two data-loss bugs PR 1.1 exists to fix: the unconditional
``shutil.rmtree`` of the output directory, and the unvalidated
``output_dir / key`` join that let an LLM-chosen file name write anywhere on the
filesystem.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from gimle.hugin.apps.agent_builder.tools.agent_paths import (
    PathConfinementError,
    check_output_path,
    confine,
    run_command,
    validate_generated_key,
)
from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
    write_agent_files,
)


@pytest.fixture
def generated_files():
    """A minimal, valid generated-agent payload."""
    return {
        "configs/demo.yaml": "name: demo\n",
        "tasks/main.yaml": "name: main\n",
        "templates/demo_system.yaml": "name: demo_system\n",
    }


@pytest.fixture
def stack(generated_files):
    """A stack stub exposing only what the writer touches."""
    environment = SimpleNamespace(
        env_vars={
            "generated_files": generated_files,
            "user_input": {
                "agent_name": "demo",
                "description": "A demo agent",
            },
        },
        load_agent_from_path=lambda path: "demo",
    )
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


class TestGeneratedKeyValidation:
    """Keys come from the LLM, so they are validated before any path join."""

    @pytest.mark.parametrize(
        "key",
        [
            "../../../../etc/passwd",
            "tools/../../../escape.py",
            "/etc/passwd",
            "~/.bashrc",
            "..",
            "tools\\win.py",
            " configs/demo.yaml",
        ],
    )
    def test_rejects_escaping_keys(self, key):
        """Traversal, absolute and home-relative keys are refused."""
        assert validate_generated_key(key) is not None

    @pytest.mark.parametrize(
        "key",
        [
            "configs/demo.yaml",
            "tasks/main.yaml",
            "tools/fetch_prices.py",
            "templates/demo_system.yaml",
        ],
    )
    def test_accepts_well_formed_keys(self, key):
        """The shape the generators actually emit passes."""
        assert validate_generated_key(key) is None

    def test_rejects_unexpected_extension(self):
        """Only YAML and Python belong in a generated agent."""
        assert validate_generated_key("configs/demo.txt") is not None


class TestConfinement:
    """An absolute operand replaces the root, so joins must be checked."""

    def test_absolute_key_would_escape_without_confinement(self, tmp_path):
        """Documents the pathlib behaviour this module exists to defeat."""
        assert str(tmp_path / "/etc/passwd") == "/etc/passwd"

    def test_confine_rejects_absolute_key(self, tmp_path):
        """The same join goes through confine() and is refused."""
        with pytest.raises(PathConfinementError):
            confine(tmp_path, "/etc/passwd")

    def test_confine_rejects_traversal(self, tmp_path):
        """``..`` never resolves outside the output directory."""
        with pytest.raises(PathConfinementError):
            confine(tmp_path, "../../evil.py")

    def test_confine_resolves_valid_key_under_root(self, tmp_path):
        """A well-formed key lands where it should."""
        resolved = confine(tmp_path, "tools/fetch.py")
        assert resolved == Path(tmp_path).resolve() / "tools" / "fetch.py"

    def test_confine_rejects_symlink_escape(self, tmp_path):
        """A symlinked subdirectory pointing outside the tree is refused."""
        outside = tmp_path / "outside"
        outside.mkdir()
        root = tmp_path / "agent"
        root.mkdir()
        (root / "tools").symlink_to(outside, target_is_directory=True)
        with pytest.raises(PathConfinementError):
            confine(root, "tools/evil.py")


class TestOutputPathGuards:
    """``output_path`` arrives as a plain task parameter."""

    def test_rejects_filesystem_root(self):
        """Writing an agent to / is never intended."""
        assert check_output_path("/") is not None

    def test_rejects_home_directory(self):
        """The old rmtree pointed at $HOME would have erased it."""
        assert check_output_path(str(Path.home())) is not None

    def test_rejects_repository_root(self, tmp_path):
        """A directory containing .git is a repo, not an agent target."""
        (tmp_path / ".git").mkdir()
        assert check_output_path(str(tmp_path)) is not None

    def test_rejects_symlinked_target(self, tmp_path):
        """A symlinked component means the real target is elsewhere."""
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
        assert check_output_path(str(link)) is not None

    def test_accepts_ordinary_subdirectory(self, tmp_path):
        """The normal case is not blocked."""
        assert check_output_path(str(tmp_path / "agents" / "demo")) is None


class TestWriterDoesNotDestroy:
    """The headline regression: the writer used to rmtree its target."""

    def test_preserves_unrelated_existing_file(
        self, stack, tmp_path, generated_files
    ):
        """A hand-added file survives a write and is reported as preserved."""
        output = tmp_path / "demo"
        output.mkdir()
        keep = output / "my_notes.md"
        keep.write_text("hand-written, do not delete")

        result = write_agent_files(stack, str(output), "demo")

        assert not result.is_error
        assert keep.exists()
        assert keep.read_text() == "hand-written, do not delete"
        assert "my_notes.md" in result.content["preserved"]

    def test_preserves_hand_edited_tool(self, stack, tmp_path):
        """Files the builder did not generate are never overwritten."""
        output = tmp_path / "demo"
        (output / "tools").mkdir(parents=True)
        custom = output / "tools" / "my_own_tool.py"
        custom.write_text("# mine\n")

        write_agent_files(stack, str(output), "demo")

        assert custom.read_text() == "# mine\n"

    def test_second_run_writes_nothing_when_unchanged(
        self, stack, tmp_path
    ):
        """Re-running over an identical agent is a no-op, not a rewrite."""
        output = tmp_path / "demo"

        first = write_agent_files(stack, str(output), "demo")
        assert first.content["written"]

        second = write_agent_files(stack, str(output), "demo")
        assert second.content["written"] == []
        assert "configs/demo.yaml" in second.content["unchanged"]

    def test_updates_only_the_changed_file(self, stack, tmp_path):
        """A single regenerated file touches exactly one path on disk."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")

        env_vars = stack.agent.environment.env_vars
        env_vars["generated_files"]["configs/demo.yaml"] = "name: demo2\n"

        result = write_agent_files(stack, str(output), "demo")

        assert result.content["written"] == ["configs/demo.yaml"]


class TestWriterRefusals:
    """Bad input is refused rather than written."""

    def test_refuses_escaping_generated_key(self, stack, tmp_path):
        """A traversal key is a hard error, and nothing is written."""
        env_vars = stack.agent.environment.env_vars
        env_vars["generated_files"]["../../evil.py"] = "pwned"
        output = tmp_path / "demo"

        result = write_agent_files(stack, str(output), "demo")

        assert result.is_error
        assert not (tmp_path.parent / "evil.py").exists()
        assert not output.exists()

    def test_refuses_absolute_generated_key(self, stack, tmp_path):
        """An absolute key would otherwise replace the output directory."""
        env_vars = stack.agent.environment.env_vars
        env_vars["generated_files"]["/tmp/pwned.py"] = "pwned"

        result = write_agent_files(stack, str(tmp_path / "demo"), "demo")

        assert result.is_error

    def test_refuses_unsafe_output_path(self, stack):
        """The output path guards apply to the tool, not just the helper."""
        result = write_agent_files(stack, str(Path.home()), "demo")
        assert result.is_error

    def test_refuses_when_nothing_generated(self, stack, tmp_path):
        """Unchanged behaviour, kept under test."""
        stack.agent.environment.env_vars["generated_files"] = {}
        result = write_agent_files(stack, str(tmp_path / "demo"), "demo")
        assert result.is_error


class TestDryRun:
    """``dry_run`` is what makes a preview possible before any write."""

    def test_writes_nothing(self, stack, tmp_path):
        """The directory is not even created."""
        output = tmp_path / "demo"
        result = write_agent_files(stack, str(output), "demo", dry_run=True)

        assert not result.is_error
        assert not output.exists()
        assert result.content["dry_run"] is True

    def test_reports_what_would_be_written(self, stack, tmp_path):
        """The reported set matches what a real write produces."""
        output = tmp_path / "demo"
        preview = write_agent_files(
            stack, str(output), "demo", dry_run=True
        )
        actual = write_agent_files(stack, str(output), "demo")

        assert preview.content["would_write"] == actual.content["written"]


class TestGeneratedReadme:
    """The README used to name an entrypoint that does not exist."""

    def test_run_command_uses_the_real_entrypoint(self, stack, tmp_path):
        """``run-agent`` is gone; ``hugin run`` is the only command."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")

        readme = (output / "README.md").read_text()

        assert "run-agent" not in readme
        assert "uv run hugin run" in readme

    def test_run_command_names_the_generated_task(self, stack, tmp_path):
        """The command is runnable as printed, not a placeholder."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")

        readme = (output / "README.md").read_text()

        assert "--task main" in readme

    def test_run_command_helper_omits_task_when_unknown(self):
        """Without a task the command degrades rather than lying."""
        assert run_command("/tmp/demo", None) == (
            "uv run hugin run --task-path /tmp/demo"
        )

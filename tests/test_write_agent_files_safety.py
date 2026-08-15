"""Safety tests for the agent builder's file writer.

Covers the two data-loss bugs PR 1.1 exists to fix: the unconditional
``shutil.rmtree`` of the output directory, and the unvalidated
``output_dir / key`` join that let an LLM-chosen file name write anywhere on the
filesystem.
"""

import shlex
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
    _write_confined,
    write_agent_files,
)
from gimle.hugin.cli import create_agent


@pytest.fixture
def generated_files():
    """Return a minimal, valid generated-agent payload."""
    return {
        "configs/demo.yaml": "name: demo\n",
        "tasks/main.yaml": "name: main\n",
        "templates/demo_system.yaml": "name: demo_system\n",
    }


@pytest.fixture
def stack(generated_files):
    """Return a stack stub exposing only what the writer touches."""
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

    def test_refuses_to_overwrite_existing_generated_path(
        self, stack, tmp_path
    ):
        """A same-named user file is a conflict, not permission to truncate."""
        output = tmp_path / "demo"
        (output / "configs").mkdir(parents=True)
        custom = output / "configs" / "demo.yaml"
        custom.write_text("# customized\n")

        result = write_agent_files(stack, str(output), "demo")

        assert result.is_error
        assert result.content["conflicts"] == ["configs/demo.yaml"]
        assert custom.read_text() == "# customized\n"
        assert not (output / "tasks" / "main.yaml").exists()

    def test_refuses_to_overwrite_builder_file_modified_by_user(
        self, stack, tmp_path
    ):
        """Ownership ends when on-disk content no longer matches its hash."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")
        config = output / "configs" / "demo.yaml"
        config.write_text("# user's change\n")
        stack.agent.environment.env_vars["generated_files"][
            "configs/demo.yaml"
        ] = "name: regenerated\n"

        result = write_agent_files(stack, str(output), "demo")

        assert result.is_error
        assert "configs/demo.yaml" in result.content["conflicts"]
        assert config.read_text() == "# user's change\n"

    def test_second_run_writes_nothing_when_unchanged(self, stack, tmp_path):
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
        preview = write_agent_files(stack, str(output), "demo", dry_run=True)
        actual = write_agent_files(stack, str(output), "demo")

        assert preview.content["would_write"] == actual.content["written"]


class TestNamingStyleDoesNotDiscardTheBuild:
    """Confinement is a security rule; snake_case was taste, and it aborted."""

    @pytest.mark.parametrize(
        "key",
        [
            "tools/getWeather.py",
            "tools/my-tool.py",
            "tools/fetch.v2.py",
            "configs/Demo.yaml",
        ],
    )
    def test_unconventional_but_safe_names_are_accepted(self, key):
        """One oddly-named tool must not discard an otherwise good agent."""
        assert validate_generated_key(key) is None

    def test_a_camelcase_tool_still_writes_the_whole_agent(
        self, stack, tmp_path
    ):
        """The regression: every valid file was dropped over one name."""
        env_vars = stack.agent.environment.env_vars
        env_vars["generated_files"]["tools/getWeather.py"] = "x = 1\n"

        result = write_agent_files(stack, str(tmp_path / "demo"), "demo")

        assert not result.is_error
        assert "tools/getWeather.py" in result.content["written"]

    def test_traversal_is_still_refused(self):
        """Loosening style must not loosen confinement."""
        assert validate_generated_key("tools/../../evil.py") is not None


class TestEncoding:
    """Content is written as UTF-8, so it must be read back as UTF-8."""

    def test_non_ascii_roundtrips_as_unchanged(self, stack, tmp_path):
        """A locale-default read made this comparison wrong off UTF-8."""
        env_vars = stack.agent.environment.env_vars
        env_vars["generated_files"][
            "templates/demo_system.yaml"
        ] = "name: demo_system\ntemplate: Grüße, naïve café\n"
        output = tmp_path / "demo"

        write_agent_files(stack, str(output), "demo")
        second = write_agent_files(stack, str(output), "demo")

        assert "templates/demo_system.yaml" in second.content["unchanged"]

    def test_undecodable_existing_file_is_preserved(self, stack, tmp_path):
        """Unknown binary content is a conflict rather than overwrite fodder."""
        output = tmp_path / "demo"
        (output / "configs").mkdir(parents=True)
        existing = output / "configs" / "demo.yaml"
        existing.write_bytes(b"\xff\xfe\x00bad")

        result = write_agent_files(stack, str(output), "demo")

        assert result.is_error
        assert existing.read_bytes() == b"\xff\xfe\x00bad"


class TestFileMode:
    """Generated agents are ordinary project files, not sandbox scratch."""

    def test_files_are_not_owner_only(self, stack, tmp_path):
        """0600 broke running the agent as a service or container user."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")

        mode = (output / "configs" / "demo.yaml").stat().st_mode & 0o777

        assert mode & 0o044, oct(mode)


class TestArgumentCoercion:
    """Tool arguments arrive from the model unconverted."""

    def test_string_false_does_not_skip_the_write(self, stack, tmp_path):
        """bool("false") is True, which silently turned a write into a no-op."""
        output = tmp_path / "demo"

        result = write_agent_files(stack, str(output), "demo", dry_run="false")

        assert result.content.get("dry_run") is not True
        assert (output / "configs" / "demo.yaml").exists()

    def test_string_true_still_previews(self, stack, tmp_path):
        """The affirmative spelling keeps working."""
        output = tmp_path / "demo"

        result = write_agent_files(stack, str(output), "demo", dry_run="true")

        assert result.content["dry_run"] is True
        assert not output.exists()


class TestSupersededFiles:
    """Dropping rmtree lost the "directory holds one generation" invariant."""

    def test_regenerated_under_a_new_name_removes_the_old(
        self, stack, tmp_path
    ):
        """Otherwise both configs register and the stale one can win."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")
        assert (output / "configs" / "demo.yaml").exists()

        env_vars = stack.agent.environment.env_vars
        files = env_vars["generated_files"]
        files["configs/renamed.yaml"] = files.pop("configs/demo.yaml")

        result = write_agent_files(stack, str(output), "demo")

        assert not (output / "configs" / "demo.yaml").exists()
        assert (output / "configs" / "renamed.yaml").exists()
        assert "configs/demo.yaml" in result.content["removed"]

    def test_user_files_are_never_removed(self, stack, tmp_path):
        """Removal is driven by what we wrote, never by scanning the dir."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")
        mine = output / "configs" / "mine.yaml"
        mine.write_text("hand-written")

        env_vars = stack.agent.environment.env_vars
        files = env_vars["generated_files"]
        files["configs/renamed.yaml"] = files.pop("configs/demo.yaml")
        write_agent_files(stack, str(output), "demo")

        assert mine.read_text() == "hand-written"

    def test_modified_builder_file_is_not_removed(self, stack, tmp_path):
        """A superseded path is deletable only while its ownership hash matches."""
        output = tmp_path / "demo"
        write_agent_files(stack, str(output), "demo")
        old = output / "configs" / "demo.yaml"
        old.write_text("# user changed this\n")

        files = stack.agent.environment.env_vars["generated_files"]
        files["configs/renamed.yaml"] = files.pop("configs/demo.yaml")
        result = write_agent_files(stack, str(output), "demo")

        assert result.is_error
        assert "configs/demo.yaml" in result.content["conflicts"]
        assert old.read_text() == "# user changed this\n"
        assert not (output / "configs" / "renamed.yaml").exists()

    def test_identical_preexisting_file_is_not_claimed_or_removed(
        self, stack, tmp_path
    ):
        """An unchanged file is not proof that this builder created it."""
        output = tmp_path / "demo"
        (output / "configs").mkdir(parents=True)
        old = output / "configs" / "demo.yaml"
        old.write_text("name: demo\n")
        write_agent_files(stack, str(output), "demo")

        files = stack.agent.environment.env_vars["generated_files"]
        files["configs/renamed.yaml"] = files.pop("configs/demo.yaml")
        result = write_agent_files(stack, str(output), "demo")

        assert not result.is_error
        assert old.read_text() == "name: demo\n"
        assert "configs/demo.yaml" in result.content["preserved"]

    def test_ownership_is_scoped_to_output_directory(self, stack, tmp_path):
        """Writes in one destination never authorize deletion in another."""
        first = tmp_path / "first"
        second = tmp_path / "second"
        write_agent_files(stack, str(first), "demo")
        (second / "configs").mkdir(parents=True)
        keep = second / "configs" / "demo.yaml"
        keep.write_text("name: demo\n")

        files = stack.agent.environment.env_vars["generated_files"]
        files["configs/renamed.yaml"] = files.pop("configs/demo.yaml")
        result = write_agent_files(stack, str(second), "demo")

        assert not result.is_error
        assert keep.exists()
        assert "configs/demo.yaml" in result.content["preserved"]


class TestNoFollowWrites:
    """Every directory hop is protected, not only the final filename."""

    def test_refuses_symlinked_parent_even_when_target_stays_inside_root(
        self, tmp_path
    ):
        """A parent symlink cannot redirect the descriptor-relative write."""
        root = tmp_path / "agent"
        real = root / "real-tools"
        real.mkdir(parents=True)
        (root / "tools").symlink_to(real, target_is_directory=True)

        with pytest.raises(PathConfinementError):
            _write_confined(root, "tools/escape.py", "escaped = True\n")

        assert not (real / "escape.py").exists()


class TestHomeDirectoryExpansion:
    """One half of check_output_path expanded ~ and the other did not."""

    def test_tilde_home_is_refused(self):
        """The guard whose only job is refusing $HOME must see it."""
        assert check_output_path("~") is not None

    def test_tilde_subpath_is_allowed_but_expanded(self, stack, tmp_path):
        """~ paths must not create a literal '~' directory in the cwd."""
        assert check_output_path("~/agents/demo") is None

    def test_wizard_returns_the_expanded_home_path(self, monkeypatch, tmp_path):
        """Validation and the path handed to the builder must agree."""
        answers = iter(["demo", "description", "haiku-latest", "~/agents/demo"])
        confirmations = iter([True, True])
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(
            create_agent, "prompt_user", lambda *args, **kwargs: next(answers)
        )
        monkeypatch.setattr(
            create_agent,
            "prompt_yes_no",
            lambda *args, **kwargs: next(confirmations),
        )
        monkeypatch.setattr(create_agent, "show_header", lambda *args: None)

        result = create_agent.run_wizard(builder_model="builder-model")

        assert result["output_path"] == str(tmp_path / "agents" / "demo")


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

    def test_run_command_shell_quotes_output_path(self):
        """Spaces in a user-selected output directory remain one argument."""
        command = run_command("/tmp/my generated agent", "main")

        assert shlex.split(command) == [
            "uv",
            "run",
            "hugin",
            "run",
            "--task",
            "main",
            "--task-path",
            "/tmp/my generated agent",
        ]

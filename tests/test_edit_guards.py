"""The two guards that bound what an unattended edit can destroy.

An edit rewrites files in place. Interactively that is fine -- a diff is shown
and the user can decline. Under ``--yes`` nobody sees it, so the blast radius
has to be bounded before the run rather than reviewed after it.
"""

import argparse
import subprocess
from types import SimpleNamespace

import pytest

from gimle.hugin.apps.agent_builder.git_guard import uncommitted_changes
from gimle.hugin.apps.agent_builder.tools.load_agent_files import (
    load_agent_files,
)
from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
    write_agent_files,
)
from gimle.hugin.cli.create_agent import run_edit_wizard

CONFIG = (
    "name: demo\n"
    "description: A demo agent\n"
    "system_template: demo_system\n"
    "tools:\n"
    "  - builtins.finish:finish\n"
)
TASK = "name: main\ndescription: The demo task\nprompt: Do the thing.\n"
TEMPLATE = "name: demo_system\ntemplate: You are a demo agent.\n"


def _args(**overrides):
    values = {
        "edit": None,
        "instruction": "change something",
        "yes": True,
        "dry_run": False,
        "builder_model": None,
        "allow_dirty": False,
        "only": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture
def agent_dir(tmp_path):
    """An agent on disk, not under version control."""
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


def _git(arguments, cwd):
    subprocess.run(
        ["git", *arguments], cwd=str(cwd), check=True, capture_output=True
    )


@pytest.fixture
def repo(agent_dir):
    """Put the agent in a git repository with everything committed."""
    _git(["init", "-q"], agent_dir)
    _git(["config", "user.email", "t@example.com"], agent_dir)
    _git(["config", "user.name", "t"], agent_dir)
    _git(["add", "-A"], agent_dir)
    _git(["commit", "-qm", "initial"], agent_dir)
    return agent_dir


class TestTheDirtyTreeGuard:
    """Version control is the only undo an in-place edit has."""

    def test_a_clean_repository_reports_nothing(self, repo):
        assert uncommitted_changes(repo) == []

    def test_an_uncommitted_change_is_reported(self, repo):
        (repo / "configs" / "demo.yaml").write_text(CONFIG + "# edited\n")

        assert uncommitted_changes(repo)

    def test_a_directory_outside_git_has_no_opinion(self, agent_dir):
        """None means "cannot check", which must not read as "clean"."""
        assert uncommitted_changes(agent_dir) is None

    def test_an_unattended_edit_into_a_dirty_tree_is_refused(self, repo):
        """--yes is exactly when nobody is there to see the diff."""
        (repo / "configs" / "demo.yaml").write_text(CONFIG + "# edited\n")

        with pytest.raises(SystemExit) as exit_info:
            run_edit_wizard(_args(edit=str(repo), yes=True))

        assert exit_info.value.code == 2

    def test_allow_dirty_overrides_it(self, repo):
        """The escape hatch has to actually work, or people stop using -y."""
        (repo / "configs" / "demo.yaml").write_text(CONFIG + "# edited\n")

        result = run_edit_wizard(
            _args(edit=str(repo), yes=True, allow_dirty=True)
        )

        assert result["agent_path"] == str(repo.resolve())

    def test_an_unversioned_agent_is_not_refused(self, agent_dir):
        """Unversioned agents are ordinary; refusing them protects nothing."""
        result = run_edit_wizard(_args(edit=str(agent_dir), yes=True))

        assert result["agent_path"] == str(agent_dir.resolve())


class TestTheAuthorisedWriteList:
    """`--only` bounds the edit deterministically, without guessing."""

    @pytest.fixture
    def stack(self, agent_dir):
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
        return stack

    def _regenerate(self, stack, key, content):
        stack.agent.environment.env_vars["generated_files"][key] = content

    def test_a_write_outside_the_list_is_refused(self, stack, agent_dir):
        """The protection an unattended edit does not otherwise have."""
        env_vars = stack.agent.environment.env_vars
        env_vars["authorised_keys"] = ["templates/demo_system.yaml"]
        self._regenerate(stack, "configs/demo.yaml", CONFIG + "# extra\n")

        response = write_agent_files(stack, str(agent_dir))

        assert response.is_error
        assert response.content["unauthorised"] == ["configs/demo.yaml"]

    def test_nothing_is_written_when_one_file_is_unauthorised(
        self, stack, agent_dir
    ):
        """Refuse the edit, not just the offending file: a half-applied
        edit is harder to reason about than none of it."""
        env_vars = stack.agent.environment.env_vars
        env_vars["authorised_keys"] = ["templates/demo_system.yaml"]
        self._regenerate(stack, "configs/demo.yaml", CONFIG + "# extra\n")
        self._regenerate(
            stack, "templates/demo_system.yaml", TEMPLATE + "# ok\n"
        )

        write_agent_files(stack, str(agent_dir))

        assert (
            agent_dir / "templates" / "demo_system.yaml"
        ).read_text() == TEMPLATE

    def test_a_write_inside_the_list_goes_through(self, stack, agent_dir):
        env_vars = stack.agent.environment.env_vars
        env_vars["authorised_keys"] = ["templates/demo_system.yaml"]
        self._regenerate(
            stack, "templates/demo_system.yaml", TEMPLATE + "# ok\n"
        )

        response = write_agent_files(stack, str(agent_dir))

        assert not response.is_error, response.content
        assert response.content["written"] == ["templates/demo_system.yaml"]

    def test_no_list_authorises_everything(self, stack, agent_dir):
        """The flag is opt-in; without it nothing changes."""
        self._regenerate(stack, "configs/demo.yaml", CONFIG + "# extra\n")

        response = write_agent_files(stack, str(agent_dir))

        assert not response.is_error, response.content

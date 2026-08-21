"""An installed Hugin must be able to open the examples it advertises.

`examples/` lives at the repository root, outside the `src/gimle` package, so
it never reaches a wheel. `list_examples` nonetheless advertised those examples
by name from hardcoded metadata -- so every pip-installed builder was told
sixteen examples existed and could not open one of them. The build prompt even
carried a fallback instruction for it.

A curated copy now ships inside the package. That is two copies of the same
files, so the first test here is the one that keeps them honest.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from gimle.hugin.apps.agent_builder.tools.example_files import (
    discover_examples_path,
    packaged_examples_path,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_EXAMPLES = REPO_ROOT / "examples"
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync_packaged_examples.py"


def _packaged_files():
    root = packaged_examples_path()
    return sorted(
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


class TestTheCopyDoesNotDrift:
    """Two copies of a file are a promise to keep them equal."""

    @pytest.mark.skipif(
        not SOURCE_EXAMPLES.is_dir(), reason="not a source checkout"
    )
    def test_every_packaged_file_matches_its_source(self):
        """Edit one and forget the other, and this fails.

        Resync with: uv run python scripts/sync_packaged_examples.py
        """
        mismatched = []
        for relative in _packaged_files():
            packaged = packaged_examples_path() / relative
            source = SOURCE_EXAMPLES / relative
            if not source.is_file():
                mismatched.append(f"{relative}: no longer in examples/")
            elif source.read_bytes() != packaged.read_bytes():
                mismatched.append(f"{relative}: differs from examples/")

        assert not mismatched, "\n".join(mismatched)

    @pytest.mark.skipif(
        not SOURCE_EXAMPLES.is_dir(), reason="not a source checkout"
    )
    def test_the_sync_script_is_idempotent(self):
        """Running it on a synced tree must change nothing."""
        before = {
            path: (packaged_examples_path() / path).read_bytes()
            for path in _packaged_files()
        }

        subprocess.run(
            [sys.executable, str(SYNC_SCRIPT)], check=True, capture_output=True
        )

        after = {
            path: (packaged_examples_path() / path).read_bytes()
            for path in _packaged_files()
        }
        assert before == after


class TestWhatShips:
    """The packaged set has to be usable, not merely present."""

    def test_it_exists_inside_the_package(self):
        """Outside `src/gimle` it would not reach a wheel at all."""
        packaged = packaged_examples_path()

        assert packaged.is_dir()
        assert "src/gimle" in str(packaged).replace("\\", "/") or (
            "site-packages" in str(packaged)
        )

    def test_it_covers_the_shapes_the_builder_is_asked_for(self):
        """One example per architecture the build prompt names."""
        names = {path.parts[0] for path in _packaged_files()}

        assert {
            "basic_agent",
            "tool_chaining",
            "task_sequences",
            "human_interaction",
            "sub_agent",
        } <= names

    def test_each_example_is_a_loadable_agent(self):
        """A packaged example that does not validate teaches the wrong shape."""
        for name in {path.parts[0] for path in _packaged_files()}:
            directory = packaged_examples_path() / name
            assert (directory / "configs").is_dir(), name
            assert (directory / "tasks").is_dir(), name

    def test_it_stays_small(self):
        """Everyone carries this, whether they build agents or not."""
        total = sum(
            (packaged_examples_path() / path).stat().st_size
            for path in _packaged_files()
        )

        assert total < 250_000, f"{total} bytes packaged"


class TestDiscovery:
    """The packaged copy is the last resort, never the first."""

    def test_it_is_found_when_nothing_else_is(self, tmp_path, monkeypatch):
        """The installed case: no env var, no source checkout."""
        from gimle.hugin.apps.agent_builder.tools import example_files

        monkeypatch.delenv("HUGIN_EXAMPLES_PATH", raising=False)
        monkeypatch.setattr(
            example_files,
            "source_examples_path",
            lambda: tmp_path / "nowhere" / "examples",
        )

        assert discover_examples_path() == packaged_examples_path().resolve()

    def test_an_explicit_path_still_wins(self, tmp_path, monkeypatch):
        """HUGIN_EXAMPLES_PATH must not be overridden by what we ship."""
        catalogue = tmp_path / "mine"
        (catalogue / "case" / "configs").mkdir(parents=True)
        monkeypatch.setenv("HUGIN_EXAMPLES_PATH", str(catalogue))

        assert discover_examples_path() == catalogue.resolve()

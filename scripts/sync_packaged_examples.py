"""Copy the curated examples into the package, so an installed Hugin has them.

`examples/` lives at the repository root and is not part of the `src/gimle`
package, so it does not ship in the wheel. The builder's `list_examples` and
`read_example` therefore return nothing in every installed distribution --
while `list_examples` still advertises the examples by name from hardcoded
metadata, so the builder is told they exist and then cannot open one.

The fix is a curated copy inside the package. That means two copies of the
same files, which is a drift risk, so `tests/test_packaged_examples.py`
asserts they are byte-identical and fails if anyone edits one without the
other. Run this script to resync:

    uv run python scripts/sync_packaged_examples.py
"""

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "examples"
PACKAGED = (
    REPO_ROOT
    / "src"
    / "gimle"
    / "hugin"
    / "apps"
    / "agent_builder"
    / "packaged_examples"
)

# One example per shape the builder is asked to produce. Not the whole
# catalogue: every file here is carried in the wheel by everyone, whether they
# build agents or not, so this is a working set rather than an archive.
CURATED = (
    "basic_agent",
    "tool_chaining",
    "task_sequences",
    "human_interaction",
    "sub_agent",
    "shared_state",
    "artifacts",
)

# Build artefacts and anything that is not a readable source file.
SKIP_DIRECTORIES = {"__pycache__", "storage", "artifacts_output", ".git"}
KEEP_SUFFIXES = {".yaml", ".yml", ".py", ".md"}


def wanted_files(root: Path):
    """Yield the files worth shipping, relative to ``root``."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRECTORIES for part in relative.parts):
            continue
        if path.suffix not in KEEP_SUFFIXES:
            continue
        yield relative


def sync() -> int:
    """Rewrite the packaged copy from the source examples."""
    if not SOURCE.is_dir():
        print(f"no examples directory at {SOURCE}")
        return 1

    if PACKAGED.exists():
        shutil.rmtree(PACKAGED)
    PACKAGED.mkdir(parents=True)

    total = 0
    for name in CURATED:
        source = SOURCE / name
        if not source.is_dir():
            print(f"curated example missing from {SOURCE}: {name}")
            return 1
        for relative in wanted_files(source):
            destination = PACKAGED / name / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, destination)
            total += 1

    size = sum(p.stat().st_size for p in PACKAGED.rglob("*") if p.is_file())
    print(f"synced {total} file(s) from {len(CURATED)} example(s)")
    print(f"packaged size: {size / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(sync())

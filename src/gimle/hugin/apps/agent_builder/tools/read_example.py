"""Tool: read_example.

Read detailed information about a specific Hugin example.
Includes README, config, task, template, and optionally tool implementations.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.apps.agent_builder.tools.example_files import (
    MAX_EXAMPLE_BYTES,
    MAX_EXAMPLE_FILES,
    ReadBudget,
    child_directory_names,
    discover_examples_path,
    has_child_directory,
    open_child_directory,
    open_directory,
    read_optional_text_file,
    read_text_file,
)
from gimle.hugin.tools.tool import ToolResponse


def _get_examples_path() -> Optional[Path]:
    """Discover an explicit or source-checkout examples path."""
    return discover_examples_path()


def _confine_example(examples_path: Path, name: str) -> Optional[Path]:
    """Validate ``name`` as one directory beneath ``examples_path``.

    ``example_name`` is chosen by the model, and ``examples_path / name`` is
    the same unconfined join the writer side guards against: ``pathlib`` does
    not normalise ``..`` and an absolute operand replaces the left-hand side
    entirely. Unconfined, this tool read any directory on the host that
    happened to look like an example -- another repo, the builder's own source
    -- straight into model context and into persisted interaction JSON.

    A single path component is all a legitimate example name ever needs, so the
    rule is deliberately narrow rather than clever.
    """
    if not name or name.strip() != name:
        return None
    if name in (".", "..") or "/" in name or "\\" in name:
        return None
    if Path(name).is_absolute() or name.startswith("~"):
        return None
    return examples_path / name


def _read_yaml_files(
    example_fd: int, directory_name: str, budget: ReadBudget
) -> List[Dict[str, str]]:
    """Read YAML files from one real child directory."""
    files: List[Dict[str, str]] = []
    if not has_child_directory(example_fd, directory_name):
        return files

    with open_child_directory(example_fd, directory_name) as directory_fd:
        for filename in sorted(os.listdir(directory_fd)):
            if Path(filename).suffix in (".yaml", ".yml"):
                files.append(
                    {
                        "filename": filename,
                        "content": read_text_file(
                            directory_fd, filename, budget
                        ),
                    }
                )
    return files


def _read_tool_files(
    example_fd: int, budget: ReadBudget
) -> List[Dict[str, Any]]:
    """Read tool implementations from a real child directory."""
    tools: List[Dict[str, Any]] = []
    if not has_child_directory(example_fd, "tools"):
        return tools

    with open_child_directory(example_fd, "tools") as tools_fd:
        filenames = sorted(os.listdir(tools_fd))
        tool_names = {
            Path(filename).stem
            for filename in filenames
            if Path(filename).suffix in (".yaml", ".yml")
        }

        for tool_name in sorted(tool_names):
            tool_info: Dict[str, Any] = {"name": tool_name}
            yaml_content = read_optional_text_file(
                tools_fd, f"{tool_name}.yaml", budget
            )
            if yaml_content is None:
                yaml_content = read_optional_text_file(
                    tools_fd, f"{tool_name}.yml", budget
                )
            if yaml_content is not None:
                tool_info["yaml"] = yaml_content

            python_content = read_optional_text_file(
                tools_fd, f"{tool_name}.py", budget
            )
            if python_content is not None:
                tool_info["python"] = python_content

            if "yaml" in tool_info or "python" in tool_info:
                tools.append(tool_info)

    return tools


def read_example(
    example_name: str,
    include_tools: bool = False,
) -> ToolResponse:
    """
    Read detailed information about a specific Hugin example.

    Args:
        example_name: Name of the example to read
        include_tools: Whether to include tool implementations (can be verbose)

    Returns:
        ToolResponse with example details
    """
    try:
        examples_path = _get_examples_path()
        if not examples_path:
            return ToolResponse(
                is_error=True,
                content={
                    "error": "Examples folder not found. Cannot read example details.",
                    "hint": "Set HUGIN_EXAMPLES_PATH to a trusted examples "
                    "directory, or use a source checkout.",
                },
            )

        example_dir = _confine_example(examples_path, example_name)
        if example_dir is None:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"'{example_name}' is not an example name. Pass a "
                        "single name from list_examples, not a path."
                    )
                },
            )
        budget = ReadBudget(
            max_files=MAX_EXAMPLE_FILES, max_bytes=MAX_EXAMPLE_BYTES
        )
        with open_directory(examples_path) as examples_fd:
            available = [
                name
                for name in child_directory_names(examples_fd)
                if not name.startswith(".") and not name.startswith("_")
            ]
            if example_name not in available:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": f"Example '{example_name}' not found.",
                        "available_examples": available,
                    },
                )

            with open_child_directory(examples_fd, example_name) as example_fd:
                result: Dict[str, Any] = {"name": example_name}

                readme = read_optional_text_file(
                    example_fd, "README.md", budget
                )
                if readme is not None:
                    result["readme"] = readme

                configs = _read_yaml_files(example_fd, "configs", budget)
                if configs:
                    result["configs"] = configs

                tasks = _read_yaml_files(example_fd, "tasks", budget)
                if tasks:
                    result["tasks"] = tasks

                templates = _read_yaml_files(example_fd, "templates", budget)
                if templates:
                    result["templates"] = templates

                if include_tools:
                    tools = _read_tool_files(example_fd, budget)
                    if tools:
                        result["tools"] = tools

        return ToolResponse(
            is_error=False,
            content=result,
        )

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to read example: {e}"},
        )

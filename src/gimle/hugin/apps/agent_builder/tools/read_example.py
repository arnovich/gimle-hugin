"""Tool: read_example.

Read detailed information about a specific Hugin example.
Includes README, config, task, template, and optionally tool implementations.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.tools.tool import ToolResponse


def _get_examples_path() -> Optional[Path]:
    """Discover examples path with multiple fallbacks."""
    # Try 1: Relative to hugin package (src/gimle/hugin -> examples)
    hugin_path = Path(__file__).parent.parent.parent.parent.parent
    examples_path = hugin_path.parent.parent / "examples"
    if examples_path.exists() and examples_path.is_dir():
        return examples_path

    # Try 2: Environment variable
    env_path = os.environ.get("HUGIN_EXAMPLES_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists() and path.is_dir():
            return path

    # Try 3: Current working directory
    cwd_examples = Path.cwd() / "examples"
    if cwd_examples.exists() and cwd_examples.is_dir():
        return cwd_examples

    return None


def _read_yaml_files(directory: Path) -> List[Dict[str, str]]:
    """Read all YAML files in a directory."""
    files: List[Dict[str, str]] = []
    if not directory.exists():
        return files
    for item in sorted(directory.iterdir()):
        if item.suffix in (".yaml", ".yml"):
            try:
                files.append(
                    {
                        "filename": item.name,
                        "content": item.read_text(),
                    }
                )
            except Exception:
                pass
    return files


def _read_tool_files(tools_dir: Path) -> List[Dict[str, Any]]:
    """Read tool implementations (both .py and .yaml)."""
    tools: List[Dict[str, Any]] = []
    if not tools_dir.exists():
        return tools

    # Find all tool names (from .yaml files)
    tool_names = set()
    for item in tools_dir.iterdir():
        if item.suffix in (".yaml", ".yml"):
            tool_names.add(item.stem)

    for tool_name in sorted(tool_names):
        tool_info: Dict[str, Any] = {"name": tool_name}

        yaml_file = tools_dir / f"{tool_name}.yaml"
        py_file = tools_dir / f"{tool_name}.py"

        if yaml_file.exists():
            try:
                tool_info["yaml"] = yaml_file.read_text()
            except Exception:
                pass

        if py_file.exists():
            try:
                tool_info["python"] = py_file.read_text()
            except Exception:
                pass

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
                    "hint": "Set HUGIN_EXAMPLES_PATH environment variable "
                    "or run from project root.",
                },
            )

        example_dir = examples_path / example_name
        if not example_dir.exists() or not example_dir.is_dir():
            # List available examples to help the user
            available = [
                d.name
                for d in examples_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Example '{example_name}' not found.",
                    "available_examples": sorted(available),
                },
            )

        result: Dict[str, Any] = {"name": example_name}

        # Read README
        readme_path = example_dir / "README.md"
        if readme_path.exists():
            try:
                result["readme"] = readme_path.read_text()
            except Exception:
                pass

        # Read configs
        configs = _read_yaml_files(example_dir / "configs")
        if configs:
            result["configs"] = configs

        # Read tasks
        tasks = _read_yaml_files(example_dir / "tasks")
        if tasks:
            result["tasks"] = tasks

        # Read templates
        templates = _read_yaml_files(example_dir / "templates")
        if templates:
            result["templates"] = templates

        # Read tools if requested
        if include_tools:
            tools = _read_tool_files(example_dir / "tools")
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

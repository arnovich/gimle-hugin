"""Tool: list_examples.

List available Hugin examples with descriptions and key concepts.
Fault-tolerant: falls back to hardcoded metadata if filesystem unavailable.
"""

import os
import re
from pathlib import Path
from typing import List, Optional

from gimle.hugin.tools.tool import ToolResponse

# Hardcoded fallback metadata for when examples folder is unavailable
FALLBACK_EXAMPLES = [
    {
        "name": "basic_agent",
        "description": "Simplest possible agent",
        "key_concept": "Agent structure basics",
        "category": "basic",
        "has_tools": False,
    },
    {
        "name": "tool_chaining",
        "description": "Deterministic pipelines",
        "key_concept": "next_tool in ToolResponse",
        "category": "basic",
        "has_tools": True,
    },
    {
        "name": "task_chaining",
        "description": "Sequential tasks with result passing",
        "key_concept": "next_task, pass_result_as",
        "category": "basic",
        "has_tools": False,
    },
    {
        "name": "task_sequences",
        "description": "Multi-stage pipelines",
        "key_concept": "task_sequence array",
        "category": "basic",
        "has_tools": True,
    },
    {
        "name": "human_interaction",
        "description": "Human-in-the-loop approval",
        "key_concept": "AskHuman, HumanResponse",
        "category": "basic",
        "has_tools": True,
    },
    {
        "name": "sub_agent",
        "description": "Parent spawns child agents",
        "key_concept": "builtins.launch_agent",
        "category": "multi_agent",
        "has_tools": False,
    },
    {
        "name": "parallel_agents",
        "description": "Side-by-side independent agents",
        "key_concept": "session.step()",
        "category": "multi_agent",
        "has_tools": False,
    },
    {
        "name": "agent_messaging",
        "description": "Direct peer-to-peer messaging",
        "key_concept": "agent.message_agent()",
        "category": "multi_agent",
        "has_tools": True,
    },
    {
        "name": "shared_state",
        "description": "Multi-agent state sharing",
        "key_concept": "session.state, namespaces",
        "category": "multi_agent",
        "has_tools": True,
    },
    {
        "name": "self_reflection",
        "description": "Self-critique via task chaining",
        "key_concept": "chain_config for model switching",
        "category": "reflection",
        "has_tools": False,
    },
    {
        "name": "reflexion",
        "description": "Multi-agent reflection with critic",
        "key_concept": "launch_agent for evaluation",
        "category": "reflection",
        "has_tools": False,
    },
    {
        "name": "artifacts",
        "description": "Long-term persistent memory",
        "key_concept": "save_insight, query_artifacts",
        "category": "advanced",
        "has_tools": False,
    },
    {
        "name": "branching",
        "description": "Parallel exploration of approaches",
        "key_concept": "create_branch, stack isolation",
        "category": "advanced",
        "has_tools": True,
    },
    {
        "name": "simple_branching",
        "description": "Basic branching with artifact output",
        "key_concept": "create_branch for follow-up questions",
        "category": "advanced",
        "has_tools": True,
    },
    {
        "name": "plan_execute_agent",
        "description": "Mode switching state machine",
        "key_concept": "state_machine, transitions",
        "category": "advanced",
        "has_tools": False,
    },
    {
        "name": "custom_artifacts",
        "description": "Extend artifact system with custom types",
        "key_concept": "@Artifact.register, custom UI",
        "category": "advanced",
        "has_tools": True,
    },
]


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


def _parse_readme_description(readme_path: Path) -> Optional[str]:
    """Extract description from example README."""
    try:
        content = readme_path.read_text()
        # Look for first paragraph after the title
        lines = content.split("\n")
        description_lines: List[str] = []
        in_description = False
        for line in lines:
            if line.startswith("# "):
                in_description = True
                continue
            if in_description:
                if line.strip() == "":
                    if description_lines:
                        break
                    continue
                if line.startswith("#"):
                    break
                description_lines.append(line.strip())
        if description_lines:
            return " ".join(description_lines)[:200]
    except Exception:
        pass
    return None


def _parse_key_concept(readme_path: Path) -> Optional[str]:
    """Extract key concept from example README."""
    try:
        content = readme_path.read_text()
        # Look for "Key Concept" or similar patterns
        match = re.search(
            r"(?:Key Concept|Demonstrates|Shows)[:\s]+(.+?)(?:\n|$)",
            content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()[:100]
    except Exception:
        pass
    return None


def _detect_category(example_name: str) -> str:
    """Infer category from example name."""
    multi_agent_keywords = [
        "agent",
        "messaging",
        "shared",
        "parallel",
        "sub_agent",
    ]
    reflection_keywords = ["reflection", "reflexion", "critique"]
    advanced_keywords = ["artifact", "branch", "state_machine", "custom"]

    name_lower = example_name.lower()
    for keyword in multi_agent_keywords:
        if keyword in name_lower:
            return "multi_agent"
    for keyword in reflection_keywords:
        if keyword in name_lower:
            return "reflection"
    for keyword in advanced_keywords:
        if keyword in name_lower:
            return "advanced"
    return "basic"


def _list_from_filesystem(
    examples_path: Path, category: Optional[str]
) -> List[dict]:
    """List examples from filesystem."""
    examples = []
    for item in sorted(examples_path.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith(".") or item.name.startswith("_"):
            continue

        readme_path = item / "README.md"
        tools_dir = item / "tools"

        example_info = {
            "name": item.name,
            "description": (
                _parse_readme_description(readme_path)
                if readme_path.exists()
                else None
            ),
            "key_concept": (
                _parse_key_concept(readme_path)
                if readme_path.exists()
                else None
            ),
            "category": _detect_category(item.name),
            "has_tools": tools_dir.exists() and tools_dir.is_dir(),
        }

        # Apply category filter
        if category and example_info["category"] != category:
            continue

        examples.append(example_info)

    return examples


def _list_from_fallback(category: Optional[str]) -> List[dict]:
    """List examples from hardcoded fallback."""
    if category:
        return [ex for ex in FALLBACK_EXAMPLES if ex["category"] == category]
    return FALLBACK_EXAMPLES.copy()


def list_examples(
    category: Optional[str] = None,
) -> ToolResponse:
    """
    List available Hugin examples with descriptions and key concepts.

    Args:
        stack: Agent stack (auto-injected)
        category: Filter by category (basic, multi_agent, reflection, advanced)
        branch: Branch identifier (auto-injected)

    Returns:
        ToolResponse with list of examples
    """
    try:
        examples_path = _get_examples_path()
        if examples_path:
            examples = _list_from_filesystem(examples_path, category)
            source = "filesystem"
        else:
            examples = _list_from_fallback(category)
            source = "fallback"

        categories = list(set(ex["category"] for ex in FALLBACK_EXAMPLES))

        return ToolResponse(
            is_error=False,
            content={
                "examples": examples,
                "total": len(examples),
                "categories": sorted(categories),
                "source": source,
            },
        )

    except Exception as e:
        # Graceful degradation - return fallback with warning
        examples = _list_from_fallback(category)
        return ToolResponse(
            is_error=False,
            content={
                "examples": examples,
                "total": len(examples),
                "categories": [
                    "basic",
                    "multi_agent",
                    "reflection",
                    "advanced",
                ],
                "source": "fallback",
                "warning": f"Could not read live examples: {e}",
            },
        )

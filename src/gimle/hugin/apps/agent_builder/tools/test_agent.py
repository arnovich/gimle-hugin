"""Test a newly created agent to verify it works."""

import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import (
    Environment,
    invalidate_modules_under,
    unregister_tools_under,
)
from gimle.hugin.agent.task import Task
from gimle.hugin.apps.agent_builder.tools.validate_agent import (
    AgentReadError,
    collect_files,
    validate_files,
)
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)
_EXPLICIT_TEMPLATE_REFERENCE = re.compile(
    r"^\s*\{\{\s*([a-z][a-z0-9]*(?:_[a-z0-9]+)*)\.template\s*\}\}\s*$"
)


def _select(items: list, name: Optional[str]) -> Optional[Any]:
    """Return the named item, or the only one when no name was given."""
    if name:
        for item in items:
            if item.name == name:
                return item
        return None
    return items[0] if len(items) == 1 else None


def _inline_template(
    reference: Optional[str], templates: Dict[str, Any]
) -> Optional[str]:
    """Expand a bare template reference to its body, if it is one.

    Leaves inline prompts untouched. Bare names and exact
    ``{{ name.template }}`` references are substituted to match the renderer.
    """
    if not reference:
        return reference
    explicit = _EXPLICIT_TEMPLATE_REFERENCE.fullmatch(reference)
    name = explicit.group(1) if explicit else reference
    template = templates.get(name)
    if template is None:
        return reference
    return str(getattr(template, "template", reference))


def test_agent(
    stack: "Stack",
    agent_path: str,
    test_prompt: str,
    config_name: Optional[str] = None,
    task_name: Optional[str] = None,
) -> Union[ToolResponse, AgentCall]:
    """Launch the agent at agent_path with test_prompt as a sub-agent.

    This tool loads the agent from the specified path and returns an AgentCall
    to spawn it as a child agent. The framework handles running it and returning
    results through the normal agent lifecycle.

    Args:
        stack: Agent stack (auto-injected)
        agent_path: Path to the agent directory to test
        test_prompt: Test input/prompt to give the agent

    Returns:
        AgentCall to spawn the test agent, or ToolResponse on error
    """
    agent_path_obj = Path(agent_path)
    if not agent_path_obj.is_absolute():
        agent_path_obj = agent_path_obj.resolve()

    # Validate agent path exists
    if not agent_path_obj.exists():
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Agent path does not exist: {agent_path}",
            },
        )

    try:
        files = collect_files(str(agent_path_obj))
    except AgentReadError as error:
        return ToolResponse(is_error=True, content={"error": str(error)})

    if not any(key.startswith("configs/") for key in files):
        return ToolResponse(
            is_error=True,
            content={"error": "No configs found in agent directory"},
        )
    if not any(key.startswith("tasks/") for key in files):
        return ToolResponse(
            is_error=True,
            content={"error": "No tasks found in agent directory"},
        )

    report = validate_files(files, agent_path=str(agent_path_obj))
    if not report["ok"]:
        first = report["errors"][0]
        label = (
            "Syntax error" if first["check"] == "syntax" else "Validation error"
        )
        return ToolResponse(
            is_error=True,
            content={
                "error": f"{label} in {first['file']}: {first['message']}",
                "errors": report["errors"],
            },
        )

    try:
        # Add agent path's parent to sys.path so modules can be imported
        parent_path = str(agent_path_obj.parent)
        if parent_path in sys.path:
            sys.path.remove(parent_path)
        sys.path.insert(0, parent_path)

        # Add tools folder to sys.path
        tools_path = str(agent_path_obj / "tools")
        if tools_path in sys.path:
            sys.path.remove(tools_path)
        sys.path.insert(0, tools_path)

        # Drop any cached modules from a previous run of this same agent.
        # Without this a fix-and-retest loop re-imports the code it already
        # has, sees the identical failure, and spends every attempt on a
        # defect that was repaired on disk after the first import.
        unregistered = unregister_tools_under(str(agent_path_obj))
        if unregistered:
            logger.info("Unregistering %d stale tool(s)", len(unregistered))
        dropped = invalidate_modules_under(str(agent_path_obj))
        if dropped:
            logger.info("Reloading %d changed module(s)", len(dropped))

        # Load the agent's environment to get configs, tasks, tools, templates
        # We use None storage since we just need to load the definitions
        import tempfile

        from gimle.hugin.storage.local import LocalStorage

        # Use a temp dir for loading (we won't actually store anything)
        with tempfile.TemporaryDirectory(prefix="test_agent_load_") as temp_dir:
            temp_storage = LocalStorage(base_path=temp_dir)
            try:
                test_env = Environment.load(
                    str(agent_path_obj),
                    storage=temp_storage,
                    replace_tools=False,
                )
            except Exception:
                # A later tool can fail after earlier ones registered. Keep a
                # refused test from leaking that partial agent process-wide.
                unregister_tools_under(str(agent_path_obj))
                raise

        # Get the config and task from the loaded environment
        configs = list(test_env.config_registry.registered().values())
        tasks = list(test_env.task_registry.registered().values())

        if not configs:
            return ToolResponse(
                is_error=True,
                content={"error": "No configs found in agent directory"},
            )

        if not tasks:
            return ToolResponse(
                is_error=True,
                content={"error": "No tasks found in agent directory"},
            )

        # Explicit selection: picking configs[0] made the tested agent depend
        # on registry iteration order, so a multi-config agent could be tested
        # through a config the description never asked for.
        source_config = _select(configs, config_name)
        source_task = _select(tasks, task_name)
        if source_config is None:
            selection_error = (
                f"No config named '{config_name}' in {agent_path}"
                if config_name
                else "Multiple configs found; specify config_name"
            )
            return ToolResponse(
                is_error=True,
                content={
                    "error": selection_error,
                    "available": sorted(c.name for c in configs),
                },
            )
        if source_task is None:
            selection_error = (
                f"No task named '{task_name}' in {agent_path}"
                if task_name
                else "Multiple tasks found; specify task_name"
            )
            return ToolResponse(
                is_error=True,
                content={
                    "error": selection_error,
                    "available": sorted(t.name for t in tasks),
                },
            )

        # The child agent renders against the *parent's* registry, because
        # AgentCall carries no environment of its own. Rather than copy the
        # tested agent's templates in -- which leaked its prompts into the
        # builder's namespace, and left a stale body behind when a repair
        # regenerated one -- resolve the reference to its literal text here.
        # An inline system prompt is a documented form, so nothing is lost.
        templates = test_env.template_registry.registered()
        system_template = _inline_template(
            source_config.system_template, templates
        )
        task_template = _inline_template(source_task.system_template, templates)

        # Create a new config with the loaded settings
        # Tools are already registered globally by Environment.load()
        config = Config(
            name=f"test_{source_config.name}",
            description=f"Test run of {source_config.name}",
            system_template=system_template or "",
            llm_model=source_config.llm_model,
            tools=source_config.tools,
            interactive=False,
        )

        # Create task with the test prompt
        task = Task(
            name=f"test_{source_task.name}",
            description=f"Test: {test_prompt}",
            parameters={},
            prompt=test_prompt,
            tools=source_task.tools or config.tools,
            system_template=task_template or config.system_template,
        )

        logger.info(f"Launching test agent from {agent_path}")

        return AgentCall(
            stack=stack,
            config=config,
            task=task,
        )

    except SyntaxError as e:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Syntax error in agent code: {e}",
                "file": getattr(e, "filename", "unknown"),
                "line": getattr(e, "lineno", "unknown"),
            },
        )

    except ImportError as e:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Import error (missing dependency?): {e}",
            },
        )

    except Exception as e:
        import traceback

        logger.error(f"Error loading agent: {e}")
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Error loading agent: {type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            },
        )

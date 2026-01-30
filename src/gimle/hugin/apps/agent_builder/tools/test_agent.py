"""Test a newly created agent to verify it works."""

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Union

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)


def test_agent(
    stack: "Stack",
    agent_path: str,
    test_prompt: str,
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
        # Add agent path's parent to sys.path so modules can be imported
        parent_path = str(agent_path_obj.parent)
        if parent_path not in sys.path:
            sys.path.insert(0, parent_path)

        # Add tools folder to sys.path
        tools_path = str(agent_path_obj / "tools")
        if tools_path not in sys.path:
            sys.path.insert(0, tools_path)

        # Load the agent's environment to get configs, tasks, tools, templates
        # We use None storage since we just need to load the definitions
        import tempfile

        from gimle.hugin.storage.local import LocalStorage

        # Use a temp dir for loading (we won't actually store anything)
        with tempfile.TemporaryDirectory(prefix="test_agent_load_") as temp_dir:
            temp_storage = LocalStorage(base_path=temp_dir)
            test_env = Environment.load(
                str(agent_path_obj), storage=temp_storage
            )

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

        # Use the first config and task
        source_config = configs[0]
        source_task = tasks[0]

        # Create a new config with the loaded settings
        # Tools are already registered globally by Environment.load()
        config = Config(
            name=f"test_{source_config.name}",
            description=f"Test run of {source_config.name}",
            system_template=source_config.system_template,
            llm_model=source_config.llm_model,
            tools=source_config.tools,
            interactive=False,
        )

        # Register templates from the test environment into the current environment
        current_env = stack.agent.environment
        for (
            template_name,
            template,
        ) in test_env.template_registry.registered().items():
            if template_name not in current_env.template_registry.registered():
                current_env.template_registry.register(template)

        # Create task with the test prompt
        task = Task(
            name=f"test_{source_task.name}",
            description=f"Test: {test_prompt}",
            parameters={},
            prompt=test_prompt,
            tools=source_task.tools or config.tools,
            system_template=source_task.system_template
            or config.system_template,
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

"""Generate task YAML."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import yaml

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def generate_task(
    task_name: str,
    description: str,
    prompt: str,
    stack: "Stack",
    parameters: Optional[Dict[str, Any]] = None,
    tools: Optional[List[str]] = None,
    task_sequence: Optional[List[str]] = None,
    next_task: Optional[str] = None,
    pass_result_as: Optional[str] = None,
    chain_config: Optional[str] = None,
    system_template: Optional[str] = None,
) -> ToolResponse:
    """Generate a task definition YAML.

    Args:
        task_name: Name of the task (snake_case)
        description: Human-readable description
        prompt: The prompt template with Jinja2 syntax
        stack: Agent stack (auto-injected)
        parameters: Dictionary of parameter names to parameter schema dicts.
            Each parameter schema MUST include at least:
              - type: string|integer|number|boolean|array|object|categorical
              - description: string
            Optional:
              - required: bool
              - default: any
              - choices: list[str] (required for categorical)
        tools: List of tool names (optional)

    Returns:
        ToolResponse with generated task content
    """
    if parameters is not None:
        for name, spec in parameters.items():
            # spec is Any from Dict[str, Any], so runtime check is needed
            if not isinstance(spec, dict):
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": (
                            f"Task parameter '{name}' must be a schema dict "
                            "(must include 'type' and 'description'). "
                            "Old scalar-style parameters are not supported."
                        )
                    },
                )
            if "type" not in spec or "description" not in spec:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": (
                            f"Task parameter '{name}' schema must include "
                            "'type' and 'description'."
                        )
                    },
                )
            if spec.get("type") == "categorical":
                choices = spec.get("choices")
                if not isinstance(choices, list) or not all(
                    isinstance(c, str) for c in choices
                ):
                    return ToolResponse(
                        is_error=True,
                        content={
                            "error": (
                                f"Categorical parameter '{name}' must include "
                                "'choices' as a list of strings."
                            )
                        },
                    )

    task_data: Dict[str, Any] = {
        "name": task_name,
        "description": description,
        "parameters": parameters or {},
        "prompt": prompt,
    }

    if tools:
        task_data["tools"] = tools

    # Multi-stage fields. Without these the generator could only ever emit a
    # flat, single-task agent -- it had no way to express the chaining the
    # framework supports and its own build pipeline uses. A golden-set eval
    # confirmed the consequence: neither pipeline case produced a chained
    # agent, because there was no field to put the chain in.
    if task_sequence:
        task_data["task_sequence"] = list(task_sequence)
    if next_task:
        task_data["next_task"] = next_task
    if pass_result_as:
        task_data["pass_result_as"] = pass_result_as
    if chain_config:
        task_data["chain_config"] = chain_config
    if system_template:
        task_data["system_template"] = system_template

    task_yaml = yaml.dump(task_data, default_flow_style=False, sort_keys=False)

    # Store in environment for later writing
    generated_files = stack.agent.environment.env_vars.setdefault(
        "generated_files", {}
    )
    generated_files[f"tasks/{task_name}.yaml"] = task_yaml

    return ToolResponse(
        is_error=False,
        content={
            "file_path": f"tasks/{task_name}.yaml",
            "content": task_yaml,
            "message": f"Generated task: {task_name}",
        },
    )

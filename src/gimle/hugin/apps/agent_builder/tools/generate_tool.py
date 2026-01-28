"""Generate tool Python and YAML files."""

from typing import TYPE_CHECKING, Any, Dict, Optional

import yaml

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def validate_python_syntax(code: str) -> Optional[str]:
    """Validate Python syntax, return error message or None if valid."""
    try:
        compile(code, "<string>", "exec")
        return None
    except SyntaxError as e:
        return f"Syntax error at line {e.lineno}: {e.msg}"


def generate_tool(
    tool_name: str,
    description: str,
    parameters_schema: Dict[str, Any],
    implementation_code: str,
    agent_name: str,
    stack: "Stack",
) -> ToolResponse:
    """Generate tool Python implementation and YAML definition.

    Args:
        tool_name: Name of the tool (snake_case)
        description: What the tool does
        parameters_schema: Dict of parameter definitions
        implementation_code: Python code for the function body
        agent_name: Name of the agent (for import path)
        stack: Agent stack (auto-injected)

    Returns:
        ToolResponse with generated files info
    """
    # Build parameter signature for function definition
    param_parts = []
    for param_name, param_info in parameters_schema.items():
        required = param_info.get("required", True)
        if required:
            param_parts.append(f"{param_name}: str")
        else:
            param_parts.append(f"{param_name}: Optional[str] = None")

    param_signature = ", ".join(param_parts)
    if param_signature:
        param_signature += ", "

    # Build docstring parameters
    docstring_params = []
    for param_name, param_info in parameters_schema.items():
        param_desc = param_info.get("description", "No description")
        docstring_params.append(f"        {param_name}: {param_desc}")

    docstring_params_str = (
        "\n".join(docstring_params) if docstring_params else ""
    )

    # Indent implementation code
    impl_lines = implementation_code.strip().split("\n")
    indented_impl = "\n".join(
        "        " + line if line.strip() else "" for line in impl_lines
    )

    # Generate Python file content
    python_code = f'''"""Tool: {tool_name}

{description}
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def {tool_name}(
    {param_signature}stack: "Stack",
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    {description}

    Args:
{docstring_params_str}
        stack: Agent stack (auto-injected)
        branch: Branch identifier (auto-injected)

    Returns:
        ToolResponse with operation result
    """
    try:
{indented_impl}
    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={{"error": str(e)}},
        )
'''

    # Validate Python syntax
    syntax_error = validate_python_syntax(python_code)
    if syntax_error:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Generated Python code has syntax error: {syntax_error}",
                "code": python_code,
            },
        )

    # Generate YAML file content
    yaml_data = {
        "name": tool_name,
        "description": description,
        "parameters": parameters_schema,
        "is_interactive": False,
        "implementation_path": f"{agent_name}.tools.{tool_name}:{tool_name}",
        "options": {},
    }

    yaml_content = yaml.dump(
        yaml_data, default_flow_style=False, sort_keys=False
    )

    # Store both files in environment for later writing
    generated_files = stack.agent.environment.env_vars.setdefault(
        "generated_files", {}
    )
    generated_files[f"tools/{tool_name}.py"] = python_code
    generated_files[f"tools/{tool_name}.yaml"] = yaml_content

    return ToolResponse(
        is_error=False,
        content={
            "python_file": f"tools/{tool_name}.py",
            "yaml_file": f"tools/{tool_name}.yaml",
            "message": f"Generated tool: {tool_name}",
        },
    )

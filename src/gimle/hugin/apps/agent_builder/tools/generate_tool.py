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


# Helper code that gets included in generated tools for robust input parsing
PARSE_INPUT_HELPER = '''
def _parse_input(value: Any) -> Any:
    """Parse input that might be JSON string, Python repr, or already parsed.

    LLMs sometimes pass data as:
    - JSON strings (double quotes): '{"key": "value"}'
    - Python repr (single quotes): "{'key': 'value'}"
    - Already parsed dicts/lists

    This helper handles all these cases robustly.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    if not isinstance(value, str):
        return value

    value = value.strip()
    if not value:
        return value

    # Try JSON first (most common for structured data)
    if value.startswith(("{", "[")):
        try:
            import json
            return json.loads(value)
        except json.JSONDecodeError:
            pass
        # Try Python literal eval (handles single quotes, tuples, etc.)
        try:
            import ast
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass

    return value
'''


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
    # Separate required and optional parameters to maintain valid Python syntax
    # (parameters with defaults must come after those without)
    required_params = []
    optional_params = []
    for param_name, param_info in parameters_schema.items():
        required = param_info.get("required", True)
        if required:
            required_params.append(f"{param_name}: str")
        else:
            optional_params.append(f"{param_name}: Optional[str] = None")

    # Combine: required first, then optional
    param_parts = required_params + optional_params
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

    # Build parameter parsing code (parse all user parameters)
    param_parse_lines = []
    for param_name in parameters_schema.keys():
        param_parse_lines.append(
            f"        {param_name} = _parse_input({param_name})"
        )
    param_parse_code = "\n".join(param_parse_lines) if param_parse_lines else ""

    # Generate Python file content with helper function
    python_code = f'''"""Tool: {tool_name}

{description}
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

{PARSE_INPUT_HELPER}

def {tool_name}(
    {param_signature}stack: "Stack" = None,
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
        # Parse inputs (handles JSON strings, Python repr, dicts, etc.)
{param_parse_code}

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
        # Use simple path since tools/ folder is added to sys.path by Environment.load()
        "implementation_path": f"{tool_name}:{tool_name}",
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

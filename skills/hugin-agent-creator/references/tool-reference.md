# Tool Reference

Custom tools extend agent capabilities with Python code.

## File Structure

Each tool has two files:

```
tools/
├── my_tool.yaml    # Tool definition (schema, description)
└── my_tool.py      # Tool implementation (Python code)
```

## YAML Definition Schema

```yaml
name: string              # Required. Tool identifier
description: string       # Required. What the tool does
parameters: object        # Required. Input parameters
implementation_path: str  # Optional. Python module:function path
options: object           # Optional. Tool options
```

## Python Implementation

```python
from typing import TYPE_CHECKING
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="tool_name",
    description="What this tool does",
    parameters={...},
    is_interactive=False,
)
def tool_function(stack: "Stack", param1: str, param2: int) -> ToolResponse:
    """Tool docstring."""
    # Implementation
    return ToolResponse(is_error=False, content={"result": "value"})
```

## Return Types

Tools can return three types:

### 1. ToolResponse (most common)
Returns immediately with a result.

```python
from gimle.hugin.tools.tool import ToolResponse

def my_tool(stack, data: str) -> ToolResponse:
    result = process(data)
    return ToolResponse(
        is_error=False,
        content={"result": result, "message": "Success"},
    )
```

**Error response:**
```python
return ToolResponse(
    is_error=True,
    content={"error": "Description of what went wrong"},
)
```

### 2. AgentCall (spawn sub-agent)
Launches a child agent and waits for it to complete.

```python
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.agent.task import Task

def delegate_tool(stack, task_description: str) -> AgentCall:
    config = stack.agent.environment.config_registry.get("child_config")
    task = Task(
        name="delegated_task",
        description=task_description,
        parameters={},
        prompt=task_description,
        tools=config.tools,
        system_template=config.system_template,
        llm_model=config.llm_model,
    )
    return AgentCall(stack=stack, config=config, task=task)
```

### 3. AskHuman (request human input)
Pauses execution until human responds.

```python
from gimle.hugin.interaction.ask_human import AskHuman

def request_approval(stack, action: str, reason: str) -> ToolResponse:
    question = f"""
    Action: {action}
    Reason: {reason}

    Do you approve? (yes/no)
    """
    ask_human = AskHuman(
        stack=stack,
        question=question,
        response_template_name="approval_response",
    )
    return ToolResponse(
        is_error=False,
        content={"message": "Waiting for approval..."},
        response_interaction=ask_human,
    )
```

## Complete Examples

### Simple Tool

**tools/process_text.yaml:**
```yaml
name: process_text
description: Process and transform text
parameters:
  text:
    type: string
    description: Text to process
  operation:
    type: string
    description: "Operation: uppercase, lowercase, reverse"
implementation_path: process_text:process_text
```

**tools/process_text.py:**
```python
"""Text processing tool."""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="process_text",
    description="Process and transform text",
    parameters={
        "text": {
            "type": "string",
            "description": "Text to process",
            "required": True,
        },
        "operation": {
            "type": "string",
            "description": "Operation: uppercase, lowercase, reverse",
            "required": True,
        },
    },
    is_interactive=False,
)
def process_text(stack: "Stack", text: str, operation: str) -> ToolResponse:
    """Process text with the specified operation."""
    operations = {
        "uppercase": lambda t: t.upper(),
        "lowercase": lambda t: t.lower(),
        "reverse": lambda t: t[::-1],
    }

    if operation not in operations:
        return ToolResponse(
            is_error=True,
            content={"error": f"Unknown operation: {operation}"},
        )

    result = operations[operation](text)
    return ToolResponse(
        is_error=False,
        content={"result": result, "operation": operation},
    )
```

### Tool with Sub-Agent

**tools/delegate_analysis.yaml:**
```yaml
name: delegate_analysis
description: Delegate analysis to a specialized sub-agent
parameters:
  data:
    type: string
    description: Data to analyze
  analysis_type:
    type: string
    description: Type of analysis to perform
implementation_path: delegate_analysis:delegate_analysis
```

**tools/delegate_analysis.py:**
```python
"""Delegation tool that spawns sub-agents."""

from typing import TYPE_CHECKING, Union

from gimle.hugin.agent.task import Task, TaskParameter
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="delegate_analysis",
    description="Delegate analysis to a specialized sub-agent",
    parameters={
        "data": {
            "type": "string",
            "description": "Data to analyze",
            "required": True,
        },
        "analysis_type": {
            "type": "string",
            "description": "Type of analysis to perform",
            "required": True,
        },
    },
    is_interactive=False,
)
def delegate_analysis(
    stack: "Stack", data: str, analysis_type: str
) -> Union[ToolResponse, AgentCall]:
    """Spawn a sub-agent to perform analysis."""
    try:
        config = stack.agent.environment.config_registry.get("analyst")
    except (KeyError, ValueError):
        return ToolResponse(
            is_error=True,
            content={"error": "Analyst config not found"},
        )

    task = Task(
        name="analysis_task",
        description=f"Perform {analysis_type} analysis",
        parameters={
            "data": TaskParameter(
                type="string",
                description="Data to analyze",
                required=True,
                value=data,
            ),
        },
        prompt=f"Analyze this data using {analysis_type} methods:\n\n{data}",
        tools=config.tools,
        system_template=config.system_template,
        llm_model=config.llm_model,
    )

    return AgentCall(stack=stack, config=config, task=task)
```

### Interactive Tool

**tools/request_approval.yaml:**
```yaml
name: request_approval
description: Request approval from a human
parameters:
  action:
    type: string
    description: The action to approve
  reason:
    type: string
    description: Why approval is needed
implementation_path: request_approval:request_approval
options:
  respond_with_text: true
```

**tools/request_approval.py:**
```python
"""Human approval tool."""

from typing import TYPE_CHECKING

from gimle.hugin.interaction.ask_human import AskHuman
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def request_approval(
    stack: "Stack", action: str, reason: str
) -> ToolResponse:
    """Request human approval for an action."""
    question = f"""APPROVAL REQUEST

Action: {action}

Reason: {reason}

Do you approve this action? (yes/no)
Please provide any feedback or conditions."""

    ask_human = AskHuman(
        stack=stack,
        question=question,
        response_template_name="approval_response",
    )

    return ToolResponse(
        is_error=False,
        content={"action": action, "message": "Waiting for approval..."},
        response_interaction=ask_human,
    )
```

## Accessing Agent Context

The `stack` parameter provides access to the agent's context:

```python
def my_tool(stack: "Stack", ...) -> ToolResponse:
    # Access environment variables (shared state)
    env_vars = stack.agent.environment.env_vars
    shared_data = env_vars.get("shared_key")

    # Access registries
    config_registry = stack.agent.environment.config_registry
    task_registry = stack.agent.environment.task_registry

    # Access current agent info
    agent_name = stack.agent.config.name
```

## Parameter Types

Supported parameter types:

| Type | Python | Example |
|------|--------|---------|
| `string` | `str` | `"hello"` |
| `integer` | `int` | `42` |
| `number` | `float` | `3.14` |
| `boolean` | `bool` | `true` |
| `array` | `list` | `["a", "b"]` |
| `object` | `dict` | `{"key": "value"}` |

## Best Practices

1. **Always include `stack` parameter** - It's auto-injected by the framework
2. **Return ToolResponse for immediate results** - Most tools should use this
3. **Use AgentCall for delegation** - Never run sub-agents synchronously
4. **Handle errors gracefully** - Return `is_error=True` with descriptive message
5. **Keep tools focused** - One tool, one responsibility
6. **Document parameters clearly** - Good descriptions help the LLM use tools correctly

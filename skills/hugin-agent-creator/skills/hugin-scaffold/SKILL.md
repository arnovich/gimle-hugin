---
name: hugin-scaffold
description: Generate starter files for a new Hugin agent
argument-hint: "[agent-name] [type: minimal|tool|pipeline]"
allowed-tools:
  - Write
  - Bash
---

# Hugin Agent Scaffold Generator

Generate starter files for a new Hugin agent based on the provided arguments.

## Arguments

Parse the user's arguments to extract:
1. **agent_name**: Name for the agent (required, snake_case)
2. **type**: One of `minimal`, `tool`, or `pipeline` (default: `minimal`)

Example invocations:
- `/hugin-agent-creator:hugin-scaffold my_agent` - Creates minimal agent
- `/hugin-agent-creator:hugin-scaffold data_processor tool` - Creates agent with custom tool
- `/hugin-agent-creator:hugin-scaffold report_generator pipeline` - Creates multi-stage pipeline

## Directory Structure to Create

For ALL types, create under `./[agent_name]/`:

```
[agent_name]/
├── configs/
│   └── [agent_name].yaml
├── tasks/
│   └── [task_name].yaml
├── templates/
│   └── [agent_name]_system.yaml
└── tools/                      # Only for 'tool' type
    ├── [tool_name].yaml
    └── [tool_name].py
```

## Templates by Type

### Minimal Type

**configs/[agent_name].yaml:**
```yaml
name: [agent_name]
description: [Agent description - ask user or generate from name]
system_template: [agent_name]_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
interactive: false
options: {}
```

**tasks/[agent_name]_task.yaml:**
```yaml
name: [agent_name]_task
description: Main task for [agent_name]
parameters:
  input:
    type: string
    description: Input to process
    required: false
    default: "Hello, world!"
prompt: |
  Process this input: {{ input.value }}

  When complete, use the finish tool with your result.
```

**templates/[agent_name]_system.yaml:**
```yaml
name: [agent_name]_system
template: |
  You are a helpful AI assistant.

  Your task is to help the user accomplish their goals. Be concise and clear in your responses.

  When you have completed the task, use the finish tool to indicate completion.
```

### Tool Type

Same as minimal, plus:

**tools/[agent_name]_tool.yaml:**
```yaml
name: [agent_name]_tool
description: Custom tool for [agent_name]
parameters:
  data:
    type: string
    description: Data to process
implementation_path: [agent_name]_tool:[agent_name]_tool
```

**tools/[agent_name]_tool.py:**
```python
"""Custom tool for [agent_name]."""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="[agent_name]_tool",
    description="Custom tool for [agent_name]",
    parameters={
        "data": {
            "type": "string",
            "description": "Data to process",
            "required": True,
        },
    },
    is_interactive=False,
)
def [agent_name]_tool(stack: "Stack", data: str) -> ToolResponse:
    """Process data and return result.

    Args:
        stack: The stack (auto-injected)
        data: Data to process

    Returns:
        ToolResponse with processed result
    """
    # TODO: Implement your tool logic here
    result = f"Processed: {data}"

    return ToolResponse(
        is_error=False,
        content={
            "result": result,
            "message": "Processing complete",
        },
    )
```

Update config to include the tool:
```yaml
tools:
  - [agent_name]_tool:[agent_name]_tool
  - builtins.finish:finish
```

### Pipeline Type

Creates a 3-stage pipeline:

**configs/[agent_name].yaml:**
```yaml
name: [agent_name]
description: Multi-stage pipeline agent
system_template: [agent_name]_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
interactive: false
options: {}
```

**tasks/stage_1_extract.yaml:**
```yaml
name: stage_1_extract
description: Extract data from input (Stage 1)
parameters:
  raw_input:
    type: string
    description: Raw input data
    required: false
    default: "Sample input data"
task_sequence:
  - stage_2_transform
  - stage_3_output
pass_result_as: extracted_data
prompt: |
  STAGE 1: EXTRACT

  Raw Input: {{ raw_input.value }}

  Your task:
  1. Parse the raw input
  2. Extract key information
  3. Use finish with your structured extraction as the result

  The result will be passed to Stage 2.
```

**tasks/stage_2_transform.yaml:**
```yaml
name: stage_2_transform
description: Transform extracted data (Stage 2)
parameters:
  extracted_data:
    type: string
    description: Data from Stage 1
    required: false
    default: ""
task_sequence: []
pass_result_as: transformed_data
prompt: |
  STAGE 2: TRANSFORM

  Extracted Data: {{ extracted_data.value }}

  Your task:
  1. Transform the extracted data
  2. Apply any necessary processing
  3. Use finish with your transformed result

  The result will be passed to Stage 3.
```

**tasks/stage_3_output.yaml:**
```yaml
name: stage_3_output
description: Generate final output (Stage 3)
parameters:
  transformed_data:
    type: string
    description: Data from Stage 2
    required: false
    default: ""
prompt: |
  STAGE 3: OUTPUT

  Transformed Data: {{ transformed_data.value }}

  Your task:
  1. Generate the final output
  2. Format it appropriately
  3. Use finish with your final result
```

**templates/[agent_name]_system.yaml:**
```yaml
name: [agent_name]_system
template: |
  You are a data processing assistant working in a multi-stage pipeline.

  Follow your stage instructions carefully. Your output will be passed to the next stage.

  Always use the finish tool when your stage is complete, including your result.
```

## After Scaffolding

Print these next steps:

```
Created [agent_name] agent ([type] type)

Directory: ./[agent_name]/

Run your agent:
  uv run hugin run --task [task_name] --task-path ./[agent_name]

Next steps:
  1. Edit configs/[agent_name].yaml to customize the agent
  2. Edit tasks/[task_name].yaml to define your task logic
  3. Edit templates/[agent_name]_system.yaml for the system prompt
  [If tool type:]
  4. Implement your tool in tools/[agent_name]_tool.py
  [If pipeline type:]
  4. Customize each stage task in tasks/

For more guidance: /hugin-agent-creator:hugin-guide
```

## Implementation Instructions

1. Parse arguments to get agent_name and type
2. Validate agent_name is snake_case
3. Create directory structure using Bash mkdir
4. Write all files using the Write tool
5. Replace all `[agent_name]` placeholders with actual name
6. Print the "After Scaffolding" message

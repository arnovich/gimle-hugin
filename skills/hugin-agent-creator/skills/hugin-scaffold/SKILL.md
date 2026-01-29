---
name: hugin-scaffold
description: Generate starter files for a new Hugin agent
argument-hint: "[agent-name] [type: minimal|tool|pipeline]"
allowed-tools:
  - Read
  - Write
  - Bash
---

# Hugin Agent Scaffold Generator

Generate starter files for a new Hugin agent by reading templates from this plugin and customizing them.

## Arguments

Parse the user's arguments to extract:
1. **agent_name**: Name for the agent (required, snake_case)
2. **type**: One of `minimal`, `tool`, or `pipeline` (default: `minimal`)

Example invocations:
- `/hugin-agent-creator:hugin-scaffold my_agent` - Creates minimal agent
- `/hugin-agent-creator:hugin-scaffold data_processor tool` - Creates agent with custom tool
- `/hugin-agent-creator:hugin-scaffold report_generator pipeline` - Creates multi-stage pipeline

## Implementation Steps

### Step 1: Parse Arguments
Extract `agent_name` and `type` from user input. Validate `agent_name` is snake_case.

### Step 2: Create Directory Structure
Use Bash to create the directories:

```bash
mkdir -p [agent_name]/configs [agent_name]/tasks [agent_name]/templates
# For 'tool' type also:
mkdir -p [agent_name]/tools
```

### Step 3: Read and Customize Templates

**IMPORTANT**: Read the actual template files from this plugin, then customize them.

#### For ALL types, read these templates:

1. **Read** `templates/minimal-config.yaml` from this plugin
   - Replace `my_agent` with `[agent_name]`
   - Replace `my_system` with `[agent_name]_system`
   - For 'tool' type: add the custom tool to the tools list
   - Write to `[agent_name]/configs/[agent_name].yaml`

2. **Read** `templates/minimal-task.yaml` from this plugin
   - Replace `my_task` with `[agent_name]_task`
   - Write to `[agent_name]/tasks/[agent_name]_task.yaml`

3. **Read** `templates/minimal-template.yaml` from this plugin
   - Replace `my_system` with `[agent_name]_system`
   - Write to `[agent_name]/templates/[agent_name]_system.yaml`

#### For 'tool' type, also read:

4. **Read** `templates/tool-definition.yaml` from this plugin
   - Replace `my_tool` with `[agent_name]_tool`
   - Write to `[agent_name]/tools/[agent_name]_tool.yaml`

5. **Read** `templates/tool-implementation.py` from this plugin
   - Replace `my_tool` with `[agent_name]_tool`
   - Write to `[agent_name]/tools/[agent_name]_tool.py`

#### For 'pipeline' type:

Instead of the single task, create 3 stage tasks:

1. **Read** `templates/minimal-task.yaml` as base, then create:

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

2. Update the system template for pipeline context:
   ```yaml
   name: [agent_name]_system
   template: |
     You are a data processing assistant working in a multi-stage pipeline.

     Follow your stage instructions carefully. Your output will be passed to the next stage.

     Always use the finish tool when your stage is complete, including your result.
   ```

### Step 4: Print Success Message

After creating all files, print:

```
Created [agent_name] agent ([type] type)

Directory: ./[agent_name]/

Files created:
  - configs/[agent_name].yaml
  - tasks/[task_name].yaml
  - templates/[agent_name]_system.yaml
  [If tool type:]
  - tools/[agent_name]_tool.yaml
  - tools/[agent_name]_tool.py

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

## Template File Locations

All templates are in this plugin's `templates/` directory:
- `templates/minimal-config.yaml`
- `templates/minimal-task.yaml`
- `templates/minimal-template.yaml`
- `templates/tool-definition.yaml`
- `templates/tool-implementation.py`

**Always read these files** rather than hardcoding their content. This ensures scaffolded agents use the latest template versions.

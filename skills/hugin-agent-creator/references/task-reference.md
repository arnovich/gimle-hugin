# Task Reference

Task files define what an agent should do, including prompts and parameters.

## File Location

`tasks/<task_name>.yaml`

## Schema

```yaml
name: string              # Required. Unique identifier
description: string       # Required. What this task does
parameters: object        # Optional. Input parameters
prompt: string            # Required. Jinja2 template for the task prompt
tools: list               # Optional. Override config's tools
system_template: string   # Optional. Override config's template
llm_model: string         # Optional. Override config's model
task_sequence: list       # Optional. Follow-up tasks to run
pass_result_as: string    # Optional. Parameter name for next task
```

## Fields

### name
Unique identifier for this task.

```yaml
name: analyze_data
```

### description
Human-readable description.

```yaml
description: Analyze input data and generate insights
```

### parameters
Typed input parameters with validation. Two formats supported:

**Structured format (recommended):**
```yaml
parameters:
  data_source:
    type: string
    description: Path to the data file
    required: true
  limit:
    type: integer
    description: Maximum items to process
    required: false
    default: 10
```

**Simple format:**
```yaml
parameters:
  query: "What is the meaning of life?"
```

**Parameter types:**
- `string` - Text values
- `integer` - Whole numbers
- `number` - Decimal numbers
- `boolean` - true/false
- `array` - Lists

**Accessing in prompts:**
```yaml
prompt: |
  Process: {{ data_source.value }}
  Limit: {{ limit.value }}
```

### prompt
Jinja2 template for the task prompt. Use `{{ param_name.value }}` to access parameters.

```yaml
prompt: |
  Analyze the following data:
  {{ input_data.value }}

  Focus on: {{ focus_area.value }}

  When complete, use the finish tool with your analysis.
```

### tools (optional)
Override the config's tool list for this specific task.

```yaml
tools:
  - special_tool:special
  - builtins.finish:finish
```

### system_template (optional)
Override the config's system template for this task.

```yaml
system_template: specialized_system
```

### llm_model (optional)
Override the config's model for this task.

```yaml
llm_model: sonnet-latest  # Use more capable model for this task
```

### task_sequence
List of tasks to run after this one completes. Creates a pipeline.

```yaml
task_sequence:
  - transform_data
  - generate_report
```

### pass_result_as
Parameter name to use when passing this task's result to the next task.

```yaml
pass_result_as: extracted_data
# The next task receives {{ extracted_data.value }}
```

## Examples

### Simple Task

```yaml
name: hello_world
description: Respond to user questions
parameters:
  question:
    type: string
    description: The question to answer
    required: false
    default: "What is the meaning of life?"
prompt: |
  Please answer this question:

  {{ question.value }}

  When done, use finish with your answer.
```

### Task with Multiple Parameters

```yaml
name: process_order
description: Process a customer order
parameters:
  customer_id:
    type: string
    description: Customer identifier
    required: true
  items:
    type: array
    description: List of items to order
    required: true
  priority:
    type: string
    description: Order priority level
    required: false
    default: "normal"
prompt: |
  Process order for customer: {{ customer_id.value }}

  Items: {{ items.value }}
  Priority: {{ priority.value }}

  Validate the order and confirm processing.
```

### Pipeline First Stage

```yaml
name: extract_data
description: Extract data from raw input (Stage 1)
parameters:
  raw_data:
    type: string
    description: Raw input data
    required: false
    default: "Sample data here"
task_sequence:
  - transform_data
  - analyze_data
  - generate_report
pass_result_as: extracted_data
prompt: |
  STAGE 1: EXTRACT

  Raw Data: {{ raw_data.value }}

  Extract the key information and use finish with your structured result.
  This will be passed to the next stage.
```

### Pipeline Middle Stage

```yaml
name: transform_data
description: Transform extracted data (Stage 2)
parameters:
  extracted_data:
    type: string
    description: Data from previous stage
    required: false
    default: ""
task_sequence: []  # Sequence continues from first task
pass_result_as: transformed_data
prompt: |
  STAGE 2: TRANSFORM

  Input from Stage 1: {{ extracted_data.value }}

  Transform the data and use finish with your result.
```

### Task with Model Override

```yaml
name: complex_analysis
description: Complex analysis requiring advanced reasoning
parameters:
  data:
    type: string
    description: Data to analyze
    required: true
llm_model: opus-4-5  # Override to use most capable model
prompt: |
  Perform deep analysis on:
  {{ data.value }}

  Consider edge cases and provide comprehensive insights.
```

## Parameter Validation

- **Required parameters**: Must be provided when creating agent
- **Optional parameters**: Use default if not provided
- **Type checking**: Values validated against declared type

```yaml
parameters:
  required_param:
    type: string
    required: true        # Must be provided
  optional_param:
    type: integer
    required: false       # Uses default if not provided
    default: 42
```

## Running Tasks

```bash
# Basic run
uv run hugin run --task task_name --task-path ./agent_dir

# With parameters
uv run hugin run --task task_name --task-path ./agent_dir \
  --parameters '{"param1": "value1", "param2": 42}'
```

# Task Sequences Example - Data Pipeline

This example demonstrates multi-stage task sequencing with result passing using `task_sequence` and `pass_result_as`.

## Concept

**Task Sequences** allow you to:
- Chain multiple tasks together in a defined order
- Pass results from one task to the next
- Build ETL-style pipelines
- Create multi-stage workflows
- Each stage processes the output of the previous stage

This is ideal for workflows where each step builds on the previous step's output.

## Key Features

### task_sequence
Defines the ordered list of tasks to execute:
```yaml
task_sequence:
  - transform_data
  - analyze_data
  - generate_report
```

### `task_sequence` - Chain Through Multiple Tasks
```yaml
name: process_document
task_sequence:
  - extract_text
  - analyze_content
  - create_summary
```

### pass_result_as
Specifies the parameter name for passing the previous task's result:
```yaml
pass_result_as: extracted_data
```

The result from this task will be injected into the next task's parameters as `extracted_data`.

### Automatic Chaining
The framework automatically:
1. Executes each task in sequence
2. Captures the task result
3. Injects it into the next task's parameters
4. Continues until all tasks complete

## The Pipeline

This example implements a 4-stage data processing pipeline:

```
Raw Data → Extract → Transform → Analyze → Report
```

**Stage 1: Extract**
- Input: Raw text data
- Process: Parse and structure data
- Output: Structured data → `extracted_data`

**Stage 2: Transform**
- Input: `extracted_data` from Stage 1
- Process: Clean, normalize, enrich
- Output: Transformed data → `transformed_data`

**Stage 3: Analyze**
- Input: `transformed_data` from Stage 2
- Process: Find patterns, calculate statistics
- Output: Analysis results → `analysis_results`

**Stage 4: Report**
- Input: `analysis_results` from Stage 3
- Process: Generate final report
- Output: Complete report

## Running the Example

### Basic Pipeline

```bash
uv run hugin run \
  --task extract_data \
  --task-path examples/task_sequences
```

### With Custom Data

```bash
uv run hugin run \
  --task extract_data \
  --task-path examples/task_sequences \
  --parameters '{"raw_data": "Sales: Alice $100, Bob $200, Carol $150"}'
```

## Workflow Demonstration

```
extract_data task starts
         │
         ▼
    Parse raw data
         │
         ▼
    process_data(
      stage="extract",
      output="Alice: 3 apples, Bob: 2 oranges, Carol: 5 apples"
    )
         │
         ▼
    finish() with result
         │
         ▼
    TaskChain → transform_data
    (result injected as extracted_data)
         │
         ▼
    transform_data task starts
         │
         ▼
    Clean and normalize data
         │
         ▼
    process_data(
      stage="transform",
      output="Normalized data with totals"
    )
         │
         ▼
    finish() with result
         │
         ▼
    TaskChain → analyze_data
    (result injected as transformed_data)
         │
         ▼
    analyze_data task starts
         │
         ▼
    Analyze for patterns
         │
         ▼
    process_data(
      stage="analyze",
      output="Apples most popular, Alice best customer"
    )
         │
         ▼
    finish() with result
         │
         ▼
    TaskChain → generate_report
    (result injected as analysis_results)
         │
         ▼
    generate_report task starts
         │
         ▼
    Generate final report
         │
         ▼
    finish() - Pipeline complete
```

## Task Definition Details

Each task in the sequence defines:

1. **Parameters** - Including the `pass_result_as` parameter
```yaml
parameters:
  extracted_data: ""  # Will be filled by previous task
```

2. **Result Passing** - What to call the result when passing to next task
```yaml
pass_result_as: transformed_data
```

3. **Sequence** - Only the first task needs this (it defines the full sequence)
```yaml
task_sequence:
  - transform_data
  - analyze_data
  - generate_report
```

## Use Cases

This pattern is ideal for:

- **ETL Pipelines** - Extract, Transform, Load workflows
- **Data Processing** - Multi-stage data cleaning and analysis
- **Report Generation** - Gather → Process → Analyze → Report
- **Content Pipelines** - Fetch → Parse → Enrich → Publish
- **Multi-Stage Validation** - Check → Clean → Verify → Approve
- **Workflow Automation** - Step-by-step business processes

## Key Concepts Demonstrated

1. **Sequential Execution** - Tasks run in defined order
2. **Result Injection** - Previous result becomes next task's input
3. **Parameter Passing** - Clean interface between stages
4. **Pipeline Completion** - Automatic chaining until sequence ends
5. **Stage Isolation** - Each task focuses on its specific stage

## Extending This Example

You can extend this pattern by:
- Adding more stages to the pipeline
- Using `chain_config` to switch agent configurations between stages
- Implementing error handling and rollback
- Adding conditional branching based on results
- Parallelizing independent stages
- Storing intermediate results as artifacts

## Comparison with Other Patterns

**vs. tool_chaining:**
- Tool chaining: Multiple tools in one task
- Task sequences: Multiple tasks with different prompts

**vs. task_chaining:**
- task_chaining: Simple next_task link
- task_sequences: Ordered list with result passing

**vs. branching:**
- Branching: Parallel exploration
- Sequences: Sequential processing

Use task sequences when each stage needs its own task definition and the output of one stage directly feeds into the next.

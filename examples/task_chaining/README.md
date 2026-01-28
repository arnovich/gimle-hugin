# Task Chaining Example - Document Processing Pipeline

This example demonstrates **task chaining** where one task automatically triggers the next without returning to the caller.

## Concept

When processing documents, we often have a fixed pipeline of tasks:
1. **Extract** text from the document
2. **Analyze** the extracted content
3. **Summarize** the analysis results

Instead of having the caller orchestrate each task, they chain automatically:
- `extract_text` → automatically starts `analyze_content`
- `analyze_content` → automatically starts `create_summary`
- `create_summary` → returns to caller with final result

This is useful for complex workflows where each step needs different tools or prompts and you want the higher level steps in the flow to be deterministic.

## Key Features

### `next_task` - Chain to Single Task
```yaml
name: extract_text
next_task: analyze_content
pass_result_as: extracted_text
```

### `pass_result_as` - Pass Results to Next Task
```yaml
name: analyze_content
pass_result_as: content
prompt: |
  Analyze the following content:
  {{ content }}
```

### `chain_config` - Use Different Config for Chained Task
```yaml
name: analyze_content
next_task: create_summary
chain_config: summary_agent  # Use different tools/model
```

### Using the result of the last task in the template of the next
```
{{ extracted_text.value["result"] }}
```

### Using `agent.stack` in task template to access the last tool result

```
agent.stack.get_last_tool_result_interaction(tool_name="analyze_content").result
```


## Running the Example

```bash
uv run hugin run \
  --task process_document \
  --task-path examples/task_chaining \
  --agent extract_text \
  --parameters '{"document": "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the alphabet."}'
```

## Flow Diagram

```
Caller starts process_document
         │
         ▼
┌─────────────────┐
│  extract_text   │ ──► next_task="analyze_content"
│  (extractor)    │     pass_result_as="extracted_text"
└─────────────────┘
         │
         ▼ (automatic via TaskChain)
┌─────────────────┐
│ analyze_content │ ──► next_task="create_summary"
│  (analyzer)     │     pass_result_as="analysis"
└─────────────────┘
         │
         ▼ (automatic via TaskChain)
┌─────────────────┐
│ create_summary  │ ──► next_task=None (end chain)
│  (summarizer)   │
└─────────────────┘
         │
         ▼
Caller receives final summary
```

## Files

- `tools/document_tools.py` - Document processing tool implementations
- `tools/*.yaml` - Tool definitions
- `configs/document_agent.yaml` - Agent config
- `tasks/*.yaml` - Task definitions with chaining

## Use Cases

Task chaining is ideal for:
- **Document processing pipelines** - Extract, analyze, summarize
- **Data ETL workflows** - Extract, transform, load
- **Multi-step analysis** - Gather, process, report
- **Approval workflows** - Submit, review, approve

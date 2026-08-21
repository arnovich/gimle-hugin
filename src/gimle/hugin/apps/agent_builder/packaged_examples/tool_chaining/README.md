# Tool Chaining Example - Data Processing Pipeline

This example demonstrates **deterministic tool chaining** where one tool automatically triggers the next without returning to the LLM.

## Concept

When processing data, we often have a fixed pipeline:
1. **Validate** the input data
2. **Transform** the data (if valid)
3. **Store** the result

Instead of having the LLM decide each step, the tools chain automatically:
- `validate_data` → automatically calls `transform_data`
- `transform_data` → automatically calls `store_data`
- `store_data` → returns to LLM with final result

This is faster (fewer LLM calls) and more reliable (deterministic flow).

## Key Feature: `next_tool` in ToolResponse

```python
def validate_data(data: str, stack: Stack, **kwargs) -> ToolResponse:
    # ... validation logic ...
    return ToolResponse(
        is_error=False,
        content={"validated": True, "data": parsed_data},
        next_tool="transform_data",           # Chain to next tool
        next_tool_args={"data": parsed_data}, # Pass arguments
        include_in_context=False,             # Hide from LLM context
    )
```

## The `include_in_context` Flag

When `include_in_context=False`:
- The tool result is NOT shown to the LLM in the conversation history
- Useful for intermediate steps that the LLM doesn't need to see
- Reduces context size and cost

When `include_in_context=True` (default):
- The tool result appears in the conversation history
- The LLM sees all intermediate results

## Running the Example

```bash
uv run hugin run \
  --task process_data \
  --task-path examples/tool_chaining \
  --parameters '{"input_data": "{\"name\": \"John\", \"age\": 30}"}'
```

## Flow Diagram

```
LLM decides to call validate_data
         │
         ▼
┌─────────────────┐
│  validate_data  │ ──► next_tool="transform_data"
└─────────────────┘     include_in_context=False
         │
         ▼ (automatic, no LLM call)
┌─────────────────┐
│ transform_data  │ ──► next_tool="store_data"
└─────────────────┘     include_in_context=False
         │
         ▼ (automatic, no LLM call)
┌─────────────────┐
│   store_data    │ ──► next_tool=None (end chain)
└─────────────────┘     include_in_context=True
         │
         ▼
LLM sees only the final result
```

# Self-Reflection Example

This example demonstrates **self-reflection via task chaining** - a pattern where an agent evaluates and refines its own work through a deterministic pipeline.

## Pattern Overview

```
write_article → evaluate_article → refine_article
     ↓                ↓                  ↓
  (haiku)         (sonnet)           (haiku)
```

The agent:
1. **Writes** an initial draft (using haiku-latest)
2. **Evaluates** the draft against quality criteria (switches to sonnet-latest via `chain_config`)
3. **Refines** the article based on evaluation feedback (back to haiku-latest)

## Key Features Demonstrated

- **Task Chaining**: `task_sequence` defines the pipeline stages
- **Result Passing**: `pass_result_as` injects previous output as next task's parameter
- **Config Switching**: `chain_config` uses a different LLM model for evaluation

## Running the Example

```bash
# Basic run (specify -c writer to start with the writer config)
uv run hugin run -p examples/self_reflection -t write_article -c writer \
  --parameters '{"topic": "The future of remote work"}'

# With dashboard to observe the reflection flow
uv run hugin run -p examples/self_reflection -t write_article -c writer \
  --parameters '{"topic": "AI ethics"}' --monitor
```

## File Structure

```
self_reflection/
├── configs/
│   ├── writer.yaml      # Writer config (haiku-latest)
│   └── evaluator.yaml   # Evaluator config (sonnet-latest)
├── tasks/
│   ├── write_article.yaml     # Initial task with task_sequence
│   ├── evaluate_article.yaml  # Evaluation task (chain_config: evaluator)
│   └── refine_article.yaml    # Refinement task
├── templates/
│   ├── writer_system.yaml
│   ├── evaluator_system.yaml
│   ├── write_article_prompt.yaml
│   ├── evaluate_article_prompt.yaml
│   └── refine_article_prompt.yaml
└── README.md
```

## How It Works

### Task Chaining Flow

1. `write_article.yaml` defines:
   ```yaml
   task_sequence: [evaluate_article, refine_article]
   pass_result_as: draft
   ```

2. After writing completes, the framework automatically:
   - Creates a `TaskChain` interaction
   - Loads `evaluate_article` task
   - Injects the draft via `draft` parameter

3. `evaluate_article.yaml` switches configs:
   ```yaml
   chain_config: evaluator  # Uses sonnet-latest
   pass_result_as: evaluation
   ```

4. `refine_article.yaml` receives both:
   - `draft.value` - the original article
   - `evaluation.value` - the critique

### Model Switching Benefits

Using a stronger model (sonnet) for evaluation provides:
- More nuanced critique
- Better identification of logical gaps
- Higher quality improvement suggestions

While using a faster model (haiku) for writing keeps costs lower.

## Extending This Pattern

### Add More Stages

```yaml
# In write_article.yaml
task_sequence: [evaluate_article, refine_article, final_review, polish]
```

### Loop Until Quality Threshold

Create a custom tool that checks quality score and conditionally sets `next_task`:
```python
if score < 8:
    return {"next_task": "refine_article"}
else:
    return {"next_task": "publish"}
```

## See Also

- `examples/reflexion/` - Multi-agent reflection with separate critic agent
- `examples/task_sequences/` - More task chaining examples

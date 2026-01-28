# Reflexion Example

This example demonstrates the **Reflexion pattern** - a popular multi-agent reflection approach where a separate agent provides feedback that the primary agent uses to improve its work.

## Pattern Overview

```
┌─────────────────────────────────────────────────┐
│                  Writer Agent                    │
│                 (haiku-latest)                   │
│                                                  │
│  1. Write initial draft                         │
│  2. Call launch_agent("critic", draft)  ───────────┐
│  3. Receive feedback                    ←──────────┤
│  4. Revise based on feedback                     │
│  5. Call finish with final article               │
└─────────────────────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌─────────────────────────────────────┐
                              │          Critic Agent               │
                              │        (sonnet-latest)              │
                              │                                     │
                              │  1. Receive article                 │
                              │  2. Evaluate against criteria       │
                              │  3. Return structured feedback      │
                              └─────────────────────────────────────┘
```

## Key Features Demonstrated

- **Multi-Agent Reflection**: Separate critic agent reviews the work
- **Sub-Agent Spawning**: `launch_agent` creates and runs the critic synchronously
- **Model Specialization**: Stronger model (sonnet) for evaluation, faster model (haiku) for generation
- **Dynamic Flow**: Writer decides when to request feedback and when quality is sufficient

## Running the Example

```bash
# Run the writer with the reflexion pattern
uv run hugin run -p examples/reflexion -t write_with_feedback -c writer \
  --parameters '{"topic": "Benefits of meditation"}'

# Test the critic task directly
uv run hugin run -p examples/reflexion -t critique_article -c critic \
  --parameters '{"article": "Your article text here..."}'

# With dashboard to observe the multi-agent interaction
uv run hugin run -p examples/reflexion -t write_with_feedback -c writer \
  --parameters '{"topic": "Climate change solutions"}' --monitor
```

> **Note**: The `launch_agent` tool creates sub-agents dynamically. When the writer
> calls launch_agent, include the full article in the `task_description` parameter
> as that becomes the critic's prompt.

## File Structure

```
reflexion/
├── configs/
│   ├── writer.yaml    # Writer agent (haiku-latest, has launch_agent)
│   └── critic.yaml    # Critic agent (sonnet-latest)
├── tasks/
│   ├── write_with_feedback.yaml   # Writer's main task
│   └── critique_article.yaml      # Critic's task
├── templates/
│   ├── writer_system.yaml
│   ├── critic_system.yaml
│   ├── write_with_feedback_prompt.yaml
│   └── critique_article_prompt.yaml
└── README.md
```

## How It Works

### The Reflexion Flow

1. **Writer generates draft**: The writer agent creates an initial article

2. **Writer spawns critic**: Using `launch_agent`:
   ```python
   launch_agent(
     config_name="critic",
     task_name="critique_article",
     task_description="Please critique this article:\n\n[FULL ARTICLE TEXT]\n\nProvide score, strengths, weaknesses, and suggestions."
   )
   ```
   Note: The `task_description` becomes the critic's prompt, so include the full article there.

3. **Critic evaluates**: The critic agent (using sonnet-latest):
   - Scores the article
   - Identifies strengths and weaknesses
   - Provides specific improvement suggestions

4. **Writer receives feedback**: The `launch_agent` result contains:
   - `final_response`: The critic's structured feedback
   - `artifacts`: Any artifacts the critic created
   - `completed`: Whether the critic finished successfully

5. **Writer revises**: The writer incorporates feedback and improves the article

6. **Writer finishes**: When satisfied, calls `finish` with the final article

### Why Use Separate Agents?

| Benefit | Explanation |
|---------|-------------|
| **Specialization** | Each agent focuses on one role |
| **Model flexibility** | Use stronger model for evaluation |
| **Clear separation** | Critique is independent from creation |
| **Reusability** | Critic can evaluate any content |

### Comparison with Self-Reflection

| Aspect | Self-Reflection | Reflexion |
|--------|-----------------|-----------|
| Control | Deterministic pipeline | Dynamic agent decision |
| Flexibility | Fixed stages | Agent decides when to iterate |
| Cost | May use stronger model unnecessarily | Only uses strong model for critique |
| Complexity | Simpler to implement | More flexible but complex |

## Extending This Pattern

### Multiple Critique Rounds

The writer can call `launch_agent` multiple times:
```
Draft → Critique → Revise → Critique → Revise → Final
```

### Different Specialist Critics

Create multiple critic configs for different aspects:
```yaml
# grammar_critic.yaml - focuses on language
# logic_critic.yaml - focuses on reasoning
# style_critic.yaml - focuses on engagement
```

### Collaborative Refinement

Combine with shared state for iterative improvement:
```python
# Store drafts and feedback in shared namespace
stack.set_shared_state("draft_v1", draft, namespace="documents")
stack.set_shared_state("feedback_v1", feedback, namespace="reviews")
```

## See Also

- `examples/self_reflection/` - Self-reflection via task chaining
- `examples/sub_agent/` - Basic sub-agent spawning
- `examples/agent_messaging/` - Peer-to-peer agent communication

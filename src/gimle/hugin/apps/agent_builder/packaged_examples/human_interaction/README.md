# Human Interaction Example - Approval Agent

This example demonstrates human-in-the-loop workflows using the `AskHuman` and `HumanResponse` interaction types.

## Concept

**Human-in-the-Loop** allows agents to:
- Pause execution to ask humans for input
- Request approval before taking important actions
- Incorporate human feedback into their decision-making
- Create interactive workflows with human oversight

This enables agents to handle sensitive operations safely by requiring human approval at critical decision points.

## Key Features

### AskHuman Interaction
- Pauses agent execution
- Presents a question to the human
- Waits for human response before continuing

### HumanResponse Interaction
- Captures human's answer
- Can be approval (yes/no) or detailed feedback
- Resumes agent execution with the human's input

### Custom Tool: request_approval
Structured way to request approval:
- **action**: What the agent wants to do
- **reason**: Why it's needed
- **considerations**: Risks or important factors

## Running the Example

### Interactive Mode (Default)

```bash
uv run hugin run \
  --task make_decision \
  --task-path examples/human_interaction
```

The agent will pause and wait for your input when it calls `request_approval`.

### With Custom Decision

```bash
uv run hugin run \
  --task make_decision \
  --task-path examples/human_interaction \
  --parameters '{"decision": "Deploy to production", "context": "New feature is ready but needs final approval"}'
```

## Workflow Demonstration

```
Agent starts make_decision task
         │
         ▼
    Analyze decision and context
         │
         ▼
    request_approval(
      action="Proceed with deployment",
      reason="Feature is tested and ready",
      considerations="Will affect live users"
    )
         │
         ▼
    [PAUSE] - AskHuman created
         │
    Waiting for human response...
         │
         ▼
    Human provides response:
    "yes, but do it during off-peak hours"
         │
         ▼
    HumanResponse created
         │
         ▼
    Agent resumes execution
         │
         ▼
    Incorporates feedback:
    "I'll schedule deployment for 2 AM"
         │
         ▼
    finish("Deployment approved with timing condition")
```

## Use Cases

This pattern is ideal for:

- **Approval Workflows** - Financial transactions, deployments, data deletions
- **Compliance** - Operations requiring human oversight for regulatory reasons
- **Quality Control** - Human review before finalizing reports or decisions
- **Interactive Debugging** - Ask human for clarification when uncertain
- **Risk Management** - Human approval for high-risk operations
- **Training** - Allow humans to provide feedback to improve agent behavior

## Example Interaction

**Agent:**
```
APPROVAL REQUEST

Action: Migrate database schema

Reason: Need to add new columns for user preferences feature

Considerations:
- Requires 15 minutes of downtime
- Affects all users
- Rollback possible but time-consuming

Do you approve this action? (yes/no)
If you have feedback or conditions, please provide them.
```

**Human:** "Yes, but schedule it for Sunday at 3 AM when traffic is lowest"

**Agent:** "Understood. I'll schedule the migration for Sunday at 3 AM to minimize user impact. Creating deployment plan..."

## Important Notes

- Agents with `interactive: true` in config can use interactive tools
- AskHuman blocks execution until human responds
- Use for critical decisions, not routine operations
- Keep questions clear and concise
- Provide sufficient context for informed decisions

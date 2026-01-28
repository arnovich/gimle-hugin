# Plan-Execute Agent Example

This example demonstrates the **Config State Machine** feature for creating agents that operate in different modes.

## Concept

The agent has two modes:
- **Planning Mode**: Analyzes the task, breaks it down, creates a step-by-step plan
- **Execution Mode**: Follows the plan step by step

The agent automatically transitions between modes based on tool calls:
- `approve_plan` → switches from planning to execution
- `request_replan` → switches from execution back to planning

## Directory Structure

```
plan_execute_agent/
├── configs/
│   ├── planner_agent.yaml    # Main config with state machine definition
│   ├── planning_mode.yaml    # Config for planning mode (different tools/prompt)
│   └── execution_mode.yaml   # Config for execution mode (different tools/prompt)
├── tasks/
│   └── solve_problem.yaml    # Example task
├── templates/
│   ├── planner_system.yaml   # Base system prompt
│   ├── planning_system.yaml  # Planning-specific prompt
│   └── execution_system.yaml # Execution-specific prompt
└── tools/
    ├── planning_tools.py     # Python implementations for planning
    ├── execution_tools.py    # Python implementations for execution
    └── *.yaml                # Tool definitions
```

## How It Works

1. Agent starts in `planning_mode` (defined by `state_machine.initial_state`)
2. In planning mode, agent has access to: `analyze_task`, `create_plan`, `approve_plan`
3. When agent calls `approve_plan`, state machine triggers transition to `execution_mode`
4. In execution mode, agent has access to: `execute_step`, `mark_step_complete`, `request_replan`, `finish`
5. If agent calls `request_replan`, it transitions back to `planning_mode`

## Running the Example

```bash
uv run hugin run \
  --task solve_problem \
  --task-path examples/plan_execute_agent \
  --parameters '{"problem": "Calculate the sum of numbers from 1 to 100"}'
```

## State Machine Definition

```yaml
state_machine:
  initial_state: planning_mode
  transitions:
    - name: start_execution
      from_state: planning_mode
      to_state: execution_mode
      trigger:
        type: tool_call
        tool_name: approve_plan

    - name: replan_requested
      from_state: execution_mode
      to_state: planning_mode
      trigger:
        type: tool_call
        tool_name: request_replan

    - name: replan_on_blocked
      from_state: execution_mode
      to_state: planning_mode
      trigger:
        type: state_pattern
        pattern:
          blocked: true
```

## Key Features Demonstrated

1. **Config State Machine**: Automatic mode switching based on tool calls
2. **Different Tool Sets**: Each mode has its own set of available tools
3. **Different System Prompts**: Each mode has a tailored system prompt
4. **Shared State**: Plan and progress tracked in session shared state
5. **Looping**: Agent can go back and forth between modes as needed

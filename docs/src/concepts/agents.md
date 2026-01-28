---
layout: base.njk
title: Agents
---

# Sessions & Agents

An **Agent** is the central entity in Hugin. It combines a configuration (how it behaves), a task (what it does), and a stack (its history of interactions).

## Creating Agents

The standard way to create agents is from tasks:

```python
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.storage.local import LocalStorage

# Load environment from a directory
storage = LocalStorage(base_path="./storage")
env = Environment.load("./my_agent", storage=storage)
session = Session(environment=env)

# Create agent from task
config = env.config_registry.get("my_config")
task = env.task_registry.get("my_task")
session.create_agent_from_task(config, task)

# Run all agents in session to completion
session.run()
```

## Agent Configuration

Agents are configured via YAML files:

```yaml
# configs/analyst.yaml
name: analyst
description: Data analysis agent
system_template: analyst_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
  - builtins.save_insight:save_insight
  - query_database:query_database
```

### Configuration Options

| Field | Description |
|-------|-------------|
| `name` | Unique identifier |
| `description` | Human-readable description |
| `system_template` | Name of the template for system prompt |
| `llm_model` | Model to use (e.g., `haiku-latest`, `gpt-4o`, `llama3.2`) |
| `tools` | List of available tools (format: `module:tool_name`) |

## Agent Lifecycle

<div id="lifecycle-animation" style="width: 100%; height: 480px; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; margin: 24px 0; overflow: hidden;"></div>
<style>
  #lifecycle-animation svg { cursor: default !important; }
  /* Hide hover tooltip */
  #lifecycle-animation .tooltip { display: none !important; }
</style>

<script type="module">
  import { StateMachineAnimator } from '/assets/js/animator/state-machine-animator.js';

  const container = document.getElementById('lifecycle-animation');
  const containerWidth = container.clientWidth || 800;

  const animator = new StateMachineAnimator({
    container: '#lifecycle-animation',
    theme: 'light',
    responsive: true,
    padding: 30,
  });

  // Disable pan/zoom interactions
  const svg = container.querySelector('svg');
  if (svg) {
    svg.style.cursor = 'default';
    svg.addEventListener('wheel', e => e.stopPropagation(), { capture: true });
    svg.addEventListener('mousedown', e => e.stopPropagation(), { capture: true });
  }

  async function runAnimation() {
    const renderer = animator.getRenderer();
    renderer.clear();

    // Center the stack horizontally
    const stackX = Math.max(120, (containerWidth - 400) / 2);

    // Draw the main agent stack with initial task
    const stackRef = animator.addStack({
      id: 'agent',
      label: 'Agent Stack',
      states: [
        { type: 'TaskDefinition', label: 'Analyze data' },
      ],
    }, { x: stackX, y: 10 });

    await animator.delay(600);

    // First oracle cycle
    await animator.pushState('agent', { type: 'AskOracle', label: 'What tools needed?' });
    await animator.delay(400);
    await animator.pushState('agent', { type: 'OracleResponse', label: 'Use query_db tool' });
    await animator.delay(500);

    // First tool call
    await animator.pushState('agent', { type: 'ToolCall', label: 'query_db(...)' });
    await animator.delay(400);
    await animator.pushState('agent', { type: 'ToolResult', label: '42 rows returned' });
    await animator.delay(500);

    // Second oracle cycle
    await animator.pushState('agent', { type: 'AskOracle', label: 'Analyze results?' });
    await animator.delay(400);
    await animator.pushState('agent', { type: 'OracleResponse', label: 'Calculate average' });
    await animator.delay(500);

    // Second tool call
    await animator.pushState('agent', { type: 'ToolCall', label: 'calculate(...)' });
    await animator.delay(400);
    await animator.pushState('agent', { type: 'ToolResult', label: 'avg: 127.5' });
    await animator.delay(500);

    // Final oracle cycle leading to completion
    await animator.pushState('agent', { type: 'AskOracle', label: 'Task complete?' });
    await animator.delay(400);
    await animator.pushState('agent', { type: 'OracleResponse', label: 'Yes, finish' });
    await animator.delay(500);

    // Task completion
    await animator.pushState('agent', { type: 'TaskResult', label: 'Analysis complete' });

    // Wait before restarting
    await animator.delay(3000);
    animator.reset();
    runAnimation();
  }

  // Start animation when container is visible
  if (container.clientWidth > 0) {
    runAnimation();
  } else {
    const observer = new ResizeObserver((entries) => {
      if (entries[0].contentRect.width > 0) {
        observer.disconnect();
        runAnimation();
      }
    });
    observer.observe(container);
  }
</script>

1. **Task Definition** - Agent receives initial task prompt
2. **Ask Oracle** - Agent consults the LLM with current context
3. **Oracle Response** - LLM returns text or tool calls
4. **Tool Call** - Agent executes requested tools
5. **Tool Result** - Results are added to the stack
6. **Repeat** until task completion or `finish` tool is called

### States and Transitions

The exact type of states and transitions are:

<div class="demo-container" style="padding: 16px;">
  <div id="transition-map-illustration" style="width: 100%; height: auto;"></div>
</div>

### State Machine

Or illustrated in another way:

<div class="demo-container" style="padding: 16px;">
  <div id="state-transitions-illustration" style="width: 100%; height: 520px;"></div>
</div>

<script type="module">
  import { renderTransitionMap, renderStateTransitions } from '/assets/js/embeds/agent-transition-illustrations.js';

  renderTransitionMap('#transition-map-illustration');
  renderStateTransitions('#state-transitions-illustration');
</script>

## Multi-Agent Sessions

Multiple agents can run in a session with shared environment:

```python
session = Session(environment=env)

# Create multiple agents
session.create_agent_from_task(config1, task1)
session.create_agent_from_task(config2, task2)

# Run all agents
session.run()
```

### Shared State

Agents can share state via namespaces:

```python
# In a tool, access shared state
shared = stack.get_shared_state("my_namespace")
shared["key"] = "value"
stack.set_shared_state("my_namespace", shared)
```

See [Stacks & Interactions](/concepts/stacks/) for more on state management.

## State Machines

Agents can have dynamic behavior via state machines:

```yaml
# configs/plan_execute.yaml
name: plan_execute
state_machine:
  initial: planning
  states:
    planning:
      tools: [create_plan, review_plan]
      transitions:
        - on_tool: approve_plan
          to: executing
    executing:
      tools: [execute_step, finish]
```

This enables agents to change their available tools and behavior based on their current state.

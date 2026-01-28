---
layout: base.njk
title: Stacks & Interactions
---

# Stacks & Interactions

The **Stack** is the heart of Hugin's architecture. Every step an agent takes is an **Interaction** pushed onto the stack. This immutable history enables powerful features like replay, step-through debugging, and branching.

## Interaction Types

| Type | Description |
|------|-------------|
| `TaskDefinition` | Initial task prompt that starts the agent |
| `AskOracle` | Request sent to an LLM |
| `OracleResponse` | Response from the LLM (text or tool calls) |
| `ToolCall` | Request to execute a tool |
| `ToolResult` | Result returned from a tool |
| `AskHuman` | Request for human input |
| `HumanResponse` | Response from a human |
| `TaskResult` | Final result when task completes |
| `TaskChain` | Transition to a new task |
| `AgentCall` | Call to another agent |
| `AgentResult` | Result from another agent |

## Stack Visualization

<div id="stack-animation" style="width: 100%; height: 480px; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; margin: 24px 0; overflow: hidden;"></div>
<style>
  #stack-animation svg { cursor: default !important; }
  #stack-animation svg > g { transform: translate(var(--offset-x, 20px), -50px) !important; }
  /* Hide hover tooltip/modal */
  #stack-animation .tooltip, #stack-animation .state-tooltip, #stack-animation .hover-info { display: none !important; }
</style>

<script type="module">
  import { StateMachineAnimator } from '/assets/js/animator/state-machine-animator.js';

  const container = document.getElementById('stack-animation');

  const animator = new StateMachineAnimator({
    container: '#stack-animation',
    theme: 'light',
    responsive: true,
    padding: 10,
  });

  // Disable pan/zoom and center content
  const svg = container.querySelector('svg');
  if (svg) {
    svg.style.cursor = 'default';
    svg.addEventListener('wheel', e => e.stopPropagation(), { capture: true });
    svg.addEventListener('mousedown', e => e.stopPropagation(), { capture: true });

    // Center the content horizontally
    const containerWidth = container.clientWidth || 800;
    const contentWidth = 400; // approximate width of stack + tool
    const offsetX = Math.max(10, (containerWidth - contentWidth) / 2);
    container.style.setProperty('--offset-x', offsetX + 'px');
  }

  async function runAnimation() {
    await animator.playToolExecution({
      stack: {
        id: 'main',
        label: 'Interaction Stack',
        states: [
          { type: 'TaskDefinition', label: 'Research topic X' },
        ],
      },
      preStates: [
        { type: 'AskOracle', label: 'What should I research?' },
        { type: 'OracleResponse', label: 'Search the web first' },
      ],
      triggerState: { type: 'ToolCall', label: 'search_web' },
      tool: { id: 'search', name: '🔍 Web Search' },
      resultState: { type: 'ToolResult', label: '10 results found' },
      postStates: [
        { type: 'AskOracle', label: 'Analyze these results' },
        { type: 'OracleResponse', label: 'Key findings are...' },
        { type: 'TaskResult', label: 'Research complete' },
      ],
    });

    setTimeout(() => {
      animator.reset();
      runAnimation();
    }, 3000);
  }

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

Each interaction is pushed onto the stack in order. The stack provides the context window for LLM calls - when the agent asks the oracle, the full stack is rendered into the prompt.

## Branching

Branches allow parallel exploration from any point in the stack:

<div id="branching-animation" style="width: 100%; height: 540px; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; margin: 24px 0; overflow: hidden;"></div>
<style>
  #branching-animation svg { cursor: default !important; }
  #branching-animation svg > g { transform: translate(var(--offset-x, 20px), -30px) !important; }
  /* Hide hover tooltip/modal */
  #branching-animation .tooltip, #branching-animation .state-tooltip, #branching-animation .hover-info { display: none !important; }
</style>

<script type="module">
  import { StateMachineAnimator } from '/assets/js/animator/state-machine-animator.js';

  const container = document.getElementById('branching-animation');
  const containerWidth = container.clientWidth || 800;

  const animator = new StateMachineAnimator({
    container: '#branching-animation',
    theme: 'light',
    responsive: true,
    padding: 10,
  });

  // Disable pan/zoom and center content
  const svg = container.querySelector('svg');
  if (svg) {
    svg.style.cursor = 'default';
    svg.addEventListener('wheel', e => e.stopPropagation(), { capture: true });
    svg.addEventListener('mousedown', e => e.stopPropagation(), { capture: true });

    const contentWidth = 650;
    const offsetX = Math.max(10, (containerWidth - contentWidth) / 2);
    container.style.setProperty('--offset-x', offsetX + 'px');
  }

  // State dimensions
  const STATE_HEIGHT = 42;
  const STATE_WIDTH = 165;
  const STATE_SPACING = 4;
  const LABEL_HEIGHT = 40;

  // Get Y position of top state in a stack
  function getTopStateY(stackY, stateCount) {
    return stackY + LABEL_HEIGHT;
  }

  async function runAnimation() {
    const renderer = animator.getRenderer();
    renderer.clear();

    // Position: branch labels at top, main stack states lower
    const mainX = 240;
    const branchAX = 0;
    const branchBX = 480;
    const labelY = 60;  // Branch labels at top
    const mainStackY = 360;  // Main stack positioned near bottom

    // Draw main stack label manually at same height as branches
    const svgEl = container.querySelector('svg');
    const mainGroup = svgEl.querySelector('g');
    const mainLabelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    mainLabelText.setAttribute('x', String(mainX + STATE_WIDTH / 2));
    mainLabelText.setAttribute('y', String(labelY + 24));
    mainLabelText.setAttribute('text-anchor', 'middle');
    mainLabelText.setAttribute('font-weight', '600');
    mainLabelText.setAttribute('font-size', '14px');
    mainLabelText.setAttribute('fill', '#1e293b');
    mainLabelText.textContent = 'Main Stack';
    mainGroup.appendChild(mainLabelText);

    // Create main stack without label, positioned lower
    animator.addStack({
      id: 'main',
      label: '',
      states: [],
    }, { x: mainX, y: mainStackY });

    animator.addStack({
      id: 'branch-a',
      label: 'Branch A',
      states: [],
    }, { x: branchAX, y: labelY });

    animator.addStack({
      id: 'branch-b',
      label: 'Branch B',
      states: [],
    }, { x: branchBX, y: labelY });

    await animator.delay(400);

    // Animate shared history on main stack
    let mainStateCount = 0;

    await animator.pushState('main', { type: 'TaskDefinition', label: 'Solve problem' });
    mainStateCount++;
    await animator.delay(400);

    await animator.pushState('main', { type: 'AskOracle', label: 'How to approach?' });
    mainStateCount++;
    await animator.delay(400);

    await animator.pushState('main', { type: 'OracleResponse', label: 'Two options...' });
    mainStateCount++;
    await animator.delay(600);

    // Calculate arrow connection points
    // From: left/right sides of main stack's top state (middle of the edges)
    const mainTopStateCenterY = mainStackY + STATE_HEIGHT / 2;  // Vertical center of top state

    // To: left/right sides of branch's bottom state (grows as states are added)
    const branchFirstStateCenterY = labelY + LABEL_HEIGHT + STATE_HEIGHT / 2;  // Center of first state

    // Draw branch arrows with curved shape from inside top state to sides of branch states
    const arrowInset = 8;  // How far inside the state the arrow starts
    const arrow1 = renderer.drawArrow({
      from: { x: mainX + arrowInset, y: mainTopStateCenterY },  // Inside left of main's top state
      to: { x: branchAX + STATE_WIDTH, y: branchFirstStateCenterY },  // Right side of Branch A's state
      style: 'curved',
      dashArray: '5,5',
    });
    const arrow2 = renderer.drawArrow({
      from: { x: mainX + STATE_WIDTH - arrowInset, y: mainTopStateCenterY },  // Inside right of main's top state
      to: { x: branchBX, y: branchFirstStateCenterY },  // Left side of Branch B's state
      style: 'curved',
      dashArray: '5,5',
    });
    await Promise.all([
      renderer.fadeIn(arrow1.element, 300),
      renderer.fadeIn(arrow2.element, 300),
    ]);

    await animator.delay(300);

    // Track branch state counts for arrow updates
    let branchStateCount = 0;

    // Helper to update arrows as branches grow
    async function updateArrows() {
      // Center Y of the bottom state in branches
      const branchBottomStateCenterY = labelY + LABEL_HEIGHT + (branchStateCount - 1) * (STATE_HEIGHT + STATE_SPACING) + STATE_HEIGHT / 2;
      await Promise.all([
        renderer.updateArrowPath(
          arrow1,
          { x: mainX + arrowInset, y: mainTopStateCenterY },  // Inside left of main's top state
          { x: branchAX + STATE_WIDTH, y: branchBottomStateCenterY },  // Right side of Branch A's bottom state
          'curved', 200
        ),
        renderer.updateArrowPath(
          arrow2,
          { x: mainX + STATE_WIDTH - arrowInset, y: mainTopStateCenterY },  // Inside right of main's top state
          { x: branchBX, y: branchBottomStateCenterY },  // Left side of Branch B's bottom state
          'curved', 200
        ),
      ]);
    }

    // Animate shared history on both branches in parallel (with arrow updates)
    branchStateCount++;
    await Promise.all([
      animator.pushState('branch-a', { type: 'TaskDefinition', label: 'Solve problem' }),
      animator.pushState('branch-b', { type: 'TaskDefinition', label: 'Solve problem' }),
      updateArrows(),
    ]);
    await animator.delay(350);

    branchStateCount++;
    await Promise.all([
      animator.pushState('branch-a', { type: 'AskOracle', label: 'How to approach?' }),
      animator.pushState('branch-b', { type: 'AskOracle', label: 'How to approach?' }),
      updateArrows(),
    ]);
    await animator.delay(350);

    branchStateCount++;
    await Promise.all([
      animator.pushState('branch-a', { type: 'OracleResponse', label: 'Two options...' }),
      animator.pushState('branch-b', { type: 'OracleResponse', label: 'Two options...' }),
      updateArrows(),
    ]);
    await animator.delay(400);

    // Animate branch-specific states in parallel (with arrow updates)
    branchStateCount++;
    await Promise.all([
      animator.pushState('branch-a', { type: 'ToolCall', label: 'try_method_a' }),
      animator.pushState('branch-b', { type: 'ToolCall', label: 'try_method_b' }),
      updateArrows(),
    ]);
    await animator.delay(400);

    branchStateCount++;
    await Promise.all([
      animator.pushState('branch-a', { type: 'ToolResult', label: 'Success!' }),
      animator.pushState('branch-b', { type: 'ToolResult', label: 'Failed' }),
      updateArrows(),
    ]);
    await animator.delay(400);

    // Final state on both branches
    branchStateCount++;
    await Promise.all([
      animator.pushState('branch-a', { type: 'TaskResult', label: 'Complete' }),
      animator.pushState('branch-b', { type: 'TaskResult', label: 'Retry needed' }),
      updateArrows(),
    ]);

    await animator.delay(3500);
    animator.reset();
    runAnimation();
  }

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

```python
# Create a branch from current position
branch_id = stack.create_branch("exploration_a")

# Work in the branch
stack.push(interaction, branch_id=branch_id)

# Branch has isolated context but shares parent history
context = stack.get_branch_context(branch_id)
```

### Use Cases for Branching

- **Parallel problem solving**: Try multiple approaches simultaneously
- **Hypothesis testing**: Explore different assumptions
- **Rollback**: Return to a previous state and try again

## Context Windows

The stack manages context for LLM calls:

```python
# Get context for main stack
context = stack.get_context()

# Get context for a specific branch
context = stack.get_branch_context(branch_id)
```

Context includes:
- All interactions from the start to current position
- Branch-specific interactions (if in a branch)
- Rendered templates with current state

## Shared State

Stacks can access session-wide shared state via namespaces:

```python
# Get state for a namespace
state = stack.get_shared_state("analytics")

# Modify and save
state["total_processed"] = 100
stack.set_shared_state("analytics", state)
```

Namespaces enable:
- **Producer-consumer patterns**: One agent writes, others read
- **Coordination**: Agents synchronize via shared state
- **Access control**: Restrict which agents can read/write

## Accessing the Stack in Tools

Tools receive the stack as their first parameter:

```python
def my_tool(stack, param1: str) -> str:
    # Access agent
    agent = stack.agent

    # Access environment
    env = agent.environment

    # Access shared state
    state = stack.get_shared_state("my_namespace")

    # Access previous interactions
    history = stack.get_context()

    return "result"
```

## Stack Persistence

Stacks are automatically persisted to storage, enabling:
- **Resume from any point**: Restart an agent from saved state
- **Debugging**: Inspect the full history of an agent run
- **Auditing**: Track every decision an agent made

---
layout: base.njk
title: Tools
---

# Tools

**Tools** are functions that agents can call to interact with the world. Hugin provides built-in tools for common operations and makes it easy to create custom tools.

## Tool Execution Flow

<div id="tool-animation" style="width: 100%; height: 450px; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; margin: 24px 0; overflow: hidden;"></div>
<style>
  #tool-animation svg { cursor: default !important; }
  #tool-animation svg > g { transform: translate(var(--offset-x, 20px), -50px) !important; }
  /* Hide hover tooltip/modal */
  #tool-animation .tooltip { display: none !important; }
  /* Hide internal stack arrows (↓ text elements) */
  #tool-animation svg text[font-size="10"] { display: none !important; }
</style>

<script type="module">
  import { StateMachineAnimator } from '/assets/js/animator/state-machine-animator.js';

  const container = document.getElementById('tool-animation');

  const animator = new StateMachineAnimator({
    container: '#tool-animation',
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
    const contentWidth = 400;
    const offsetX = Math.max(10, (containerWidth - contentWidth) / 2);
    container.style.setProperty('--offset-x', offsetX + 'px');
  }

  async function runAnimation() {
    const renderer = animator.getRenderer();
    renderer.clear();

    // Position and size constants
    const stackX = 20;
    const toolX = 250;
    const dbX = 420;
    const toolY = 140;
    const STATE_WIDTH = 165;
    const STATE_HEIGHT = 42;
    const STATE_SPACING = 4;
    const LABEL_HEIGHT = 40;
    const stackY = 60;
    const TOOL_BOX_WIDTH = 140;  // From dimensions.tool.width
    const TOOL_BOX_HEIGHT = 44;  // From dimensions.tool.height

    // Track state count and arrow references
    let stateCount = 1; // Start with TaskDefinition
    let arrow1 = null; // ToolCall -> query_database
    let returnArrow2 = null; // query_database -> ToolResult

    // Helper to get state Y position - states push down as new ones are added at top
    // stateIndex is counted from top (0 = topmost/newest)
    function getStateCenterY(statesFromTop) {
      return stackY + LABEL_HEIGHT + statesFromTop * (STATE_HEIGHT + STATE_SPACING) + STATE_HEIGHT / 2;
    }

    // Get position of ToolCall (it will be pushed down as states are added)
    function getToolCallY() {
      // ToolCall is added as 4th state, so it's (stateCount - 4) positions from top after more are added
      const positionFromTop = stateCount - 4;
      return getStateCenterY(positionFromTop);
    }

    // Get position of ToolResult (it will be pushed down as states are added)
    function getToolResultY() {
      // ToolResult is added as 5th state
      const positionFromTop = stateCount - 5;
      return getStateCenterY(positionFromTop);
    }

    // Update arrows to follow their attached states
    async function updateArrows() {
      const updates = [];
      if (arrow1) {
        updates.push(renderer.updateArrowPath(
          arrow1,
          { x: stackX + STATE_WIDTH, y: getToolCallY() },
          { x: toolX, y: toolY + TOOL_BOX_HEIGHT / 2 },
          'curved', 200
        ));
      }
      if (returnArrow2) {
        updates.push(renderer.updateArrowPath(
          returnArrow2,
          { x: toolX, y: toolY + TOOL_BOX_HEIGHT / 2 },
          { x: stackX + STATE_WIDTH, y: getToolResultY() },
          'curved', 200
        ));
      }
      if (updates.length > 0) {
        await Promise.all(updates);
      }
    }

    // Create the stack
    animator.addStack({
      id: 'main',
      label: 'Agent Stack',
      states: [
        { type: 'TaskDefinition', label: 'Process data' },
      ],
    }, { x: stackX, y: stackY });

    await animator.delay(400);

    // Add initial states
    await animator.pushState('main', { type: 'AskOracle', label: 'What tool should I use?' });
    stateCount++;
    await animator.delay(300);
    await animator.pushState('main', { type: 'OracleResponse', label: 'Use query_database' });
    stateCount++;
    await animator.delay(300);

    // Add ToolCall (index 3)
    await animator.pushState('main', { type: 'ToolCall', label: 'query_database' });
    stateCount++;
    await animator.delay(300);

    // Draw the query_database tool box (hidden initially)
    const toolRef = renderer.drawTool({ id: 'tool', name: '🔧 query_database' }, toolX, toolY, true);
    await animator.delay(200);

    // Fade in tool box
    await renderer.fadeIn(toolRef.element, 300);

    // Draw arrow from ToolCall to query_database (left side of tool box)
    arrow1 = renderer.drawArrow({
      from: { x: stackX + STATE_WIDTH, y: getToolCallY() },
      to: { x: toolX, y: toolY + TOOL_BOX_HEIGHT / 2 },
      style: 'curved',
      hidden: true,
    });
    await renderer.fadeIn(arrow1.element, 300);
    await animator.delay(200);

    // Draw the Database external resource box (hidden initially)
    const dbRef = renderer.drawTool({ id: 'db', name: '🗄️ Database' }, dbX, toolY, true);
    await animator.delay(200);

    // Fade in database box
    await renderer.fadeIn(dbRef.element, 300);

    // Draw arrow from query_database (right side) to Database (left side) - outgoing request
    const arrowOffset = 8; // Offset from center for parallel arrows
    const arrow2 = renderer.drawArrow({
      from: { x: toolX + TOOL_BOX_WIDTH, y: toolY + TOOL_BOX_HEIGHT / 2 - arrowOffset },
      to: { x: dbX, y: toolY + TOOL_BOX_HEIGHT / 2 - arrowOffset },
      style: 'straight',
      hidden: true,
    });
    await renderer.fadeIn(arrow2.element, 300);
    await animator.delay(400);

    // Return flow: Database (left side) -> query_database (right side) - response coming back
    const returnArrow1 = renderer.drawArrow({
      from: { x: dbX, y: toolY + TOOL_BOX_HEIGHT / 2 + arrowOffset },
      to: { x: toolX + TOOL_BOX_WIDTH, y: toolY + TOOL_BOX_HEIGHT / 2 + arrowOffset },
      style: 'straight',
      hidden: true,
    });
    await renderer.fadeIn(returnArrow1.element, 300);
    await animator.delay(300);

    // Draw return arrow from query_database (left side) toward where ToolResult will be
    returnArrow2 = renderer.drawArrow({
      from: { x: toolX, y: toolY + TOOL_BOX_HEIGHT / 2 },
      to: { x: stackX + STATE_WIDTH, y: getToolResultY() },
      style: 'curved',
      hidden: true,
    });

    // Add ToolResult as the return arrow appears, and update arrow1 since ToolCall moves down
    stateCount++;
    await Promise.all([
      renderer.fadeIn(returnArrow2.element, 300),
      animator.pushState('main', { type: 'ToolResult', label: 'Query returned 500 rows' }),
      // Update arrow1 to follow ToolCall as it's pushed down
      renderer.updateArrowPath(
        arrow1,
        { x: stackX + STATE_WIDTH, y: getToolCallY() },
        { x: toolX, y: toolY + TOOL_BOX_HEIGHT / 2 },
        'curved', 200
      ),
    ]);
    await animator.delay(300);

    // Continue with post states - update arrows as each state pushes others down
    stateCount++;
    await Promise.all([
      animator.pushState('main', { type: 'AskOracle', label: 'Now what?' }),
      updateArrows(),
    ]);
    await animator.delay(300);

    stateCount++;
    await Promise.all([
      animator.pushState('main', { type: 'OracleResponse', label: 'Analyze the results...' }),
      updateArrows(),
    ]);
    await animator.delay(300);

    stateCount++;
    await Promise.all([
      animator.pushState('main', { type: 'TaskResult', label: 'Analysis complete' }),
      updateArrows(),
    ]);

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

1. Agent asks oracle what to do
2. Oracle responds with a tool call
3. Tool executes and returns result
4. Result is pushed to stack
5. Agent continues with new context

## Built-in Tools

Located in `gimle.hugin.tools.builtins`:

| Tool | Description |
|------|-------------|
| `finish` | Complete the current task |
| `save_insight` | Save information to long-term memory (artifacts) |
| `query_artifacts` | Search saved artifacts |
| `get_artifact_content` | Retrieve a specific artifact |
| `ask_human` | Request input from a human |
| `create_branch` | Create a parallel exploration branch |
| `call_agent` | Invoke another agent |

## Creating Custom Tools

A tool consists of two files:

### Python Implementation

**tools/greet.py**:
```python
def greet(stack, name: str, formal: bool = False) -> str:
    """
    Greet someone by name.

    Args:
        stack: The agent's interaction stack (auto-injected)
        name: The name of the person to greet
        formal: Whether to use formal greeting

    Returns:
        A greeting string
    """
    if formal:
        return f"Good day, {name}."
    return f"Hello, {name}!"
```

### YAML Definition

**tools/greet.yaml**:
```yaml
name: greet
description: Greet someone by name
parameters:
  - name: name
    type: string
    description: The name of the person to greet
    required: true
  - name: formal
    type: boolean
    description: Whether to use formal greeting
    required: false
    default: false
implementation: greet:greet
```

### Parameter Types

| Type | Description |
|------|-------------|
| `string` | Text value |
| `integer` | Whole number |
| `number` | Decimal number |
| `boolean` | True/false |
| `array` | List of values |
| `object` | Nested structure |

## Adding Tools to Agents

Reference tools in your agent config:

```yaml
# configs/my_agent.yaml
name: my_agent
tools:
  # Built-in tools
  - builtins.finish:finish
  - builtins.save_insight:save_insight

  # Custom tools from tools/ directory
  - greet:greet
  - query_database:query_database
```

## Accessing Context in Tools

The `stack` parameter provides full access to agent context:

```python
def my_tool(stack, param: str) -> str:
    # Access the agent
    agent = stack.agent

    # Access environment variables
    api_key = agent.environment.env_vars.get("API_KEY")

    # Access shared state
    state = stack.get_shared_state("my_namespace")

    # Access storage
    storage = agent.environment.storage

    # Access other registries
    config_registry = agent.environment.config_registry

    return "result"
```

## Tool Chaining

Tools can trigger other tools using `next_tool`:

```yaml
# tools/process_data.yaml
name: process_data
description: Process and then analyze data
implementation: process_data:process_data
next_tool: analyze_results  # Automatically call this tool next
```

This creates deterministic pipelines where one tool always leads to another.

## Interactive Tools

Some tools require human interaction:

```python
def approve_action(stack, action: str) -> str:
    """Request human approval for an action."""
    # This will pause and wait for human input
    stack.push(AskHuman(
        prompt=f"Do you approve this action: {action}?",
        options=["yes", "no"]
    ))
    # Execution continues when human responds
    return "Waiting for approval..."
```

## Error Handling

Tools should handle errors gracefully:

```python
def query_database(stack, query: str) -> str:
    try:
        result = execute_query(query)
        return f"Query returned {len(result)} rows"
    except DatabaseError as e:
        return f"Error executing query: {e}"
```

The result (including errors) is always pushed to the stack, allowing the agent to adapt its behavior.

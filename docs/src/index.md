---
layout: base.njk
title: Home
---

<div class="hero">
  <h1>Hugin</h1>
  <p>A framework for building agents with a focus on longer running, creative, reasoning tasks.</p>
  <div class="hero-buttons">
    <a href="/getting-started/" class="btn btn-primary">Get Started</a>
    <a href="https://github.com/gimlelabs/gimle-hugin" class="btn btn-secondary">View on GitHub</a>
  </div>
</div>

<div id="hero-animation"></div>

<script type="module">
  import { StateMachineAnimator } from '/assets/js/animator/state-machine-animator.js';

  const animator = new StateMachineAnimator({
    container: '#hero-animation',
    theme: 'light',
    responsive: true,
  });

  // Helper for delays
  const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  // Layout constants (matching the animator's internal dimensions from layout.ts)
  const STATE_WIDTH = 165;
  const STATE_HEIGHT = 42;
  const STATE_SPACING = 4;
  const STACK_PADDING = 0;
  const STACK_LABEL_HEIGHT = 40;
  const STACK_MIN_WIDTH = 170;
  const TOOL_HEIGHT = 44;
  const ARTIFACT_HEIGHT = 70;

  // Calculate state position within a stack (matching getStatePositionInStack from layout.ts)
  function getStatePosition(stackX, stackY, totalStates, stateIndex) {
    // Center state horizontally in stack
    const x = stackX + (STACK_MIN_WIDTH - STATE_WIDTH) / 2;

    // Position from top, but logically index from bottom
    // So index 0 appears at the bottom, index n-1 at the top
    const reversedIndex = totalStates - 1 - stateIndex;
    const y = stackY + STACK_LABEL_HEIGHT + STACK_PADDING + reversedIndex * (STATE_HEIGHT + STATE_SPACING);

    return { x, y };
  }

  // Color palette for visual flair (from the theme)
  const colors = {
    tool: '#5BA3E0',     // Blue for Tools
    agent: '#A094C0',    // Lavender for Agents
    artifact: '#4caf50', // Green for artifacts
  };

  async function runAnimation() {
    const renderer = animator.getRenderer();
    const duration = 400;

    const stackY = 40;

    // Track state counts for position calculations
    let parentStateCount = 0;
    let childStateCount = 0;
    let analystStateCount = 0;

    // Track active stack pulses
    let coordinatorPulse = null;
    let reporterPulse = null;
    let analystPulseCancel = null;

    // Stack positions (left to right: Coordinator, Report Agent, Tools/Artifacts, Analyst)
    const parentStackX = 40;
    const childStackX = parentStackX + 200;
    const toolsX = childStackX + 200;
    const analystStackX = toolsX + 180;

    // Draw parent stack (Coordinator)
    const coordinatorRef = animator.addStack({
      id: 'coordinator',
      label: 'Coordinator',
      states: [],
    }, { x: parentStackX, y: stackY });

    // Draw child stack (Report Agent)
    const reporterRef = animator.addStack({
      id: 'reporter',
      label: 'Report Agent',
      states: [],
    }, { x: childStackX, y: stackY });

    // Draw analyst stack (will activate after others finish)
    const analystRef = animator.addStack({
      id: 'analyst',
      label: 'Analyst',
      states: [],
    }, { x: analystStackX, y: stackY });

    await delay(duration);

    // Start coordinator pulse (it's the first active stack)
    coordinatorPulse = renderer.pulse(coordinatorRef.element, 1500);

    // Helper to push state and return its position (with highlight effect)
    async function pushParent(state) {
      const stateRef = await animator.pushState('coordinator', state);
      parentStateCount++;
      // Brief highlight effect on new state
      if (stateRef && stateRef.element) {
        renderer.highlight(stateRef.element, 400);
      }
      return getStatePosition(parentStackX, stackY, parentStateCount, parentStateCount - 1);
    }

    async function pushChild(state) {
      const stateRef = await animator.pushState('reporter', state);
      childStateCount++;
      // Brief highlight effect on new state
      if (stateRef && stateRef.element) {
        renderer.highlight(stateRef.element, 400);
      }
      return getStatePosition(childStackX, stackY, childStateCount, childStateCount - 1);
    }

    // Get position of a state by its index (0 = oldest/bottom)
    function getParentStatePos(index) {
      return getStatePosition(parentStackX, stackY, parentStateCount, index);
    }

    function getChildStatePos(index) {
      return getStatePosition(childStackX, stackY, childStateCount, index);
    }

    function getAnalystStatePos(index) {
      return getStatePosition(analystStackX, stackY, analystStateCount, index);
    }

    // Track arrows and their attached state indices
    const arrows = [];

    // Parent: Task definition (index 0)
    await pushParent({ type: 'TaskDefinition', label: 'Create Q4 report' });
    await delay(duration);

    // Parent: Ask Oracle (index 1)
    await pushParent({ type: 'AskOracle', label: 'How to proceed?' });
    await delay(duration);

    // Parent: Oracle Response (index 2)
    await pushParent({ type: 'OracleResponse', label: 'Delegate to agent' });
    await delay(duration);

    // Parent: Agent Call (index 3)
    const agentCallPos = await pushParent({ type: 'AgentCall', label: 'create_report' });
    const agentCallIndex = parentStateCount - 1;
    await delay(duration / 2);

    // Child: Task definition (index 0)
    const childTaskPos = await pushChild({ type: 'TaskDefinition', label: 'Generate report' });
    const childTaskIndex = 0;

    // Draw arrow from AgentCall to first child state (lavender for agent delegation)
    const parentToChildArrow = renderer.drawArrow({
      from: { x: agentCallPos.x + STATE_WIDTH, y: agentCallPos.y + STATE_HEIGHT / 2 },
      to: { x: childTaskPos.x, y: childTaskPos.y + STATE_HEIGHT / 2 },
      style: 'curved',
      color: colors.agent,
    });
    await renderer.fadeIn(parentToChildArrow.element, duration / 2);
    arrows.push({
      ref: parentToChildArrow,
      fromStack: 'parent', fromIndex: agentCallIndex, fromSide: 'right',
      toStack: 'child', toIndex: childTaskIndex, toSide: 'left',
    });

    // Switch active stack: stop coordinator pulse, start reporter pulse
    if (coordinatorPulse) coordinatorPulse();
    reporterPulse = renderer.pulse(reporterRef.element, 1500);

    await delay(duration);

    // Helper to get state position by stack name
    function getStackStatePos(stackName, index) {
      if (stackName === 'parent') return getParentStatePos(index);
      if (stackName === 'child') return getChildStatePos(index);
      if (stackName === 'analyst') return getAnalystStatePos(index);
      return { x: 0, y: 0 };
    }

    // Helper to update all arrows (returns promise for parallel execution)
    function updateArrows() {
      const updates = arrows.map(arrow => {
        // Calculate from point
        let fromPoint;
        if (arrow.fromTool) {
          fromPoint = arrow.fromTool;
        } else {
          const fromPos = getStackStatePos(arrow.fromStack, arrow.fromIndex);
          const fromX = arrow.fromSide === 'right' ? fromPos.x + STATE_WIDTH : fromPos.x;
          fromPoint = { x: fromX, y: fromPos.y + STATE_HEIGHT / 2 };
        }

        // Calculate to point
        let toPoint;
        if (arrow.toTool) {
          toPoint = arrow.toTool;
        } else {
          const toPos = getStackStatePos(arrow.toStack, arrow.toIndex);
          const toX = arrow.toSide === 'right' ? toPos.x + STATE_WIDTH : toPos.x;
          toPoint = { x: toX, y: toPos.y + STATE_HEIGHT / 2 };
        }

        return renderer.updateArrowPath(arrow.ref, fromPoint, toPoint, 'curved', duration / 2);
      });
      return Promise.all(updates);
    }

    // Push state and update arrows in parallel (with highlight effect)
    async function pushParentWithArrows(state) {
      parentStateCount++;
      const [stateRef] = await Promise.all([
        animator.pushState('coordinator', state),
        updateArrows()
      ]);
      if (stateRef && stateRef.element) {
        renderer.highlight(stateRef.element, 400);
      }
      return getStatePosition(parentStackX, stackY, parentStateCount, parentStateCount - 1);
    }

    async function pushChildWithArrows(state) {
      childStateCount++;
      const [stateRef] = await Promise.all([
        animator.pushState('reporter', state),
        updateArrows()
      ]);
      if (stateRef && stateRef.element) {
        renderer.highlight(stateRef.element, 400);
      }
      return getStatePosition(childStackX, stackY, childStateCount, childStateCount - 1);
    }

    async function pushAnalyst(state) {
      const stateRef = await animator.pushState('analyst', state);
      analystStateCount++;
      if (stateRef && stateRef.element) {
        renderer.highlight(stateRef.element, 400);
      }
      return getStatePosition(analystStackX, stackY, analystStateCount, analystStateCount - 1);
    }

    async function pushAnalystWithArrows(state) {
      analystStateCount++;
      const [stateRef] = await Promise.all([
        animator.pushState('analyst', state),
        updateArrows()
      ]);
      if (stateRef && stateRef.element) {
        renderer.highlight(stateRef.element, 400);
      }
      return getStatePosition(analystStackX, stackY, analystStateCount, analystStateCount - 1);
    }

    // Child: Ask Oracle (index 1)
    await pushChildWithArrows({ type: 'AskOracle', label: 'Query sales data' });
    await delay(duration);

    // Child: Tool Call - Query Database (index 2)
    childStateCount++;
    const queryToolCallIndex = childStateCount - 1;
    const [queryToolCallPos] = await Promise.all([
      (async () => {
        await animator.pushState('reporter', { type: 'ToolCall', label: 'query_database' });
        return getChildStatePos(queryToolCallIndex);
      })(),
      updateArrows()
    ]);
    await delay(duration / 2);

    // Draw database tool box (will be below PDF since it's used first)
    const dbToolY = 220;
    const dbToolRef = renderer.drawTool({
      id: 'db-tool',
      name: 'Database',
      icon: '🗄️',
    }, toolsX, dbToolY, true);
    await renderer.fadeIn(dbToolRef.element, duration / 2);

    // Draw arrow to database (blue for tool calls)
    const toDbArrow = renderer.drawArrow({
      from: { x: queryToolCallPos.x + STATE_WIDTH, y: queryToolCallPos.y + STATE_HEIGHT / 2 },
      to: { x: toolsX, y: dbToolY + TOOL_HEIGHT * 0.7 },
      style: 'curved',
      color: colors.tool,
    });
    await renderer.fadeIn(toDbArrow.element, duration / 2);
    arrows.push({
      ref: toDbArrow,
      fromStack: 'child', fromIndex: queryToolCallIndex, fromSide: 'right',
      toTool: { x: toolsX, y: dbToolY + TOOL_HEIGHT * 0.7 },
    });

    // Pulse and highlight database (executing)
    renderer.highlight(dbToolRef.element, 600);
    const cancelDbPulse = renderer.pulse(dbToolRef.element, 300);
    await delay(duration * 1.5);
    cancelDbPulse();

    // Child: Tool Result (index 3)
    childStateCount++;
    const queryResultIndex = childStateCount - 1;
    await Promise.all([
      animator.pushState('reporter', { type: 'ToolResult', label: '1,234 records' }),
      updateArrows()
    ]);
    const queryResultPos = getChildStatePos(queryResultIndex);

    // Draw return arrow from database (blue for tool results)
    const fromDbArrow = renderer.drawArrow({
      from: { x: toolsX, y: dbToolY + TOOL_HEIGHT * 0.3 },
      to: { x: queryResultPos.x + STATE_WIDTH, y: queryResultPos.y + STATE_HEIGHT / 2 },
      style: 'curved',
      color: colors.tool,
    });
    await renderer.fadeIn(fromDbArrow.element, duration / 2);
    arrows.push({
      ref: fromDbArrow,
      fromTool: { x: toolsX, y: dbToolY + TOOL_HEIGHT * 0.3 },
      toStack: 'child', toIndex: queryResultIndex, toSide: 'right',
    });

    await delay(duration);

    // Child: Tool Call - Generate PDF (index 4)
    childStateCount++;
    const pdfToolCallIndex = childStateCount - 1;
    await Promise.all([
      animator.pushState('reporter', { type: 'ToolCall', label: 'generate_pdf' }),
      updateArrows()
    ]);
    const pdfToolCallPos = getChildStatePos(pdfToolCallIndex);
    await delay(duration / 2);

    // Draw PDF artifact (above database since it's created after)
    const artifactY = 100;
    const artifactRef = renderer.drawArtifact({
      id: 'pdf-artifact',
      name: 'Q4_Report',
      type: 'document',
      extension: 'pdf',
    }, toolsX, artifactY, true);

    // Draw arrow to artifact (green for artifact creation)
    const toArtifactArrow = renderer.drawArrow({
      from: { x: pdfToolCallPos.x + STATE_WIDTH, y: pdfToolCallPos.y + STATE_HEIGHT / 2 },
      to: { x: toolsX, y: artifactY + ARTIFACT_HEIGHT * 0.7 },
      style: 'curved',
      color: colors.artifact,
    });
    await renderer.fadeIn(toArtifactArrow.element, duration / 2);
    await renderer.fadeIn(artifactRef.element, duration);
    // Highlight artifact when created (green glow)
    renderer.highlight(artifactRef.element, 800);
    arrows.push({
      ref: toArtifactArrow,
      fromStack: 'child', fromIndex: pdfToolCallIndex, fromSide: 'right',
      toTool: { x: toolsX, y: artifactY + ARTIFACT_HEIGHT * 0.7 },
    });

    // Child: Tool Result - PDF created (index 5)
    await pushChildWithArrows({ type: 'ToolResult', label: 'PDF created' });
    await delay(duration);

    // Child: Task Result (index 6)
    const childResultPos = await pushChildWithArrows({ type: 'TaskResult', label: 'Report ready' });
    const childResultIndex = childStateCount - 1;
    await delay(duration);

    // Stop reporter pulse as it completes
    if (reporterPulse) reporterPulse();

    // Draw return arrow from child to parent (lavender for agent result)
    const agentResultIndex = parentStateCount; // It will be at this index
    const futureAgentResultPos = getStatePosition(parentStackX, stackY, parentStateCount + 1, agentResultIndex);

    const childToParentArrow = renderer.drawArrow({
      from: { x: childResultPos.x, y: childResultPos.y + STATE_HEIGHT / 2 },
      to: { x: futureAgentResultPos.x + STATE_WIDTH, y: futureAgentResultPos.y + STATE_HEIGHT / 2 },
      style: 'curved',
      color: colors.agent,
    });
    await renderer.fadeIn(childToParentArrow.element, duration / 2);

    // Resume coordinator pulse as control returns
    coordinatorPulse = renderer.pulse(coordinatorRef.element, 1500);

    // Parent: Agent Result - add arrow tracking first, then push with updates
    arrows.push({
      ref: childToParentArrow,
      fromStack: 'child', fromIndex: childResultIndex, fromSide: 'left',
      toStack: 'parent', toIndex: agentResultIndex, toSide: 'right',
    });
    await pushParentWithArrows({ type: 'AgentResult', label: 'Q4_Report.pdf' });
    await delay(duration);

    // Parent: Completion flow
    await pushParentWithArrows({ type: 'AskOracle', label: 'Report received' });
    await delay(duration);

    await pushParentWithArrows({ type: 'OracleResponse', label: 'Analysis needed' });
    await delay(duration);

    await pushParentWithArrows({ type: 'TaskResult', label: 'Done' });
    await delay(duration);

    // ========================================
    // ANALYST AGENT - Starts after Coordinator finishes
    // ========================================

    // Stop coordinator pulse, start analyst pulse
    if (coordinatorPulse) coordinatorPulse();
    analystPulseCancel = renderer.pulse(analystRef.element, 1500);

    // Analyst: Task Definition
    const analystTaskPos = await pushAnalyst({ type: 'TaskDefinition', label: 'Analyze Q4 report' });
    await delay(duration);

    // Analyst: Ask Oracle
    await pushAnalystWithArrows({ type: 'AskOracle', label: 'What insights?' });
    await delay(duration);

    // Analyst: Oracle Response
    await pushAnalystWithArrows({ type: 'OracleResponse', label: 'Read the report' });
    await delay(duration);

    // Analyst: Tool Call - Read from Q4 Report (index 3)
    analystStateCount++;
    const readToolCallIndex = analystStateCount - 1;
    await Promise.all([
      animator.pushState('analyst', { type: 'ToolCall', label: 'read_document' }),
      updateArrows()
    ]);
    const readToolCallPos = getAnalystStatePos(readToolCallIndex);
    await delay(duration / 2);

    // Draw arrow FROM artifact TO analyst's ToolCall (green for artifact read)
    const artifactToAnalystArrow = renderer.drawArrow({
      from: { x: toolsX + 100, y: artifactY + ARTIFACT_HEIGHT / 2 },
      to: { x: readToolCallPos.x, y: readToolCallPos.y + STATE_HEIGHT / 2 },
      style: 'curved',
      color: colors.artifact,
    });
    await renderer.fadeIn(artifactToAnalystArrow.element, duration / 2);
    // Highlight artifact when being read
    renderer.highlight(artifactRef.element, 600);
    arrows.push({
      ref: artifactToAnalystArrow,
      fromTool: { x: toolsX + 100, y: artifactY + ARTIFACT_HEIGHT / 2 },
      toStack: 'analyst', toIndex: readToolCallIndex, toSide: 'left',
    });

    await delay(duration);

    // Analyst: Tool Result
    await pushAnalystWithArrows({ type: 'ToolResult', label: 'Report contents' });
    await delay(duration);

    // Analyst: Ask Oracle
    await pushAnalystWithArrows({ type: 'AskOracle', label: 'Summarize findings' });
    await delay(duration);

    // Analyst: Oracle Response
    await pushAnalystWithArrows({ type: 'OracleResponse', label: 'Key insights...' });
    await delay(duration);

    // Analyst: Task Result
    await pushAnalystWithArrows({ type: 'TaskResult', label: 'Analysis complete' });

    // Stop analyst pulse - animation complete
    if (analystPulseCancel) analystPulseCancel();

    await delay(duration);

    // Replay after a pause
    setTimeout(() => {
      animator.reset();
      runAnimation();
    }, 6000);
  }

  runAnimation();
</script>

<div class="features">
  <div class="feature">
    <h3>State Machine Architecture</h3>
    <p>
      The progression of an agent is managed by a state machine.
      Every step is a state on a stack.
      Easily replay, step-through, branch, and debug your agent's reasoning.
    </p>
  </div>
  <div class="feature">
    <h3>Multi-Agent Native</h3>
    <p>
      Built-in support for parallel agents, synchronous and asynchronous agent-to-agent communication and shared state with namespaces.
    </p>
  </div>
  <div class="feature">
    <h3>Branching</h3>
    <p>
      Support for roll-outs and parallel reasoning traces using branching.
      Every branch is an isolated state machine with a shared history.
    </p>
  </div>
  <div class="feature">
    <h3>Short- and Long-term Memory</h3>
    <p>
      Long-term memory across sessions through artifacts with quality ratings and feedback. Short-term memory through the stack and dynamic context rendering.
    </p>
  </div>
  <div class="feature">
    <h3>Human-in-the-Loop</h3>
    <p>
      Built-in agent-human interactions enabling agents to prompt and interact with humans and for humans to provide unprompted input and guidance.
    </p>
  </div>
  <div class="feature">
    <h3>Session Persistence</h3>
    <p>
      Full execution history saved to disk. Replay from any state, resume interrupted runs, inspect past decisions.
    </p>
  </div>
  <div class="feature">
    <h3>Visual Debugging</h3>
    <p>Real-time web monitor with inter-agent communication arrows, zoom and pan on flowcharts, config transition history, and full rewind capability.</p>
  </div>
  <div class="feature">
    <h3>Dynamic Configuration</h3>
    <p>Agents change behavior mid-execution. Config state machines swap tools, templates, and models based on triggers like tool calls, patterns, or step counts.</p>
  </div>
  <div class="feature">
    <h3>Simple Configuration</h3>
    <p>YAML-based configs for agents, tasks, and tools. Python for custom tool implementations.</p>
  </div>
  <div class="feature">
    <h3>Task Pipelines</h3>
    <p>Chain tasks together into multi-stage pipelines. Each stage passes its results to the next, enabling complex workflows from simple building blocks.</p>
  </div>
  <div class="feature">
    <h3>Structured Parameters</h3>
    <p>Typed, validated task parameters with descriptions, defaults, and required flags. The CLI auto-generates prompts with type hints from your parameter definitions.</p>
  </div>
  <div class="feature">
    <h3>Batteries Included</h3>
    <p>Built-in tools, multiple LLM providers (Anthropic, OpenAI, Ollama with remote support), wait conditions for paced execution, and an interactive CLI to create agents in seconds.</p>
  </div>
</div>

<div class="showcase">
  <h2>See It In Action</h2>
  <p>Some fun examples of apps built with Hugin.</p>
  <div class="showcase-videos">
    <div class="showcase-video">
      <video autoplay loop muted playsinline>
        <source src="/assets/videos/the-hugins.mp4" type="video/mp4">
      </video>
      <h3><a href="https://github.com/gimlelabs/gimle-hugin/tree/main/apps/the_hugins">The Hugins</a></h3>
      <p>AI creatures exploring, crafting, and planning in an isometric world.</p>
    </div>
    <div class="showcase-video">
      <video autoplay loop muted playsinline>
        <source src="/assets/videos/rap-machine.mp4" type="video/mp4">
      </video>
      <h3><a href="https://github.com/gimlelabs/gimle-hugin/tree/main/apps/rap_machine">Rap Machine</a></h3>
      <p>Multi-agent rap battles with AI rappers and judges.</p>
    </div>
  </div>
  <p class="showcase-link">Explore more <a href="/examples/">examples and demo apps</a>.</p>
</div>

<div class="video-lightbox" id="video-lightbox">
  <span class="video-lightbox-close">&times;</span>
  <video autoplay loop muted playsinline id="lightbox-video">
    <source src="" type="video/mp4">
  </video>
</div>

<script>
(function() {
  const lightbox = document.getElementById('video-lightbox');
  const lightboxVideo = document.getElementById('lightbox-video');
  const closeBtn = lightbox.querySelector('.video-lightbox-close');

  // Open lightbox when clicking showcase videos
  document.querySelectorAll('.showcase-video video').forEach(video => {
    video.addEventListener('click', () => {
      const source = video.querySelector('source').src;
      lightboxVideo.querySelector('source').src = source;
      lightboxVideo.load();
      lightbox.classList.add('active');
    });
  });

  // Close lightbox
  function closeLightbox() {
    lightbox.classList.remove('active');
    lightboxVideo.pause();
  }

  closeBtn.addEventListener('click', closeLightbox);
  lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox) closeLightbox();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeLightbox();
  });
})();
</script>

## Getting Started Quickly

Install Hugin and let the agent builder guide you through creating your first agent.
```bash
# Install Hugin
pip install gimle-hugin

# Create and run your first agent
hugin create
```

Or create one manually:

```yaml
# my_agent/configs/my_agent.yaml
name: my_agent
system_template: my_agent
llm_model: haiku-latest
tools:
  - builtins.finish:finish
```

```yaml
# my_agent/templates/my_agent.yaml
name: my_agent
template: |
  You are an expert data analyst.
  Your task is to analyze the data and provide insights.
```

```yaml
# my_agent/tasks/my_task.yaml
name: my_task
parameters:
  data:
    type: string
    description: The data to analyze
    required: true
prompt: "Analyze the data and provide insights: {%raw%}{{ data.value }}{%endraw%}"
```

```bash
hugin run --task my_task --task-path ./my_agent
```

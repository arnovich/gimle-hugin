// Embedded transition illustrations for docs pages.
//
// Kept as a small, standalone renderer so markdown pages stay readable.
// This intentionally mirrors the visuals from the package examples, but renders
// into an existing container instead of being a full page.
const TRANSITIONS = {
  // Left column - main flow
  TaskDefinition: ["AskOracle"],
  AskOracle: ["OracleResponse"],
  OracleResponse: ["ToolCall", "TaskResult"],
  ToolCall: ["ToolResult", "AgentCall"],
  ToolResult: ["AskOracle", "ToolCall", "TaskResult"],
  TaskResult: ["TaskChain"],

  // Right column - secondary flows
  TaskChain: ["TaskDefinition"],
  AgentCall: ["AgentResult"],
  AgentResult: ["AskOracle"],
  AskHuman: ["HumanResponse"],
  HumanResponse: ["AskOracle"],
  ExternalInput: ["AskOracle"],
};

const STATE_CATEGORIES = {
  TaskDefinition: "agent",
  TaskResult: "terminal",
  TaskChain: "agent",
  AskOracle: "llm",
  OracleResponse: "llm",
  ToolCall: "tool",
  ToolResult: "tool",
  AgentCall: "agent",
  AgentResult: "agent",
  AskHuman: "user",
  HumanResponse: "user",
  ExternalInput: "user",
};

function resolveEl(container) {
  if (typeof container === "string") {
    const el = document.querySelector(container);
    if (!el) throw new Error(`Container not found: ${container}`);
    return el;
  }
  return container;
}

function injectStylesOnce() {
  const id = "agent-transition-illustrations-styles";
  if (document.getElementById(id)) return;

  const style = document.createElement("style");
  style.id = id;
  style.textContent = `
  .hugin-embed {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #1f2937;
  }

  /* Transition map */
  .hugin-transition-map .tm-diagram {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: auto;
    background: #ffffff;
  }

  .hugin-transition-map .tm-grid {
    padding: 16px 16px 16px 80px;
  }

  .hugin-transition-map .tm-rows {
    position: relative;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 80px;
  }

  .hugin-transition-map .tm-row {
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 64px;
    align-items: start;
    padding: 6px 0;
  }

  .hugin-transition-map .tm-source {
    display: flex;
    align-items: flex-start;
  }

  .hugin-transition-map .tm-targets {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .hugin-transition-map .tm-state {
    border-radius: 10px;
    padding: 6px 10px;
    font-weight: 600;
    font-size: 12px;
    border: 1px solid;
    user-select: none;
    white-space: nowrap;
  }

  .hugin-transition-map .cat-llm { background: #FFE082; border-color: #E6C200; }
  .hugin-transition-map .cat-tool { background: #90CAF9; border-color: #5BA3E0; }
  .hugin-transition-map .cat-agent { background: #D1C4E9; border-color: #A094C0; }
  .hugin-transition-map .cat-user { background: #FFCDD2; border-color: #E0A0A5; }
  .hugin-transition-map .cat-terminal { background: #A5D6A7; border-color: #70B873; }

  .hugin-transition-map svg.tm-arrows {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  .hugin-transition-map .tm-legend {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 10px 14px;
    margin-top: 16px;
    margin-left: -32px;
    margin-right: 32px;
    padding: 10px 12px;
    border-radius: 10px;
    background: #f8fafc;
    border: 1px solid rgba(0,0,0,0.06);
    color: #334155;
    font-size: 12px;
  }

  .hugin-transition-map .tm-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
    border: 1px solid rgba(0,0,0,0.18);
    margin-right: 6px;
    transform: translateY(1px);
  }

  .hugin-transition-map .dot-llm { background: #FFE082; }
  .hugin-transition-map .dot-tool { background: #90CAF9; }
  .hugin-transition-map .dot-agent { background: #D1C4E9; }
  .hugin-transition-map .dot-user { background: #FFCDD2; }
  .hugin-transition-map .dot-terminal { background: #A5D6A7; }

  /* State graph */
  .hugin-state-graph {
    width: 100%;
    height: 100%;
    background: #ffffff;
    overflow: hidden;
  }
  .hugin-state-graph svg {
    width: 100%;
    height: 100%;
    display: block;
  }
  .hugin-state-graph .node rect {
    rx: 10;
    ry: 10;
    stroke-width: 2;
  }
  .hugin-state-graph .node text {
    font-weight: 600;
    font-size: 12px;
    fill: #0f172a;
  }
  .hugin-state-graph .edge {
    stroke: rgba(100, 116, 139, 0.9);
    stroke-width: 2;
    fill: none;
    marker-end: url(#hugin-arrowhead);
  }
  `;
  document.head.appendChild(style);
}

function catClass(stateType) {
  const cat = STATE_CATEGORIES[stateType] || "agent";
  return `cat-${cat}`;
}

export function renderTransitionMap(container) {
  injectStylesOnce();
  const root = resolveEl(container);
  root.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "hugin-embed hugin-transition-map";

  const diagram = document.createElement("div");
  diagram.className = "tm-diagram";

  const arrows = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  arrows.classList.add("tm-arrows");
  arrows.setAttribute("aria-hidden", "true");

  const grid = document.createElement("div");
  grid.className = "tm-grid";

  const rows = document.createElement("div");
  rows.className = "tm-rows";

  // Build rows
  for (const [source, targets] of Object.entries(TRANSITIONS)) {
    const row = document.createElement("div");
    row.className = "tm-row";

    const sourceCol = document.createElement("div");
    sourceCol.className = "tm-source";
    const sourceBox = document.createElement("div");
    sourceBox.className = `tm-state ${catClass(source)}`;
    sourceBox.dataset.state = source;
    sourceBox.textContent = source;
    sourceCol.appendChild(sourceBox);

    const targetsCol = document.createElement("div");
    targetsCol.className = "tm-targets";
    for (const t of targets) {
      const targetBox = document.createElement("div");
      targetBox.className = `tm-state ${catClass(t)}`;
      targetBox.dataset.state = t;
      targetBox.dataset.from = source;
      targetBox.textContent = t;
      targetsCol.appendChild(targetBox);
    }

    row.appendChild(sourceCol);
    row.appendChild(targetsCol);
    rows.appendChild(row);
  }

  const legend = document.createElement("div");
  legend.className = "tm-legend";
  legend.innerHTML = `
    <span><span class="tm-dot dot-llm"></span>LLM/Oracle</span>
    <span><span class="tm-dot dot-tool"></span>Tool</span>
    <span><span class="tm-dot dot-agent"></span>Agent/Task</span>
    <span><span class="tm-dot dot-user"></span>Human/User</span>
    <span><span class="tm-dot dot-terminal"></span>Terminal</span>
  `;

  grid.appendChild(rows);
  grid.appendChild(legend);

  diagram.appendChild(arrows);
  diagram.appendChild(grid);
  wrap.appendChild(diagram);
  root.appendChild(wrap);

  function drawArrows() {
    // Clear SVG
    while (arrows.firstChild) arrows.removeChild(arrows.firstChild);

    // Match SVG to scrollable area
    const rect = diagram.getBoundingClientRect();
    arrows.setAttribute("width", String(diagram.scrollWidth));
    arrows.setAttribute("height", String(diagram.scrollHeight));
    arrows.setAttribute("viewBox", `0 0 ${diagram.scrollWidth} ${diagram.scrollHeight}`);

    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    defs.innerHTML = `
      <marker id="hugin-tm-arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
        <polygon points="0 0, 10 3.5, 0 7" fill="rgba(100,116,139,0.9)" />
      </marker>
    `;
    arrows.appendChild(defs);

    // For each row, connect source -> each target with a gentle curve.
    const rowsEls = rows.querySelectorAll(".tm-row");
    rowsEls.forEach((rowEl) => {
      const sourceEl = rowEl.querySelector(".tm-source .tm-state");
      const targetEls = rowEl.querySelectorAll(".tm-targets .tm-state");
      if (!sourceEl || targetEls.length === 0) return;

      const s = sourceEl.getBoundingClientRect();
      const sX = s.right - rect.left + diagram.scrollLeft;
      const sY = s.top - rect.top + diagram.scrollTop + s.height / 2;

      targetEls.forEach((targetEl) => {
        const t = targetEl.getBoundingClientRect();
        const tX = t.left - rect.left + diagram.scrollLeft;
        const tY = t.top - rect.top + diagram.scrollTop + t.height / 2;

        const midX = (sX + tX) / 2;
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute(
          "d",
          `M ${sX} ${sY} C ${midX} ${sY}, ${midX} ${tY}, ${tX} ${tY}`
        );
        path.setAttribute("fill", "none");
        path.setAttribute("stroke", "rgba(100, 116, 139, 0.85)");
        path.setAttribute("stroke-width", "2");
        path.setAttribute("marker-end", "url(#hugin-tm-arrowhead)");
        arrows.appendChild(path);
      });
    });
  }

  // Initial + keep arrows aligned with scrolling/resizing
  drawArrows();
  diagram.addEventListener("scroll", () => drawArrows(), { passive: true });
  new ResizeObserver(() => drawArrows()).observe(diagram);
}

export function renderStateTransitions(container) {
  injectStylesOnce();
  const root = resolveEl(container);
  root.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "hugin-embed hugin-state-graph";

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Hugin interaction state transitions");
  wrap.appendChild(svg);
  root.appendChild(wrap);

  // Simple, static layout (mirrors the example's positions)
  const positions = {
    // Main flow (left column)
    TaskDefinition: { x: 80, y: 50 },
    AskOracle: { x: 80, y: 170 },
    OracleResponse: { x: 80, y: 290 },

    // Tool flow (center column)
    ToolCall: { x: 320, y: 210 },
    ToolResult: { x: 320, y: 330 },

    // Agent delegation (right-center column)
    AgentCall: { x: 560, y: 210 },
    AgentResult: { x: 560, y: 330 },

    // Human interactions (right column)
    AskHuman: { x: 800, y: 210 },
    HumanResponse: { x: 800, y: 330 },
    ExternalInput: { x: 800, y: 90 },

    // Completion states (bottom row)
    TaskResult: { x: 80, y: 450 },
    TaskChain: { x: 320, y: 450 },
  };

  const colors = {
    llm: { bg: "#FFE082", border: "#E6C200" },
    tool: { bg: "#90CAF9", border: "#5BA3E0" },
    agent: { bg: "#D1C4E9", border: "#A094C0" },
    user: { bg: "#FFCDD2", border: "#E0A0A5" },
    terminal: { bg: "#A5D6A7", border: "#70B873" },
  };

  const stateW = 150;
  const stateH = 44;

  function ensureSize() {
    const w = root.clientWidth || 900;
    const h = root.clientHeight || 600;
    svg.setAttribute("viewBox", `0 0 ${Math.max(w, 980)} ${Math.max(h, 540)}`);
  }

  function addDefs() {
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    defs.innerHTML = `
      <marker id="hugin-arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
        <polygon points="0 0, 10 3.5, 0 7" fill="rgba(100,116,139,0.9)" />
      </marker>
    `;
    svg.appendChild(defs);
  }

  function connection(from, to) {
    const a = positions[from];
    const b = positions[to];
    if (!a || !b) return null;

    const ax = a.x + stateW / 2;
    const ay = a.y + stateH / 2;
    const bx = b.x + stateW / 2;
    const by = b.y + stateH / 2;

    // Exit/entry points (rough but clean)
    const dx = bx - ax;
    const dy = by - ay;
    const fromPoint =
      Math.abs(dx) > Math.abs(dy)
        ? { x: a.x + (dx > 0 ? stateW : 0), y: ay }
        : { x: ax, y: a.y + (dy > 0 ? stateH : 0) };
    const toPoint =
      Math.abs(dx) > Math.abs(dy)
        ? { x: b.x + (dx > 0 ? 0 : stateW), y: by }
        : { x: bx, y: b.y + (dy > 0 ? 0 : stateH) };

    const midX = (fromPoint.x + toPoint.x) / 2;
    return `M ${fromPoint.x} ${fromPoint.y} C ${midX} ${fromPoint.y}, ${midX} ${toPoint.y}, ${toPoint.x} ${toPoint.y}`;
  }

  function draw() {
    ensureSize();
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    addDefs();

    // Edges first (behind nodes)
    for (const [from, tos] of Object.entries(TRANSITIONS)) {
      for (const to of tos) {
        const d = connection(from, to);
        if (!d) continue;
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", d);
        path.setAttribute("class", "edge");
        svg.appendChild(path);
      }
    }

    // Nodes
    for (const [state, pos] of Object.entries(positions)) {
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "node");
      g.setAttribute("transform", `translate(${pos.x}, ${pos.y})`);

      const cat = STATE_CATEGORIES[state] || "agent";
      const c = colors[cat] || colors.agent;

      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("width", String(stateW));
      rect.setAttribute("height", String(stateH));
      rect.setAttribute("fill", c.bg);
      rect.setAttribute("stroke", c.border);

      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", String(stateW / 2));
      text.setAttribute("y", String(stateH / 2 + 5));
      text.setAttribute("text-anchor", "middle");
      text.textContent = state;

      g.appendChild(rect);
      g.appendChild(text);
      svg.appendChild(g);
    }
  }

  draw();
  new ResizeObserver(() => draw()).observe(root);
}

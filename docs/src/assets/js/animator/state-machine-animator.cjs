"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var src_exports = {};
__export(src_exports, {
  SVGRenderer: () => SVGRenderer,
  StateMachineAnimator: () => StateMachineAnimator,
  categoryLabels: () => categoryLabels,
  darkTheme: () => darkTheme,
  dimensions: () => dimensions,
  easeIn: () => easeIn,
  easeInBack: () => easeInBack,
  easeInBounce: () => easeInBounce,
  easeInCubic: () => easeInCubic,
  easeInOut: () => easeInOut,
  easeInOutBack: () => easeInOutBack,
  easeInOutCubic: () => easeInOutCubic,
  easeInOutQuad: () => easeInOutQuad,
  easeInQuad: () => easeInQuad,
  easeOut: () => easeOut,
  easeOutBack: () => easeOutBack,
  easeOutBounce: () => easeOutBounce,
  easeOutCubic: () => easeOutCubic,
  easeOutQuad: () => easeOutQuad,
  easingPresets: () => easingPresets,
  getEasing: () => getEasing,
  getStateCategory: () => getStateCategory,
  getStateColors: () => getStateColors,
  getTheme: () => getTheme,
  lightTheme: () => lightTheme,
  linear: () => linear
});
module.exports = __toCommonJS(src_exports);

// src/core/types.ts
function getStateCategory(type) {
  switch (type) {
    // LLM/Oracle interactions (yellow)
    case "AskOracle":
    case "OracleResponse":
      return "llm";
    // Tool interactions (blue)
    case "ToolCall":
    case "ToolResult":
      return "tool";
    // Agent/Task interactions (purple)
    case "AgentCall":
    case "AgentResult":
    case "TaskDefinition":
    case "TaskChain":
      return "agent";
    // Human interactions (orange)
    case "AskHuman":
    case "HumanResponse":
    case "ExternalInput":
      return "user";
    // Terminal/control states (green)
    case "TaskResult":
    case "Waiting":
      return "terminal";
    default:
      return "agent";
  }
}

// src/utils/colors.ts
var lightTheme = {
  background: "#ffffff",
  stateColors: {
    // Yellow - LLM interactions (UserMessage, AssistantMessage)
    llm: {
      background: "#FFE082",
      border: "#E6C200",
      text: "#000000"
    },
    // Blue - Tool interactions (ToolCall, ToolResult)
    tool: {
      background: "#90CAF9",
      border: "#5BA3E0",
      text: "#000000"
    },
    // Lavender/Purple - Agent interactions (AgentCall, AgentResult)
    agent: {
      background: "#D1C4E9",
      border: "#A094C0",
      text: "#000000"
    },
    // Pink/Salmon - User interactions (UserInputRequired, UserResponse)
    user: {
      background: "#FFCDD2",
      border: "#E0A0A5",
      text: "#000000"
    },
    // Green - Terminal states (Finished)
    terminal: {
      background: "#A5D6A7",
      border: "#70B873",
      text: "#000000"
    }
  },
  textColor: "#000000",
  arrowColor: "#424242",
  stackBackground: "transparent",
  stackBorderColor: "transparent",
  // Orange/Peach for "execution" boxes (Tool Execution, LLM Call, etc.)
  toolColor: "#FFCC80",
  toolBorderColor: "#E6A550",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif"
};
var darkTheme = {
  background: "#1a1a2e",
  stateColors: {
    // Yellow - LLM/Oracle interactions
    llm: {
      background: "#3d3d00",
      border: "#fbc02d",
      text: "#fff9c4"
    },
    // Blue - Tool interactions
    tool: {
      background: "#0d2137",
      border: "#5dade2",
      text: "#e3f2fd"
    },
    // Purple - Agent/Task interactions
    agent: {
      background: "#2d1f3d",
      border: "#bb8fce",
      text: "#f3e5f5"
    },
    // Orange - User/Human interactions
    user: {
      background: "#3d2600",
      border: "#f5b041",
      text: "#fff3e0"
    },
    // Green/Gray - Terminal states
    terminal: {
      background: "#1a3d1f",
      border: "#58d68d",
      text: "#e8f5e9"
    }
  },
  textColor: "#eaecee",
  arrowColor: "#5dade2",
  stackBackground: "#2d2d44",
  stackBorderColor: "#3d3d5c",
  toolColor: "#1a2f3d",
  toolBorderColor: "#5dade2",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif"
};
function getTheme(theme) {
  if (theme === "light") return lightTheme;
  if (theme === "dark") return darkTheme;
  return theme;
}
function getStateColors(state, theme) {
  if (state.color || state.borderColor) {
    return {
      background: state.color || theme.stateColors.agent.background,
      border: state.borderColor || state.color || theme.stateColors.agent.border,
      text: theme.textColor
    };
  }
  const category = getStateCategory(state.type);
  const colors = theme.stateColors[category];
  return {
    background: colors.background,
    border: colors.border,
    text: colors.text || theme.textColor
  };
}
var categoryLabels = {
  llm: "LLM Interaction",
  tool: "Tool Execution",
  agent: "Agent/Task",
  user: "User Input",
  terminal: "Terminal"
};

// src/utils/layout.ts
var dimensions = {
  state: {
    width: 165,
    height: 42,
    borderRadius: 14,
    // Generous rounded corners like the blog
    padding: 12,
    fontSize: 15,
    labelFontSize: 11
  },
  stack: {
    stateSpacing: 4,
    // Small gap between states
    padding: 0,
    // No container padding (floating boxes)
    labelHeight: 40,
    // Height for stack label area (includes spacing below label)
    minWidth: 170,
    borderRadius: 14
  },
  tool: {
    width: 140,
    height: 44,
    borderRadius: 14,
    // Match state border radius
    iconSize: 18
  },
  artifact: {
    width: 100,
    height: 70,
    foldSize: 16,
    // Size of the folded corner
    borderRadius: 4
    // Smaller radius for document look
  },
  arrow: {
    strokeWidth: 1.5,
    // Thin arrows like the blog
    headSize: 6,
    dashArray: "5,5"
  },
  spacing: {
    stackGap: 80,
    // Gap between stacks
    toolGap: 50,
    // Gap between stack and tool
    branchGap: 50
    // Gap between branches
  }
};
function calculateStackHeight(numStates) {
  const { stateSpacing, padding, labelHeight } = dimensions.stack;
  const { height: stateHeight } = dimensions.state;
  if (numStates === 0) {
    return labelHeight + padding * 2 + stateHeight;
  }
  return labelHeight + padding * 2 + numStates * stateHeight + (numStates - 1) * stateSpacing;
}
function getStatePositionInStack(stackX, stackY, stackWidth, totalStates, stateIndex) {
  const { stateSpacing, padding, labelHeight } = dimensions.stack;
  const { height: stateHeight, width: stateWidth } = dimensions.state;
  const x = stackX + (stackWidth - stateWidth) / 2;
  const reversedIndex = totalStates - 1 - stateIndex;
  const y = stackY + labelHeight + padding + reversedIndex * (stateHeight + stateSpacing);
  return { x, y };
}
function getRectCenter(rect) {
  return {
    x: rect.x + rect.width / 2,
    y: rect.y + rect.height / 2
  };
}
function getConnectionPoints(from, to, fromSide = "right", toSide = "left") {
  const getPoint = (rect, side) => {
    switch (side) {
      case "top":
        return { x: rect.x + rect.width / 2, y: rect.y };
      case "bottom":
        return { x: rect.x + rect.width / 2, y: rect.y + rect.height };
      case "left":
        return { x: rect.x, y: rect.y + rect.height / 2 };
      case "right":
        return { x: rect.x + rect.width, y: rect.y + rect.height / 2 };
      default:
        return getRectCenter(rect);
    }
  };
  return {
    from: getPoint(from, fromSide),
    to: getPoint(to, toSide)
  };
}
function getCurvedArrowPath(from, to) {
  const midX = (from.x + to.x) / 2;
  const midY = (from.y + to.y) / 2;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const curveOffset = Math.min(Math.abs(dx), Math.abs(dy)) * 0.3;
  const controlX = midX;
  const controlY = midY - curveOffset;
  return `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`;
}
function getSteppedArrowPath(from, to) {
  const midX = (from.x + to.x) / 2;
  return `M ${from.x} ${from.y} L ${midX} ${from.y} L ${midX} ${to.y} L ${to.x} ${to.y}`;
}
function getStraightArrowPath(from, to) {
  return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
}

// src/renderers/SVGRenderer.ts
var SVG_NS = "http://www.w3.org/2000/svg";
function createSVGElement(tagName, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tagName);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  return element;
}
var idCounter = 0;
function generateId(prefix) {
  return `${prefix}-${++idCounter}`;
}
var SVGRenderer = class {
  constructor(config) {
    this.elements = /* @__PURE__ */ new Map();
    this.resizeObserver = null;
    // Pan and zoom state
    this.panX = 0;
    this.panY = 0;
    this.zoom = 1;
    this.isPanning = false;
    this.lastMouseX = 0;
    this.lastMouseY = 0;
    this.minZoom = 0.25;
    this.maxZoom = 4;
    // Tooltip elements
    this.tooltipGroup = null;
    this.tooltipVisible = false;
    if (typeof config.container === "string") {
      const el = document.querySelector(config.container);
      if (!el) {
        throw new Error(`Container not found: ${config.container}`);
      }
      this.container = el;
    } else {
      this.container = config.container;
    }
    this.theme = getTheme(config.theme || "light");
    this.padding = config.padding ?? 20;
    this.width = config.width ?? (this.container.clientWidth || 800);
    this.height = config.height ?? (this.container.clientHeight || 600);
    this.svg = createSVGElement("svg", {
      width: this.width,
      height: this.height,
      viewBox: `0 0 ${this.width} ${this.height}`
    });
    this.svg.style.fontFamily = this.theme.fontFamily;
    this.svg.style.display = "block";
    this.defs = createSVGElement("defs");
    this.svg.appendChild(this.defs);
    this.addFiltersAndGradients();
    this.mainGroup = createSVGElement("g", {
      transform: `translate(${this.padding}, ${this.padding})`
    });
    this.svg.appendChild(this.mainGroup);
    this.drawBackground();
    this.container.appendChild(this.svg);
    if (config.responsive) {
      this.setupResponsive();
    }
    this.setupPanZoom();
    this.createTooltip();
  }
  /**
   * Setup pan and zoom event handlers
   */
  setupPanZoom() {
    this.svg.style.cursor = "grab";
    this.svg.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      this.isPanning = true;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
      this.svg.style.cursor = "grabbing";
      e.preventDefault();
    });
    this.svg.addEventListener("mousemove", (e) => {
      if (!this.isPanning) return;
      const dx = e.clientX - this.lastMouseX;
      const dy = e.clientY - this.lastMouseY;
      this.panX += dx / this.zoom;
      this.panY += dy / this.zoom;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
      this.updateTransform();
    });
    this.svg.addEventListener("mouseup", () => {
      this.isPanning = false;
      this.svg.style.cursor = "grab";
    });
    this.svg.addEventListener("mouseleave", () => {
      this.isPanning = false;
      this.svg.style.cursor = "grab";
    });
    this.svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = this.svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;
      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.max(
        this.minZoom,
        Math.min(this.maxZoom, this.zoom * zoomFactor)
      );
      if (newZoom !== this.zoom) {
        const zoomRatio = newZoom / this.zoom;
        this.panX -= mouseX / this.zoom * (zoomRatio - 1);
        this.panY -= mouseY / this.zoom * (zoomRatio - 1);
        this.zoom = newZoom;
        this.updateTransform();
      }
    });
  }
  /**
   * Update the main group transform based on pan/zoom state
   */
  updateTransform() {
    this.mainGroup.setAttribute(
      "transform",
      `translate(${this.panX + this.padding}, ${this.panY + this.padding}) scale(${this.zoom})`
    );
  }
  /**
   * Reset pan and zoom to default
   */
  resetView() {
    this.panX = 0;
    this.panY = 0;
    this.zoom = 1;
    this.updateTransform();
  }
  /**
   * Set zoom level programmatically
   */
  setZoom(level) {
    this.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, level));
    this.updateTransform();
  }
  /**
   * Get current zoom level
   */
  getZoom() {
    return this.zoom;
  }
  /**
   * Create tooltip element
   */
  createTooltip() {
    this.tooltipGroup = createSVGElement("g", {
      class: "tooltip",
      style: "pointer-events: none; opacity: 0; transition: opacity 0.15s ease-out;"
    });
    const bg = createSVGElement("rect", {
      class: "tooltip-bg",
      rx: 6,
      ry: 6,
      fill: "rgba(45, 55, 72, 0.95)",
      stroke: "rgba(255, 255, 255, 0.1)",
      "stroke-width": 1
    });
    this.tooltipGroup.appendChild(bg);
    const textGroup = createSVGElement("g", {
      class: "tooltip-text"
    });
    this.tooltipGroup.appendChild(textGroup);
    this.svg.appendChild(this.tooltipGroup);
  }
  /**
   * Show tooltip with state information
   */
  showTooltip(state, screenX, screenY) {
    if (!this.tooltipGroup) return;
    const textGroup = this.tooltipGroup.querySelector(".tooltip-text");
    const bg = this.tooltipGroup.querySelector(".tooltip-bg");
    while (textGroup.firstChild) {
      textGroup.removeChild(textGroup.firstChild);
    }
    const padding = 12;
    const lineHeight = 18;
    let currentY = padding + 12;
    let maxWidth = 0;
    const typeText = createSVGElement("text", {
      x: padding,
      y: currentY,
      "font-size": 13,
      "font-weight": "600",
      fill: "#fff"
    });
    typeText.textContent = state.type;
    textGroup.appendChild(typeText);
    maxWidth = Math.max(maxWidth, state.type.length * 8);
    currentY += lineHeight;
    if (state.label) {
      const labelText = createSVGElement("text", {
        x: padding,
        y: currentY,
        "font-size": 11,
        fill: "rgba(255, 255, 255, 0.8)"
      });
      labelText.textContent = state.label;
      textGroup.appendChild(labelText);
      maxWidth = Math.max(maxWidth, state.label.length * 6);
      currentY += lineHeight;
    }
    if (state.data) {
      currentY += 4;
      const dataEntries = Object.entries(state.data).slice(0, 3);
      for (const [key, value] of dataEntries) {
        const dataText = createSVGElement("text", {
          x: padding,
          y: currentY,
          "font-size": 10,
          fill: "rgba(255, 255, 255, 0.6)"
        });
        const valueStr = String(value).substring(0, 30);
        dataText.textContent = `${key}: ${valueStr}`;
        textGroup.appendChild(dataText);
        maxWidth = Math.max(maxWidth, (key.length + valueStr.length + 2) * 5.5);
        currentY += lineHeight - 4;
      }
    }
    const tooltipWidth = Math.max(120, maxWidth + padding * 2);
    const tooltipHeight = currentY + padding - 6;
    bg.setAttribute("width", String(tooltipWidth));
    bg.setAttribute("height", String(tooltipHeight));
    const svgRect = this.svg.getBoundingClientRect();
    let tooltipX = screenX - svgRect.left + 15;
    let tooltipY = screenY - svgRect.top - tooltipHeight / 2;
    if (tooltipX + tooltipWidth > this.width - 10) {
      tooltipX = screenX - svgRect.left - tooltipWidth - 15;
    }
    if (tooltipY < 10) {
      tooltipY = 10;
    }
    if (tooltipY + tooltipHeight > this.height - 10) {
      tooltipY = this.height - tooltipHeight - 10;
    }
    this.tooltipGroup.setAttribute("transform", `translate(${tooltipX}, ${tooltipY})`);
    this.tooltipGroup.style.opacity = "1";
    this.tooltipVisible = true;
  }
  /**
   * Hide tooltip
   */
  hideTooltip() {
    if (this.tooltipGroup && this.tooltipVisible) {
      this.tooltipGroup.style.opacity = "0";
      this.tooltipVisible = false;
    }
  }
  /**
   * Pan to center on a specific point
   */
  panTo(x, y) {
    this.panX = this.width / 2 / this.zoom - x;
    this.panY = this.height / 2 / this.zoom - y;
    this.updateTransform();
  }
  /**
   * Add reusable SVG definitions
   */
  addFiltersAndGradients() {
    const dropShadow = createSVGElement("filter", {
      id: "drop-shadow",
      x: "-20%",
      y: "-20%",
      width: "140%",
      height: "140%"
    });
    const feGaussianBlur = createSVGElement("feGaussianBlur", {
      in: "SourceAlpha",
      stdDeviation: "2",
      result: "blur"
    });
    const feOffset = createSVGElement("feOffset", {
      in: "blur",
      dx: "0",
      dy: "1",
      result: "offsetBlur"
    });
    const feFlood = createSVGElement("feFlood", {
      "flood-color": "rgba(0,0,0,0.15)",
      result: "color"
    });
    const feComposite = createSVGElement("feComposite", {
      in: "color",
      in2: "offsetBlur",
      operator: "in",
      result: "shadow"
    });
    const feMerge = createSVGElement("feMerge");
    const feMergeNode1 = createSVGElement("feMergeNode", { in: "shadow" });
    const feMergeNode2 = createSVGElement("feMergeNode", { in: "SourceGraphic" });
    feMerge.appendChild(feMergeNode1);
    feMerge.appendChild(feMergeNode2);
    dropShadow.appendChild(feGaussianBlur);
    dropShadow.appendChild(feOffset);
    dropShadow.appendChild(feFlood);
    dropShadow.appendChild(feComposite);
    dropShadow.appendChild(feMerge);
    this.defs.appendChild(dropShadow);
    const glow = createSVGElement("filter", {
      id: "glow",
      x: "-50%",
      y: "-50%",
      width: "200%",
      height: "200%"
    });
    const feGlow = createSVGElement("feGaussianBlur", {
      stdDeviation: "3",
      result: "coloredBlur"
    });
    const feMergeGlow = createSVGElement("feMerge");
    const feMergeGlowNode1 = createSVGElement("feMergeNode", { in: "coloredBlur" });
    const feMergeGlowNode2 = createSVGElement("feMergeNode", { in: "SourceGraphic" });
    feMergeGlow.appendChild(feMergeGlowNode1);
    feMergeGlow.appendChild(feMergeGlowNode2);
    glow.appendChild(feGlow);
    glow.appendChild(feMergeGlow);
    this.defs.appendChild(glow);
    const arrowMarker = createSVGElement("marker", {
      id: "arrowhead",
      markerWidth: "10",
      markerHeight: "7",
      refX: "9",
      refY: "3.5",
      orient: "auto",
      markerUnits: "strokeWidth"
    });
    const arrowPath = createSVGElement("polygon", {
      points: "0 0, 10 3.5, 0 7",
      fill: this.theme.arrowColor
    });
    arrowMarker.appendChild(arrowPath);
    this.defs.appendChild(arrowMarker);
  }
  /**
   * Draw background
   */
  drawBackground() {
    const bg = createSVGElement("rect", {
      x: -this.padding,
      y: -this.padding,
      width: this.width,
      height: this.height,
      fill: this.theme.background
    });
    this.mainGroup.insertBefore(bg, this.mainGroup.firstChild);
  }
  /**
   * Setup responsive behavior
   */
  setupResponsive() {
    this.resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          this.resize(width, height);
        }
      }
    });
    this.resizeObserver.observe(this.container);
  }
  /**
   * Clear all rendered elements
   */
  clear() {
    while (this.mainGroup.children.length > 1) {
      this.mainGroup.removeChild(this.mainGroup.lastChild);
    }
    this.elements.clear();
  }
  /**
   * Resize the canvas
   */
  resize(width, height) {
    this.width = width;
    this.height = height;
    this.svg.setAttribute("width", String(width));
    this.svg.setAttribute("height", String(height));
    this.svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  }
  /**
   * Get the SVG element
   */
  getElement() {
    return this.svg;
  }
  /**
   * Get the theme
   */
  getTheme() {
    return this.theme;
  }
  /**
   * Get available drawing area
   */
  getDrawingArea() {
    return {
      x: 0,
      y: 0,
      width: this.width - this.padding * 2,
      height: this.height - this.padding * 2
    };
  }
  /**
   * Draw a state box
   */
  drawState(state, x, y) {
    const id = state.id || generateId("state");
    const colors = getStateColors(state, this.theme);
    const { width, height, borderRadius, padding, fontSize, labelFontSize } = dimensions.state;
    const group = createSVGElement("g", {
      id,
      transform: `translate(${x}, ${y})`,
      class: "state-box"
    });
    const rect = createSVGElement("rect", {
      x: 0,
      y: 0,
      width,
      height,
      rx: borderRadius,
      ry: borderRadius,
      fill: colors.background,
      stroke: colors.border,
      "stroke-width": 1.5
    });
    group.appendChild(rect);
    const typeLabel = createSVGElement("text", {
      x: width / 2,
      y: height / 2 - (state.label ? 4 : 0),
      "font-size": fontSize,
      "font-weight": "500",
      fill: colors.text,
      "text-anchor": "middle",
      "dominant-baseline": "middle"
    });
    typeLabel.textContent = state.type;
    group.appendChild(typeLabel);
    if (state.label) {
      const detailLabel = createSVGElement("text", {
        x: width / 2,
        y: height / 2 + 10,
        "font-size": labelFontSize,
        fill: colors.text,
        opacity: 0.7,
        "text-anchor": "middle",
        "dominant-baseline": "middle"
      });
      const maxLen = Math.floor((width - padding * 2) / 6);
      detailLabel.textContent = state.label.length > maxLen ? state.label.substring(0, maxLen - 2) + "..." : state.label;
      group.appendChild(detailLabel);
    }
    this.mainGroup.appendChild(group);
    group.style.cursor = "pointer";
    group.addEventListener("mouseenter", (e) => {
      rect.setAttribute("stroke-width", "2.5");
      rect.style.filter = "brightness(1.05)";
      this.showTooltip(state, e.clientX, e.clientY);
    });
    group.addEventListener("mousemove", (e) => {
      if (this.tooltipVisible) {
        this.showTooltip(state, e.clientX, e.clientY);
      }
    });
    group.addEventListener("mouseleave", () => {
      rect.setAttribute("stroke-width", "1.5");
      rect.style.filter = "";
      this.hideTooltip();
    });
    const ref = {
      type: "state",
      id,
      element: group,
      bounds: { x, y, width, height }
    };
    this.elements.set(id, ref);
    return ref;
  }
  /**
   * Draw a stack container with states
   */
  drawStack(stack, x, y) {
    const id = stack.id || generateId("stack");
    const { padding: stackPadding, borderRadius, minWidth } = dimensions.stack;
    const { width: stateWidth } = dimensions.state;
    const stackWidth = Math.max(minWidth, stateWidth + stackPadding * 2);
    const stackHeight = calculateStackHeight(stack.states.length);
    const group = createSVGElement("g", {
      id,
      transform: `translate(${x}, ${y})`,
      class: "stack-container"
    });
    const bg = createSVGElement("rect", {
      x: 0,
      y: 0,
      width: stackWidth,
      height: stackHeight,
      rx: borderRadius,
      ry: borderRadius,
      fill: this.theme.stackBackground,
      stroke: this.theme.stackBorderColor,
      "stroke-width": 1
    });
    group.appendChild(bg);
    if (stack.label) {
      const label = createSVGElement("text", {
        x: stackWidth / 2,
        y: 18,
        "font-size": 14,
        "font-weight": "600",
        fill: this.theme.textColor,
        "text-anchor": "middle",
        "dominant-baseline": "middle"
      });
      label.textContent = stack.label;
      group.appendChild(label);
      const sep = createSVGElement("line", {
        x1: stackPadding + 8,
        y1: 32,
        x2: stackWidth - stackPadding - 8,
        y2: 32,
        stroke: this.theme.stackBorderColor,
        "stroke-width": 1
      });
      group.appendChild(sep);
    }
    this.mainGroup.appendChild(group);
    const stateRefs = [];
    for (let i = 0; i < stack.states.length; i++) {
      const statePos = getStatePositionInStack(
        x,
        y,
        stackWidth,
        stack.states.length,
        i
      );
      const stateRef = this.drawState(stack.states[i], statePos.x, statePos.y);
      stateRefs.push(stateRef);
    }
    for (let i = 0; i < stateRefs.length - 1; i++) {
      const from = stateRefs[i];
      const to = stateRefs[i + 1];
      this.drawStackArrow(
        { x: from.bounds.x + from.bounds.width / 2, y: from.bounds.y },
        { x: to.bounds.x + to.bounds.width / 2, y: to.bounds.y + to.bounds.height }
      );
    }
    const ref = {
      type: "stack",
      id,
      element: group,
      bounds: { x, y, width: stackWidth, height: stackHeight },
      childRefs: stateRefs
    };
    this.elements.set(id, ref);
    return ref;
  }
  /**
   * Draw a small arrow between stack states
   */
  drawStackArrow(from, to) {
    const arrow = createSVGElement("text", {
      x: from.x,
      y: (from.y + to.y) / 2 + 2,
      "font-size": 10,
      fill: this.theme.arrowColor,
      "text-anchor": "middle",
      "dominant-baseline": "middle"
    });
    arrow.textContent = "\u2193";
    this.mainGroup.appendChild(arrow);
  }
  /**
   * Draw a tool box
   */
  drawTool(tool, x, y, hidden = false) {
    const id = tool.id || generateId("tool");
    const { width, height, borderRadius } = dimensions.tool;
    const group = createSVGElement("g", {
      id,
      transform: `translate(${x}, ${y})`,
      class: "tool-box",
      style: hidden ? "opacity: 0;" : ""
    });
    const rect = createSVGElement("rect", {
      x: 0,
      y: 0,
      width,
      height,
      rx: borderRadius,
      ry: borderRadius,
      fill: tool.color || this.theme.toolColor,
      stroke: this.theme.toolBorderColor,
      "stroke-width": 1.5
    });
    group.appendChild(rect);
    const displayText = tool.icon ? `${tool.icon} ${tool.name}` : tool.name;
    const name = createSVGElement("text", {
      x: width / 2,
      y: height / 2,
      "font-size": 14,
      "font-weight": "500",
      fill: this.theme.textColor,
      "text-anchor": "middle",
      "dominant-baseline": "middle"
    });
    name.textContent = displayText;
    group.appendChild(name);
    this.mainGroup.appendChild(group);
    const ref = {
      type: "tool",
      id,
      element: group,
      bounds: { x, y, width, height }
    };
    this.elements.set(id, ref);
    return ref;
  }
  /**
   * Draw an artifact (document with folded corner)
   */
  drawArtifact(artifact, x, y, hidden = false) {
    const id = artifact.id || generateId("artifact");
    const { width, height, foldSize, borderRadius } = dimensions.artifact;
    const group = createSVGElement("g", {
      id,
      transform: `translate(${x}, ${y})`,
      class: "artifact",
      style: hidden ? "opacity: 0;" : ""
    });
    const docPath = `
      M ${borderRadius} 0
      L ${width - foldSize} 0
      L ${width} ${foldSize}
      L ${width} ${height - borderRadius}
      Q ${width} ${height} ${width - borderRadius} ${height}
      L ${borderRadius} ${height}
      Q 0 ${height} 0 ${height - borderRadius}
      L 0 ${borderRadius}
      Q 0 0 ${borderRadius} 0
      Z
    `;
    const doc = createSVGElement("path", {
      d: docPath,
      fill: artifact.color || "#e8f5e9",
      stroke: "#4caf50",
      "stroke-width": 1.5
    });
    group.appendChild(doc);
    const foldPath = `
      M ${width - foldSize} 0
      L ${width - foldSize} ${foldSize}
      L ${width} ${foldSize}
      Z
    `;
    const fold = createSVGElement("path", {
      d: foldPath,
      fill: "#c8e6c9",
      stroke: "#4caf50",
      "stroke-width": 1
    });
    group.appendChild(fold);
    let icon = artifact.icon;
    if (!icon) {
      switch (artifact.type) {
        case "document":
          icon = "\u{1F4C4}";
          break;
        case "image":
          icon = "\u{1F5BC}";
          break;
        case "data":
          icon = "\u{1F4CA}";
          break;
        case "code":
          icon = "\u{1F4BB}";
          break;
        default:
          icon = "\u{1F4C1}";
      }
    }
    const iconText = createSVGElement("text", {
      x: width / 2,
      y: height / 2 - 6,
      "font-size": 20,
      "text-anchor": "middle",
      "dominant-baseline": "middle"
    });
    iconText.textContent = icon;
    group.appendChild(iconText);
    const name = createSVGElement("text", {
      x: width / 2,
      y: height - 12,
      "font-size": 10,
      "font-weight": "500",
      fill: "#2e7d32",
      "text-anchor": "middle"
    });
    const displayName = artifact.name.length > 12 ? artifact.name.substring(0, 10) + "..." : artifact.name;
    name.textContent = artifact.extension ? `${displayName}.${artifact.extension}` : displayName;
    group.appendChild(name);
    this.mainGroup.appendChild(group);
    const ref = {
      type: "artifact",
      id,
      element: group,
      bounds: { x, y, width, height }
    };
    this.elements.set(id, ref);
    return ref;
  }
  /**
   * Draw an arrow/connection between two points
   */
  drawArrow(options) {
    const id = generateId("arrow");
    const { from, to, style = "curved", strokeWidth = 2, color, dashArray, animated, hidden } = options;
    const group = createSVGElement("g", {
      id,
      class: "arrow",
      style: hidden ? "opacity: 0;" : ""
    });
    let pathD;
    switch (style) {
      case "straight":
        pathD = getStraightArrowPath(from, to);
        break;
      case "stepped":
        pathD = getSteppedArrowPath(from, to);
        break;
      case "curved":
      default:
        pathD = getCurvedArrowPath(from, to);
    }
    const path = createSVGElement("path", {
      d: pathD,
      fill: "none",
      stroke: color || this.theme.arrowColor,
      "stroke-width": strokeWidth,
      "stroke-linecap": "round",
      "marker-end": options.showHead !== false ? "url(#arrowhead)" : ""
    });
    if (dashArray) {
      path.setAttribute("stroke-dasharray", dashArray);
    }
    if (animated) {
      path.setAttribute("stroke-dasharray", "8 4");
      path.style.animation = "dash 0.5s linear infinite";
    }
    group.appendChild(path);
    this.mainGroup.appendChild(group);
    const minX = Math.min(from.x, to.x);
    const minY = Math.min(from.y, to.y);
    const maxX = Math.max(from.x, to.x);
    const maxY = Math.max(from.y, to.y);
    const ref = {
      type: "arrow",
      id,
      element: group,
      bounds: { x: minX, y: minY, width: maxX - minX, height: maxY - minY }
    };
    this.elements.set(id, ref);
    return ref;
  }
  /**
   * Update an arrow's path to new endpoints (with animation)
   */
  async updateArrowPath(arrowRef, from, to, style = "curved", duration = 300) {
    const group = arrowRef.element;
    const path = group.querySelector("path");
    if (!path) return;
    let pathD;
    switch (style) {
      case "straight":
        pathD = getStraightArrowPath(from, to);
        break;
      case "stepped":
        pathD = getSteppedArrowPath(from, to);
        break;
      case "curved":
      default:
        pathD = getCurvedArrowPath(from, to);
    }
    path.style.transition = `d ${duration}ms ease-in-out`;
    path.setAttribute("d", pathD);
    const minX = Math.min(from.x, to.x);
    const minY = Math.min(from.y, to.y);
    const maxX = Math.max(from.x, to.x);
    const maxY = Math.max(from.y, to.y);
    arrowRef.bounds = { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
    await new Promise((resolve) => setTimeout(resolve, duration));
  }
  /**
   * Draw a text label
   */
  drawLabel(text, x, y, options = {}) {
    const id = generateId("label");
    const { fontSize = 12, fontWeight = "normal", color, anchor = "start" } = options;
    const label = createSVGElement("text", {
      id,
      x,
      y,
      "font-size": fontSize,
      "font-weight": fontWeight,
      fill: color || this.theme.textColor,
      "text-anchor": anchor,
      "dominant-baseline": "middle"
    });
    label.textContent = text;
    this.mainGroup.appendChild(label);
    const ref = {
      type: "label",
      id,
      element: label,
      bounds: { x, y: y - fontSize / 2, width: text.length * fontSize * 0.6, height: fontSize }
    };
    this.elements.set(id, ref);
    return ref;
  }
  /**
   * Get an element reference by ID
   */
  getElementRef(id) {
    return this.elements.get(id);
  }
  /**
   * Remove an element
   */
  removeElement(id) {
    const ref = this.elements.get(id);
    if (ref) {
      ref.element.remove();
      this.elements.delete(id);
    }
  }
  /**
   * Animate an element's properties
   */
  async animate(element, props, duration = 500) {
    return new Promise((resolve) => {
      element.style.transition = `all ${duration}ms ease-in-out`;
      if ("x" in props || "y" in props) {
        const currentTransform = element.getAttribute("transform") || "";
        const match = currentTransform.match(/translate\(([\d.-]+),\s*([\d.-]+)\)/);
        const currentX = match ? parseFloat(match[1]) : 0;
        const currentY = match ? parseFloat(match[2]) : 0;
        const newX = "x" in props ? props.x : currentX;
        const newY = "y" in props ? props.y : currentY;
        element.setAttribute("transform", `translate(${newX}, ${newY})`);
      }
      for (const [key, value] of Object.entries(props)) {
        if (key !== "x" && key !== "y") {
          element.setAttribute(key, String(value));
        }
      }
      setTimeout(resolve, duration);
    });
  }
  /**
   * Fade in an element
   */
  async fadeIn(element, duration = 300) {
    element.style.opacity = "0";
    element.style.transition = `opacity ${duration}ms ease-in`;
    element.getBoundingClientRect();
    element.style.opacity = "1";
    await new Promise((resolve) => setTimeout(resolve, duration));
  }
  /**
   * Fade out an element
   */
  async fadeOut(element, duration = 300) {
    element.style.transition = `opacity ${duration}ms ease-out`;
    element.style.opacity = "0";
    await new Promise((resolve) => setTimeout(resolve, duration));
  }
  /**
   * Move an element to a new position
   */
  async moveTo(element, x, y, duration = 500) {
    return this.animate(element, { x, y }, duration);
  }
  /**
   * Highlight an element
   */
  async highlight(element, duration = 500) {
    const originalFilter = element.getAttribute("filter") || "";
    element.setAttribute("filter", "url(#glow)");
    await new Promise((resolve) => setTimeout(resolve, duration));
    element.setAttribute("filter", originalFilter);
  }
  /**
   * Add a pulsing effect to an element
   */
  pulse(element, duration = 1e3) {
    const animation = element.animate(
      [
        { filter: "brightness(1)", opacity: 1 },
        { filter: "brightness(1.15)", opacity: 0.85 },
        { filter: "brightness(1)", opacity: 1 }
      ],
      {
        duration,
        iterations: Infinity,
        easing: "ease-in-out"
      }
    );
    return () => animation.cancel();
  }
  /**
   * Clean up resources
   */
  destroy() {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    this.svg.remove();
    this.elements.clear();
  }
};

// src/core/Animator.ts
var StateMachineAnimator = class {
  constructor(config) {
    this.animationQueue = [];
    this.isPlaying = false;
    this.isPaused = false;
    this.speedMultiplier = 1;
    this.stacks = /* @__PURE__ */ new Map();
    this.eventListeners = /* @__PURE__ */ new Map();
    this.defaultAnimationDuration = 500;
    this.renderer = new SVGRenderer(config);
  }
  // ===========================================================================
  // Playback Control
  // ===========================================================================
  /**
   * Play queued animations
   */
  async play() {
    if (this.isPlaying) return;
    this.isPlaying = true;
    this.isPaused = false;
    this.emit("animationStart");
    while (this.animationQueue.length > 0 && !this.isPaused) {
      const animation = this.animationQueue.shift();
      if (animation) {
        await animation.fn();
      }
    }
    this.isPlaying = false;
    this.emit("animationComplete");
  }
  /**
   * Pause animations
   */
  pause() {
    this.isPaused = true;
  }
  /**
   * Resume paused animations
   */
  resume() {
    if (this.isPaused) {
      this.isPaused = false;
      this.play();
    }
  }
  /**
   * Stop and clear animation queue
   */
  stop() {
    this.animationQueue = [];
    this.isPlaying = false;
    this.isPaused = false;
  }
  /**
   * Reset the animator and clear canvas
   */
  reset() {
    this.stop();
    this.renderer.clear();
    this.renderer.resetView();
    this.stacks.clear();
  }
  /**
   * Set animation speed multiplier
   */
  setSpeed(multiplier) {
    this.speedMultiplier = Math.max(0.1, Math.min(10, multiplier));
  }
  /**
   * Reset pan and zoom to default view
   */
  resetView() {
    this.renderer.resetView();
  }
  /**
   * Set zoom level (0.25 to 4)
   */
  setZoom(level) {
    this.renderer.setZoom(level);
  }
  /**
   * Get current zoom level
   */
  getZoom() {
    return this.renderer.getZoom();
  }
  /**
   * Get effective duration with speed multiplier
   */
  getDuration(baseDuration) {
    const duration = baseDuration ?? this.defaultAnimationDuration;
    return duration / this.speedMultiplier;
  }
  // ===========================================================================
  // Event Handling
  // ===========================================================================
  /**
   * Subscribe to animator events
   */
  on(event, callback) {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, /* @__PURE__ */ new Set());
    }
    this.eventListeners.get(event).add(callback);
  }
  /**
   * Unsubscribe from animator events
   */
  off(event, callback) {
    this.eventListeners.get(event)?.delete(callback);
  }
  /**
   * Emit an event
   */
  emit(event, data) {
    this.eventListeners.get(event)?.forEach((callback) => callback(data));
  }
  // ===========================================================================
  // Stack Management
  // ===========================================================================
  /**
   * Add a stack to the visualization
   */
  addStack(stack, position) {
    const pos = position ?? { x: 40, y: 40 };
    const ref = this.renderer.drawStack(stack, pos.x, pos.y);
    this.stacks.set(stack.id, {
      config: { ...stack },
      position: pos,
      ref,
      stateRefs: ref.childRefs ? [...ref.childRefs] : []
      // Capture initial state refs
    });
    return ref;
  }
  /**
   * Remove a stack
   */
  removeStack(stackId) {
    const state = this.stacks.get(stackId);
    if (state) {
      this.renderer.removeElement(stackId);
      this.stacks.delete(stackId);
    }
  }
  /**
   * Get a stack's current configuration
   */
  getStack(stackId) {
    return this.stacks.get(stackId)?.config;
  }
  // ===========================================================================
  // Low-Level Animation Primitives
  // ===========================================================================
  /**
   * Push a state onto a stack (animated)
   */
  async pushState(stackId, state) {
    const stackState = this.stacks.get(stackId);
    if (!stackState) {
      throw new Error(`Stack not found: ${stackId}`);
    }
    const { config, position, stateRefs } = stackState;
    const duration = this.getDuration();
    const stackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );
    const totalStates = config.states.length + 1;
    const moveAnimations = [];
    for (let i = 0; i < stateRefs.length; i++) {
      const existingRef = stateRefs[i];
      const newPos = getStatePositionInStack(
        position.x,
        position.y,
        stackWidth,
        totalStates,
        i
        // Same index, but totalStates increased so it moves down
      );
      moveAnimations.push(
        this.renderer.moveTo(
          existingRef.element,
          newPos.x,
          newPos.y,
          duration / 2
        )
      );
    }
    if (moveAnimations.length > 0) {
      await Promise.all(moveAnimations);
    }
    const newIndex = config.states.length;
    const newStatePos = getStatePositionInStack(
      position.x,
      position.y,
      stackWidth,
      totalStates,
      newIndex
    );
    const startY = newStatePos.y - 50;
    const stateRef = this.renderer.drawState(state, newStatePos.x, startY);
    await this.renderer.fadeIn(stateRef.element, duration / 2);
    await this.renderer.moveTo(
      stateRef.element,
      newStatePos.x,
      newStatePos.y,
      duration / 2
    );
    config.states.push(state);
    stateRefs.push(stateRef);
    this.emit("stateChange", { stackId, state, action: "push" });
  }
  /**
   * Pop a state from a stack (animated)
   */
  async popState(stackId) {
    const stackState = this.stacks.get(stackId);
    if (!stackState || stackState.config.states.length === 0) {
      return void 0;
    }
    const { config } = stackState;
    const topState = config.states[config.states.length - 1];
    config.states.pop();
    this.emit("stateChange", { stackId, state: topState, action: "pop" });
    return topState;
  }
  /**
   * Highlight a specific state in a stack
   */
  async highlightState(stackId, _index) {
    const stackState = this.stacks.get(stackId);
    if (!stackState) return;
    await this.renderer.highlight(
      stackState.ref.element,
      this.getDuration()
    );
  }
  /**
   * Draw a connection between two elements
   */
  async drawConnection(fromRef, toRef, animated = true) {
    const { from, to } = getConnectionPoints(
      fromRef.bounds,
      toRef.bounds,
      "right",
      "left"
    );
    const arrowRef = this.renderer.drawArrow({
      from,
      to,
      style: "curved",
      animated
    });
    if (animated) {
      await this.renderer.fadeIn(arrowRef.element, this.getDuration());
    }
    return arrowRef;
  }
  // ===========================================================================
  // High-Level Animation APIs
  // ===========================================================================
  /**
   * Play a tool execution animation
   */
  async playToolExecution(config) {
    const duration = this.getDuration(config.options?.executionDuration || 500);
    this.renderer.clear();
    const stackRef = this.addStack(config.stack, { x: 60, y: 60 });
    const stackState = this.stacks.get(config.stack.id);
    const stackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );
    const toolX = stackRef.bounds.x + stackRef.bounds.width + dimensions.spacing.toolGap;
    const toolY = 100;
    const toolRef = this.renderer.drawTool(config.tool, toolX, toolY, true);
    await this.delay(duration / 2);
    if (config.preStates && config.preStates.length > 0) {
      for (const state of config.preStates) {
        await this.pushState(config.stack.id, state);
        await this.delay(duration / 3);
      }
    }
    await this.pushState(config.stack.id, config.triggerState);
    const toolCallIndex = stackState.config.states.length - 1;
    const toolCallPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      stackState.config.states.length,
      toolCallIndex
    );
    await this.delay(duration / 4);
    await this.renderer.fadeIn(toolRef.element, duration / 3);
    const arrow1 = this.renderer.drawArrow({
      from: {
        x: toolCallPos.x + dimensions.state.width,
        y: toolCallPos.y + dimensions.state.height / 2
      },
      to: {
        x: toolRef.bounds.x,
        y: toolRef.bounds.y + toolRef.bounds.height * 0.7
      },
      style: config.options?.arrowStyle || "curved"
    });
    await this.renderer.fadeIn(arrow1.element, duration / 3);
    const cancelPulse = this.renderer.pulse(toolRef.element, 300);
    await this.delay(duration);
    cancelPulse();
    const totalStatesAfterResult = stackState.config.states.length + 1;
    const resultPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      totalStatesAfterResult,
      totalStatesAfterResult - 1
      // The new top state
    );
    const arrow2 = this.renderer.drawArrow({
      from: {
        x: toolRef.bounds.x,
        y: toolRef.bounds.y + toolRef.bounds.height * 0.3
      },
      to: {
        x: resultPos.x + dimensions.state.width,
        y: resultPos.y + dimensions.state.height / 2
      },
      style: config.options?.arrowStyle || "curved"
    });
    await this.renderer.fadeIn(arrow2.element, duration / 3);
    await this.delay(duration / 4);
    const newToolCallPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      stackState.config.states.length + 1,
      // After result is added
      toolCallIndex
      // ToolCall stays at same index
    );
    await Promise.all([
      this.pushState(config.stack.id, config.resultState),
      this.renderer.updateArrowPath(
        arrow1,
        {
          x: newToolCallPos.x + dimensions.state.width,
          y: newToolCallPos.y + dimensions.state.height / 2
        },
        {
          x: toolRef.bounds.x,
          y: toolRef.bounds.y + toolRef.bounds.height * 0.7
        },
        config.options?.arrowStyle || "curved",
        duration / 2
      )
    ]);
    if (config.postStates && config.postStates.length > 0) {
      await this.delay(duration / 2);
      const toolResultIndex = toolCallIndex + 1;
      for (const state of config.postStates) {
        const nextTotalStates = stackState.config.states.length + 1;
        const nextToolCallPos = getStatePositionInStack(
          stackState.position.x,
          stackState.position.y,
          stackWidth,
          nextTotalStates,
          toolCallIndex
        );
        const nextToolResultPos = getStatePositionInStack(
          stackState.position.x,
          stackState.position.y,
          stackWidth,
          nextTotalStates,
          toolResultIndex
        );
        await Promise.all([
          this.pushState(config.stack.id, state),
          this.renderer.updateArrowPath(
            arrow1,
            {
              x: nextToolCallPos.x + dimensions.state.width,
              y: nextToolCallPos.y + dimensions.state.height / 2
            },
            {
              x: toolRef.bounds.x,
              y: toolRef.bounds.y + toolRef.bounds.height * 0.7
            },
            config.options?.arrowStyle || "curved",
            duration / 4
          ),
          this.renderer.updateArrowPath(
            arrow2,
            {
              x: toolRef.bounds.x,
              y: toolRef.bounds.y + toolRef.bounds.height * 0.3
            },
            {
              x: nextToolResultPos.x + dimensions.state.width,
              y: nextToolResultPos.y + dimensions.state.height / 2
            },
            config.options?.arrowStyle || "curved",
            duration / 4
          )
        ]);
        await this.delay(duration / 3);
      }
    }
    this.emit("animationComplete", { type: "toolExecution" });
  }
  /**
   * Play an artifact creation animation.
   * Shows a tool call creating an external artifact that stays attached to the interaction.
   */
  async playArtifactCreation(config) {
    const duration = this.getDuration();
    const artifactPosition = config.options?.artifactPosition || "right";
    this.renderer.clear();
    const stackRef = this.addStack(config.stack, { x: 60, y: 60 });
    const stackState = this.stacks.get(config.stack.id);
    const stackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );
    await this.delay(duration / 2);
    if (config.preStates && config.preStates.length > 0) {
      for (const state of config.preStates) {
        await this.pushState(config.stack.id, state);
        await this.delay(duration / 3);
      }
    }
    await this.pushState(config.stack.id, config.creatorState);
    const creatorIndex = stackState.config.states.length - 1;
    const creatorPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      stackState.config.states.length,
      creatorIndex
    );
    await this.delay(duration / 2);
    const artifactX = artifactPosition === "right" ? stackRef.bounds.x + stackRef.bounds.width + 60 : stackRef.bounds.x - dimensions.artifact.width - 60;
    const artifactY = creatorPos.y - 10;
    const artifactRef = this.renderer.drawArtifact(config.artifact, artifactX, artifactY, true);
    const arrowFrom = {
      x: artifactPosition === "right" ? creatorPos.x + dimensions.state.width : creatorPos.x,
      y: creatorPos.y + dimensions.state.height / 2
    };
    const arrowTo = {
      x: artifactPosition === "right" ? artifactRef.bounds.x : artifactRef.bounds.x + artifactRef.bounds.width,
      y: artifactRef.bounds.y + artifactRef.bounds.height / 2
    };
    const arrow = this.renderer.drawArrow({
      from: arrowFrom,
      to: arrowTo,
      style: config.options?.arrowStyle || "curved",
      hidden: true
    });
    await Promise.all([
      this.renderer.fadeIn(artifactRef.element, duration / 2),
      this.renderer.fadeIn(arrow.element, duration / 2)
    ]);
    await this.delay(duration / 2);
    const newTotalStates = stackState.config.states.length + 1;
    const newCreatorPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      newTotalStates,
      creatorIndex
    );
    await Promise.all([
      this.pushState(config.stack.id, config.resultState),
      this.renderer.updateArrowPath(
        arrow,
        {
          x: artifactPosition === "right" ? newCreatorPos.x + dimensions.state.width : newCreatorPos.x,
          y: newCreatorPos.y + dimensions.state.height / 2
        },
        arrowTo,
        config.options?.arrowStyle || "curved",
        duration / 4
      ),
      this.renderer.moveTo(
        artifactRef.element,
        artifactX,
        newCreatorPos.y - 10,
        duration / 4
      )
    ]);
    const newArrowTo = {
      x: arrowTo.x,
      y: newCreatorPos.y - 10 + artifactRef.bounds.height / 2
    };
    await this.renderer.updateArrowPath(
      arrow,
      {
        x: artifactPosition === "right" ? newCreatorPos.x + dimensions.state.width : newCreatorPos.x,
        y: newCreatorPos.y + dimensions.state.height / 2
      },
      newArrowTo,
      config.options?.arrowStyle || "curved",
      100
    );
    if (config.postStates && config.postStates.length > 0) {
      for (const state of config.postStates) {
        const nextTotalStates = stackState.config.states.length + 1;
        const nextCreatorPos = getStatePositionInStack(
          stackState.position.x,
          stackState.position.y,
          stackWidth,
          nextTotalStates,
          creatorIndex
        );
        const nextArtifactY = nextCreatorPos.y - 10;
        const nextArrowTo = {
          x: arrowTo.x,
          y: nextArtifactY + artifactRef.bounds.height / 2
        };
        await Promise.all([
          this.pushState(config.stack.id, state),
          this.renderer.updateArrowPath(
            arrow,
            {
              x: artifactPosition === "right" ? nextCreatorPos.x + dimensions.state.width : nextCreatorPos.x,
              y: nextCreatorPos.y + dimensions.state.height / 2
            },
            nextArrowTo,
            config.options?.arrowStyle || "curved",
            duration / 4
          ),
          this.renderer.moveTo(
            artifactRef.element,
            artifactX,
            nextArtifactY,
            duration / 4
          )
        ]);
        await this.delay(duration / 3);
      }
    }
    this.emit("animationComplete", { type: "artifactCreation" });
  }
  /**
   * Play a state transition diagram animation
   */
  async playTransitionDiagram(config) {
    const duration = this.getDuration();
    this.renderer.clear();
    const allStates = [
      { type: config.initialState },
      ...config.transitions.map((t) => ({ type: t }))
    ];
    const uniqueStates = Array.from(
      new Map(allStates.map((s) => [s.type, s])).values()
    );
    const layout = config.layout || "horizontal";
    const spacing = layout === "horizontal" ? 180 : 80;
    const stateRefs = /* @__PURE__ */ new Map();
    let x = 60;
    let y = 100;
    for (const state of uniqueStates) {
      const ref = this.renderer.drawState(state, x, y);
      stateRefs.set(state.type, ref);
      if (layout === "horizontal") {
        x += spacing;
      } else {
        y += spacing;
      }
    }
    const transitionSequence = [config.initialState, ...config.transitions];
    for (let i = 0; i < transitionSequence.length - 1; i++) {
      const fromRef = stateRefs.get(transitionSequence[i]);
      const toRef = stateRefs.get(transitionSequence[i + 1]);
      if (fromRef && toRef) {
        const fromSide = layout === "horizontal" ? "right" : "bottom";
        const toSide = layout === "horizontal" ? "left" : "top";
        const { from, to } = getConnectionPoints(
          fromRef.bounds,
          toRef.bounds,
          fromSide,
          toSide
        );
        this.renderer.drawArrow({ from, to, style: "straight" });
      }
    }
    for (let i = 0; i < transitionSequence.length; i++) {
      const currentState = transitionSequence[i];
      const ref = stateRefs.get(currentState);
      if (ref) {
        await this.renderer.highlight(ref.element, duration);
        await this.delay(duration / 2);
      }
    }
    if (config.syncWithStack) {
      const stackX = config.syncWithStack.position === "right" ? x + 100 : config.syncWithStack.position === "left" ? -200 : 60;
      const stackY = config.syncWithStack.position === "bottom" ? y + 100 : 60;
      this.addStack(config.syncWithStack.stack, { x: stackX, y: stackY });
    }
    this.emit("animationComplete", { type: "transitionDiagram" });
  }
  /**
   * Play a branching animation
   */
  async playBranching(config) {
    const duration = this.getDuration();
    this.renderer.clear();
    const sourceRef = this.addStack(config.sourceStack, { x: 200, y: 60 });
    await this.delay(duration);
    await this.highlightState(config.sourceStack.id, config.branchPoint);
    await this.delay(duration / 2);
    const branchStartX = 80;
    const branchY = sourceRef.bounds.y + sourceRef.bounds.height + 80;
    const branchSpacing = config.layout?.spacing ?? dimensions.spacing.branchGap;
    this.renderer.drawLabel("Branches", sourceRef.bounds.x + sourceRef.bounds.width / 2, branchY - 30, {
      anchor: "middle",
      fontSize: 14,
      fontWeight: "600"
    });
    let x = branchStartX;
    for (const branch of config.branches) {
      const branchStack = {
        id: branch.id,
        label: branch.label || `Branch ${branch.id}`,
        states: [
          ...config.sourceStack.states.slice(0, config.branchPoint + 1),
          ...branch.additionalStates
        ],
        branchId: branch.id,
        parentStackId: config.sourceStack.id
      };
      const branchRef = this.renderer.drawStack(branchStack, x, branchY);
      await this.renderer.fadeIn(branchRef.element, duration);
      const connectionFrom = {
        x: sourceRef.bounds.x + sourceRef.bounds.width / 2,
        y: sourceRef.bounds.y + sourceRef.bounds.height
      };
      const connectionTo = {
        x: branchRef.bounds.x + branchRef.bounds.width / 2,
        y: branchRef.bounds.y
      };
      this.renderer.drawArrow({
        from: connectionFrom,
        to: connectionTo,
        style: "curved",
        dashArray: dimensions.arrow.dashArray
      });
      this.stacks.set(branch.id, {
        config: branchStack,
        position: { x, y: branchY },
        ref: branchRef,
        stateRefs: []
      });
      x += branchRef.bounds.width + branchSpacing;
      await this.delay(duration / 2);
      this.emit("branchCreated", { branchId: branch.id });
    }
    this.emit("animationComplete", { type: "branching" });
  }
  /**
   * Play a multi-stack interaction animation
   */
  async playMultiStackInteraction(config) {
    const duration = this.getDuration();
    const childPosition = config.options?.childPosition || "right";
    this.renderer.clear();
    const parentRef = this.addStack(config.parentStack, { x: 60, y: 60 });
    const parentStackState = this.stacks.get(config.parentStack.id);
    const parentStackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );
    const childStackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );
    const childX = childPosition === "right" ? parentRef.bounds.x + parentRef.bounds.width + dimensions.spacing.stackGap : parentRef.bounds.x;
    const childY = childPosition === "below" ? parentRef.bounds.y + parentRef.bounds.height + dimensions.spacing.stackGap : parentRef.bounds.y;
    const childStackConfig = {
      ...config.childStack,
      states: []
    };
    this.addStack(childStackConfig, { x: childX, y: childY });
    const childStackState = this.stacks.get(config.childStack.id);
    await this.delay(duration);
    if (config.parentExecution && config.parentExecution.length > 0) {
      if (config.options?.animateParentSteps !== false) {
        for (const state of config.parentExecution) {
          await this.pushState(config.parentStack.id, state);
          await this.delay(duration / 2);
        }
      }
    }
    await this.pushState(config.parentStack.id, config.callState);
    const agentCallIndex = parentStackState.config.states.length - 1;
    const agentCallPos = getStatePositionInStack(
      parentStackState.position.x,
      parentStackState.position.y,
      parentStackWidth,
      parentStackState.config.states.length,
      agentCallIndex
    );
    await this.delay(duration / 2);
    if (config.childExecution.length > 0) {
      await this.pushState(config.childStack.id, config.childExecution[0]);
    }
    const firstChildStatePos = getStatePositionInStack(
      childStackState.position.x,
      childStackState.position.y,
      childStackWidth,
      1,
      // Only one state so far
      0
    );
    const parentToChild = this.renderer.drawArrow({
      from: {
        x: agentCallPos.x + dimensions.state.width,
        y: agentCallPos.y + dimensions.state.height / 2
      },
      to: {
        x: firstChildStatePos.x,
        y: firstChildStatePos.y + dimensions.state.height / 2
      },
      style: "curved",
      animated: true
    });
    await this.renderer.fadeIn(parentToChild.element, duration / 2);
    if (config.options?.animateChildSteps !== false && config.childExecution.length > 1) {
      for (let i = 1; i < config.childExecution.length; i++) {
        const state = config.childExecution[i];
        const newFirstStatePos = getStatePositionInStack(
          childStackState.position.x,
          childStackState.position.y,
          childStackWidth,
          childStackState.config.states.length + 1,
          0
          // First state stays at index 0
        );
        await Promise.all([
          this.pushState(config.childStack.id, state),
          this.renderer.updateArrowPath(
            parentToChild,
            {
              x: agentCallPos.x + dimensions.state.width,
              y: agentCallPos.y + dimensions.state.height / 2
            },
            {
              x: newFirstStatePos.x,
              y: newFirstStatePos.y + dimensions.state.height / 2
            },
            "curved",
            duration / 4
          )
        ]);
        await this.delay(duration / 2);
      }
    }
    await this.delay(duration / 2);
    const lastChildIndex = childStackState.config.states.length - 1;
    const lastChildPos = getStatePositionInStack(
      childStackState.position.x,
      childStackState.position.y,
      childStackWidth,
      childStackState.config.states.length,
      lastChildIndex
    );
    const agentResultPos = getStatePositionInStack(
      parentStackState.position.x,
      parentStackState.position.y,
      parentStackWidth,
      parentStackState.config.states.length + 1,
      // After result is added
      parentStackState.config.states.length
      // New top state
    );
    const childToParent = this.renderer.drawArrow({
      from: {
        x: lastChildPos.x,
        y: lastChildPos.y + dimensions.state.height / 2
      },
      to: {
        x: agentResultPos.x + dimensions.state.width,
        y: agentResultPos.y + dimensions.state.height / 2
      },
      style: "curved"
    });
    await this.renderer.fadeIn(childToParent.element, duration / 2);
    const newAgentCallPos = getStatePositionInStack(
      parentStackState.position.x,
      parentStackState.position.y,
      parentStackWidth,
      parentStackState.config.states.length + 1,
      agentCallIndex
    );
    await Promise.all([
      this.pushState(config.parentStack.id, config.resultState),
      this.renderer.updateArrowPath(
        parentToChild,
        {
          x: newAgentCallPos.x + dimensions.state.width,
          y: newAgentCallPos.y + dimensions.state.height / 2
        },
        {
          x: firstChildStatePos.x,
          y: getStatePositionInStack(
            childStackState.position.x,
            childStackState.position.y,
            childStackWidth,
            childStackState.config.states.length,
            0
          ).y + dimensions.state.height / 2
        },
        "curved",
        duration / 4
      )
    ]);
    if (config.parentCompletion && config.parentCompletion.length > 0) {
      await this.delay(duration / 2);
      const agentResultIndex = parentStackState.config.states.length - 1;
      const finalFirstChildPos = getStatePositionInStack(
        childStackState.position.x,
        childStackState.position.y,
        childStackWidth,
        childStackState.config.states.length,
        0
      );
      const finalLastChildPos = getStatePositionInStack(
        childStackState.position.x,
        childStackState.position.y,
        childStackWidth,
        childStackState.config.states.length,
        childStackState.config.states.length - 1
      );
      for (const state of config.parentCompletion) {
        const newTotalStates = parentStackState.config.states.length + 1;
        const newAgentCallPos2 = getStatePositionInStack(
          parentStackState.position.x,
          parentStackState.position.y,
          parentStackWidth,
          newTotalStates,
          agentCallIndex
        );
        const newAgentResultPos = getStatePositionInStack(
          parentStackState.position.x,
          parentStackState.position.y,
          parentStackWidth,
          newTotalStates,
          agentResultIndex
        );
        await Promise.all([
          this.pushState(config.parentStack.id, state),
          this.renderer.updateArrowPath(
            parentToChild,
            {
              x: newAgentCallPos2.x + dimensions.state.width,
              y: newAgentCallPos2.y + dimensions.state.height / 2
            },
            {
              x: finalFirstChildPos.x,
              y: finalFirstChildPos.y + dimensions.state.height / 2
            },
            "curved",
            duration / 4
          ),
          this.renderer.updateArrowPath(
            childToParent,
            {
              x: finalLastChildPos.x,
              y: finalLastChildPos.y + dimensions.state.height / 2
            },
            {
              x: newAgentResultPos.x + dimensions.state.width,
              y: newAgentResultPos.y + dimensions.state.height / 2
            },
            "curved",
            duration / 4
          )
        ]);
        await this.delay(duration / 2);
      }
    }
    this.emit("stackInteraction", {
      parentId: config.parentStack.id,
      childId: config.childStack.id
    });
    this.emit("animationComplete", { type: "multiStackInteraction" });
  }
  // ===========================================================================
  // Utility Methods
  // ===========================================================================
  /**
   * Wait for a duration
   */
  delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
  /**
   * Get the renderer (for advanced usage)
   */
  getRenderer() {
    return this.renderer;
  }
  /**
   * Clean up resources
   */
  destroy() {
    this.stop();
    this.renderer.destroy();
    this.stacks.clear();
    this.eventListeners.clear();
  }
};

// src/utils/easing.ts
var linear = (t) => t;
var easeInQuad = (t) => t * t;
var easeOutQuad = (t) => t * (2 - t);
var easeInOutQuad = (t) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
var easeInCubic = (t) => t * t * t;
var easeOutCubic = (t) => --t * t * t + 1;
var easeInOutCubic = (t) => t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1;
var c1 = 1.70158;
var c2 = c1 * 1.525;
var c3 = c1 + 1;
var easeInBack = (t) => c3 * t * t * t - c1 * t * t;
var easeOutBack = (t) => 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
var easeInOutBack = (t) => t < 0.5 ? Math.pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2) / 2 : (Math.pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2;
var c4 = 2 * Math.PI / 3;
var c5 = 2 * Math.PI / 4.5;
var easeOutBounce = (t) => {
  const n1 = 7.5625;
  const d1 = 2.75;
  if (t < 1 / d1) {
    return n1 * t * t;
  } else if (t < 2 / d1) {
    return n1 * (t -= 1.5 / d1) * t + 0.75;
  } else if (t < 2.5 / d1) {
    return n1 * (t -= 2.25 / d1) * t + 0.9375;
  } else {
    return n1 * (t -= 2.625 / d1) * t + 0.984375;
  }
};
var easeInBounce = (t) => 1 - easeOutBounce(1 - t);
var easeIn = easeInCubic;
var easeOut = easeOutCubic;
var easeInOut = easeInOutCubic;
var easingPresets = {
  linear,
  easeIn,
  easeOut,
  easeInOut,
  easeInQuad,
  easeOutQuad,
  easeInOutQuad,
  easeInCubic,
  easeOutCubic,
  easeInOutCubic,
  easeInBack,
  easeOutBack,
  easeInOutBack
};
function getEasing(easing) {
  if (typeof easing === "function") {
    return easing;
  }
  if (typeof easing === "string" && easing in easingPresets) {
    return easingPresets[easing];
  }
  return easeInOutCubic;
}
//# sourceMappingURL=state-machine-animator.cjs.map

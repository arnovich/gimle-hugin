/**
 * SVG-based renderer for state machine visualizations
 *
 * Uses SVG for crisp, scalable graphics with smooth CSS animations.
 */

import type {
  RendererConfig,
  ThemeConfig,
  StateConfig,
  StackConfig,
  ToolConfig,
  ArtifactConfig,
  Point,
  Rect,
  ArrowOptions,
  ElementRef,
} from '../core/types.js';
import { getTheme, getStateColors } from '../utils/colors.js';
import {
  dimensions,
  getStatePositionInStack,
  calculateStackHeight,
  getCurvedArrowPath,
  getStraightArrowPath,
  getSteppedArrowPath,
} from '../utils/layout.js';

/**
 * SVG namespace
 */
const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * Create an SVG element with attributes
 */
function createSVGElement<K extends keyof SVGElementTagNameMap>(
  tagName: K,
  attributes: Record<string, string | number> = {}
): SVGElementTagNameMap[K] {
  const element = document.createElementNS(SVG_NS, tagName);
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, String(value));
  }
  return element;
}

/**
 * Generate a unique ID
 */
let idCounter = 0;
function generateId(prefix: string): string {
  return `${prefix}-${++idCounter}`;
}

/**
 * SVG Renderer class
 */
export class SVGRenderer {
  private container: HTMLElement;
  private svg: SVGSVGElement;
  private defs: SVGDefsElement;
  private mainGroup: SVGGElement;
  private theme: ThemeConfig;
  private width: number;
  private height: number;
  private padding: number;
  private elements: Map<string, ElementRef> = new Map();
  private resizeObserver: ResizeObserver | null = null;

  // Pan and zoom state
  private panX: number = 0;
  private panY: number = 0;
  private zoom: number = 1;
  private isPanning: boolean = false;
  private lastMouseX: number = 0;
  private lastMouseY: number = 0;
  private minZoom: number = 0.25;
  private maxZoom: number = 4;

  // Tooltip elements
  private tooltipGroup: SVGGElement | null = null;
  private tooltipVisible: boolean = false;

  constructor(config: RendererConfig) {
    // Resolve container
    if (typeof config.container === 'string') {
      const el = document.querySelector(config.container);
      if (!el) {
        throw new Error(`Container not found: ${config.container}`);
      }
      this.container = el as HTMLElement;
    } else {
      this.container = config.container;
    }

    // Initialize theme
    this.theme = getTheme(config.theme || 'light');
    this.padding = config.padding ?? 20;

    // Get dimensions
    this.width = config.width ?? (this.container.clientWidth || 800);
    this.height = config.height ?? (this.container.clientHeight || 600);

    // Create SVG
    this.svg = createSVGElement('svg', {
      width: this.width,
      height: this.height,
      viewBox: `0 0 ${this.width} ${this.height}`,
    });
    this.svg.style.fontFamily = this.theme.fontFamily;
    this.svg.style.display = 'block';

    // Create defs for gradients, filters, etc.
    this.defs = createSVGElement('defs');
    this.svg.appendChild(this.defs);
    this.addFiltersAndGradients();

    // Create main group for transforms
    this.mainGroup = createSVGElement('g', {
      transform: `translate(${this.padding}, ${this.padding})`,
    });
    this.svg.appendChild(this.mainGroup);

    // Add background
    this.drawBackground();

    // Append to container
    this.container.appendChild(this.svg);

    // Setup responsive resizing
    if (config.responsive) {
      this.setupResponsive();
    }

    // Setup pan and zoom handlers
    this.setupPanZoom();

    // Create tooltip (added last so it's on top)
    this.createTooltip();
  }

  /**
   * Setup pan and zoom event handlers
   */
  private setupPanZoom(): void {
    // Change cursor to indicate draggable
    this.svg.style.cursor = 'grab';

    // Mouse down - start panning
    this.svg.addEventListener('mousedown', (e: MouseEvent) => {
      // Only pan with left mouse button
      if (e.button !== 0) return;

      this.isPanning = true;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
      this.svg.style.cursor = 'grabbing';
      e.preventDefault();
    });

    // Mouse move - pan if dragging
    this.svg.addEventListener('mousemove', (e: MouseEvent) => {
      if (!this.isPanning) return;

      const dx = e.clientX - this.lastMouseX;
      const dy = e.clientY - this.lastMouseY;

      this.panX += dx / this.zoom;
      this.panY += dy / this.zoom;

      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;

      this.updateTransform();
    });

    // Mouse up - stop panning
    this.svg.addEventListener('mouseup', () => {
      this.isPanning = false;
      this.svg.style.cursor = 'grab';
    });

    // Mouse leave - stop panning
    this.svg.addEventListener('mouseleave', () => {
      this.isPanning = false;
      this.svg.style.cursor = 'grab';
    });

    // Wheel - zoom
    this.svg.addEventListener('wheel', (e: WheelEvent) => {
      e.preventDefault();

      // Get mouse position relative to SVG
      const rect = this.svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      // Calculate zoom factor
      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.max(
        this.minZoom,
        Math.min(this.maxZoom, this.zoom * zoomFactor)
      );

      // Adjust pan to zoom towards mouse position
      if (newZoom !== this.zoom) {
        const zoomRatio = newZoom / this.zoom;
        this.panX -= (mouseX / this.zoom) * (zoomRatio - 1);
        this.panY -= (mouseY / this.zoom) * (zoomRatio - 1);
        this.zoom = newZoom;
        this.updateTransform();
      }
    });
  }

  /**
   * Update the main group transform based on pan/zoom state
   */
  private updateTransform(): void {
    this.mainGroup.setAttribute(
      'transform',
      `translate(${this.panX + this.padding}, ${this.panY + this.padding}) scale(${this.zoom})`
    );
  }

  /**
   * Reset pan and zoom to default
   */
  resetView(): void {
    this.panX = 0;
    this.panY = 0;
    this.zoom = 1;
    this.updateTransform();
  }

  /**
   * Set zoom level programmatically
   */
  setZoom(level: number): void {
    this.zoom = Math.max(this.minZoom, Math.min(this.maxZoom, level));
    this.updateTransform();
  }

  /**
   * Get current zoom level
   */
  getZoom(): number {
    return this.zoom;
  }

  /**
   * Create tooltip element
   */
  private createTooltip(): void {
    this.tooltipGroup = createSVGElement('g', {
      class: 'tooltip',
      style: 'pointer-events: none; opacity: 0; transition: opacity 0.15s ease-out;',
    });

    // Tooltip background
    const bg = createSVGElement('rect', {
      class: 'tooltip-bg',
      rx: 6,
      ry: 6,
      fill: 'rgba(45, 55, 72, 0.95)',
      stroke: 'rgba(255, 255, 255, 0.1)',
      'stroke-width': 1,
    });
    this.tooltipGroup.appendChild(bg);

    // Tooltip text container
    const textGroup = createSVGElement('g', {
      class: 'tooltip-text',
    });
    this.tooltipGroup.appendChild(textGroup);

    this.svg.appendChild(this.tooltipGroup);
  }

  /**
   * Show tooltip with state information
   */
  showTooltip(
    state: StateConfig,
    screenX: number,
    screenY: number
  ): void {
    if (!this.tooltipGroup) return;

    const textGroup = this.tooltipGroup.querySelector('.tooltip-text') as SVGGElement;
    const bg = this.tooltipGroup.querySelector('.tooltip-bg') as SVGRectElement;

    // Clear previous text
    while (textGroup.firstChild) {
      textGroup.removeChild(textGroup.firstChild);
    }

    const padding = 12;
    const lineHeight = 18;
    let currentY = padding + 12;
    let maxWidth = 0;

    // State type (bold, larger)
    const typeText = createSVGElement('text', {
      x: padding,
      y: currentY,
      'font-size': 13,
      'font-weight': '600',
      fill: '#fff',
    });
    typeText.textContent = state.type;
    textGroup.appendChild(typeText);
    maxWidth = Math.max(maxWidth, state.type.length * 8);
    currentY += lineHeight;

    // Label (if exists and different from type)
    if (state.label) {
      const labelText = createSVGElement('text', {
        x: padding,
        y: currentY,
        'font-size': 11,
        fill: 'rgba(255, 255, 255, 0.8)',
      });
      labelText.textContent = state.label;
      textGroup.appendChild(labelText);
      maxWidth = Math.max(maxWidth, state.label.length * 6);
      currentY += lineHeight;
    }

    // Additional data if present
    if (state.data) {
      currentY += 4; // Small gap
      const dataEntries = Object.entries(state.data).slice(0, 3); // Limit to 3 entries
      for (const [key, value] of dataEntries) {
        const dataText = createSVGElement('text', {
          x: padding,
          y: currentY,
          'font-size': 10,
          fill: 'rgba(255, 255, 255, 0.6)',
        });
        const valueStr = String(value).substring(0, 30);
        dataText.textContent = `${key}: ${valueStr}`;
        textGroup.appendChild(dataText);
        maxWidth = Math.max(maxWidth, (key.length + valueStr.length + 2) * 5.5);
        currentY += lineHeight - 4;
      }
    }

    // Size background
    const tooltipWidth = Math.max(120, maxWidth + padding * 2);
    const tooltipHeight = currentY + padding - 6;
    bg.setAttribute('width', String(tooltipWidth));
    bg.setAttribute('height', String(tooltipHeight));

    // Position tooltip (offset from cursor, ensure visible)
    const svgRect = this.svg.getBoundingClientRect();
    let tooltipX = screenX - svgRect.left + 15;
    let tooltipY = screenY - svgRect.top - tooltipHeight / 2;

    // Keep within bounds
    if (tooltipX + tooltipWidth > this.width - 10) {
      tooltipX = screenX - svgRect.left - tooltipWidth - 15;
    }
    if (tooltipY < 10) {
      tooltipY = 10;
    }
    if (tooltipY + tooltipHeight > this.height - 10) {
      tooltipY = this.height - tooltipHeight - 10;
    }

    this.tooltipGroup.setAttribute('transform', `translate(${tooltipX}, ${tooltipY})`);
    this.tooltipGroup.style.opacity = '1';
    this.tooltipVisible = true;
  }

  /**
   * Hide tooltip
   */
  hideTooltip(): void {
    if (this.tooltipGroup && this.tooltipVisible) {
      this.tooltipGroup.style.opacity = '0';
      this.tooltipVisible = false;
    }
  }

  /**
   * Pan to center on a specific point
   */
  panTo(x: number, y: number): void {
    this.panX = this.width / 2 / this.zoom - x;
    this.panY = this.height / 2 / this.zoom - y;
    this.updateTransform();
  }

  /**
   * Add reusable SVG definitions
   */
  private addFiltersAndGradients(): void {
    // Drop shadow filter
    const dropShadow = createSVGElement('filter', {
      id: 'drop-shadow',
      x: '-20%',
      y: '-20%',
      width: '140%',
      height: '140%',
    });

    const feGaussianBlur = createSVGElement('feGaussianBlur', {
      in: 'SourceAlpha',
      stdDeviation: '2',
      result: 'blur',
    });

    const feOffset = createSVGElement('feOffset', {
      in: 'blur',
      dx: '0',
      dy: '1',
      result: 'offsetBlur',
    });

    const feFlood = createSVGElement('feFlood', {
      'flood-color': 'rgba(0,0,0,0.15)',
      result: 'color',
    });

    const feComposite = createSVGElement('feComposite', {
      in: 'color',
      in2: 'offsetBlur',
      operator: 'in',
      result: 'shadow',
    });

    const feMerge = createSVGElement('feMerge');
    const feMergeNode1 = createSVGElement('feMergeNode', { in: 'shadow' });
    const feMergeNode2 = createSVGElement('feMergeNode', { in: 'SourceGraphic' });
    feMerge.appendChild(feMergeNode1);
    feMerge.appendChild(feMergeNode2);

    dropShadow.appendChild(feGaussianBlur);
    dropShadow.appendChild(feOffset);
    dropShadow.appendChild(feFlood);
    dropShadow.appendChild(feComposite);
    dropShadow.appendChild(feMerge);
    this.defs.appendChild(dropShadow);

    // Glow filter for highlights
    const glow = createSVGElement('filter', {
      id: 'glow',
      x: '-50%',
      y: '-50%',
      width: '200%',
      height: '200%',
    });

    const feGlow = createSVGElement('feGaussianBlur', {
      stdDeviation: '3',
      result: 'coloredBlur',
    });

    const feMergeGlow = createSVGElement('feMerge');
    const feMergeGlowNode1 = createSVGElement('feMergeNode', { in: 'coloredBlur' });
    const feMergeGlowNode2 = createSVGElement('feMergeNode', { in: 'SourceGraphic' });
    feMergeGlow.appendChild(feMergeGlowNode1);
    feMergeGlow.appendChild(feMergeGlowNode2);

    glow.appendChild(feGlow);
    glow.appendChild(feMergeGlow);
    this.defs.appendChild(glow);

    // Arrow marker
    const arrowMarker = createSVGElement('marker', {
      id: 'arrowhead',
      markerWidth: '10',
      markerHeight: '7',
      refX: '9',
      refY: '3.5',
      orient: 'auto',
      markerUnits: 'strokeWidth',
    });

    const arrowPath = createSVGElement('polygon', {
      points: '0 0, 10 3.5, 0 7',
      fill: this.theme.arrowColor,
    });
    arrowMarker.appendChild(arrowPath);
    this.defs.appendChild(arrowMarker);
  }

  /**
   * Draw background
   */
  private drawBackground(): void {
    const bg = createSVGElement('rect', {
      x: -this.padding,
      y: -this.padding,
      width: this.width,
      height: this.height,
      fill: this.theme.background,
    });
    this.mainGroup.insertBefore(bg, this.mainGroup.firstChild);
  }

  /**
   * Setup responsive behavior
   */
  private setupResponsive(): void {
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
  clear(): void {
    while (this.mainGroup.children.length > 1) {
      // Keep background
      this.mainGroup.removeChild(this.mainGroup.lastChild!);
    }
    this.elements.clear();
  }

  /**
   * Resize the canvas
   */
  resize(width: number, height: number): void {
    this.width = width;
    this.height = height;
    this.svg.setAttribute('width', String(width));
    this.svg.setAttribute('height', String(height));
    this.svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  }

  /**
   * Get the SVG element
   */
  getElement(): SVGSVGElement {
    return this.svg;
  }

  /**
   * Get the theme
   */
  getTheme(): ThemeConfig {
    return this.theme;
  }

  /**
   * Get available drawing area
   */
  getDrawingArea(): Rect {
    return {
      x: 0,
      y: 0,
      width: this.width - this.padding * 2,
      height: this.height - this.padding * 2,
    };
  }

  /**
   * Draw a state box
   */
  drawState(state: StateConfig, x: number, y: number): ElementRef {
    const id = state.id || generateId('state');
    const colors = getStateColors(state, this.theme);
    const { width, height, borderRadius, padding, fontSize, labelFontSize } =
      dimensions.state;

    // Create group for the state
    const group = createSVGElement('g', {
      id,
      transform: `translate(${x}, ${y})`,
      class: 'state-box',
    });

    // Background rectangle (flat design, no shadow)
    const rect = createSVGElement('rect', {
      x: 0,
      y: 0,
      width,
      height,
      rx: borderRadius,
      ry: borderRadius,
      fill: colors.background,
      stroke: colors.border,
      'stroke-width': 1.5,
    });
    group.appendChild(rect);

    // State type label (centered like the blog)
    const typeLabel = createSVGElement('text', {
      x: width / 2,
      y: height / 2 - (state.label ? 4 : 0),
      'font-size': fontSize,
      'font-weight': '500',
      fill: colors.text,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
    });
    typeLabel.textContent = state.type;
    group.appendChild(typeLabel);

    // Optional detail label (centered)
    if (state.label) {
      const detailLabel = createSVGElement('text', {
        x: width / 2,
        y: height / 2 + 10,
        'font-size': labelFontSize,
        fill: colors.text,
        opacity: 0.7,
        'text-anchor': 'middle',
        'dominant-baseline': 'middle',
      });
      // Truncate long labels
      const maxLen = Math.floor((width - padding * 2) / 6);
      detailLabel.textContent =
        state.label.length > maxLen
          ? state.label.substring(0, maxLen - 2) + '...'
          : state.label;
      group.appendChild(detailLabel);
    }

    this.mainGroup.appendChild(group);

    // Add hover effect and tooltip
    group.style.cursor = 'pointer';
    (group as SVGGElement).addEventListener('mouseenter', (e: MouseEvent) => {
      rect.setAttribute('stroke-width', '2.5');
      rect.style.filter = 'brightness(1.05)';
      this.showTooltip(state, e.clientX, e.clientY);
    });
    (group as SVGGElement).addEventListener('mousemove', (e: MouseEvent) => {
      if (this.tooltipVisible) {
        this.showTooltip(state, e.clientX, e.clientY);
      }
    });
    (group as SVGGElement).addEventListener('mouseleave', () => {
      rect.setAttribute('stroke-width', '1.5');
      rect.style.filter = '';
      this.hideTooltip();
    });

    const ref: ElementRef = {
      type: 'state',
      id,
      element: group,
      bounds: { x, y, width, height },
    };
    this.elements.set(id, ref);
    return ref;
  }

  /**
   * Draw a stack container with states
   */
  drawStack(stack: StackConfig, x: number, y: number): ElementRef {
    const id = stack.id || generateId('stack');
    const { padding: stackPadding, borderRadius, minWidth } =
      dimensions.stack;
    const { width: stateWidth } = dimensions.state;

    const stackWidth = Math.max(minWidth, stateWidth + stackPadding * 2);
    const stackHeight = calculateStackHeight(stack.states.length);

    // Create group for the stack
    const group = createSVGElement('g', {
      id,
      transform: `translate(${x}, ${y})`,
      class: 'stack-container',
    });

    // Stack background
    const bg = createSVGElement('rect', {
      x: 0,
      y: 0,
      width: stackWidth,
      height: stackHeight,
      rx: borderRadius,
      ry: borderRadius,
      fill: this.theme.stackBackground,
      stroke: this.theme.stackBorderColor,
      'stroke-width': 1,
    });
    group.appendChild(bg);

    // Stack label
    if (stack.label) {
      const label = createSVGElement('text', {
        x: stackWidth / 2,
        y: 18,
        'font-size': 14,
        'font-weight': '600',
        fill: this.theme.textColor,
        'text-anchor': 'middle',
        'dominant-baseline': 'middle',
      });
      label.textContent = stack.label;
      group.appendChild(label);

      // Separator line
      const sep = createSVGElement('line', {
        x1: stackPadding + 8,
        y1: 32,
        x2: stackWidth - stackPadding - 8,
        y2: 32,
        stroke: this.theme.stackBorderColor,
        'stroke-width': 1,
      });
      group.appendChild(sep);
    }

    this.mainGroup.appendChild(group);

    // Draw states within stack
    const stateRefs: ElementRef[] = [];
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

    // Draw arrows between states
    for (let i = 0; i < stateRefs.length - 1; i++) {
      const from = stateRefs[i];
      const to = stateRefs[i + 1];
      this.drawStackArrow(
        { x: from.bounds.x + from.bounds.width / 2, y: from.bounds.y },
        { x: to.bounds.x + to.bounds.width / 2, y: to.bounds.y + to.bounds.height }
      );
    }

    const ref: ElementRef = {
      type: 'stack',
      id,
      element: group,
      bounds: { x, y, width: stackWidth, height: stackHeight },
      childRefs: stateRefs,
    };
    this.elements.set(id, ref);
    return ref;
  }

  /**
   * Draw a small arrow between stack states
   */
  private drawStackArrow(from: Point, to: Point): void {
    const arrow = createSVGElement('text', {
      x: from.x,
      y: (from.y + to.y) / 2 + 2,
      'font-size': 10,
      fill: this.theme.arrowColor,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
    });
    arrow.textContent = '↓';
    this.mainGroup.appendChild(arrow);
  }

  /**
   * Draw a tool box
   */
  drawTool(tool: ToolConfig, x: number, y: number, hidden: boolean = false): ElementRef {
    const id = tool.id || generateId('tool');
    const { width, height, borderRadius } = dimensions.tool;

    const group = createSVGElement('g', {
      id,
      transform: `translate(${x}, ${y})`,
      class: 'tool-box',
      style: hidden ? 'opacity: 0;' : '',
    });

    // Background (flat design, no shadow)
    const rect = createSVGElement('rect', {
      x: 0,
      y: 0,
      width,
      height,
      rx: borderRadius,
      ry: borderRadius,
      fill: tool.color || this.theme.toolColor,
      stroke: this.theme.toolBorderColor,
      'stroke-width': 1.5,
    });
    group.appendChild(rect);

    // Tool name (centered, with optional icon)
    const displayText = tool.icon ? `${tool.icon} ${tool.name}` : tool.name;
    const name = createSVGElement('text', {
      x: width / 2,
      y: height / 2,
      'font-size': 14,
      'font-weight': '500',
      fill: this.theme.textColor,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
    });
    name.textContent = displayText;
    group.appendChild(name);

    this.mainGroup.appendChild(group);

    const ref: ElementRef = {
      type: 'tool',
      id,
      element: group,
      bounds: { x, y, width, height },
    };
    this.elements.set(id, ref);
    return ref;
  }

  /**
   * Draw an artifact (document with folded corner)
   */
  drawArtifact(artifact: ArtifactConfig, x: number, y: number, hidden: boolean = false): ElementRef {
    const id = artifact.id || generateId('artifact');
    const { width, height, foldSize, borderRadius } = dimensions.artifact;

    const group = createSVGElement('g', {
      id,
      transform: `translate(${x}, ${y})`,
      class: 'artifact',
      style: hidden ? 'opacity: 0;' : '',
    });

    // Document shape with folded corner (top-right)
    // Path: start top-left, go right (minus fold), diagonal fold, down, left, up
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

    const doc = createSVGElement('path', {
      d: docPath,
      fill: artifact.color || '#e8f5e9',
      stroke: '#4caf50',
      'stroke-width': 1.5,
    });
    group.appendChild(doc);

    // Folded corner triangle
    const foldPath = `
      M ${width - foldSize} 0
      L ${width - foldSize} ${foldSize}
      L ${width} ${foldSize}
      Z
    `;
    const fold = createSVGElement('path', {
      d: foldPath,
      fill: '#c8e6c9',
      stroke: '#4caf50',
      'stroke-width': 1,
    });
    group.appendChild(fold);

    // Icon based on artifact type
    let icon = artifact.icon;
    if (!icon) {
      switch (artifact.type) {
        case 'document':
          icon = '\u{1F4C4}'; // Page facing up
          break;
        case 'image':
          icon = '\u{1F5BC}'; // Framed picture
          break;
        case 'data':
          icon = '\u{1F4CA}'; // Bar chart
          break;
        case 'code':
          icon = '\u{1F4BB}'; // Laptop
          break;
        default:
          icon = '\u{1F4C1}'; // File folder
      }
    }

    // Icon
    const iconText = createSVGElement('text', {
      x: width / 2,
      y: height / 2 - 6,
      'font-size': 20,
      'text-anchor': 'middle',
      'dominant-baseline': 'middle',
    });
    iconText.textContent = icon;
    group.appendChild(iconText);

    // Artifact name
    const name = createSVGElement('text', {
      x: width / 2,
      y: height - 12,
      'font-size': 10,
      'font-weight': '500',
      fill: '#2e7d32',
      'text-anchor': 'middle',
    });
    // Truncate name if too long
    const displayName = artifact.name.length > 12
      ? artifact.name.substring(0, 10) + '...'
      : artifact.name;
    name.textContent = artifact.extension
      ? `${displayName}.${artifact.extension}`
      : displayName;
    group.appendChild(name);

    this.mainGroup.appendChild(group);

    const ref: ElementRef = {
      type: 'artifact',
      id,
      element: group,
      bounds: { x, y, width, height },
    };
    this.elements.set(id, ref);
    return ref;
  }

  /**
   * Draw an arrow/connection between two points
   */
  drawArrow(options: ArrowOptions): ElementRef {
    const id = generateId('arrow');
    const { from, to, style = 'curved', strokeWidth = 2, color, dashArray, animated, hidden } = options;

    const group = createSVGElement('g', {
      id,
      class: 'arrow',
      style: hidden ? 'opacity: 0;' : '',
    });

    // Calculate path based on style
    let pathD: string;
    switch (style) {
      case 'straight':
        pathD = getStraightArrowPath(from, to);
        break;
      case 'stepped':
        pathD = getSteppedArrowPath(from, to);
        break;
      case 'curved':
      default:
        pathD = getCurvedArrowPath(from, to);
    }

    // Draw path
    const path = createSVGElement('path', {
      d: pathD,
      fill: 'none',
      stroke: color || this.theme.arrowColor,
      'stroke-width': strokeWidth,
      'stroke-linecap': 'round',
      'marker-end': options.showHead !== false ? 'url(#arrowhead)' : '',
    });

    if (dashArray) {
      path.setAttribute('stroke-dasharray', dashArray);
    }

    if (animated) {
      path.setAttribute('stroke-dasharray', '8 4');
      path.style.animation = 'dash 0.5s linear infinite';
    }

    group.appendChild(path);
    this.mainGroup.appendChild(group);

    // Calculate bounding box
    const minX = Math.min(from.x, to.x);
    const minY = Math.min(from.y, to.y);
    const maxX = Math.max(from.x, to.x);
    const maxY = Math.max(from.y, to.y);

    const ref: ElementRef = {
      type: 'arrow',
      id,
      element: group,
      bounds: { x: minX, y: minY, width: maxX - minX, height: maxY - minY },
    };
    this.elements.set(id, ref);
    return ref;
  }

  /**
   * Update an arrow's path to new endpoints (with animation)
   */
  async updateArrowPath(
    arrowRef: ElementRef,
    from: Point,
    to: Point,
    style: 'straight' | 'curved' | 'stepped' = 'curved',
    duration: number = 300
  ): Promise<void> {
    const group = arrowRef.element as SVGGElement;
    const path = group.querySelector('path');
    if (!path) return;

    // Calculate new path
    let pathD: string;
    switch (style) {
      case 'straight':
        pathD = getStraightArrowPath(from, to);
        break;
      case 'stepped':
        pathD = getSteppedArrowPath(from, to);
        break;
      case 'curved':
      default:
        pathD = getCurvedArrowPath(from, to);
    }

    // Animate the path change using CSS transition
    path.style.transition = `d ${duration}ms ease-in-out`;
    path.setAttribute('d', pathD);

    // Update bounds
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
  drawLabel(
    text: string,
    x: number,
    y: number,
    options: {
      fontSize?: number;
      fontWeight?: string;
      color?: string;
      anchor?: 'start' | 'middle' | 'end';
    } = {}
  ): ElementRef {
    const id = generateId('label');
    const { fontSize = 12, fontWeight = 'normal', color, anchor = 'start' } = options;

    const label = createSVGElement('text', {
      id,
      x,
      y,
      'font-size': fontSize,
      'font-weight': fontWeight,
      fill: color || this.theme.textColor,
      'text-anchor': anchor,
      'dominant-baseline': 'middle',
    });
    label.textContent = text;

    this.mainGroup.appendChild(label);

    const ref: ElementRef = {
      type: 'label',
      id,
      element: label,
      bounds: { x, y: y - fontSize / 2, width: text.length * fontSize * 0.6, height: fontSize },
    };
    this.elements.set(id, ref);
    return ref;
  }

  /**
   * Get an element reference by ID
   */
  getElementRef(id: string): ElementRef | undefined {
    return this.elements.get(id);
  }

  /**
   * Remove an element
   */
  removeElement(id: string): void {
    const ref = this.elements.get(id);
    if (ref) {
      ref.element.remove();
      this.elements.delete(id);
    }
  }

  /**
   * Animate an element's properties
   */
  async animate(
    element: SVGElement,
    props: Record<string, string | number>,
    duration: number = 500
  ): Promise<void> {
    return new Promise((resolve) => {
      // Use CSS transitions for smooth animation
      element.style.transition = `all ${duration}ms ease-in-out`;

      // Apply transform properties
      if ('x' in props || 'y' in props) {
        const currentTransform = element.getAttribute('transform') || '';
        const match = currentTransform.match(/translate\(([\d.-]+),\s*([\d.-]+)\)/);
        const currentX = match ? parseFloat(match[1]) : 0;
        const currentY = match ? parseFloat(match[2]) : 0;
        const newX = 'x' in props ? props.x : currentX;
        const newY = 'y' in props ? props.y : currentY;
        element.setAttribute('transform', `translate(${newX}, ${newY})`);
      }

      // Apply other properties
      for (const [key, value] of Object.entries(props)) {
        if (key !== 'x' && key !== 'y') {
          element.setAttribute(key, String(value));
        }
      }

      setTimeout(resolve, duration);
    });
  }

  /**
   * Fade in an element
   */
  async fadeIn(element: SVGElement, duration: number = 300): Promise<void> {
    element.style.opacity = '0';
    element.style.transition = `opacity ${duration}ms ease-in`;

    // Force reflow (getBoundingClientRect works on SVG elements)
    element.getBoundingClientRect();

    element.style.opacity = '1';
    await new Promise((resolve) => setTimeout(resolve, duration));
  }

  /**
   * Fade out an element
   */
  async fadeOut(element: SVGElement, duration: number = 300): Promise<void> {
    element.style.transition = `opacity ${duration}ms ease-out`;
    element.style.opacity = '0';
    await new Promise((resolve) => setTimeout(resolve, duration));
  }

  /**
   * Move an element to a new position
   */
  async moveTo(
    element: SVGElement,
    x: number,
    y: number,
    duration: number = 500
  ): Promise<void> {
    return this.animate(element, { x, y }, duration);
  }

  /**
   * Highlight an element
   */
  async highlight(element: SVGElement, duration: number = 500): Promise<void> {
    const originalFilter = element.getAttribute('filter') || '';
    element.setAttribute('filter', 'url(#glow)');
    await new Promise((resolve) => setTimeout(resolve, duration));
    element.setAttribute('filter', originalFilter);
  }

  /**
   * Add a pulsing effect to an element
   */
  pulse(element: SVGElement, duration: number = 1000): () => void {
    // Use filter brightness instead of transform to avoid overriding translate
    const animation = element.animate(
      [
        { filter: 'brightness(1)', opacity: 1 },
        { filter: 'brightness(1.15)', opacity: 0.85 },
        { filter: 'brightness(1)', opacity: 1 },
      ],
      {
        duration,
        iterations: Infinity,
        easing: 'ease-in-out',
      }
    );

    // Return cancel function
    return () => animation.cancel();
  }

  /**
   * Clean up resources
   */
  destroy(): void {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    this.svg.remove();
    this.elements.clear();
  }
}

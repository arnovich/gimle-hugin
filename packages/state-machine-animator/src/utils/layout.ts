/**
 * Layout utilities for positioning elements
 */

import type { Point, Rect, StackConfig, StateConfig } from '../core/types.js';

/**
 * Default dimensions for visual elements
 *
 * These match the Erik's Funhouse blog style:
 * - Generous border radius (~14px)
 * - Clean spacing
 * - Thin arrows
 */
export const dimensions = {
  state: {
    width: 165,
    height: 42,
    borderRadius: 14, // Generous rounded corners like the blog
    padding: 12,
    fontSize: 15,
    labelFontSize: 11,
  },
  stack: {
    stateSpacing: 4, // Small gap between states
    padding: 0, // No container padding (floating boxes)
    labelHeight: 40, // Height for stack label area (includes spacing below label)
    minWidth: 170,
    borderRadius: 14,
  },
  tool: {
    width: 140,
    height: 44,
    borderRadius: 14, // Match state border radius
    iconSize: 18,
  },
  artifact: {
    width: 100,
    height: 70,
    foldSize: 16, // Size of the folded corner
    borderRadius: 4, // Smaller radius for document look
  },
  arrow: {
    strokeWidth: 1.5, // Thin arrows like the blog
    headSize: 6,
    dashArray: '5,5',
  },
  spacing: {
    stackGap: 80, // Gap between stacks
    toolGap: 50, // Gap between stack and tool
    branchGap: 50, // Gap between branches
  },
};

/**
 * Calculate the height of a stack based on number of states
 */
export function calculateStackHeight(numStates: number): number {
  const { stateSpacing, padding, labelHeight } = dimensions.stack;
  const { height: stateHeight } = dimensions.state;

  if (numStates === 0) {
    return labelHeight + padding * 2 + stateHeight; // Show at least space for one state
  }

  return (
    labelHeight +
    padding * 2 +
    numStates * stateHeight +
    (numStates - 1) * stateSpacing
  );
}

/**
 * Calculate position of a state within a stack
 * Index 0 is the bottom of the stack (first state added)
 */
export function getStatePositionInStack(
  stackX: number,
  stackY: number,
  stackWidth: number,
  totalStates: number,
  stateIndex: number
): Point {
  const { stateSpacing, padding, labelHeight } = dimensions.stack;
  const { height: stateHeight, width: stateWidth } = dimensions.state;

  // Center state horizontally in stack
  const x = stackX + (stackWidth - stateWidth) / 2;

  // Position from top, but logically index from bottom
  // So index 0 appears at the bottom, index n-1 at the top
  const reversedIndex = totalStates - 1 - stateIndex;
  const y =
    stackY + labelHeight + padding + reversedIndex * (stateHeight + stateSpacing);

  return { x, y };
}

/**
 * Calculate the bounds of a stack
 */
export function getStackBounds(
  stack: StackConfig,
  position: Point
): Rect {
  const height = calculateStackHeight(stack.states.length);
  const width = Math.max(
    dimensions.stack.minWidth,
    dimensions.state.width + dimensions.stack.padding * 2
  );

  return {
    x: position.x,
    y: position.y,
    width,
    height,
  };
}

/**
 * Calculate center point of a rectangle
 */
export function getRectCenter(rect: Rect): Point {
  return {
    x: rect.x + rect.width / 2,
    y: rect.y + rect.height / 2,
  };
}

/**
 * Calculate connection points for arrows between elements
 */
export function getConnectionPoints(
  from: Rect,
  to: Rect,
  fromSide: 'top' | 'bottom' | 'left' | 'right' = 'right',
  toSide: 'top' | 'bottom' | 'left' | 'right' = 'left'
): { from: Point; to: Point } {
  const getPoint = (rect: Rect, side: string): Point => {
    switch (side) {
      case 'top':
        return { x: rect.x + rect.width / 2, y: rect.y };
      case 'bottom':
        return { x: rect.x + rect.width / 2, y: rect.y + rect.height };
      case 'left':
        return { x: rect.x, y: rect.y + rect.height / 2 };
      case 'right':
        return { x: rect.x + rect.width, y: rect.y + rect.height / 2 };
      default:
        return getRectCenter(rect);
    }
  };

  return {
    from: getPoint(from, fromSide),
    to: getPoint(to, toSide),
  };
}

/**
 * Generate SVG path for a curved arrow
 */
export function getCurvedArrowPath(from: Point, to: Point): string {
  const midX = (from.x + to.x) / 2;
  const midY = (from.y + to.y) / 2;

  // Calculate control points for a smooth curve
  const dx = to.x - from.x;
  const dy = to.y - from.y;

  // Offset perpendicular to the line for curve
  const curveOffset = Math.min(Math.abs(dx), Math.abs(dy)) * 0.3;

  // Simple quadratic curve
  const controlX = midX;
  const controlY = midY - curveOffset;

  return `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`;
}

/**
 * Generate SVG path for a stepped arrow (right-angle turns)
 */
export function getSteppedArrowPath(from: Point, to: Point): string {
  const midX = (from.x + to.x) / 2;

  return `M ${from.x} ${from.y} L ${midX} ${from.y} L ${midX} ${to.y} L ${to.x} ${to.y}`;
}

/**
 * Generate SVG path for a straight arrow
 */
export function getStraightArrowPath(from: Point, to: Point): string {
  return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
}

/**
 * Calculate arrowhead points
 */
export function getArrowheadPoints(
  to: Point,
  from: Point,
  size: number = dimensions.arrow.headSize
): string {
  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  const angle1 = angle + Math.PI * 0.8;
  const angle2 = angle - Math.PI * 0.8;

  const x1 = to.x + size * Math.cos(angle1);
  const y1 = to.y + size * Math.sin(angle1);
  const x2 = to.x + size * Math.cos(angle2);
  const y2 = to.y + size * Math.sin(angle2);

  return `${to.x},${to.y} ${x1},${y1} ${x2},${y2}`;
}

/**
 * Layout multiple stacks horizontally
 */
export function layoutStacksHorizontally(
  stacks: StackConfig[],
  startX: number,
  startY: number
): Map<string, Point> {
  const positions = new Map<string, Point>();
  let currentX = startX;

  for (const stack of stacks) {
    positions.set(stack.id, { x: currentX, y: startY });
    const bounds = getStackBounds(stack, { x: currentX, y: startY });
    currentX += bounds.width + dimensions.spacing.stackGap;
  }

  return positions;
}

/**
 * Layout branches from a source stack
 */
export function layoutBranches(
  sourceStack: StackConfig,
  branches: Array<{ id: string; states: StateConfig[] }>,
  sourcePosition: Point,
  branchPoint: number
): Map<string, Point> {
  const positions = new Map<string, Point>();
  const sourceBounds = getStackBounds(sourceStack, sourcePosition);

  // Calculate Y position for branch point
  const branchY =
    sourcePosition.y +
    dimensions.stack.labelHeight +
    dimensions.stack.padding +
    (sourceStack.states.length - branchPoint) *
      (dimensions.state.height + dimensions.stack.stateSpacing);

  // Layout branches horizontally, centered below branch point
  const totalWidth =
    branches.length * dimensions.stack.minWidth +
    (branches.length - 1) * dimensions.spacing.branchGap;

  let startX = sourcePosition.x + sourceBounds.width / 2 - totalWidth / 2;
  const branchStartY = branchY + dimensions.spacing.branchGap;

  for (const branch of branches) {
    positions.set(branch.id, { x: startX, y: branchStartY });
    startX += dimensions.stack.minWidth + dimensions.spacing.branchGap;
  }

  return positions;
}

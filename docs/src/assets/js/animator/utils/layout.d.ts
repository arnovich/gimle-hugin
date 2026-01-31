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
export declare const dimensions: {
    state: {
        width: number;
        height: number;
        borderRadius: number;
        padding: number;
        fontSize: number;
        labelFontSize: number;
    };
    stack: {
        stateSpacing: number;
        padding: number;
        labelHeight: number;
        minWidth: number;
        borderRadius: number;
    };
    tool: {
        width: number;
        height: number;
        borderRadius: number;
        iconSize: number;
    };
    artifact: {
        width: number;
        height: number;
        foldSize: number;
        borderRadius: number;
    };
    arrow: {
        strokeWidth: number;
        headSize: number;
        dashArray: string;
    };
    spacing: {
        stackGap: number;
        toolGap: number;
        branchGap: number;
    };
};
/**
 * Calculate the height of a stack based on number of states
 */
export declare function calculateStackHeight(numStates: number): number;
/**
 * Calculate position of a state within a stack
 * Index 0 is the bottom of the stack (first state added)
 */
export declare function getStatePositionInStack(stackX: number, stackY: number, stackWidth: number, totalStates: number, stateIndex: number): Point;
/**
 * Calculate the bounds of a stack
 */
export declare function getStackBounds(stack: StackConfig, position: Point): Rect;
/**
 * Calculate center point of a rectangle
 */
export declare function getRectCenter(rect: Rect): Point;
/**
 * Calculate connection points for arrows between elements
 */
export declare function getConnectionPoints(from: Rect, to: Rect, fromSide?: 'top' | 'bottom' | 'left' | 'right', toSide?: 'top' | 'bottom' | 'left' | 'right'): {
    from: Point;
    to: Point;
};
/**
 * Generate SVG path for a curved arrow
 */
export declare function getCurvedArrowPath(from: Point, to: Point): string;
/**
 * Generate SVG path for a stepped arrow (right-angle turns)
 */
export declare function getSteppedArrowPath(from: Point, to: Point): string;
/**
 * Generate SVG path for a straight arrow
 */
export declare function getStraightArrowPath(from: Point, to: Point): string;
/**
 * Calculate arrowhead points
 */
export declare function getArrowheadPoints(to: Point, from: Point, size?: number): string;
/**
 * Layout multiple stacks horizontally
 */
export declare function layoutStacksHorizontally(stacks: StackConfig[], startX: number, startY: number): Map<string, Point>;
/**
 * Layout branches from a source stack
 */
export declare function layoutBranches(sourceStack: StackConfig, branches: Array<{
    id: string;
    states: StateConfig[];
}>, sourcePosition: Point, branchPoint: number): Map<string, Point>;
//# sourceMappingURL=layout.d.ts.map

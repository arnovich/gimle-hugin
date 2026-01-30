/**
 * SVG-based renderer for state machine visualizations
 *
 * Uses SVG for crisp, scalable graphics with smooth CSS animations.
 */
import type { RendererConfig, ThemeConfig, StateConfig, StackConfig, ToolConfig, ArtifactConfig, Point, Rect, ArrowOptions, ElementRef } from '../core/types.js';
/**
 * SVG Renderer class
 */
export declare class SVGRenderer {
    private container;
    private svg;
    private defs;
    private mainGroup;
    private theme;
    private width;
    private height;
    private padding;
    private elements;
    private resizeObserver;
    private panX;
    private panY;
    private zoom;
    private isPanning;
    private lastMouseX;
    private lastMouseY;
    private minZoom;
    private maxZoom;
    private tooltipGroup;
    private tooltipVisible;
    constructor(config: RendererConfig);
    /**
     * Setup pan and zoom event handlers
     */
    private setupPanZoom;
    /**
     * Update the main group transform based on pan/zoom state
     */
    private updateTransform;
    /**
     * Reset pan and zoom to default
     */
    resetView(): void;
    /**
     * Set zoom level programmatically
     */
    setZoom(level: number): void;
    /**
     * Get current zoom level
     */
    getZoom(): number;
    /**
     * Create tooltip element
     */
    private createTooltip;
    /**
     * Show tooltip with state information
     */
    showTooltip(state: StateConfig, screenX: number, screenY: number): void;
    /**
     * Hide tooltip
     */
    hideTooltip(): void;
    /**
     * Pan to center on a specific point
     */
    panTo(x: number, y: number): void;
    /**
     * Add reusable SVG definitions
     */
    private addFiltersAndGradients;
    /**
     * Draw background
     */
    private drawBackground;
    /**
     * Setup responsive behavior
     */
    private setupResponsive;
    /**
     * Clear all rendered elements
     */
    clear(): void;
    /**
     * Resize the canvas
     */
    resize(width: number, height: number): void;
    /**
     * Get the SVG element
     */
    getElement(): SVGSVGElement;
    /**
     * Get the theme
     */
    getTheme(): ThemeConfig;
    /**
     * Get available drawing area
     */
    getDrawingArea(): Rect;
    /**
     * Draw a state box
     */
    drawState(state: StateConfig, x: number, y: number): ElementRef;
    /**
     * Draw a stack container with states
     */
    drawStack(stack: StackConfig, x: number, y: number): ElementRef;
    /**
     * Draw a small arrow between stack states
     */
    private drawStackArrow;
    /**
     * Draw a tool box
     */
    drawTool(tool: ToolConfig, x: number, y: number, hidden?: boolean): ElementRef;
    /**
     * Draw an artifact (document with folded corner)
     */
    drawArtifact(artifact: ArtifactConfig, x: number, y: number, hidden?: boolean): ElementRef;
    /**
     * Draw an arrow/connection between two points
     */
    drawArrow(options: ArrowOptions): ElementRef;
    /**
     * Update an arrow's path to new endpoints (with animation)
     */
    updateArrowPath(arrowRef: ElementRef, from: Point, to: Point, style?: 'straight' | 'curved' | 'stepped', duration?: number): Promise<void>;
    /**
     * Draw a text label
     */
    drawLabel(text: string, x: number, y: number, options?: {
        fontSize?: number;
        fontWeight?: string;
        color?: string;
        anchor?: 'start' | 'middle' | 'end';
    }): ElementRef;
    /**
     * Get an element reference by ID
     */
    getElementRef(id: string): ElementRef | undefined;
    /**
     * Remove an element
     */
    removeElement(id: string): void;
    /**
     * Animate an element's properties
     */
    animate(element: SVGElement, props: Record<string, string | number>, duration?: number): Promise<void>;
    /**
     * Fade in an element
     */
    fadeIn(element: SVGElement, duration?: number): Promise<void>;
    /**
     * Fade out an element
     */
    fadeOut(element: SVGElement, duration?: number): Promise<void>;
    /**
     * Move an element to a new position
     */
    moveTo(element: SVGElement, x: number, y: number, duration?: number): Promise<void>;
    /**
     * Highlight an element
     */
    highlight(element: SVGElement, duration?: number): Promise<void>;
    /**
     * Add a pulsing effect to an element
     */
    pulse(element: SVGElement, duration?: number): () => void;
    /**
     * Clean up resources
     */
    destroy(): void;
}
//# sourceMappingURL=SVGRenderer.d.ts.map
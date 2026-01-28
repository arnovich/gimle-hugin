/**
 * Core Animator class for orchestrating state machine animations
 *
 * This is the main entry point for the library. It manages the rendering,
 * animation queue, and provides high-level animation APIs.
 */
import type { RendererConfig, StateConfig, StackConfig, AnimatorEvent, AnimatorEventCallback, ToolExecutionAnimation, ArtifactCreationAnimation, TransitionDiagramAnimation, BranchAnimation, MultiStackInteraction, Point, ElementRef } from './types.js';
import { SVGRenderer } from '../renderers/SVGRenderer.js';
/**
 * State Machine Animator
 */
export declare class StateMachineAnimator {
    private renderer;
    private animationQueue;
    private isPlaying;
    private isPaused;
    private speedMultiplier;
    private stacks;
    private eventListeners;
    private defaultAnimationDuration;
    constructor(config: RendererConfig);
    /**
     * Play queued animations
     */
    play(): Promise<void>;
    /**
     * Pause animations
     */
    pause(): void;
    /**
     * Resume paused animations
     */
    resume(): void;
    /**
     * Stop and clear animation queue
     */
    stop(): void;
    /**
     * Reset the animator and clear canvas
     */
    reset(): void;
    /**
     * Set animation speed multiplier
     */
    setSpeed(multiplier: number): void;
    /**
     * Reset pan and zoom to default view
     */
    resetView(): void;
    /**
     * Set zoom level (0.25 to 4)
     */
    setZoom(level: number): void;
    /**
     * Get current zoom level
     */
    getZoom(): number;
    /**
     * Get effective duration with speed multiplier
     */
    private getDuration;
    /**
     * Subscribe to animator events
     */
    on(event: AnimatorEvent, callback: AnimatorEventCallback): void;
    /**
     * Unsubscribe from animator events
     */
    off(event: AnimatorEvent, callback: AnimatorEventCallback): void;
    /**
     * Emit an event
     */
    private emit;
    /**
     * Add a stack to the visualization
     */
    addStack(stack: StackConfig, position?: Point): ElementRef;
    /**
     * Remove a stack
     */
    removeStack(stackId: string): void;
    /**
     * Get a stack's current configuration
     */
    getStack(stackId: string): StackConfig | undefined;
    /**
     * Push a state onto a stack (animated)
     */
    pushState(stackId: string, state: StateConfig): Promise<void>;
    /**
     * Pop a state from a stack (animated)
     */
    popState(stackId: string): Promise<StateConfig | undefined>;
    /**
     * Highlight a specific state in a stack
     */
    highlightState(stackId: string, _index: number): Promise<void>;
    /**
     * Draw a connection between two elements
     */
    drawConnection(fromRef: ElementRef, toRef: ElementRef, animated?: boolean): Promise<ElementRef>;
    /**
     * Play a tool execution animation
     */
    playToolExecution(config: ToolExecutionAnimation): Promise<void>;
    /**
     * Play an artifact creation animation.
     * Shows a tool call creating an external artifact that stays attached to the interaction.
     */
    playArtifactCreation(config: ArtifactCreationAnimation): Promise<void>;
    /**
     * Play a state transition diagram animation
     */
    playTransitionDiagram(config: TransitionDiagramAnimation): Promise<void>;
    /**
     * Play a branching animation
     */
    playBranching(config: BranchAnimation): Promise<void>;
    /**
     * Play a multi-stack interaction animation
     */
    playMultiStackInteraction(config: MultiStackInteraction): Promise<void>;
    /**
     * Wait for a duration
     */
    private delay;
    /**
     * Get the renderer (for advanced usage)
     */
    getRenderer(): SVGRenderer;
    /**
     * Clean up resources
     */
    destroy(): void;
}
//# sourceMappingURL=Animator.d.ts.map

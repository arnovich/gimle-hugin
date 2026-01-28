/**
 * Core Animator class for orchestrating state machine animations
 *
 * This is the main entry point for the library. It manages the rendering,
 * animation queue, and provides high-level animation APIs.
 */

import type {
  RendererConfig,
  StateConfig,
  StackConfig,
  AnimationConfig,
  AnimatorEvent,
  AnimatorEventCallback,
  ToolExecutionAnimation,
  ArtifactCreationAnimation,
  TransitionDiagramAnimation,
  BranchAnimation,
  MultiStackInteraction,
  Point,
  ElementRef,
} from './types.js';
import { SVGRenderer } from '../renderers/SVGRenderer.js';
import {
  dimensions,
  getStatePositionInStack,
  getConnectionPoints,
} from '../utils/layout.js';

/**
 * Animation queue item
 */
interface QueuedAnimation {
  fn: () => Promise<void>;
  config?: AnimationConfig;
}

/**
 * Internal stack state tracking
 */
interface StackState {
  config: StackConfig;
  position: Point;
  ref: ElementRef;
  stateRefs: ElementRef[]; // Track individual state elements for animation
}

/**
 * State Machine Animator
 */
export class StateMachineAnimator {
  private renderer: SVGRenderer;
  private animationQueue: QueuedAnimation[] = [];
  private isPlaying: boolean = false;
  private isPaused: boolean = false;
  private speedMultiplier: number = 1;
  private stacks: Map<string, StackState> = new Map();
  private eventListeners: Map<AnimatorEvent, Set<AnimatorEventCallback>> = new Map();
  private defaultAnimationDuration: number = 500;

  constructor(config: RendererConfig) {
    this.renderer = new SVGRenderer(config);
  }

  // ===========================================================================
  // Playback Control
  // ===========================================================================

  /**
   * Play queued animations
   */
  async play(): Promise<void> {
    if (this.isPlaying) return;
    this.isPlaying = true;
    this.isPaused = false;

    this.emit('animationStart');

    while (this.animationQueue.length > 0 && !this.isPaused) {
      const animation = this.animationQueue.shift();
      if (animation) {
        await animation.fn();
      }
    }

    this.isPlaying = false;
    this.emit('animationComplete');
  }

  /**
   * Pause animations
   */
  pause(): void {
    this.isPaused = true;
  }

  /**
   * Resume paused animations
   */
  resume(): void {
    if (this.isPaused) {
      this.isPaused = false;
      this.play();
    }
  }

  /**
   * Stop and clear animation queue
   */
  stop(): void {
    this.animationQueue = [];
    this.isPlaying = false;
    this.isPaused = false;
  }

  /**
   * Reset the animator and clear canvas
   */
  reset(): void {
    this.stop();
    this.renderer.clear();
    this.renderer.resetView();
    this.stacks.clear();
  }

  /**
   * Set animation speed multiplier
   */
  setSpeed(multiplier: number): void {
    this.speedMultiplier = Math.max(0.1, Math.min(10, multiplier));
  }

  /**
   * Reset pan and zoom to default view
   */
  resetView(): void {
    this.renderer.resetView();
  }

  /**
   * Set zoom level (0.25 to 4)
   */
  setZoom(level: number): void {
    this.renderer.setZoom(level);
  }

  /**
   * Get current zoom level
   */
  getZoom(): number {
    return this.renderer.getZoom();
  }

  /**
   * Get effective duration with speed multiplier
   */
  private getDuration(baseDuration?: number): number {
    const duration = baseDuration ?? this.defaultAnimationDuration;
    return duration / this.speedMultiplier;
  }

  // ===========================================================================
  // Event Handling
  // ===========================================================================

  /**
   * Subscribe to animator events
   */
  on(event: AnimatorEvent, callback: AnimatorEventCallback): void {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, new Set());
    }
    this.eventListeners.get(event)!.add(callback);
  }

  /**
   * Unsubscribe from animator events
   */
  off(event: AnimatorEvent, callback: AnimatorEventCallback): void {
    this.eventListeners.get(event)?.delete(callback);
  }

  /**
   * Emit an event
   */
  private emit(event: AnimatorEvent, data?: unknown): void {
    this.eventListeners.get(event)?.forEach((callback) => callback(data));
  }

  // ===========================================================================
  // Stack Management
  // ===========================================================================

  /**
   * Add a stack to the visualization
   */
  addStack(stack: StackConfig, position?: Point): ElementRef {
    const pos = position ?? { x: 40, y: 40 };
    const ref = this.renderer.drawStack(stack, pos.x, pos.y);

    this.stacks.set(stack.id, {
      config: { ...stack },
      position: pos,
      ref,
      stateRefs: ref.childRefs ? [...ref.childRefs] : [], // Capture initial state refs
    });

    return ref;
  }

  /**
   * Remove a stack
   */
  removeStack(stackId: string): void {
    const state = this.stacks.get(stackId);
    if (state) {
      this.renderer.removeElement(stackId);
      this.stacks.delete(stackId);
    }
  }

  /**
   * Get a stack's current configuration
   */
  getStack(stackId: string): StackConfig | undefined {
    return this.stacks.get(stackId)?.config;
  }

  // ===========================================================================
  // Low-Level Animation Primitives
  // ===========================================================================

  /**
   * Push a state onto a stack (animated)
   */
  async pushState(stackId: string, state: StateConfig): Promise<void> {
    const stackState = this.stacks.get(stackId);
    if (!stackState) {
      throw new Error(`Stack not found: ${stackId}`);
    }

    const { config, position, stateRefs } = stackState;
    const duration = this.getDuration();

    // Calculate stack width
    const stackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );

    // Total states after push
    const totalStates = config.states.length + 1;

    // First, animate all existing states down to their new positions
    const moveAnimations: Promise<void>[] = [];
    for (let i = 0; i < stateRefs.length; i++) {
      const existingRef = stateRefs[i];
      // Each existing state keeps its logical index but there's now one more state
      const newPos = getStatePositionInStack(
        position.x,
        position.y,
        stackWidth,
        totalStates,
        i // Same index, but totalStates increased so it moves down
      );
      moveAnimations.push(
        this.renderer.moveTo(
          existingRef.element as SVGElement,
          newPos.x,
          newPos.y,
          duration / 2
        )
      );
    }

    // Wait for all existing states to move down
    if (moveAnimations.length > 0) {
      await Promise.all(moveAnimations);
    }

    // Calculate position for new state (at the top of stack)
    const newIndex = config.states.length; // Will be the topmost (newest) state
    const newStatePos = getStatePositionInStack(
      position.x,
      position.y,
      stackWidth,
      totalStates,
      newIndex
    );

    // Create state above the stack (for drop-in animation)
    const startY = newStatePos.y - 50;
    const stateRef = this.renderer.drawState(state, newStatePos.x, startY);

    // Fade in
    await this.renderer.fadeIn(stateRef.element as SVGElement, duration / 2);

    // Animate down to position
    await this.renderer.moveTo(
      stateRef.element as SVGElement,
      newStatePos.x,
      newStatePos.y,
      duration / 2
    );

    // Update stack state
    config.states.push(state);
    stateRefs.push(stateRef);

    this.emit('stateChange', { stackId, state, action: 'push' });
  }

  /**
   * Pop a state from a stack (animated)
   */
  async popState(stackId: string): Promise<StateConfig | undefined> {
    const stackState = this.stacks.get(stackId);
    if (!stackState || stackState.config.states.length === 0) {
      return undefined;
    }

    const { config } = stackState;

    // Get the top state
    const topState = config.states[config.states.length - 1];

    // Remove from config (animation could be added in the future)

    config.states.pop();

    this.emit('stateChange', { stackId, state: topState, action: 'pop' });

    return topState;
  }

  /**
   * Highlight a specific state in a stack
   */
  async highlightState(stackId: string, _index: number): Promise<void> {
    const stackState = this.stacks.get(stackId);
    if (!stackState) return;

    // TODO: Would need element tracking to highlight specific state
    // For now, highlight the entire stack
    await this.renderer.highlight(
      stackState.ref.element as SVGElement,
      this.getDuration()
    );
  }

  /**
   * Draw a connection between two elements
   */
  async drawConnection(
    fromRef: ElementRef,
    toRef: ElementRef,
    animated: boolean = true
  ): Promise<ElementRef> {
    const { from, to } = getConnectionPoints(
      fromRef.bounds,
      toRef.bounds,
      'right',
      'left'
    );

    const arrowRef = this.renderer.drawArrow({
      from,
      to,
      style: 'curved',
      animated,
    });

    if (animated) {
      await this.renderer.fadeIn(arrowRef.element as SVGElement, this.getDuration());
    }

    return arrowRef;
  }

  // ===========================================================================
  // High-Level Animation APIs
  // ===========================================================================

  /**
   * Play a tool execution animation
   */
  async playToolExecution(config: ToolExecutionAnimation): Promise<void> {
    const duration = this.getDuration(config.options?.executionDuration || 500);

    // Clear and set up
    this.renderer.clear();

    // Draw the initial stack
    const stackRef = this.addStack(config.stack, { x: 60, y: 60 });
    const stackState = this.stacks.get(config.stack.id)!;

    // Calculate stack width (used for positioning calculations)
    const stackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );

    // Calculate tool position - place it to the right, vertically centered
    const toolX = stackRef.bounds.x + stackRef.bounds.width + dimensions.spacing.toolGap;
    const toolY = 100; // Fixed Y position for stability

    // Draw tool box (hidden initially)
    const toolRef = this.renderer.drawTool(config.tool, toolX, toolY, true);

    await this.delay(duration / 2);

    // Push pre-states if any (e.g., AskOracle, OracleResponse before ToolCall)
    if (config.preStates && config.preStates.length > 0) {
      for (const state of config.preStates) {
        await this.pushState(config.stack.id, state);
        await this.delay(duration / 3);
      }
    }

    // Animate trigger state (ToolCall) pushing onto stack
    await this.pushState(config.stack.id, config.triggerState);

    // Calculate the actual position of the ToolCall state (top of stack after push)
    const toolCallIndex = stackState.config.states.length - 1;
    const toolCallPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      stackState.config.states.length,
      toolCallIndex
    );

    await this.delay(duration / 4);

    // Fade in the tool box as we're about to connect to it
    await this.renderer.fadeIn(toolRef.element as SVGElement, duration / 3);

    // Draw arrow from ToolCall to tool (outgoing request) - anchored to bottom of tool
    const arrow1 = this.renderer.drawArrow({
      from: {
        x: toolCallPos.x + dimensions.state.width,
        y: toolCallPos.y + dimensions.state.height / 2,
      },
      to: {
        x: toolRef.bounds.x,
        y: toolRef.bounds.y + toolRef.bounds.height * 0.7,
      },
      style: config.options?.arrowStyle || 'curved',
    });

    await this.renderer.fadeIn(arrow1.element as SVGElement, duration / 3);

    // Pulse tool (execution)
    const cancelPulse = this.renderer.pulse(toolRef.element as SVGElement, 300);
    await this.delay(duration);
    cancelPulse();

    // Calculate where the ToolResult will appear (at the top of the stack after push)
    const totalStatesAfterResult = stackState.config.states.length + 1;
    const resultPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      totalStatesAfterResult,
      totalStatesAfterResult - 1 // The new top state
    );

    // Draw arrow from tool back to where result will appear (incoming response) - anchored from top of tool
    const arrow2 = this.renderer.drawArrow({
      from: {
        x: toolRef.bounds.x,
        y: toolRef.bounds.y + toolRef.bounds.height * 0.3,
      },
      to: {
        x: resultPos.x + dimensions.state.width,
        y: resultPos.y + dimensions.state.height / 2,
      },
      style: config.options?.arrowStyle || 'curved',
    });

    await this.renderer.fadeIn(arrow2.element as SVGElement, duration / 3);

    await this.delay(duration / 4);

    // Calculate where ToolCall will be after ToolResult is pushed
    const newToolCallPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      stackState.config.states.length + 1, // After result is added
      toolCallIndex // ToolCall stays at same index
    );

    // Push result state AND update arrow1 in parallel
    // The arrow follows ToolCall as it moves down
    await Promise.all([
      this.pushState(config.stack.id, config.resultState),
      this.renderer.updateArrowPath(
        arrow1,
        {
          x: newToolCallPos.x + dimensions.state.width,
          y: newToolCallPos.y + dimensions.state.height / 2,
        },
        {
          x: toolRef.bounds.x,
          y: toolRef.bounds.y + toolRef.bounds.height * 0.7,
        },
        config.options?.arrowStyle || 'curved',
        duration / 2
      ),
    ]);

    // Push post-states if any, updating arrows as ToolCall and ToolResult move down
    if (config.postStates && config.postStates.length > 0) {
      await this.delay(duration / 2);

      // ToolResult is right above ToolCall (index = toolCallIndex + 1)
      const toolResultIndex = toolCallIndex + 1;

      for (const state of config.postStates) {
        // Calculate new positions after this state is pushed
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

        // Push state and update both arrows in parallel
        await Promise.all([
          this.pushState(config.stack.id, state),
          this.renderer.updateArrowPath(
            arrow1,
            {
              x: nextToolCallPos.x + dimensions.state.width,
              y: nextToolCallPos.y + dimensions.state.height / 2,
            },
            {
              x: toolRef.bounds.x,
              y: toolRef.bounds.y + toolRef.bounds.height * 0.7,
            },
            config.options?.arrowStyle || 'curved',
            duration / 4
          ),
          this.renderer.updateArrowPath(
            arrow2,
            {
              x: toolRef.bounds.x,
              y: toolRef.bounds.y + toolRef.bounds.height * 0.3,
            },
            {
              x: nextToolResultPos.x + dimensions.state.width,
              y: nextToolResultPos.y + dimensions.state.height / 2,
            },
            config.options?.arrowStyle || 'curved',
            duration / 4
          ),
        ]);

        await this.delay(duration / 3);
      }
    }

    this.emit('animationComplete', { type: 'toolExecution' });
  }

  /**
   * Play an artifact creation animation.
   * Shows a tool call creating an external artifact that stays attached to the interaction.
   */
  async playArtifactCreation(config: ArtifactCreationAnimation): Promise<void> {
    const duration = this.getDuration();
    const artifactPosition = config.options?.artifactPosition || 'right';

    // Clear and set up
    this.renderer.clear();

    // Draw the initial stack
    const stackRef = this.addStack(config.stack, { x: 60, y: 60 });
    const stackState = this.stacks.get(config.stack.id)!;

    // Calculate stack width
    const stackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );

    await this.delay(duration / 2);

    // Push pre-states if any
    if (config.preStates && config.preStates.length > 0) {
      for (const state of config.preStates) {
        await this.pushState(config.stack.id, state);
        await this.delay(duration / 3);
      }
    }

    // Push the creator state (e.g., ToolCall that creates the artifact)
    await this.pushState(config.stack.id, config.creatorState);

    // Get creator state position
    const creatorIndex = stackState.config.states.length - 1;
    const creatorPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      stackState.config.states.length,
      creatorIndex
    );

    await this.delay(duration / 2);

    // Calculate artifact position
    const artifactX =
      artifactPosition === 'right'
        ? stackRef.bounds.x + stackRef.bounds.width + 60
        : stackRef.bounds.x - dimensions.artifact.width - 60;
    const artifactY = creatorPos.y - 10;

    // Draw artifact (hidden initially)
    const artifactRef = this.renderer.drawArtifact(config.artifact, artifactX, artifactY, true);

    // Draw arrow from creator state to artifact
    const arrowFrom = {
      x: artifactPosition === 'right'
        ? creatorPos.x + dimensions.state.width
        : creatorPos.x,
      y: creatorPos.y + dimensions.state.height / 2,
    };
    const arrowTo = {
      x: artifactPosition === 'right'
        ? artifactRef.bounds.x
        : artifactRef.bounds.x + artifactRef.bounds.width,
      y: artifactRef.bounds.y + artifactRef.bounds.height / 2,
    };

    const arrow = this.renderer.drawArrow({
      from: arrowFrom,
      to: arrowTo,
      style: config.options?.arrowStyle || 'curved',
      hidden: true,
    });

    // Fade in artifact and arrow together
    await Promise.all([
      this.renderer.fadeIn(artifactRef.element as SVGElement, duration / 2),
      this.renderer.fadeIn(arrow.element as SVGElement, duration / 2),
    ]);

    await this.delay(duration / 2);

    // Push result state
    // Calculate new positions after result is pushed
    const newTotalStates = stackState.config.states.length + 1;
    const newCreatorPos = getStatePositionInStack(
      stackState.position.x,
      stackState.position.y,
      stackWidth,
      newTotalStates,
      creatorIndex
    );

    // Push result and update arrow in parallel
    await Promise.all([
      this.pushState(config.stack.id, config.resultState),
      this.renderer.updateArrowPath(
        arrow,
        {
          x: artifactPosition === 'right'
            ? newCreatorPos.x + dimensions.state.width
            : newCreatorPos.x,
          y: newCreatorPos.y + dimensions.state.height / 2,
        },
        arrowTo,
        config.options?.arrowStyle || 'curved',
        duration / 4
      ),
      this.renderer.moveTo(
        artifactRef.element as SVGElement,
        artifactX,
        newCreatorPos.y - 10,
        duration / 4
      ),
    ]);

    // Update arrow endpoint to match new artifact position
    const newArrowTo = {
      x: arrowTo.x,
      y: newCreatorPos.y - 10 + artifactRef.bounds.height / 2,
    };

    await this.renderer.updateArrowPath(
      arrow,
      {
        x: artifactPosition === 'right'
          ? newCreatorPos.x + dimensions.state.width
          : newCreatorPos.x,
        y: newCreatorPos.y + dimensions.state.height / 2,
      },
      newArrowTo,
      config.options?.arrowStyle || 'curved',
      100
    );

    // Push post-states if any, updating arrow and artifact position each time
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
          y: nextArtifactY + artifactRef.bounds.height / 2,
        };

        await Promise.all([
          this.pushState(config.stack.id, state),
          this.renderer.updateArrowPath(
            arrow,
            {
              x: artifactPosition === 'right'
                ? nextCreatorPos.x + dimensions.state.width
                : nextCreatorPos.x,
              y: nextCreatorPos.y + dimensions.state.height / 2,
            },
            nextArrowTo,
            config.options?.arrowStyle || 'curved',
            duration / 4
          ),
          this.renderer.moveTo(
            artifactRef.element as SVGElement,
            artifactX,
            nextArtifactY,
            duration / 4
          ),
        ]);

        await this.delay(duration / 3);
      }
    }

    this.emit('animationComplete', { type: 'artifactCreation' });
  }

  /**
   * Play a state transition diagram animation
   */
  async playTransitionDiagram(config: TransitionDiagramAnimation): Promise<void> {
    const duration = this.getDuration();

    // Clear canvas
    this.renderer.clear();

    // Determine which states to show
    const allStates: StateConfig[] = [
      { type: config.initialState },
      ...config.transitions.map((t) => ({ type: t })),
    ];

    // Remove duplicates
    const uniqueStates = Array.from(
      new Map(allStates.map((s) => [s.type, s])).values()
    );

    // Layout states in a flow
    const layout = config.layout || 'horizontal';
    const spacing = layout === 'horizontal' ? 180 : 80;
    const stateRefs: Map<string, ElementRef> = new Map();

    let x = 60;
    let y = 100;

    for (const state of uniqueStates) {
      const ref = this.renderer.drawState(state, x, y);
      stateRefs.set(state.type, ref);

      if (layout === 'horizontal') {
        x += spacing;
      } else {
        y += spacing;
      }
    }

    // Draw transition arrows
    const transitionSequence = [config.initialState, ...config.transitions];
    for (let i = 0; i < transitionSequence.length - 1; i++) {
      const fromRef = stateRefs.get(transitionSequence[i]);
      const toRef = stateRefs.get(transitionSequence[i + 1]);

      if (fromRef && toRef) {
        const fromSide = layout === 'horizontal' ? 'right' : 'bottom';
        const toSide = layout === 'horizontal' ? 'left' : 'top';

        const { from, to } = getConnectionPoints(
          fromRef.bounds,
          toRef.bounds,
          fromSide as 'right' | 'left' | 'top' | 'bottom',
          toSide as 'right' | 'left' | 'top' | 'bottom'
        );

        this.renderer.drawArrow({ from, to, style: 'straight' });
      }
    }

    // Animate through transitions
    for (let i = 0; i < transitionSequence.length; i++) {
      const currentState = transitionSequence[i];
      const ref = stateRefs.get(currentState);

      if (ref) {
        await this.renderer.highlight(ref.element as SVGElement, duration);
        await this.delay(duration / 2);
      }
    }

    // If syncing with stack, draw it alongside
    if (config.syncWithStack) {
      const stackX =
        config.syncWithStack.position === 'right'
          ? x + 100
          : config.syncWithStack.position === 'left'
            ? -200
            : 60;
      const stackY = config.syncWithStack.position === 'bottom' ? y + 100 : 60;

      this.addStack(config.syncWithStack.stack, { x: stackX, y: stackY });
    }

    this.emit('animationComplete', { type: 'transitionDiagram' });
  }

  /**
   * Play a branching animation
   */
  async playBranching(config: BranchAnimation): Promise<void> {
    const duration = this.getDuration();

    // Clear canvas
    this.renderer.clear();

    // Draw source stack
    const sourceRef = this.addStack(config.sourceStack, { x: 200, y: 60 });

    await this.delay(duration);

    // Highlight branch point
    await this.highlightState(config.sourceStack.id, config.branchPoint);

    await this.delay(duration / 2);

    // Calculate branch positions
    const branchStartX = 80;
    const branchY = sourceRef.bounds.y + sourceRef.bounds.height + 80;
    const branchSpacing = config.layout?.spacing ?? dimensions.spacing.branchGap;

    // Draw label for branching
    this.renderer.drawLabel('Branches', sourceRef.bounds.x + sourceRef.bounds.width / 2, branchY - 30, {
      anchor: 'middle',
      fontSize: 14,
      fontWeight: '600',
    });

    // Create branch stacks
    let x = branchStartX;
    for (const branch of config.branches) {
      // Create stack config for branch
      const branchStack: StackConfig = {
        id: branch.id,
        label: branch.label || `Branch ${branch.id}`,
        states: [
          ...config.sourceStack.states.slice(0, config.branchPoint + 1),
          ...branch.additionalStates,
        ],
        branchId: branch.id,
        parentStackId: config.sourceStack.id,
      };

      const branchRef = this.renderer.drawStack(branchStack, x, branchY);
      await this.renderer.fadeIn(branchRef.element as SVGElement, duration);

      // Draw connection line from source to branch
      const connectionFrom = {
        x: sourceRef.bounds.x + sourceRef.bounds.width / 2,
        y: sourceRef.bounds.y + sourceRef.bounds.height,
      };
      const connectionTo = {
        x: branchRef.bounds.x + branchRef.bounds.width / 2,
        y: branchRef.bounds.y,
      };

      this.renderer.drawArrow({
        from: connectionFrom,
        to: connectionTo,
        style: 'curved',
        dashArray: dimensions.arrow.dashArray,
      });

      this.stacks.set(branch.id, {
        config: branchStack,
        position: { x, y: branchY },
        ref: branchRef,
        stateRefs: [],
      });

      x += branchRef.bounds.width + branchSpacing;

      await this.delay(duration / 2);

      this.emit('branchCreated', { branchId: branch.id });
    }

    this.emit('animationComplete', { type: 'branching' });
  }

  /**
   * Play a multi-stack interaction animation
   */
  async playMultiStackInteraction(config: MultiStackInteraction): Promise<void> {
    const duration = this.getDuration();
    const childPosition = config.options?.childPosition || 'right';

    // Clear canvas
    this.renderer.clear();

    // Draw parent stack
    const parentRef = this.addStack(config.parentStack, { x: 60, y: 60 });
    const parentStackState = this.stacks.get(config.parentStack.id)!;

    // Calculate stack widths for position calculations
    const parentStackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );
    const childStackWidth = Math.max(
      dimensions.stack.minWidth,
      dimensions.state.width + dimensions.stack.padding * 2
    );

    // Calculate child position
    const childX =
      childPosition === 'right'
        ? parentRef.bounds.x + parentRef.bounds.width + dimensions.spacing.stackGap
        : parentRef.bounds.x;
    const childY =
      childPosition === 'below'
        ? parentRef.bounds.y + parentRef.bounds.height + dimensions.spacing.stackGap
        : parentRef.bounds.y;

    // Draw child stack (initially empty)
    const childStackConfig: StackConfig = {
      ...config.childStack,
      states: [],
    };
    this.addStack(childStackConfig, { x: childX, y: childY });
    const childStackState = this.stacks.get(config.childStack.id)!;

    await this.delay(duration);

    // Animate parent execution steps before AgentCall
    if (config.parentExecution && config.parentExecution.length > 0) {
      if (config.options?.animateParentSteps !== false) {
        for (const state of config.parentExecution) {
          await this.pushState(config.parentStack.id, state);
          await this.delay(duration / 2);
        }
      }
    }

    // Push call state onto parent
    await this.pushState(config.parentStack.id, config.callState);

    // Get AgentCall position for arrow start
    const agentCallIndex = parentStackState.config.states.length - 1;
    const agentCallPos = getStatePositionInStack(
      parentStackState.position.x,
      parentStackState.position.y,
      parentStackWidth,
      parentStackState.config.states.length,
      agentCallIndex
    );

    await this.delay(duration / 2);

    // Push first child state
    if (config.childExecution.length > 0) {
      await this.pushState(config.childStack.id, config.childExecution[0]);
    }

    // Calculate first child state position (it's at the top initially)
    const firstChildStatePos = getStatePositionInStack(
      childStackState.position.x,
      childStackState.position.y,
      childStackWidth,
      1, // Only one state so far
      0
    );

    // Draw arrow from AgentCall to first child state
    const parentToChild = this.renderer.drawArrow({
      from: {
        x: agentCallPos.x + dimensions.state.width,
        y: agentCallPos.y + dimensions.state.height / 2,
      },
      to: {
        x: firstChildStatePos.x,
        y: firstChildStatePos.y + dimensions.state.height / 2,
      },
      style: 'curved',
      animated: true,
    });

    await this.renderer.fadeIn(parentToChild.element as SVGElement, duration / 2);

    // Animate remaining child execution states
    if (config.options?.animateChildSteps !== false && config.childExecution.length > 1) {
      for (let i = 1; i < config.childExecution.length; i++) {
        const state = config.childExecution[i];

        // Calculate where first state will be after this push
        const newFirstStatePos = getStatePositionInStack(
          childStackState.position.x,
          childStackState.position.y,
          childStackWidth,
          childStackState.config.states.length + 1,
          0 // First state stays at index 0
        );

        // Push state and update arrow in parallel
        await Promise.all([
          this.pushState(config.childStack.id, state),
          this.renderer.updateArrowPath(
            parentToChild,
            {
              x: agentCallPos.x + dimensions.state.width,
              y: agentCallPos.y + dimensions.state.height / 2,
            },
            {
              x: newFirstStatePos.x,
              y: newFirstStatePos.y + dimensions.state.height / 2,
            },
            'curved',
            duration / 4
          ),
        ]);

        await this.delay(duration / 2);
      }
    }

    await this.delay(duration / 2);

    // Get the position of the last child state (Finished)
    const lastChildIndex = childStackState.config.states.length - 1;
    const lastChildPos = getStatePositionInStack(
      childStackState.position.x,
      childStackState.position.y,
      childStackWidth,
      childStackState.config.states.length,
      lastChildIndex
    );

    // Calculate where AgentResult will appear on parent stack
    const agentResultPos = getStatePositionInStack(
      parentStackState.position.x,
      parentStackState.position.y,
      parentStackWidth,
      parentStackState.config.states.length + 1, // After result is added
      parentStackState.config.states.length // New top state
    );

    // Draw arrow from last child state (Finished) to where AgentResult will be
    const childToParent = this.renderer.drawArrow({
      from: {
        x: lastChildPos.x,
        y: lastChildPos.y + dimensions.state.height / 2,
      },
      to: {
        x: agentResultPos.x + dimensions.state.width,
        y: agentResultPos.y + dimensions.state.height / 2,
      },
      style: 'curved',
    });

    await this.renderer.fadeIn(childToParent.element as SVGElement, duration / 2);

    // Calculate where AgentCall will move to after result is pushed
    const newAgentCallPos = getStatePositionInStack(
      parentStackState.position.x,
      parentStackState.position.y,
      parentStackWidth,
      parentStackState.config.states.length + 1,
      agentCallIndex
    );

    // Push result onto parent and update parentToChild arrow in parallel
    await Promise.all([
      this.pushState(config.parentStack.id, config.resultState),
      this.renderer.updateArrowPath(
        parentToChild,
        {
          x: newAgentCallPos.x + dimensions.state.width,
          y: newAgentCallPos.y + dimensions.state.height / 2,
        },
        {
          x: firstChildStatePos.x,
          y: getStatePositionInStack(
            childStackState.position.x,
            childStackState.position.y,
            childStackWidth,
            childStackState.config.states.length,
            0
          ).y + dimensions.state.height / 2,
        },
        'curved',
        duration / 4
      ),
    ]);

    // Animate parent completion steps after AgentResult
    if (config.parentCompletion && config.parentCompletion.length > 0) {
      await this.delay(duration / 2);

      // Track indices - AgentResult was just pushed, so it's at the top
      const agentResultIndex = parentStackState.config.states.length - 1;

      // Get final positions of child states (they don't move anymore)
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
        // Calculate new positions after this state is pushed
        const newTotalStates = parentStackState.config.states.length + 1;

        const newAgentCallPos = getStatePositionInStack(
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

        // Push state and update both arrows in parallel
        await Promise.all([
          this.pushState(config.parentStack.id, state),
          this.renderer.updateArrowPath(
            parentToChild,
            {
              x: newAgentCallPos.x + dimensions.state.width,
              y: newAgentCallPos.y + dimensions.state.height / 2,
            },
            {
              x: finalFirstChildPos.x,
              y: finalFirstChildPos.y + dimensions.state.height / 2,
            },
            'curved',
            duration / 4
          ),
          this.renderer.updateArrowPath(
            childToParent,
            {
              x: finalLastChildPos.x,
              y: finalLastChildPos.y + dimensions.state.height / 2,
            },
            {
              x: newAgentResultPos.x + dimensions.state.width,
              y: newAgentResultPos.y + dimensions.state.height / 2,
            },
            'curved',
            duration / 4
          ),
        ]);

        await this.delay(duration / 2);
      }
    }

    this.emit('stackInteraction', {
      parentId: config.parentStack.id,
      childId: config.childStack.id,
    });
    this.emit('animationComplete', { type: 'multiStackInteraction' });
  }

  // ===========================================================================
  // Utility Methods
  // ===========================================================================

  /**
   * Wait for a duration
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Get the renderer (for advanced usage)
   */
  getRenderer(): SVGRenderer {
    return this.renderer;
  }

  /**
   * Clean up resources
   */
  destroy(): void {
    this.stop();
    this.renderer.destroy();
    this.stacks.clear();
    this.eventListeners.clear();
  }
}

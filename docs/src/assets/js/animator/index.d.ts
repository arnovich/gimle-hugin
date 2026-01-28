/**
 * State Machine Animator
 *
 * A library for creating animated visualizations of state machines
 * and interaction stacks, designed for documentation and educational content.
 *
 * @example
 * ```typescript
 * import { StateMachineAnimator } from '@gimle/state-machine-animator';
 *
 * const animator = new StateMachineAnimator({
 *   container: '#animation-container',
 *   theme: 'light',
 * });
 *
 * await animator.playToolExecution({
 *   stack: { id: 'main', label: 'Agent', states: [] },
 *   triggerState: { type: 'ToolCall', label: 'search' },
 *   tool: { id: 'search', name: 'Search', icon: '🔍' },
 *   resultState: { type: 'ToolResult', label: 'Found 10 results' },
 * });
 * ```
 */
export { StateMachineAnimator } from './core/Animator.js';
export { getStateCategory, type StateType, type StateCategory, type StateConfig, type StackConfig, type ToolConfig, type ArtifactConfig, type AnimationConfig, type ThemeConfig, type RendererConfig, type EasingFunction, type EasingPreset, type ToolExecutionAnimation, type ArtifactCreationAnimation, type TransitionDiagramAnimation, type BranchAnimation, type MultiStackInteraction, type AnimatorEvent, type AnimatorEventCallback, type Point, type Rect, type ArrowOptions, type ElementRef, } from './core/types.js';
export { SVGRenderer } from './renderers/SVGRenderer.js';
export { lightTheme, darkTheme, getTheme, getStateColors, categoryLabels, } from './utils/colors.js';
export { linear, easeIn, easeOut, easeInOut, easeInQuad, easeOutQuad, easeInOutQuad, easeInCubic, easeOutCubic, easeInOutCubic, easeInBack, easeOutBack, easeInOutBack, easeOutBounce, easeInBounce, getEasing, easingPresets, } from './utils/easing.js';
export { dimensions } from './utils/layout.js';
//# sourceMappingURL=index.d.ts.map

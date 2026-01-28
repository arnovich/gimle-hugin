/**
 * Core type definitions for the State Machine Animator
 *
 * These types align with the Hugin agent framework's interaction model
 * while providing flexibility for custom visualizations.
 */

// =============================================================================
// State Types
// =============================================================================

/**
 * Standard state types from the Hugin framework.
 * Maps to interaction types in the Python codebase.
 */
export type StateType =
  // Task Interactions
  | 'TaskDefinition'
  | 'TaskResult'
  | 'TaskChain'
  // LLM/Oracle Interactions
  | 'AskOracle'
  | 'OracleResponse'
  // Tool Interactions
  | 'ToolCall'
  | 'ToolResult'
  // Agent Interactions (sub-agents)
  | 'AgentCall'
  | 'AgentResult'
  // Human Interactions
  | 'AskHuman'
  | 'HumanResponse'
  | 'ExternalInput'
  // Control Flow
  | 'Waiting'
  // Generic/custom (for backwards compatibility or custom visualizations)
  | 'Custom';

/**
 * Categories for grouping state types by their nature.
 * Used for color coding and layout grouping.
 */
export type StateCategory =
  | 'llm' // LLM/Oracle interactions (yellow)
  | 'tool' // Tool interactions (blue)
  | 'agent' // Agent/Task interactions (purple)
  | 'user' // User/Human interactions (orange)
  | 'terminal'; // Terminal states (green/gray)

/**
 * Get the category for a state type
 */
export function getStateCategory(type: StateType): StateCategory {
  switch (type) {
    // LLM/Oracle interactions (yellow)
    case 'AskOracle':
    case 'OracleResponse':
      return 'llm';
    // Tool interactions (blue)
    case 'ToolCall':
    case 'ToolResult':
      return 'tool';
    // Agent/Task interactions (purple)
    case 'AgentCall':
    case 'AgentResult':
    case 'TaskDefinition':
    case 'TaskChain':
      return 'agent';
    // Human interactions (orange)
    case 'AskHuman':
    case 'HumanResponse':
    case 'ExternalInput':
      return 'user';
    // Terminal/control states (green)
    case 'TaskResult':
    case 'Waiting':
      return 'terminal';
    default:
      return 'agent'; // Default for custom types
  }
}

// =============================================================================
// State Configuration
// =============================================================================

/**
 * Configuration for a single state in the visualization
 */
export interface StateConfig {
  /** The type of state */
  type: StateType;
  /** Optional display label (defaults to type name) */
  label?: string;
  /** Optional metadata for custom rendering */
  data?: Record<string, unknown>;
  /** Override the default color for this state */
  color?: string;
  /** Optional border color override */
  borderColor?: string;
  /** Unique identifier for this state instance */
  id?: string;
}

// =============================================================================
// Stack Configuration
// =============================================================================

/**
 * Configuration for an interaction stack
 */
export interface StackConfig {
  /** Unique identifier for this stack */
  id: string;
  /** Display label for the stack */
  label?: string;
  /** States in this stack (bottom to top) */
  states: StateConfig[];
  /** Branch identifier (for branched stacks) */
  branchId?: string;
  /** Parent stack ID (for sub-agent stacks) */
  parentStackId?: string;
  /** Optional metadata */
  data?: Record<string, unknown>;
}

// =============================================================================
// Tool Configuration
// =============================================================================

/**
 * Configuration for a tool in the visualization
 */
export interface ToolConfig {
  /** Unique identifier */
  id: string;
  /** Display name */
  name: string;
  /** Optional icon (emoji or URL) */
  icon?: string;
  /** Override color */
  color?: string;
  /** Optional description */
  description?: string;
}

// =============================================================================
// Artifact Configuration
// =============================================================================

/**
 * Configuration for an artifact in the visualization.
 * Artifacts are external outputs created by tool calls (e.g., PDF documents, files).
 */
export interface ArtifactConfig {
  /** Unique identifier */
  id: string;
  /** Display name */
  name: string;
  /** Artifact type (for icon selection) */
  type?: 'document' | 'image' | 'data' | 'code' | 'generic';
  /** Optional icon (emoji or URL) */
  icon?: string;
  /** Override color */
  color?: string;
  /** Optional file extension to display */
  extension?: string;
}

// =============================================================================
// Animation Configuration
// =============================================================================

/**
 * Easing function type
 */
export type EasingFunction = (t: number) => number;

/**
 * Named easing presets
 */
export type EasingPreset =
  | 'linear'
  | 'easeIn'
  | 'easeOut'
  | 'easeInOut'
  | 'easeInQuad'
  | 'easeOutQuad'
  | 'easeInOutQuad'
  | 'easeInCubic'
  | 'easeOutCubic'
  | 'easeInOutCubic'
  | 'easeInBack'
  | 'easeOutBack'
  | 'easeInOutBack';

/**
 * Configuration for individual animations
 */
export interface AnimationConfig {
  /** Duration in milliseconds (default: 500) */
  duration?: number;
  /** Easing function or preset name */
  easing?: EasingFunction | EasingPreset;
  /** Delay before starting (ms) */
  delay?: number;
  /** Callback when animation starts */
  onStart?: () => void;
  /** Callback when animation completes */
  onComplete?: () => void;
}

// =============================================================================
// Theme Configuration
// =============================================================================

/**
 * Color configuration for state categories
 */
export interface StateCategoryColors {
  /** Background color */
  background: string;
  /** Border color */
  border: string;
  /** Text color (optional, defaults to theme text color) */
  text?: string;
}

/**
 * Full theme configuration
 */
export interface ThemeConfig {
  /** Canvas/SVG background */
  background: string;
  /** Colors for each state category */
  stateColors: Record<StateCategory, StateCategoryColors>;
  /** Default text color */
  textColor: string;
  /** Arrow/connector color */
  arrowColor: string;
  /** Stack container background */
  stackBackground: string;
  /** Stack border color */
  stackBorderColor: string;
  /** Tool box color */
  toolColor: string;
  /** Tool box border */
  toolBorderColor: string;
  /** Font family */
  fontFamily: string;
}

// =============================================================================
// Renderer Configuration
// =============================================================================

/**
 * Configuration for the renderer
 */
export interface RendererConfig {
  /** Container element or CSS selector */
  container: HTMLElement | string;
  /** Canvas width (default: auto) */
  width?: number;
  /** Canvas height (default: auto) */
  height?: number;
  /** Theme preset or custom config */
  theme?: 'light' | 'dark' | ThemeConfig;
  /** Enable responsive sizing */
  responsive?: boolean;
  /** Padding inside the canvas */
  padding?: number;
}

// =============================================================================
// Animation Types
// =============================================================================

/**
 * Configuration for tool execution animation
 */
export interface ToolExecutionAnimation {
  /** The stack receiving the states */
  stack: StackConfig;
  /** States to push before the tool call */
  preStates?: StateConfig[];
  /** The state that triggers the tool call */
  triggerState: StateConfig;
  /** The tool being executed */
  tool: ToolConfig;
  /** The result state pushed after execution */
  resultState: StateConfig;
  /** States to push after the tool result */
  postStates?: StateConfig[];
  /** Animation options */
  options?: {
    /** Show tool name/icon */
    showToolDetails?: boolean;
    /** How long tool "runs" in ms */
    executionDuration?: number;
    /** Arrow style */
    arrowStyle?: 'straight' | 'curved' | 'stepped';
  };
}

/**
 * Configuration for artifact creation animation.
 * Shows a tool call creating an external artifact that stays attached to the interaction.
 */
export interface ArtifactCreationAnimation {
  /** The stack receiving the states */
  stack: StackConfig;
  /** States to push before the artifact-creating tool call */
  preStates?: StateConfig[];
  /** The state that creates the artifact (typically a ToolCall) */
  creatorState: StateConfig;
  /** The artifact being created */
  artifact: ArtifactConfig;
  /** The result state pushed after creation */
  resultState: StateConfig;
  /** States to push after the artifact is created */
  postStates?: StateConfig[];
  /** Animation options */
  options?: {
    /** Position of artifact relative to stack */
    artifactPosition?: 'right' | 'left';
    /** Arrow style */
    arrowStyle?: 'straight' | 'curved' | 'stepped';
  };
}

/**
 * Configuration for state transition diagram animation
 */
export interface TransitionDiagramAnimation {
  /** Which states to show */
  visibleStates?: StateType[] | 'all';
  /** Starting state */
  initialState: StateType;
  /** Sequence of transitions to animate */
  transitions: StateType[];
  /** Sync with a stack view */
  syncWithStack?: {
    stack: StackConfig;
    position: 'left' | 'right' | 'bottom';
  };
  /** Layout style */
  layout?: 'horizontal' | 'vertical' | 'circular';
}

/**
 * Configuration for branching animation
 */
export interface BranchAnimation {
  /** Original stack before branching */
  sourceStack: StackConfig;
  /** Point at which branching occurs (index in stack) */
  branchPoint: number;
  /** The branched stacks */
  branches: Array<{
    id: string;
    label?: string;
    additionalStates: StateConfig[];
  }>;
  /** Layout options */
  layout?: {
    direction: 'horizontal' | 'vertical';
    spacing: number;
  };
}

/**
 * Configuration for multi-stack interaction animation
 */
export interface MultiStackInteraction {
  /** The initiating stack (parent agent) */
  parentStack: StackConfig;
  /** The receiving stack (sub-agent) */
  childStack: StackConfig;
  /** States to push on parent before the AgentCall */
  parentExecution?: StateConfig[];
  /** The call state on parent (AgentCall) */
  callState: StateConfig;
  /** States that execute on child */
  childExecution: StateConfig[];
  /** The result returned to parent */
  resultState: StateConfig;
  /** States to push on parent after the AgentResult */
  parentCompletion?: StateConfig[];
  /** Visual options */
  options?: {
    /** Show message content */
    showMessageContent?: boolean;
    /** Child stack position */
    childPosition?: 'right' | 'below';
    /** Animate each child step or just result */
    animateChildSteps?: boolean;
    /** Animate parent steps before AgentCall */
    animateParentSteps?: boolean;
  };
}

// =============================================================================
// Event Types
// =============================================================================

/**
 * Events emitted by the animator
 */
export type AnimatorEvent =
  | 'animationStart'
  | 'animationComplete'
  | 'animationStep'
  | 'stateChange'
  | 'branchCreated'
  | 'stackInteraction'
  | 'error';

/**
 * Event callback signature
 */
export type AnimatorEventCallback = (data?: unknown) => void;

// =============================================================================
// Geometry Types
// =============================================================================

/**
 * 2D point
 */
export interface Point {
  x: number;
  y: number;
}

/**
 * Rectangle bounds
 */
export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Arrow connection options
 */
export interface ArrowOptions {
  /** Start point */
  from: Point;
  /** End point */
  to: Point;
  /** Arrow style */
  style?: 'straight' | 'curved' | 'stepped';
  /** Show arrowhead */
  showHead?: boolean;
  /** Stroke width */
  strokeWidth?: number;
  /** Color */
  color?: string;
  /** Dash pattern (for "in progress" arrows) */
  dashArray?: string;
  /** Animation style */
  animated?: boolean;
  /** Start hidden (opacity 0) */
  hidden?: boolean;
}

// =============================================================================
// Visual Element References
// =============================================================================

/**
 * Reference to a rendered element
 */
export interface ElementRef {
  /** Element type */
  type: 'state' | 'stack' | 'tool' | 'artifact' | 'arrow' | 'label';
  /** Unique ID */
  id: string;
  /** DOM/SVG element */
  element: SVGElement | HTMLElement;
  /** Bounding box */
  bounds: Rect;
  /** Child element refs (e.g., state refs within a stack) */
  childRefs?: ElementRef[];
}

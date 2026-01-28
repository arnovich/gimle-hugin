/**
 * Color schemes and theme definitions
 *
 * These colors match Erik's Funhouse blog styling for state machine diagrams.
 * The design is flat with colored backgrounds and slightly darker borders.
 */

import type { ThemeConfig, StateCategory, StateConfig } from '../core/types.js';
import { getStateCategory } from '../core/types.js';

/**
 * Light theme - matches Erik's Funhouse blog styling
 *
 * Colors from the state machine diagrams:
 * - Yellow for LLM interactions
 * - Blue for Tool interactions
 * - Pink/Salmon for User interactions
 * - Lavender for Agent interactions
 * - Green for Terminal/Finished states
 */
export const lightTheme: ThemeConfig = {
  background: '#ffffff',

  stateColors: {
    // Yellow - LLM interactions (UserMessage, AssistantMessage)
    llm: {
      background: '#FFE082',
      border: '#E6C200',
      text: '#000000',
    },
    // Blue - Tool interactions (ToolCall, ToolResult)
    tool: {
      background: '#90CAF9',
      border: '#5BA3E0',
      text: '#000000',
    },
    // Lavender/Purple - Agent interactions (AgentCall, AgentResult)
    agent: {
      background: '#D1C4E9',
      border: '#A094C0',
      text: '#000000',
    },
    // Pink/Salmon - User interactions (UserInputRequired, UserResponse)
    user: {
      background: '#FFCDD2',
      border: '#E0A0A5',
      text: '#000000',
    },
    // Green - Terminal states (Finished)
    terminal: {
      background: '#A5D6A7',
      border: '#70B873',
      text: '#000000',
    },
  },

  textColor: '#000000',
  arrowColor: '#424242',
  stackBackground: 'transparent',
  stackBorderColor: 'transparent',
  // Orange/Peach for "execution" boxes (Tool Execution, LLM Call, etc.)
  toolColor: '#FFCC80',
  toolBorderColor: '#E6A550',
  fontFamily:
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif",
};

/**
 * Dark theme for dark mode contexts
 */
export const darkTheme: ThemeConfig = {
  background: '#1a1a2e',

  stateColors: {
    // Yellow - LLM/Oracle interactions
    llm: {
      background: '#3d3d00',
      border: '#fbc02d',
      text: '#fff9c4',
    },
    // Blue - Tool interactions
    tool: {
      background: '#0d2137',
      border: '#5dade2',
      text: '#e3f2fd',
    },
    // Purple - Agent/Task interactions
    agent: {
      background: '#2d1f3d',
      border: '#bb8fce',
      text: '#f3e5f5',
    },
    // Orange - User/Human interactions
    user: {
      background: '#3d2600',
      border: '#f5b041',
      text: '#fff3e0',
    },
    // Green/Gray - Terminal states
    terminal: {
      background: '#1a3d1f',
      border: '#58d68d',
      text: '#e8f5e9',
    },
  },

  textColor: '#eaecee',
  arrowColor: '#5dade2',
  stackBackground: '#2d2d44',
  stackBorderColor: '#3d3d5c',
  toolColor: '#1a2f3d',
  toolBorderColor: '#5dade2',
  fontFamily:
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif",
};

/**
 * Get theme by name or return custom theme
 */
export function getTheme(theme: 'light' | 'dark' | ThemeConfig): ThemeConfig {
  if (theme === 'light') return lightTheme;
  if (theme === 'dark') return darkTheme;
  return theme;
}

/**
 * Get colors for a state based on its type and theme
 */
export function getStateColors(
  state: StateConfig,
  theme: ThemeConfig
): { background: string; border: string; text: string } {
  // Allow per-state color overrides
  if (state.color || state.borderColor) {
    return {
      background: state.color || theme.stateColors.agent.background,
      border: state.borderColor || state.color || theme.stateColors.agent.border,
      text: theme.textColor,
    };
  }

  const category = getStateCategory(state.type);
  const colors = theme.stateColors[category];

  return {
    background: colors.background,
    border: colors.border,
    text: colors.text || theme.textColor,
  };
}

/**
 * Lighten a hex color by a percentage
 */
export function lighten(hex: string, percent: number): string {
  const num = parseInt(hex.replace('#', ''), 16);
  const amt = Math.round(2.55 * percent);
  const R = Math.min(255, (num >> 16) + amt);
  const G = Math.min(255, ((num >> 8) & 0x00ff) + amt);
  const B = Math.min(255, (num & 0x0000ff) + amt);
  return `#${((1 << 24) | (R << 16) | (G << 8) | B).toString(16).slice(1)}`;
}

/**
 * Darken a hex color by a percentage
 */
export function darken(hex: string, percent: number): string {
  const num = parseInt(hex.replace('#', ''), 16);
  const amt = Math.round(2.55 * percent);
  const R = Math.max(0, (num >> 16) - amt);
  const G = Math.max(0, ((num >> 8) & 0x00ff) - amt);
  const B = Math.max(0, (num & 0x0000ff) - amt);
  return `#${((1 << 24) | (R << 16) | (G << 8) | B).toString(16).slice(1)}`;
}

/**
 * Add transparency to a hex color
 */
export function withAlpha(hex: string, alpha: number): string {
  const num = parseInt(hex.replace('#', ''), 16);
  const R = num >> 16;
  const G = (num >> 8) & 0x00ff;
  const B = num & 0x0000ff;
  return `rgba(${R}, ${G}, ${B}, ${alpha})`;
}

/**
 * Category labels for legend/documentation
 */
export const categoryLabels: Record<StateCategory, string> = {
  llm: 'LLM Interaction',
  tool: 'Tool Execution',
  agent: 'Agent/Task',
  user: 'User Input',
  terminal: 'Terminal',
};

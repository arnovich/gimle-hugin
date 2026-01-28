/**
 * Color schemes and theme definitions
 *
 * These colors match Erik's Funhouse blog styling for state machine diagrams.
 * The design is flat with colored backgrounds and slightly darker borders.
 */
import type { ThemeConfig, StateCategory, StateConfig } from '../core/types.js';
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
export declare const lightTheme: ThemeConfig;
/**
 * Dark theme for dark mode contexts
 */
export declare const darkTheme: ThemeConfig;
/**
 * Get theme by name or return custom theme
 */
export declare function getTheme(theme: 'light' | 'dark' | ThemeConfig): ThemeConfig;
/**
 * Get colors for a state based on its type and theme
 */
export declare function getStateColors(state: StateConfig, theme: ThemeConfig): {
    background: string;
    border: string;
    text: string;
};
/**
 * Lighten a hex color by a percentage
 */
export declare function lighten(hex: string, percent: number): string;
/**
 * Darken a hex color by a percentage
 */
export declare function darken(hex: string, percent: number): string;
/**
 * Add transparency to a hex color
 */
export declare function withAlpha(hex: string, alpha: number): string;
/**
 * Category labels for legend/documentation
 */
export declare const categoryLabels: Record<StateCategory, string>;
//# sourceMappingURL=colors.d.ts.map

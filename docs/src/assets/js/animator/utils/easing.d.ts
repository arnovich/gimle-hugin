/**
 * Easing functions for smooth animations
 *
 * All functions take a progress value t in [0, 1] and return
 * a transformed value, also typically in [0, 1].
 */
import type { EasingFunction, EasingPreset } from '../core/types.js';
/**
 * Linear - no easing
 */
export declare const linear: EasingFunction;
/**
 * Quadratic easing
 */
export declare const easeInQuad: EasingFunction;
export declare const easeOutQuad: EasingFunction;
export declare const easeInOutQuad: EasingFunction;
/**
 * Cubic easing
 */
export declare const easeInCubic: EasingFunction;
export declare const easeOutCubic: EasingFunction;
export declare const easeInOutCubic: EasingFunction;
/**
 * Quartic easing
 */
export declare const easeInQuart: EasingFunction;
export declare const easeOutQuart: EasingFunction;
export declare const easeInOutQuart: EasingFunction;
export declare const easeInBack: EasingFunction;
export declare const easeOutBack: EasingFunction;
export declare const easeInOutBack: EasingFunction;
export declare const easeInElastic: EasingFunction;
export declare const easeOutElastic: EasingFunction;
export declare const easeInOutElastic: EasingFunction;
/**
 * Bounce easing
 */
export declare const easeOutBounce: EasingFunction;
export declare const easeInBounce: EasingFunction;
export declare const easeInOutBounce: EasingFunction;
/**
 * Aliases for common easing names
 */
export declare const easeIn: EasingFunction;
export declare const easeOut: EasingFunction;
export declare const easeInOut: EasingFunction;
/**
 * Map of preset names to functions
 */
export declare const easingPresets: Record<EasingPreset, EasingFunction>;
/**
 * Get an easing function from a preset name or function
 */
export declare function getEasing(easing: EasingFunction | EasingPreset | undefined): EasingFunction;
//# sourceMappingURL=easing.d.ts.map
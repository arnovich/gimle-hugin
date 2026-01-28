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
export const linear: EasingFunction = (t) => t;

/**
 * Quadratic easing
 */
export const easeInQuad: EasingFunction = (t) => t * t;
export const easeOutQuad: EasingFunction = (t) => t * (2 - t);
export const easeInOutQuad: EasingFunction = (t) =>
  t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;

/**
 * Cubic easing
 */
export const easeInCubic: EasingFunction = (t) => t * t * t;
export const easeOutCubic: EasingFunction = (t) => --t * t * t + 1;
export const easeInOutCubic: EasingFunction = (t) =>
  t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1;

/**
 * Quartic easing
 */
export const easeInQuart: EasingFunction = (t) => t * t * t * t;
export const easeOutQuart: EasingFunction = (t) => 1 - --t * t * t * t;
export const easeInOutQuart: EasingFunction = (t) =>
  t < 0.5 ? 8 * t * t * t * t : 1 - 8 * --t * t * t * t;

/**
 * Back easing - slight overshoot
 */
const c1 = 1.70158;
const c2 = c1 * 1.525;
const c3 = c1 + 1;

export const easeInBack: EasingFunction = (t) => c3 * t * t * t - c1 * t * t;
export const easeOutBack: EasingFunction = (t) =>
  1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
export const easeInOutBack: EasingFunction = (t) =>
  t < 0.5
    ? (Math.pow(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2
    : (Math.pow(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2;

/**
 * Elastic easing - springy effect
 */
const c4 = (2 * Math.PI) / 3;
const c5 = (2 * Math.PI) / 4.5;

export const easeInElastic: EasingFunction = (t) =>
  t === 0
    ? 0
    : t === 1
      ? 1
      : -Math.pow(2, 10 * t - 10) * Math.sin((t * 10 - 10.75) * c4);

export const easeOutElastic: EasingFunction = (t) =>
  t === 0
    ? 0
    : t === 1
      ? 1
      : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;

export const easeInOutElastic: EasingFunction = (t) =>
  t === 0
    ? 0
    : t === 1
      ? 1
      : t < 0.5
        ? -(Math.pow(2, 20 * t - 10) * Math.sin((20 * t - 11.125) * c5)) / 2
        : (Math.pow(2, -20 * t + 10) * Math.sin((20 * t - 11.125) * c5)) / 2 +
          1;

/**
 * Bounce easing
 */
export const easeOutBounce: EasingFunction = (t) => {
  const n1 = 7.5625;
  const d1 = 2.75;

  if (t < 1 / d1) {
    return n1 * t * t;
  } else if (t < 2 / d1) {
    return n1 * (t -= 1.5 / d1) * t + 0.75;
  } else if (t < 2.5 / d1) {
    return n1 * (t -= 2.25 / d1) * t + 0.9375;
  } else {
    return n1 * (t -= 2.625 / d1) * t + 0.984375;
  }
};

export const easeInBounce: EasingFunction = (t) => 1 - easeOutBounce(1 - t);
export const easeInOutBounce: EasingFunction = (t) =>
  t < 0.5
    ? (1 - easeOutBounce(1 - 2 * t)) / 2
    : (1 + easeOutBounce(2 * t - 1)) / 2;

/**
 * Aliases for common easing names
 */
export const easeIn = easeInCubic;
export const easeOut = easeOutCubic;
export const easeInOut = easeInOutCubic;

/**
 * Map of preset names to functions
 */
export const easingPresets: Record<EasingPreset, EasingFunction> = {
  linear,
  easeIn,
  easeOut,
  easeInOut,
  easeInQuad,
  easeOutQuad,
  easeInOutQuad,
  easeInCubic,
  easeOutCubic,
  easeInOutCubic,
  easeInBack,
  easeOutBack,
  easeInOutBack,
};

/**
 * Get an easing function from a preset name or function
 */
export function getEasing(
  easing: EasingFunction | EasingPreset | undefined
): EasingFunction {
  if (typeof easing === 'function') {
    return easing;
  }
  if (typeof easing === 'string' && easing in easingPresets) {
    return easingPresets[easing];
  }
  return easeInOutCubic; // Default
}

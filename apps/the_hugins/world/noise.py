"""Self-contained 2D Perlin noise for terrain generation."""

import math
import random
from typing import List, Tuple


def _generate_gradients(
    seed: int, size: int = 256
) -> List[Tuple[float, float]]:
    """Generate a table of random unit gradient vectors."""
    rng = random.Random(seed)
    gradients = []
    for _ in range(size):
        angle = rng.uniform(0, 2 * math.pi)
        gradients.append((math.cos(angle), math.sin(angle)))
    return gradients


def _fade(t: float) -> float:
    """Smoothstep fade curve: 6t^5 - 15t^4 + 10t^3."""
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation."""
    return a + t * (b - a)


def _dot_grid_gradient(
    gradients: List[Tuple[float, float]],
    perm: List[int],
    ix: int,
    iy: int,
    x: float,
    y: float,
) -> float:
    """Compute dot product of distance and gradient vectors."""
    # Hash grid coordinates to get gradient index
    idx = perm[(perm[ix % 256] + iy) % 256] % len(gradients)
    gx, gy = gradients[idx]
    dx = x - ix
    dy = y - iy
    return dx * gx + dy * gy


def perlin_2d(
    x: float,
    y: float,
    gradients: List[Tuple[float, float]],
    perm: List[int],
) -> float:
    """Compute 2D Perlin noise at (x, y).

    Returns a value roughly in [-1, 1].
    """
    # Grid cell coordinates
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    x1 = x0 + 1
    y1 = y0 + 1

    # Interpolation weights
    sx = _fade(x - x0)
    sy = _fade(y - y0)

    # Dot products at corners
    n00 = _dot_grid_gradient(gradients, perm, x0, y0, x, y)
    n10 = _dot_grid_gradient(gradients, perm, x1, y0, x, y)
    n01 = _dot_grid_gradient(gradients, perm, x0, y1, x, y)
    n11 = _dot_grid_gradient(gradients, perm, x1, y1, x, y)

    # Bilinear interpolation
    ix0 = _lerp(n00, n10, sx)
    ix1 = _lerp(n01, n11, sx)
    return _lerp(ix0, ix1, sy)


def fractal_noise(
    x: float,
    y: float,
    octaves: int,
    gradients: List[Tuple[float, float]],
    perm: List[int],
    lacunarity: float = 2.0,
    persistence: float = 0.5,
) -> float:
    """Multi-octave fractal noise for natural-looking terrain.

    Args:
        x, y: World coordinates (will be scaled internally)
        octaves: Number of noise layers to combine
        gradients: Precomputed gradient table
        perm: Permutation table
        lacunarity: Frequency multiplier per octave
        persistence: Amplitude multiplier per octave

    Returns:
        Noise value roughly in [-1, 1].
    """
    value = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_amplitude = 0.0

    for _ in range(octaves):
        value += amplitude * perlin_2d(
            x * frequency, y * frequency, gradients, perm
        )
        max_amplitude += amplitude
        amplitude *= persistence
        frequency *= lacunarity

    # Normalize to [-1, 1]
    if max_amplitude > 0:
        value /= max_amplitude
    return value


def make_noise_context(
    seed: int,
) -> Tuple[List[Tuple[float, float]], List[int]]:
    """Create gradient and permutation tables for a given seed.

    Returns (gradients, perm) tuple to pass to noise functions.
    """
    gradients = _generate_gradients(seed)
    rng = random.Random(seed + 1)
    perm = list(range(256))
    rng.shuffle(perm)
    return gradients, perm

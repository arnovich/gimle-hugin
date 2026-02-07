// World visualization JavaScript
// Extracted from html_renderer.py for maintainability
//
// Table of Contents:
//   1. Utilities & Config ............... ~line 5
//   2. Ambient Particles ................ ~line 100
//   3. Action Effects ................... ~line 155
//   4. Day/Night Cycle .................. ~line 240
//   5. Main Render (drawWorld) .......... ~line 303
//   6. Minimap .......................... ~line 438
//   7. Terrain Rendering ................ ~line 573
//   8. Decoration Rendering ............. ~line 890
//   9. Structure Rendering .............. ~line 1017
//  10. Item Rendering ................... ~line 1213
//  11. Creature Rendering ............... ~line 1456
//  12. Speech Bubbles ................... ~line 1590
//  13. Drag & Drop ...................... ~line 1670
//  14. Sidebar & Creatures List ......... ~line 1846
//  15. World Update & API ............... ~line 1936
//  16. Action Log Filtering ............. ~line 2206
//  17. Animation Loop ................... ~line 2332
//  18. Interaction & Modals ............. ~line 2385
//  19. Keyboard Controls ................ ~line 2524
//  20. Initialization ................... ~line 2654

// ============================================================
// 1. Utilities & Config
// ============================================================

// HTML escaping to prevent XSS from LLM-generated content
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

const canvas = document.getElementById('worldCanvas');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');

// Configuration from server-side data
const TILE_SIZE = window.WORLD_DATA.tileSize;
const CANVAS_WIDTH = window.WORLD_DATA.canvasWidth;
const CANVAS_HEIGHT = window.WORLD_DATA.canvasHeight;

// World data
const cells = window.WORLD_DATA.cells;
let creatures = window.WORLD_DATA.creatures;
const items = window.WORLD_DATA.items;

// Sprite paths
const spritePaths = window.WORLD_DATA.spritePaths;
const useSprites = window.WORLD_DATA.useSprites;

// Preload sprites with error handling
const spriteImages = {};
const spriteLoadPromises = [];
if (useSprites) {
    for (let key in spritePaths) {
        const img = new Image();
        const promise = new Promise((resolve, reject) => {
            img.onload = () => {
                console.log('Sprite loaded:', key, spritePaths[key]);
                resolve(img);
            };
            img.onerror = (error) => {
                console.warn('Sprite failed to load:', key, spritePaths[key], error);
                // Don't reject, just mark as failed
                spriteImages[key] = null;
                resolve(null);
            };
        });
        img.src = spritePaths[key];
        spriteImages[key] = img;
        spriteLoadPromises.push(promise);
    }
}

let viewOffsetX = 0;
let viewOffsetY = 0;
let updateInterval = null;
let currentUpdateSpeed = 1.0; // seconds
let worldTick = window.WORLD_DATA.worldTick;
// View center in world coordinates (used for positioning)
let viewCenterX = window.WORLD_DATA.viewCenterX;
let viewCenterY = window.WORLD_DATA.viewCenterY;
// Zoom state
let zoomLevel = 1.0;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3.0;
const ZOOM_STEP = 0.1;

// Keyboard navigation state
const PAN_SPEED = 30;  // Pixels per key press
const PAN_SPEED_FAST = 80;  // Pixels when holding shift
const ZOOM_KEY_STEP = 0.15;  // Zoom step for keyboard
const keysPressed = new Set();  // Track held keys for smooth movement
let keyboardPanInterval = null;
const viewStartX = window.WORLD_DATA.viewStartX;
const viewStartY = window.WORLD_DATA.viewStartY;
const worldWidth = window.WORLD_DATA.worldWidth;
const worldHeight = window.WORLD_DATA.worldHeight;

// Creature color cache (preserves server-assigned colors across updates)
const creatureColors = {};
creatures.forEach(c => { creatureColors[c.name] = c.color; });

// Interaction state
let selectedCreature = null;
let isSimulationPaused = false;

// Animation state for creatures
const creatureAnimations = {}; // agent_id -> {startX, startY, targetX, targetY, progress, duration}
let animationFrameId = null;

// Creature footprint trails (last 5 screen positions per creature)
const creatureFootprints = {}; // agent_id -> [{x, y, time}]
const MAX_FOOTPRINTS = 5;
const FOOTPRINT_FADE_MS = 8000; // Footprints fade over 8 seconds

// Ambient particle system (floating dust motes / fireflies)
const particles = [];
const MAX_PARTICLES = 25;
let particlesInitialized = false;

// ============================================================
// 2. Ambient Particles
// ============================================================

function initParticles() {
    if (particlesInitialized) return;
    for (let i = 0; i < MAX_PARTICLES; i++) {
        particles.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            vx: (Math.random() - 0.5) * 0.3,
            vy: (Math.random() - 0.5) * 0.3,
            size: 1 + Math.random() * 2,
            alpha: 0.2 + Math.random() * 0.4,
            phase: Math.random() * Math.PI * 2,
            speed: 1.5 + Math.random() * 1.5
        });
    }
    particlesInitialized = true;
}

function updateParticles() {
    particles.forEach(p => {
        p.x += p.vx;
        p.y += p.vy;
        p.phase += 0.02;

        // Wrap around screen edges
        if (p.x < -10) p.x = canvas.width + 10;
        if (p.x > canvas.width + 10) p.x = -10;
        if (p.y < -10) p.y = canvas.height + 10;
        if (p.y > canvas.height + 10) p.y = -10;

        // Slowly change direction
        p.vx += (Math.random() - 0.5) * 0.01;
        p.vy += (Math.random() - 0.5) * 0.01;
        p.vx = Math.max(-0.5, Math.min(0.5, p.vx));
        p.vy = Math.max(-0.5, Math.min(0.5, p.vy));
    });
}

function drawParticles() {
    const time = performance.now() / 1000;
    particles.forEach(p => {
        const flicker = 0.5 + Math.sin(time * p.speed + p.phase) * 0.5;
        const alpha = p.alpha * flicker;
        ctx.fillStyle = `rgba(255, 255, 220, ${alpha})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * flicker, 0, Math.PI * 2);
        ctx.fill();

        // Subtle glow
        ctx.fillStyle = `rgba(255, 255, 200, ${alpha * 0.3})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * 2 * flicker, 0, Math.PI * 2);
        ctx.fill();
    });
}

// Action visual effects system
// ============================================================
// 3. Action Effects
// ============================================================

const actionEffects = [];
const seenActions = new Set(); // Track which actions we've already processed

function addActionEffect(x, y, actionType) {
    const effect = {
        x: x,
        y: y,
        type: actionType,
        startTime: performance.now(),
        duration: 600,
        particles: []
    };

    // Create particles based on action type
    const numParticles = actionType === 'say' || actionType === 'talk_to' ? 5 : 8;
    for (let i = 0; i < numParticles; i++) {
        effect.particles.push({
            offsetX: (Math.random() - 0.5) * 20,
            offsetY: Math.random() * -10,
            vx: (Math.random() - 0.5) * 2,
            vy: actionType === 'drop' ? Math.random() * 2 : -Math.random() * 3 - 1,
            size: 2 + Math.random() * 3,
            rotation: Math.random() * Math.PI * 2
        });
    }

    actionEffects.push(effect);
}

function updateAndDrawActionEffects() {
    const now = performance.now();

    for (let i = actionEffects.length - 1; i >= 0; i--) {
        const effect = actionEffects[i];
        const elapsed = now - effect.startTime;
        const progress = elapsed / effect.duration;

        if (progress >= 1) {
            actionEffects.splice(i, 1);
            continue;
        }

        const alpha = 1 - progress;

        effect.particles.forEach(p => {
            const px = effect.x + p.offsetX + p.vx * elapsed * 0.01;
            const py = effect.y + p.offsetY + p.vy * elapsed * 0.01;

            if (effect.type === 'take') {
                // Rising sparkles (golden)
                ctx.fillStyle = `rgba(255, 215, 0, ${alpha})`;
                ctx.beginPath();
                ctx.moveTo(px, py - p.size);
                ctx.lineTo(px + p.size * 0.3, py);
                ctx.lineTo(px, py + p.size);
                ctx.lineTo(px - p.size * 0.3, py);
                ctx.closePath();
                ctx.fill();
            } else if (effect.type === 'drop') {
                // Falling particles (brown/dust)
                ctx.fillStyle = `rgba(139, 90, 43, ${alpha * 0.7})`;
                ctx.beginPath();
                ctx.arc(px, py, p.size * 0.7, 0, Math.PI * 2);
                ctx.fill();
            } else if (effect.type === 'say' || effect.type === 'talk_to') {
                // Speech particles (hearts/stars)
                ctx.fillStyle = `rgba(255, 105, 180, ${alpha})`;
                // Draw small heart
                ctx.beginPath();
                ctx.moveTo(px, py + p.size * 0.5);
                ctx.bezierCurveTo(px - p.size, py - p.size * 0.5, px - p.size, py - p.size, px, py - p.size * 0.3);
                ctx.bezierCurveTo(px + p.size, py - p.size, px + p.size, py - p.size * 0.5, px, py + p.size * 0.5);
                ctx.fill();
            } else {
                // Default: white sparkles
                ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
                ctx.beginPath();
                ctx.arc(px, py, p.size, 0, Math.PI * 2);
                ctx.fill();
            }
        });
    }
}

// Draw functions
// ============================================================
// 4. Day/Night Cycle
// ============================================================
// One full day-night cycle every 400 ticks
const DAY_CYCLE_LENGTH = 400;

function getDayPhase(tick) {
    const phase = (tick % DAY_CYCLE_LENGTH) / DAY_CYCLE_LENGTH; // 0..1
    // 0.0-0.2 = dawn, 0.2-0.5 = day, 0.5-0.7 = dusk, 0.7-1.0 = night
    return phase;
}

function getSkyColors(phase) {
    if (phase < 0.15) {
        // Dawn: dark blue -> warm orange
        const t = phase / 0.15;
        return {
            top: lerpColor('#1a1a3e', '#ff8c42', t),
            bottom: lerpColor('#2c2c5e', '#ffc97e', t),
            overlay: `rgba(255, 140, 60, ${0.08 * (1 - t)})`,
            ambientAlpha: 0.15 * (1 - t)
        };
    } else if (phase < 0.5) {
        // Day: clear sky
        const t = Math.min(1, (phase - 0.15) / 0.1);
        return {
            top: lerpColor('#ff8c42', '#5DADE2', t),
            bottom: lerpColor('#ffc97e', '#AED6F1', t),
            overlay: 'rgba(0, 0, 0, 0)',
            ambientAlpha: 0
        };
    } else if (phase < 0.65) {
        // Dusk: clear -> purple/orange
        const t = (phase - 0.5) / 0.15;
        return {
            top: lerpColor('#5DADE2', '#8e44ad', t),
            bottom: lerpColor('#AED6F1', '#e67e22', t),
            overlay: `rgba(180, 80, 40, ${0.06 * t})`,
            ambientAlpha: 0.05 * t
        };
    } else {
        // Night: dark blue
        const t = Math.min(1, (phase - 0.65) / 0.1);
        return {
            top: lerpColor('#8e44ad', '#0d1b2a', t),
            bottom: lerpColor('#e67e22', '#1b2838', t),
            overlay: `rgba(10, 20, 50, ${0.25 * t})`,
            ambientAlpha: 0.25 * t
        };
    }
}

function lerpColor(c1, c2, t) {
    const r1 = parseInt(c1.slice(1, 3), 16);
    const g1 = parseInt(c1.slice(3, 5), 16);
    const b1 = parseInt(c1.slice(5, 7), 16);
    const r2 = parseInt(c2.slice(1, 3), 16);
    const g2 = parseInt(c2.slice(3, 5), 16);
    const b2 = parseInt(c2.slice(5, 7), 16);
    const r = Math.round(r1 + (r2 - r1) * t);
    const g = Math.round(g1 + (g2 - g1) * t);
    const b = Math.round(b1 + (b2 - b1) * t);
    return `rgb(${r}, ${g}, ${b})`;
}

// ============================================================
// 5. Main Render (drawWorld)
// ============================================================

function drawWorld() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw sky background with day/night cycle
    const dayPhase = getDayPhase(worldTick);
    const sky = getSkyColors(dayPhase);
    const skyGradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    skyGradient.addColorStop(0, sky.top);
    skyGradient.addColorStop(1, sky.bottom);
    ctx.fillStyle = skyGradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Initialize and draw ambient particles (before zoom transform)
    initParticles();
    updateParticles();
    drawParticles();

    // Save context and apply zoom transformation
    ctx.save();

    // Apply zoom from center of canvas
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    ctx.translate(centerX, centerY);
    ctx.scale(zoomLevel, zoomLevel);
    ctx.translate(-centerX, -centerY);

    // Draw terrain (sorted by y for proper layering)
    const sortedCells = [...cells].sort((a, b) => a.y - b.y);
    sortedCells.forEach(cell => {
        drawIsometricTile(
            cell.x + viewOffsetX,
            cell.y + viewOffsetY,
            cell.color,
            cell.terrain
        );
    });

    // Draw terrain transitions (blend edges between different terrain types)
    sortedCells.forEach(cell => {
        if (cell.neighbors) {
            drawTerrainTransitions(
                cell.x + viewOffsetX,
                cell.y + viewOffsetY,
                cell.terrain,
                cell.neighbors
            );
        }
    });

    // Draw decorations on terrain (flowers, mushrooms, etc.)
    sortedCells.forEach(cell => {
        drawDecorations(
            cell.x + viewOffsetX,
            cell.y + viewOffsetY,
            cell.terrain,
            cell.world_x,
            cell.world_y
        );
    });

    // Draw campfire glow on lit cells (before structures for layering)
    sortedCells.forEach(cell => {
        if (cell.lit) {
            drawCampfireGlow(cell.x + viewOffsetX, cell.y + viewOffsetY);
        }
    });

    // Draw structures on terrain (sorted by y for proper layering)
    sortedCells.forEach(cell => {
        if (cell.structure) {
            drawStructure(
                cell.x + viewOffsetX,
                cell.y + viewOffsetY,
                cell.structure,
                cell.item_count
            );
        }
    });

    // Draw items
    items.forEach(item => {
        drawItem(
            item.x + viewOffsetX,
            item.y + viewOffsetY,
            item.name
        );
    });

    // Draw creature footprint trails (below creatures)
    drawFootprintTrails();

    // Draw creatures (sorted by y for proper layering)
    const sortedCreatures = [...creatures].sort((a, b) => a.y - b.y);
    sortedCreatures.forEach(creature => {
        drawCreature(
            creature.x + viewOffsetX,
            creature.y + viewOffsetY,
            creature.name,
            creature.color,
            creature.last_action,
            creature.agent_id,
            creature.energy,
            creature.max_energy,
            creature.money
        );

        // Trigger action effects for recent actions
        if (creature.last_action && (worldTick - creature.last_action.timestamp) <= 1) {
            const actionKey = `${creature.agent_id}_${creature.last_action.timestamp}`;
            if (!seenActions.has(actionKey)) {
                seenActions.add(actionKey);
                const actionType = creature.last_action.action_type;
                if (actionType === 'take' || actionType === 'drop' ||
                    actionType === 'say' || actionType === 'talk_to') {
                    addActionEffect(
                        creature.x + viewOffsetX,
                        creature.y + viewOffsetY - 25,
                        actionType
                    );
                }
                // Clean up old action keys
                if (seenActions.size > 100) {
                    const keys = Array.from(seenActions);
                    keys.slice(0, 50).forEach(k => seenActions.delete(k));
                }
            }
        }
    });

    // Draw action effects on top of everything
    updateAndDrawActionEffects();

    // Restore context
    ctx.restore();

    // Day/night ambient overlay (drawn after restore, covers entire canvas)
    if (sky.ambientAlpha > 0) {
        ctx.fillStyle = sky.overlay;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    // Draw minimap overlay
    drawMinimap();
}

// ============================================================
// 6. Minimap
// ============================================================
const minimapCanvas = document.getElementById('minimapCanvas');
const minimapCtx = minimapCanvas ? minimapCanvas.getContext('2d') : null;
let minimapVisible = true;

const TERRAIN_MINIMAP_COLORS = {
    grass: '#7ec850',
    water: '#4a90d9',
    sand: '#e8d174',
    stone: '#8a8a8a',
    dirt: '#a0785a',
    forest: '#3e7a28'
};

function drawMinimap() {
    if (!minimapCtx || !minimapVisible) return;
    const mw = minimapCanvas.width;
    const mh = minimapCanvas.height;
    minimapCtx.clearRect(0, 0, mw, mh);

    // Background
    minimapCtx.fillStyle = 'rgba(20, 20, 20, 0.7)';
    minimapCtx.fillRect(0, 0, mw, mh);

    if (cells.length === 0) return;

    // Find world bounds from cell world coordinates
    let minWX = Infinity, maxWX = -Infinity;
    let minWY = Infinity, maxWY = -Infinity;
    cells.forEach(cell => {
        if (cell.world_x < minWX) minWX = cell.world_x;
        if (cell.world_x > maxWX) maxWX = cell.world_x;
        if (cell.world_y < minWY) minWY = cell.world_y;
        if (cell.world_y > maxWY) maxWY = cell.world_y;
    });

    // Use full world dimensions if available
    const ww = worldWidth || (maxWX - minWX + 1);
    const wh = worldHeight || (maxWY - minWY + 1);
    const cellW = (mw - 4) / ww;
    const cellH = (mh - 4) / wh;
    const pad = 2;

    // Draw terrain cells
    cells.forEach(cell => {
        const cx = pad + (cell.world_x - minWX) * cellW;
        const cy = pad + (cell.world_y - minWY) * cellH;
        minimapCtx.fillStyle = TERRAIN_MINIMAP_COLORS[cell.terrain] || '#666';
        minimapCtx.fillRect(cx, cy, Math.max(cellW, 1), Math.max(cellH, 1));
    });

    // Draw creature positions as bright dots
    creatures.forEach(creature => {
        const wx = creature.world_x !== undefined ? creature.world_x : 0;
        const wy = creature.world_y !== undefined ? creature.world_y : 0;
        const cx = pad + (wx - minWX) * cellW + cellW / 2;
        const cy = pad + (wy - minWY) * cellH + cellH / 2;
        minimapCtx.fillStyle = creature.color || '#fff';
        minimapCtx.beginPath();
        minimapCtx.arc(cx, cy, Math.max(3, cellW * 0.6), 0, Math.PI * 2);
        minimapCtx.fill();
        minimapCtx.strokeStyle = '#fff';
        minimapCtx.lineWidth = 0.5;
        minimapCtx.stroke();
    });

    // Draw viewport rectangle using inverse isometric transform
    // Screen point -> world coordinate mapping:
    //   adjustedX = screenX - viewOffsetX - CANVAS_WIDTH/4
    //   adjustedY = screenY - viewOffsetY - CANVAS_HEIGHT/8
    //   worldX = (adjustedX/halfTile + adjustedY/quarterTile) / 2 + viewStartX
    //   worldY = (adjustedY/quarterTile - adjustedX/halfTile) / 2 + viewStartY
    const halfTile = TILE_SIZE / 2;
    const quarterTile = TILE_SIZE / 4;
    const offsetX0 = CANVAS_WIDTH / 4;
    const offsetY0 = CANVAS_HEIGHT / 8;

    // Account for zoom: visible area in unzoomed coords
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    // Corners of canvas in unzoomed space
    const corners = [
        [cx - cx / zoomLevel, cy - cy / zoomLevel],  // top-left
        [cx + cx / zoomLevel, cy - cy / zoomLevel],  // top-right
        [cx + cx / zoomLevel, cy + cy / zoomLevel],  // bottom-right
        [cx - cx / zoomLevel, cy + cy / zoomLevel],  // bottom-left
    ];

    let minWorldX = Infinity, maxWorldX = -Infinity;
    let minWorldY = Infinity, maxWorldY = -Infinity;
    corners.forEach(([sx, sy]) => {
        const ax = sx - viewOffsetX - offsetX0;
        const ay = sy - viewOffsetY - offsetY0;
        const wx = (ax / halfTile + ay / quarterTile) / 2 + viewStartX;
        const wy = (ay / quarterTile - ax / halfTile) / 2 + viewStartY;
        if (wx < minWorldX) minWorldX = wx;
        if (wx > maxWorldX) maxWorldX = wx;
        if (wy < minWorldY) minWorldY = wy;
        if (wy > maxWorldY) maxWorldY = wy;
    });

    // Clamp to world bounds
    minWorldX = Math.max(0, minWorldX);
    minWorldY = Math.max(0, minWorldY);
    maxWorldX = Math.min(ww, maxWorldX);
    maxWorldY = Math.min(wh, maxWorldY);

    // Convert to minimap coordinates
    const vpX = pad + (minWorldX / ww) * (mw - 2 * pad);
    const vpY = pad + (minWorldY / wh) * (mh - 2 * pad);
    const vpW = ((maxWorldX - minWorldX) / ww) * (mw - 2 * pad);
    const vpH = ((maxWorldY - minWorldY) / wh) * (mh - 2 * pad);

    minimapCtx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
    minimapCtx.lineWidth = 1.5;
    minimapCtx.strokeRect(vpX, vpY, vpW, vpH);
}

function toggleMinimap() {
    minimapVisible = !minimapVisible;
    if (minimapCanvas) {
        minimapCanvas.classList.toggle('hidden', !minimapVisible);
    }
    if (minimapVisible) drawMinimap();
}

// Click on minimap to navigate
if (minimapCanvas) {
    minimapCanvas.addEventListener('click', function(e) {
        const rect = minimapCanvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const mw = minimapCanvas.width;
        const mh = minimapCanvas.height;

        // Convert click to fraction of map
        const fracX = mx / mw;
        const fracY = my / mh;

        // Convert to world coordinates
        const targetWX = fracX * worldWidth;
        const targetWY = fracY * worldHeight;

        // Convert to isometric screen coordinates
        const relX = targetWX - viewStartX;
        const relY = targetWY - viewStartY;
        const iso = worldToIsometric(relX, relY, TILE_SIZE);
        const screenX = iso[0] + (CANVAS_WIDTH / 4);
        const screenY = iso[1] + (CANVAS_HEIGHT / 8);

        // Center the viewport on this position
        viewOffsetX = canvas.width / 2 - screenX;
        viewOffsetY = canvas.height / 2 - screenY;
        drawWorld();
    });
}

// ============================================================
// 7. Terrain Rendering
// ============================================================

function drawIsometricTile(x, y, color, terrain) {
    const tileSize = TILE_SIZE;
    const halfTile = tileSize / 2;

    // Try to use sprite first
    const spriteKey = `terrain_${terrain}`;
    const spriteImg = spriteImages[spriteKey];
    if (useSprites && spriteImg && spriteImg.complete && spriteImg.naturalWidth > 0 && spriteImg.naturalHeight > 0) {
        try {
            // Draw sprite
            const spriteWidth = tileSize;
            const spriteHeight = tileSize;

            // Save context
            ctx.save();

            // Create clipping path for isometric diamond
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(x + halfTile, y - halfTile / 2);
            ctx.lineTo(x, y - halfTile);
            ctx.lineTo(x - halfTile, y - halfTile / 2);
            ctx.closePath();
            ctx.clip();

            // Draw sprite centered
            ctx.drawImage(
                spriteImg,
                x - spriteWidth / 2,
                y - halfTile - spriteHeight / 2,
                spriteWidth,
                spriteHeight
            );

            ctx.restore();

            // Add subtle border
            ctx.strokeStyle = darkenColor(color, 20);
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(x + halfTile, y - halfTile / 2);
            ctx.lineTo(x, y - halfTile);
            ctx.lineTo(x - halfTile, y - halfTile / 2);
            ctx.closePath();
            ctx.stroke();
        } catch (error) {
            console.warn('Error drawing sprite for terrain', terrain, error);
            // Fall through to programmatic rendering
        }
    }

    // Use programmatic rendering if sprite not available or failed
    if (!useSprites || !spriteImg || !spriteImg.complete || spriteImg.naturalWidth === 0 || spriteImg.naturalHeight === 0) {
        // Enhanced programmatic rendering with more detail
        // Create gradient for depth
        const gradient = ctx.createLinearGradient(x, y - halfTile, x, y);
        gradient.addColorStop(0, lightenColor(color, 25));
        gradient.addColorStop(0.5, color);
        gradient.addColorStop(1, darkenColor(color, 15));

        ctx.fillStyle = gradient;
        ctx.strokeStyle = darkenColor(color, 30);
        ctx.lineWidth = 2;

        // Draw isometric diamond with rounded effect
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + halfTile, y - halfTile / 2);
        ctx.lineTo(x, y - halfTile);
        ctx.lineTo(x - halfTile, y - halfTile / 2);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Add highlight for 3D effect
        ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
        ctx.beginPath();
        ctx.moveTo(x, y - halfTile);
        ctx.lineTo(x + halfTile * 0.4, y - halfTile * 0.7);
        ctx.lineTo(x, y - halfTile * 0.75);
        ctx.closePath();
        ctx.fill();

        // Add texture based on terrain type
        // Use deterministic pseudo-random based on position for stable rendering
        const seed = (x * 7919 + y * 6983) % 1000;
        const seededRandom = (i) => ((seed + i * 997) % 1000) / 1000;

        if (terrain === 'grass') {
            // Draw varied grass blades with curves
            for (let i = 0; i < 12; i++) {
                const offsetX = (seededRandom(i) - 0.5) * halfTile * 0.7;
                const offsetY = (seededRandom(i + 100) - 0.5) * halfTile * 0.35;
                const height = 3 + seededRandom(i + 200) * 5;
                const lean = (seededRandom(i + 300) - 0.5) * 4;

                // Alternate between light and dark grass
                ctx.strokeStyle = i % 2 === 0 ? darkenColor(color, 15) : lightenColor(color, 10);
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(x + offsetX, y - halfTile/2 + offsetY);
                ctx.quadraticCurveTo(
                    x + offsetX + lean, y - halfTile/2 + offsetY - height/2,
                    x + offsetX + lean * 0.5, y - halfTile/2 + offsetY - height
                );
                ctx.stroke();
            }
        } else if (terrain === 'water') {
            // Animated water with sine-wave shimmer overlay
            const time = Date.now() / 1000;
            const phase = (time + seed / 100) % 3;

            // Sine-wave shimmer bands across the tile
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(x + halfTile, y - halfTile / 2);
            ctx.lineTo(x, y - halfTile);
            ctx.lineTo(x - halfTile, y - halfTile / 2);
            ctx.closePath();
            ctx.clip();

            for (let band = 0; band < 5; band++) {
                const bandY = y - halfTile + band * (halfTile / 4);
                const wave = Math.sin(time * 2 + band * 1.2 + seed * 0.01) * 2;
                const alpha = 0.08 + Math.sin(time * 1.5 + band) * 0.04;
                ctx.fillStyle = `rgba(200, 230, 255, ${alpha})`;
                ctx.fillRect(x - halfTile, bandY + wave, halfTile * 2, halfTile / 6);
            }
            ctx.restore();

            // Ripple rings
            ctx.lineWidth = 1;
            for (let i = 0; i < 3; i++) {
                const ripplePhase = (phase + i) % 3;
                const radius = halfTile * 0.15 + ripplePhase * halfTile * 0.12;
                const opacity = 0.4 - ripplePhase * 0.12;
                ctx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
                ctx.beginPath();
                ctx.ellipse(x, y - halfTile/2, radius, radius * 0.5, 0, 0, Math.PI * 2);
                ctx.stroke();
            }
            // Shimmer highlight
            ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
            ctx.beginPath();
            ctx.ellipse(x - halfTile * 0.15, y - halfTile * 0.6, 3, 2, -0.3, 0, Math.PI * 2);
            ctx.fill();
        } else if (terrain === 'forest') {
            // Draw layered trees with swaying canopy
            const time = Date.now() / 1000;
            const sway = Math.sin(time * 0.8 + seed * 0.05) * 4;

            // Background trees (smaller, darker) — slight sway
            ctx.fillStyle = darkenColor(color, 25);
            ctx.beginPath();
            ctx.arc(x - 8 + sway * 0.4, y - halfTile * 0.4, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = darkenColor(color, 20);
            ctx.beginPath();
            ctx.arc(x + 7 + sway * 0.3, y - halfTile * 0.35, 5, 0, Math.PI * 2);
            ctx.fill();

            // Main tree trunk (static)
            ctx.fillStyle = '#5D4037';
            ctx.fillRect(x - 3, y - halfTile * 0.25, 6, 12);

            // Main tree canopy layers (sway increases with height)
            ctx.fillStyle = darkenColor(color, 10);
            ctx.beginPath();
            ctx.arc(x + sway * 0.3, y - halfTile * 0.45, 10, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(x - 2 + sway * 0.6, y - halfTile * 0.55, 8, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = lightenColor(color, 15);
            ctx.beginPath();
            ctx.arc(x - 3 + sway * 0.9, y - halfTile * 0.65, 5, 0, Math.PI * 2);
            ctx.fill();
        } else if (terrain === 'stone') {
            // Draw scattered rounded rocks
            for (let i = 0; i < 5; i++) {
                const offsetX = (seededRandom(i) - 0.5) * halfTile * 0.5;
                const offsetY = (seededRandom(i + 100) - 0.5) * halfTile * 0.25;
                const size = 2 + seededRandom(i + 200) * 4;

                // Rock shadow
                ctx.fillStyle = darkenColor(color, 20);
                ctx.beginPath();
                ctx.ellipse(x + offsetX + 1, y - halfTile/2 + offsetY + 1, size, size * 0.6, 0, 0, Math.PI * 2);
                ctx.fill();

                // Rock body
                ctx.fillStyle = i % 2 === 0 ? darkenColor(color, 5) : lightenColor(color, 5);
                ctx.beginPath();
                ctx.ellipse(x + offsetX, y - halfTile/2 + offsetY, size, size * 0.6, 0, 0, Math.PI * 2);
                ctx.fill();
            }
        } else if (terrain === 'sand') {
            // Draw sand texture with small dots
            for (let i = 0; i < 8; i++) {
                const offsetX = (seededRandom(i) - 0.5) * halfTile * 0.6;
                const offsetY = (seededRandom(i + 100) - 0.5) * halfTile * 0.3;
                ctx.fillStyle = i % 2 === 0 ? darkenColor(color, 8) : lightenColor(color, 8);
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY, 1.5, 0, Math.PI * 2);
                ctx.fill();
            }
        } else if (terrain === 'dirt') {
            // Draw dirt with scratches
            ctx.strokeStyle = darkenColor(color, 15);
            ctx.lineWidth = 1;
            for (let i = 0; i < 4; i++) {
                const offsetX = (seededRandom(i) - 0.5) * halfTile * 0.5;
                const offsetY = (seededRandom(i + 100) - 0.5) * halfTile * 0.25;
                const length = 4 + seededRandom(i + 200) * 6;
                const angle = seededRandom(i + 300) * Math.PI;
                ctx.beginPath();
                ctx.moveTo(x + offsetX, y - halfTile/2 + offsetY);
                ctx.lineTo(x + offsetX + Math.cos(angle) * length, y - halfTile/2 + offsetY + Math.sin(angle) * length * 0.5);
                ctx.stroke();
            }
        }
    }
}

function lightenColor(color, percent) {
    const num = parseInt(color.replace("#",""), 16);
    const amt = Math.round(2.55 * percent);
    const R = Math.min(255, (num >> 16) + amt);
    const G = Math.min(255, (num >> 8 & 0x00FF) + amt);
    const B = Math.min(255, (num & 0x0000FF) + amt);
    return "#" + (0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1);
}

function darkenColor(color, percent) {
    const num = parseInt(color.replace("#",""), 16);
    const amt = Math.round(2.55 * percent);
    const R = Math.max(0, (num >> 16) - amt);
    const G = Math.max(0, (num >> 8 & 0x00FF) - amt);
    const B = Math.max(0, (num & 0x0000FF) - amt);
    return "#" + (0x1000000 + R * 0x10000 + G * 0x100 + B).toString(16).slice(1);
}

// Draw terrain transitions - subtle blending at edges where different terrains meet
function drawTerrainTransitions(x, y, terrain, neighbors) {
    const tileSize = TILE_SIZE;
    const halfTile = tileSize / 2;

    // Define compatible terrain pairs that can blend
    const canBlend = (t1, t2) => {
        const blendGroups = [
            ['grass', 'forest', 'dirt', 'tilled', 'planted'],  // Land terrains
            ['water', 'sand'],  // Water edge terrains
            ['stone', 'dirt', 'sand'],  // Rocky terrains
        ];
        for (const group of blendGroups) {
            if (group.includes(t1) && group.includes(t2)) return true;
        }
        return false;
    };

    // Draw a soft edge blend for each direction
    // North edge (top-right side of diamond)
    if (neighbors.north && neighbors.north.terrain !== terrain && canBlend(terrain, neighbors.north.terrain)) {
        const gradient = ctx.createLinearGradient(
            x, y - halfTile,
            x + halfTile * 0.3, y - halfTile * 0.85
        );
        gradient.addColorStop(0, 'transparent');
        gradient.addColorStop(1, neighbors.north.color + '40');  // 25% opacity

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(x, y - halfTile);
        ctx.lineTo(x + halfTile * 0.4, y - halfTile * 0.8);
        ctx.lineTo(x + halfTile * 0.3, y - halfTile * 0.65);
        ctx.lineTo(x, y - halfTile * 0.85);
        ctx.closePath();
        ctx.fill();
    }

    // East edge (bottom-right side of diamond)
    if (neighbors.east && neighbors.east.terrain !== terrain && canBlend(terrain, neighbors.east.terrain)) {
        const gradient = ctx.createLinearGradient(
            x + halfTile, y - halfTile / 2,
            x + halfTile * 0.7, y - halfTile * 0.35
        );
        gradient.addColorStop(0, 'transparent');
        gradient.addColorStop(1, neighbors.east.color + '40');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(x + halfTile, y - halfTile / 2);
        ctx.lineTo(x + halfTile * 0.7, y - halfTile * 0.35);
        ctx.lineTo(x + halfTile * 0.7, y - halfTile * 0.15);
        ctx.lineTo(x + halfTile, y - halfTile * 0.3);
        ctx.closePath();
        ctx.fill();
    }

    // South edge (bottom-left side of diamond)
    if (neighbors.south && neighbors.south.terrain !== terrain && canBlend(terrain, neighbors.south.terrain)) {
        const gradient = ctx.createLinearGradient(
            x, y,
            x - halfTile * 0.3, y - halfTile * 0.15
        );
        gradient.addColorStop(0, 'transparent');
        gradient.addColorStop(1, neighbors.south.color + '40');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x - halfTile * 0.4, y - halfTile * 0.2);
        ctx.lineTo(x - halfTile * 0.3, y - halfTile * 0.35);
        ctx.lineTo(x, y - halfTile * 0.15);
        ctx.closePath();
        ctx.fill();
    }

    // West edge (top-left side of diamond)
    if (neighbors.west && neighbors.west.terrain !== terrain && canBlend(terrain, neighbors.west.terrain)) {
        const gradient = ctx.createLinearGradient(
            x - halfTile, y - halfTile / 2,
            x - halfTile * 0.7, y - halfTile * 0.65
        );
        gradient.addColorStop(0, 'transparent');
        gradient.addColorStop(1, neighbors.west.color + '40');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(x - halfTile, y - halfTile / 2);
        ctx.lineTo(x - halfTile * 0.7, y - halfTile * 0.65);
        ctx.lineTo(x - halfTile * 0.7, y - halfTile * 0.85);
        ctx.lineTo(x - halfTile, y - halfTile * 0.7);
        ctx.closePath();
        ctx.fill();
    }
}

// ============================================================
// 8. Decoration Rendering
// ============================================================

function drawDecorations(x, y, terrain, worldX, worldY) {
    // Use deterministic random based on world position
    const seed = (worldX * 7919 + worldY * 6983) % 1000;
    const seededRandom = (i) => ((seed + i * 997) % 1000) / 1000;

    // Only 30% of tiles get decorations
    if (seededRandom(500) > 0.3) return;

    const tileSize = TILE_SIZE;
    const halfTile = tileSize / 2;
    const numDecorations = 1 + Math.floor(seededRandom(501) * 3);

    for (let i = 0; i < numDecorations; i++) {
        const offsetX = (seededRandom(i * 10) - 0.5) * halfTile * 0.5;
        const offsetY = (seededRandom(i * 10 + 1) - 0.5) * halfTile * 0.25;
        const decorType = Math.floor(seededRandom(i * 10 + 2) * 4);

        if (terrain === 'grass') {
            if (decorType === 0) {
                // Red flower
                ctx.fillStyle = '#FF6B6B';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY - 2, 3, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#FFD700';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY - 2, 1.5, 0, Math.PI * 2);
                ctx.fill();
                // Stem
                ctx.strokeStyle = '#228B22';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(x + offsetX, y - halfTile/2 + offsetY - 2);
                ctx.lineTo(x + offsetX, y - halfTile/2 + offsetY + 3);
                ctx.stroke();
            } else if (decorType === 1) {
                // Yellow flower
                ctx.fillStyle = '#FFD700';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY - 2, 2.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#FFA500';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY - 2, 1, 0, Math.PI * 2);
                ctx.fill();
            } else if (decorType === 2) {
                // Purple flower
                ctx.fillStyle = '#9370DB';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY - 2, 2.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#FFE4E1';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY - 2, 1, 0, Math.PI * 2);
                ctx.fill();
            } else {
                // Small rock
                ctx.fillStyle = '#808080';
                ctx.beginPath();
                ctx.ellipse(x + offsetX, y - halfTile/2 + offsetY, 2.5, 1.5, 0, 0, Math.PI * 2);
                ctx.fill();
            }
        } else if (terrain === 'forest') {
            if (decorType === 0 || decorType === 1) {
                // Mushroom
                ctx.fillStyle = '#8B4513';
                ctx.fillRect(x + offsetX - 1.5, y - halfTile/2 + offsetY - 2, 3, 4);
                ctx.fillStyle = decorType === 0 ? '#FF6347' : '#DEB887';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY - 3, 4, Math.PI, 0);
                ctx.fill();
                // Dots on mushroom
                ctx.fillStyle = '#FFF';
                ctx.beginPath();
                ctx.arc(x + offsetX - 1, y - halfTile/2 + offsetY - 4, 1, 0, Math.PI * 2);
                ctx.arc(x + offsetX + 1.5, y - halfTile/2 + offsetY - 3.5, 0.8, 0, Math.PI * 2);
                ctx.fill();
            } else {
                // Bush
                ctx.fillStyle = '#228B22';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY, 4, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#32CD32';
                ctx.beginPath();
                ctx.arc(x + offsetX - 1.5, y - halfTile/2 + offsetY - 1.5, 2.5, 0, Math.PI * 2);
                ctx.fill();
            }
        } else if (terrain === 'sand') {
            if (decorType === 0 || decorType === 1) {
                // Shell
                ctx.fillStyle = '#FFE4C4';
                ctx.beginPath();
                ctx.arc(x + offsetX, y - halfTile/2 + offsetY, 2.5, 0, Math.PI);
                ctx.fill();
                ctx.strokeStyle = '#DEB887';
                ctx.lineWidth = 0.5;
                ctx.beginPath();
                ctx.moveTo(x + offsetX - 2, y - halfTile/2 + offsetY);
                ctx.lineTo(x + offsetX, y - halfTile/2 + offsetY - 1);
                ctx.lineTo(x + offsetX + 2, y - halfTile/2 + offsetY);
                ctx.stroke();
            } else {
                // Driftwood
                ctx.fillStyle = '#A0522D';
                ctx.beginPath();
                ctx.ellipse(x + offsetX, y - halfTile/2 + offsetY, 5, 1.5, seededRandom(i * 10 + 3) * 0.5, 0, Math.PI * 2);
                ctx.fill();
            }
        } else if (terrain === 'stone') {
            // Crystal
            if (seededRandom(i * 10 + 4) > 0.7) {
                ctx.fillStyle = seededRandom(i * 10 + 5) > 0.5 ? '#87CEEB' : '#E6E6FA';
                ctx.beginPath();
                ctx.moveTo(x + offsetX, y - halfTile/2 + offsetY - 5);
                ctx.lineTo(x + offsetX - 2, y - halfTile/2 + offsetY);
                ctx.lineTo(x + offsetX + 2, y - halfTile/2 + offsetY);
                ctx.closePath();
                ctx.fill();
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
                ctx.lineWidth = 0.5;
                ctx.stroke();
            }
        }
    }
}

// Campfire warm glow on lit cells (stronger at night)
function drawCampfireGlow(x, y) {
    const dayPhase = getDayPhase(worldTick);
    // Glow is subtle during day, strong at night
    const nightStrength = dayPhase > 0.65 ? 0.18 : dayPhase > 0.5 ? 0.08 : 0.04;
    const glowRadius = TILE_SIZE * 0.8;
    const grad = ctx.createRadialGradient(x, y - TILE_SIZE / 4, 0, x, y - TILE_SIZE / 4, glowRadius);
    grad.addColorStop(0, `rgba(255, 160, 60, ${nightStrength})`);
    grad.addColorStop(1, 'rgba(255, 160, 60, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(x, y - TILE_SIZE / 4, glowRadius, 0, Math.PI * 2);
    ctx.fill();
}

// ============================================================
// 9. Structure Rendering
// ============================================================

function drawStructure(x, y, structureType, itemCount) {
    if (!structureType) return;

    // All structures use tile center as reference point
    const qt = TILE_SIZE / 4;
    const cy = y - qt;  // visual center of the isometric tile

    // Shadow under structure (small, within diamond)
    ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
    ctx.beginPath();
    ctx.ellipse(x, cy + qt * 0.4, qt * 0.7, qt * 0.2, 0, 0, Math.PI * 2);
    ctx.fill();

    if (structureType === 'shelter') {
        // Tiny A-frame shelter fitting within one tile
        const wallW = qt * 0.25;
        const wallBot = cy + qt * 0.1;
        const wallTop = cy - qt * 0.025;
        const roofPeak = cy - qt * 0.325;
        const roofW = wallW + 1;

        // Wooden back wall
        ctx.fillStyle = '#6D4C41';
        ctx.beginPath();
        ctx.moveTo(x - wallW, wallTop);
        ctx.lineTo(x + wallW, wallTop);
        ctx.lineTo(x + wallW, wallBot);
        ctx.lineTo(x - wallW, wallBot);
        ctx.closePath();
        ctx.fill();

        // Left roof slope (shadow side)
        ctx.fillStyle = '#8B4513';
        ctx.beginPath();
        ctx.moveTo(x, roofPeak);
        ctx.lineTo(x - roofW, wallTop);
        ctx.lineTo(x, wallTop + 1);
        ctx.closePath();
        ctx.fill();

        // Right roof slope (lit side)
        ctx.fillStyle = '#A0522D';
        ctx.beginPath();
        ctx.moveTo(x, roofPeak);
        ctx.lineTo(x + roofW, wallTop);
        ctx.lineTo(x, wallTop + 1);
        ctx.closePath();
        ctx.fill();

        // Roof ridge outline
        ctx.strokeStyle = '#4E342E';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, roofPeak);
        ctx.lineTo(x - roofW, wallTop);
        ctx.moveTo(x, roofPeak);
        ctx.lineTo(x + roofW, wallTop);
        ctx.stroke();

        // Door opening
        ctx.fillStyle = '#2E1B0E';
        ctx.fillRect(x - 3, wallBot - 5, 6, 5);

        // Log texture lines on left roof slope
        ctx.strokeStyle = '#5D4037';
        ctx.lineWidth = 0.5;
        for (let i = 1; i <= 2; i++) {
            const t = i / 3;
            ctx.beginPath();
            ctx.moveTo(x - roofW * (1 - t), roofPeak + (wallTop - roofPeak) * t);
            ctx.lineTo(x, roofPeak + (wallTop + 1 - roofPeak) * t);
            ctx.stroke();
        }
    } else if (structureType === 'marker') {
        // Flag post centered on tile
        const postBase = cy + qt * 0.4;
        const postTop = cy - qt * 1.6;
        ctx.fillStyle = '#5D4037';
        ctx.fillRect(x - 2, postTop, 4, postBase - postTop);

        // Animated flag with wave
        const time = performance.now() / 1000;
        const wave = Math.sin(time * 3) * 2;
        ctx.fillStyle = '#E53935';
        ctx.beginPath();
        ctx.moveTo(x + 2, postTop);
        ctx.quadraticCurveTo(x + 10, postTop + 3 + wave, x + 18, postTop + 6);
        ctx.lineTo(x + 2, postTop + 12);
        ctx.closePath();
        ctx.fill();

        // Flag outline
        ctx.strokeStyle = '#B71C1C';
        ctx.lineWidth = 0.8;
        ctx.stroke();

        // Visibility ring (dashed circle showing extended look range)
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(229, 57, 53, 0.35)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.ellipse(x, cy, TILE_SIZE * 1.2, TILE_SIZE * 0.6, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    } else if (structureType === 'bridge') {
        // Wooden bridge planks centered on tile
        ctx.fillStyle = '#8D6E63';
        for (let i = -2; i <= 2; i++) {
            ctx.fillRect(x + i * 8 - 3, cy - qt * 0.5, 6, qt);
        }

        // Plank lines
        ctx.strokeStyle = '#5D4037';
        ctx.lineWidth = 0.5;
        for (let i = -2; i <= 2; i++) {
            ctx.beginPath();
            ctx.moveTo(x + i * 8, cy - qt * 0.4);
            ctx.lineTo(x + i * 8, cy + qt * 0.4);
            ctx.stroke();
        }

        // Rails
        ctx.strokeStyle = '#4E342E';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(x - 20, cy - qt * 0.6);
        ctx.lineTo(x + 20, cy - qt * 0.6);
        ctx.moveTo(x - 20, cy + qt * 0.4);
        ctx.lineTo(x + 20, cy + qt * 0.4);
        ctx.stroke();

        // Rail posts
        ctx.fillStyle = '#5D4037';
        ctx.fillRect(x - 20, cy - qt * 0.85, 3, qt * 0.5);
        ctx.fillRect(x + 17, cy - qt * 0.85, 3, qt * 0.5);
    } else if (structureType === 'storage') {
        // Wooden chest centered on tile
        const chestTop = cy - qt * 0.1;
        const chestBot = cy + qt * 0.6;
        const chestW = qt * 0.75;
        ctx.fillStyle = '#A1887F';
        ctx.fillRect(x - chestW, chestTop, chestW * 2, chestBot - chestTop);
        // Chest lid (slightly darker)
        ctx.fillStyle = '#8D6E63';
        ctx.fillRect(x - chestW - 1, chestTop - qt * 0.25, chestW * 2 + 2, qt * 0.25);
        // Lid arc
        ctx.beginPath();
        ctx.moveTo(x - chestW - 1, chestTop - qt * 0.25);
        ctx.quadraticCurveTo(x, chestTop - qt * 0.5, x + chestW + 1, chestTop - qt * 0.25);
        ctx.strokeStyle = '#5D4037';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        // Lock
        ctx.fillStyle = '#FFD54F';
        ctx.fillRect(x - 3, chestTop - qt * 0.12, 6, qt * 0.2);
        ctx.strokeStyle = '#F9A825';
        ctx.lineWidth = 0.8;
        ctx.strokeRect(x - 3, chestTop - qt * 0.12, 6, qt * 0.2);
        // Outline
        ctx.strokeStyle = '#4E342E';
        ctx.lineWidth = 1;
        ctx.strokeRect(x - chestW, chestTop, chestW * 2, chestBot - chestTop);

        // Item count badge (top-right corner)
        if (itemCount !== undefined && itemCount > 0) {
            const badgeX = x + chestW + 2;
            const badgeY = chestTop - qt * 0.3;
            ctx.fillStyle = '#1565C0';
            ctx.beginPath();
            ctx.arc(badgeX, badgeY, 7, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 9px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(String(itemCount), badgeX, badgeY);
        }
    } else if (structureType === 'campfire') {
        // Small stone circle centered on tile
        const stoneR = qt * 0.4;
        const stoneAngles = [0, 0.8, 1.6, 2.4, 3.2, 4.0, 4.8, 5.6];
        ctx.fillStyle = '#78909C';
        stoneAngles.forEach(a => {
            ctx.beginPath();
            ctx.ellipse(
                x + Math.cos(a) * stoneR,
                cy + Math.sin(a) * stoneR * 0.5,
                3, 2, a * 0.3, 0, Math.PI * 2
            );
            ctx.fill();
        });

        // Animated flames rising from tile center
        const time = performance.now() / 1000;
        const flames = [
            { dx: 0, h: qt * 0.7, w: qt * 0.2, color: '#FF6F00' },
            { dx: -3, h: qt * 0.5, w: qt * 0.15, color: '#FF8F00' },
            { dx: 3, h: qt * 0.55, w: qt * 0.15, color: '#FFA000' },
            { dx: -1, h: qt * 0.4, w: qt * 0.18, color: '#FFCA28' }
        ];
        flames.forEach((f, i) => {
            const flicker = Math.sin(time * 8 + i * 2) * 1.5;
            const sway = Math.sin(time * 3 + i) * 1;
            ctx.fillStyle = f.color;
            ctx.beginPath();
            ctx.moveTo(x + f.dx - f.w + sway, cy);
            ctx.quadraticCurveTo(
                x + f.dx + sway, cy - f.h - flicker,
                x + f.dx + f.w + sway, cy
            );
            ctx.closePath();
            ctx.fill();
        });

        // Inner glow dot
        ctx.fillStyle = '#FFF8E1';
        ctx.globalAlpha = 0.6 + Math.sin(time * 6) * 0.2;
        ctx.beginPath();
        ctx.ellipse(x, cy - 2, 2, 3, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1.0;
    }
}

// ============================================================
// 10. Item Rendering
// ============================================================

function drawItem(x, y, name) {
    const s = 7; // base size
    const time = performance.now() / 1000;

    // Gentle shadow glow
    ctx.shadowBlur = 4 + Math.sin(time * 2) * 2;
    ctx.shadowColor = 'rgba(255, 255, 200, 0.6)';

    ctx.save();
    ctx.translate(x, y);

    switch (name) {
        case 'apple':
            // Red apple with green leaf
            ctx.fillStyle = '#e53935';
            ctx.beginPath();
            ctx.arc(0, 0, s, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#b71c1c';
            ctx.lineWidth = 1;
            ctx.stroke();
            // Stem
            ctx.strokeStyle = '#5d4037';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(0, -s);
            ctx.lineTo(1, -s - 4);
            ctx.stroke();
            // Leaf
            ctx.fillStyle = '#4caf50';
            ctx.beginPath();
            ctx.ellipse(3, -s - 3, 4, 2, 0.3, 0, Math.PI * 2);
            ctx.fill();
            break;

        case 'berry':
            // Cluster of 3 small purple circles
            ctx.fillStyle = '#7b1fa2';
            [[-3, 1], [3, 1], [0, -3]].forEach(([bx, by]) => {
                ctx.beginPath();
                ctx.arc(bx, by, s * 0.55, 0, Math.PI * 2);
                ctx.fill();
            });
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            [[-3, 1], [3, 1], [0, -3]].forEach(([bx, by]) => {
                ctx.beginPath();
                ctx.arc(bx - 1, by - 1, 1.5, 0, Math.PI * 2);
                ctx.fill();
            });
            break;

        case 'stone':
            // Gray rounded rock
            ctx.fillStyle = '#90a4ae';
            ctx.beginPath();
            ctx.ellipse(0, 0, s * 1.1, s * 0.8, 0, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#607d8b';
            ctx.lineWidth = 1;
            ctx.stroke();
            ctx.fillStyle = 'rgba(255,255,255,0.25)';
            ctx.beginPath();
            ctx.ellipse(-2, -2, s * 0.4, s * 0.3, 0, 0, Math.PI * 2);
            ctx.fill();
            break;

        case 'stick':
            // Brown diagonal stick
            ctx.strokeStyle = '#795548';
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(-s, s * 0.6);
            ctx.lineTo(s, -s * 0.6);
            ctx.stroke();
            ctx.strokeStyle = '#a1887f';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(-s + 1, s * 0.6 - 1);
            ctx.lineTo(s + 1, -s * 0.6 - 1);
            ctx.stroke();
            break;

        case 'flower':
            // Petals around yellow center
            const petalColors = ['#f48fb1', '#f06292', '#ec407a', '#f48fb1', '#f06292'];
            for (let i = 0; i < 5; i++) {
                const a = (i / 5) * Math.PI * 2 - Math.PI / 2;
                ctx.fillStyle = petalColors[i];
                ctx.beginPath();
                ctx.ellipse(
                    Math.cos(a) * s * 0.5, Math.sin(a) * s * 0.5,
                    s * 0.45, s * 0.3, a, 0, Math.PI * 2
                );
                ctx.fill();
            }
            ctx.fillStyle = '#fdd835';
            ctx.beginPath();
            ctx.arc(0, 0, s * 0.35, 0, Math.PI * 2);
            ctx.fill();
            break;

        case 'mushroom':
            // Red cap on white stem
            ctx.fillStyle = '#efebe9';
            ctx.fillRect(-2, 0, 4, s);
            ctx.fillStyle = '#e53935';
            ctx.beginPath();
            ctx.ellipse(0, 0, s, s * 0.6, 0, Math.PI, 0);
            ctx.fill();
            ctx.strokeStyle = '#b71c1c';
            ctx.lineWidth = 0.8;
            ctx.stroke();
            // White dots
            ctx.fillStyle = '#fff';
            [[-3, -3], [2, -4], [4, -1]].forEach(([dx, dy]) => {
                ctx.beginPath();
                ctx.arc(dx, dy, 1.2, 0, Math.PI * 2);
                ctx.fill();
            });
            break;

        case 'leaf':
            // Green leaf shape
            ctx.fillStyle = '#66bb6a';
            ctx.beginPath();
            ctx.ellipse(0, 0, s * 0.5, s, 0.4, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#388e3c';
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(-s * 0.3, s * 0.6);
            ctx.lineTo(s * 0.3, -s * 0.6);
            ctx.stroke();
            break;

        case 'feather':
            // Light curved stroke
            ctx.strokeStyle = '#b0bec5';
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(-s, s * 0.5);
            ctx.quadraticCurveTo(0, -s, s, s * 0.3);
            ctx.stroke();
            // Central quill
            ctx.strokeStyle = '#cfd8dc';
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(-s * 0.8, s * 0.4);
            ctx.lineTo(s * 0.8, s * 0.2);
            ctx.stroke();
            break;

        case 'pebble':
            // Small gray oval
            ctx.fillStyle = '#b0bec5';
            ctx.beginPath();
            ctx.ellipse(0, 0, s * 0.7, s * 0.5, 0.2, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#78909c';
            ctx.lineWidth = 0.8;
            ctx.stroke();
            break;

        case 'acorn':
            // Brown bottom + tan cap
            ctx.fillStyle = '#8d6e63';
            ctx.beginPath();
            ctx.ellipse(0, 2, s * 0.6, s * 0.7, 0, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#a1887f';
            ctx.beginPath();
            ctx.ellipse(0, -2, s * 0.7, s * 0.4, 0, Math.PI, 0);
            ctx.fill();
            // Cap texture lines
            ctx.strokeStyle = '#6d4c41';
            ctx.lineWidth = 0.5;
            for (let i = -2; i <= 2; i++) {
                ctx.beginPath();
                ctx.moveTo(i * 2, -4);
                ctx.lineTo(i * 2, -1);
                ctx.stroke();
            }
            break;

        case 'seed':
            // Small teardrop
            ctx.fillStyle = '#a1887f';
            ctx.beginPath();
            ctx.moveTo(0, -s * 0.7);
            ctx.quadraticCurveTo(s * 0.5, 0, 0, s * 0.7);
            ctx.quadraticCurveTo(-s * 0.5, 0, 0, -s * 0.7);
            ctx.fill();
            break;

        case 'herb':
            // Green sprig with small leaves
            ctx.strokeStyle = '#388e3c';
            ctx.lineWidth = 1.5;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(0, s);
            ctx.lineTo(0, -s);
            ctx.stroke();
            ctx.fillStyle = '#66bb6a';
            [[-1, -3, -0.5], [1, -1, 0.5], [-1, 1, -0.3]].forEach(([dir, py, rot]) => {
                ctx.save();
                ctx.translate(0, py);
                ctx.rotate(rot);
                ctx.beginPath();
                ctx.ellipse(dir * 3, 0, 3, 1.5, 0, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            });
            break;

        default:
            // Fallback: simple colored circle
            ctx.fillStyle = '#ffd700';
            ctx.beginPath();
            ctx.arc(0, 0, s, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#cc7000';
            ctx.lineWidth = 1;
            ctx.stroke();
            break;
    }

    ctx.restore();
    ctx.shadowBlur = 0;

    // Draw item name below
    ctx.fillStyle = '#fff';
    ctx.font = '500 8px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.strokeStyle = 'rgba(0,0,0,0.6)';
    ctx.lineWidth = 2.5;
    ctx.strokeText(name, x, y + s + 10);
    ctx.fillText(name, x, y + s + 10);
}

// Draw footprint trails for all creatures
function drawFootprintTrails() {
    const now = performance.now();
    for (const agentId in creatureFootprints) {
        const prints = creatureFootprints[agentId];
        // Remove expired footprints
        while (prints.length > 0 && (now - prints[0].time) > FOOTPRINT_FADE_MS) {
            prints.shift();
        }
        // Draw remaining footprints as fading ellipses
        prints.forEach((fp, i) => {
            const age = now - fp.time;
            const fade = 1 - age / FOOTPRINT_FADE_MS;
            const alpha = Math.max(0, 0.25 * fade);
            const size = 3 + fade * 2;
            ctx.fillStyle = `rgba(80, 60, 40, ${alpha})`;
            ctx.beginPath();
            ctx.ellipse(
                fp.x + viewOffsetX,
                fp.y + viewOffsetY - 6,
                size, size * 0.4, 0, 0, Math.PI * 2
            );
            ctx.fill();
        });
    }
}

// Store idle animation phase per creature (deterministic based on agentId)
// ============================================================
// 11. Creature Rendering
// ============================================================

const creatureIdlePhases = {};
function getCreatureIdlePhase(agentId) {
    if (!creatureIdlePhases[agentId]) {
        // Use hash of agentId to get deterministic random phase
        let hash = 0;
        for (let i = 0; i < agentId.length; i++) {
            hash = ((hash << 5) - hash) + agentId.charCodeAt(i);
            hash |= 0;
        }
        creatureIdlePhases[agentId] = {
            phase: (Math.abs(hash) % 1000) / 1000 * Math.PI * 2,
            speed: 0.8 + (Math.abs(hash >> 10) % 40) / 100
        };
    }
    return creatureIdlePhases[agentId];
}

function drawCreature(x, y, name, color, lastAction, agentId, energy, maxEnergy, money) {
    // Check if this creature is animating
    let jumpOffset = 0;
    const anim = creatureAnimations[agentId];
    if (anim && anim.progress < 1) {
        // No vertical offset during walking — smooth ground-level slide
        jumpOffset = 0;
    } else {
        // Idle animation: gentle bobbing when not moving
        const time = performance.now() / 1000;
        const idleAnim = getCreatureIdlePhase(agentId);
        jumpOffset = Math.sin(time * idleAnim.speed + idleAnim.phase) * 2;
    }

    const creatureY = y - 25 + jumpOffset; // Apply jump/idle offset
    const creatureSize = TILE_SIZE * 0.9; // Scale with tile size (increased from 0.4 to 0.65 for bigger sprites)

    // Draw ground shadow (subtle pulse in sync with walking bob)
    const shadowScale = 1 - Math.abs(jumpOffset) / 80;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.18)';
    ctx.beginPath();
    ctx.ellipse(x, y - 8, creatureSize * 0.25 * shadowScale, creatureSize * 0.1 * shadowScale, 0, 0, Math.PI * 2);
    ctx.fill();

    // Draw speech bubble if there's a recent action (within last 5 ticks)
    if (lastAction && (worldTick - lastAction.timestamp) <= 5) {
        drawSpeechBubble(x, creatureY - 30, lastAction.description, lastAction.action_type);
    }

    // Apply directional lean when walking
    let leanAngle = 0;
    if (anim && anim.progress < 1) {
        const dx = anim.targetX - anim.startX;
        if (dx !== 0) {
            leanAngle = dx > 0 ? 0.087 : -0.087; // ~5 degrees
        }
    }

    ctx.save();
    ctx.translate(x, creatureY);
    ctx.rotate(leanAngle);

    // Try to use sprite first
    const spriteKey = `creature_${name.toLowerCase()}`;
    const spriteImg = spriteImages[spriteKey];
    if (useSprites && spriteImg && spriteImg.complete && spriteImg.naturalWidth > 0 && spriteImg.naturalHeight > 0) {
        try {
            // Draw sprite
            const spriteWidth = creatureSize;
            const spriteHeight = creatureSize;

            ctx.drawImage(
                spriteImg,
                -spriteWidth / 2,
                -spriteHeight / 2,
                spriteWidth,
                spriteHeight
            );
        } catch (error) {
            console.warn('Error drawing sprite for creature', name, error);
            // Fall through to programmatic rendering
        }
    }

    // Minimal fallback if sprite not available
    if (!useSprites || !spriteImg || !spriteImg.complete || spriteImg.naturalWidth === 0 || spriteImg.naturalHeight === 0) {
        const dotRadius = creatureSize * 0.15;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(0, 0, dotRadius, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = darkenColor(color, 40);
        ctx.lineWidth = 1.5;
        ctx.stroke();
    }

    ctx.restore();

    // Draw name label below with better styling
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${Math.max(12, TILE_SIZE * 0.18)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 4;
    ctx.strokeText(name, x, creatureY + creatureSize / 2 + 16);
    ctx.fillText(name, x, creatureY + creatureSize / 2 + 16);

    // Draw energy bar above creature
    if (energy !== undefined && maxEnergy !== undefined) {
        const barWidth = 40;
        const barHeight = 5;
        const barX = x - barWidth / 2;
        const barY = creatureY - creatureSize / 2 - 12;
        const energyPercent = Math.max(0, Math.min(1, energy / maxEnergy));

        // Background (dark)
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(barX - 1, barY - 1, barWidth + 2, barHeight + 2);

        // Empty bar (dark red)
        ctx.fillStyle = '#4a1c1c';
        ctx.fillRect(barX, barY, barWidth, barHeight);

        // Filled bar (green to yellow to red based on energy)
        let barColor;
        if (energyPercent > 0.5) {
            barColor = '#4caf50';  // Green
        } else if (energyPercent > 0.25) {
            barColor = '#ff9800';  // Orange
        } else {
            barColor = '#f44336';  // Red
        }
        ctx.fillStyle = barColor;
        ctx.fillRect(barX, barY, barWidth * energyPercent, barHeight);

        // Money indicator (small coin icon with amount)
        if (money !== undefined) {
            ctx.font = 'bold 9px sans-serif';
            ctx.fillStyle = '#ffd700';
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 2;
            const moneyText = `${money}`;
            ctx.strokeText(moneyText, x + barWidth / 2 + 5, barY + barHeight - 1);
            ctx.fillText(moneyText, x + barWidth / 2 + 5, barY + barHeight - 1);
        }
    }
}

// ============================================================
// 12. Speech Bubbles
// ============================================================

function drawSpeechBubble(x, y, text, actionType) {
    const maxWidth = 120;
    const padding = 8;
    const fontSize = 11;
    ctx.font = `${fontSize}px sans-serif`;

    // Measure text and wrap if needed
    const words = text.split(' ');
    const lines = [];
    let currentLine = '';

    for (let word of words) {
        const testLine = currentLine + (currentLine ? ' ' : '') + word;
        const metrics = ctx.measureText(testLine);
        if (metrics.width > maxWidth && currentLine) {
            lines.push(currentLine);
            currentLine = word;
        } else {
            currentLine = testLine;
        }
    }
    if (currentLine) lines.push(currentLine);

    const lineHeight = fontSize + 4;
    const bubbleHeight = lines.length * lineHeight + padding * 2;
    const bubbleWidth = Math.min(maxWidth + padding * 2, Math.max(...lines.map(l => ctx.measureText(l).width)) + padding * 2);

    const bubbleX = x - bubbleWidth / 2;
    const bubbleY = y - bubbleHeight - 8;

    // Bubble colors based on action type
    const bubbleColors = {
        'move': '#e8f5e9',
        'take': '#fff3e0',
        'drop': '#fce4ec',
        'say': '#f3e5f5',
        'talk_to': '#e0f2f1',
        'look': '#e3f2fd'
    };
    const bubbleColor = bubbleColors[actionType] || '#fff';

    // Draw bubble with rounded corners
    ctx.fillStyle = bubbleColor;
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;

    const radius = 8;
    ctx.beginPath();
    ctx.moveTo(bubbleX + radius, bubbleY);
    ctx.lineTo(bubbleX + bubbleWidth - radius, bubbleY);
    ctx.quadraticCurveTo(bubbleX + bubbleWidth, bubbleY, bubbleX + bubbleWidth, bubbleY + radius);
    ctx.lineTo(bubbleX + bubbleWidth, bubbleY + bubbleHeight - radius);
    ctx.quadraticCurveTo(bubbleX + bubbleWidth, bubbleY + bubbleHeight, bubbleX + bubbleWidth - radius, bubbleY + bubbleHeight);
    ctx.lineTo(bubbleX + radius, bubbleY + bubbleHeight);
    ctx.quadraticCurveTo(bubbleX, bubbleY + bubbleHeight, bubbleX, bubbleY + bubbleHeight - radius);
    ctx.lineTo(bubbleX, bubbleY + radius);
    ctx.quadraticCurveTo(bubbleX, bubbleY, bubbleX + radius, bubbleY);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Draw pointer triangle
    ctx.beginPath();
    ctx.moveTo(x, bubbleY + bubbleHeight);
    ctx.lineTo(x - 6, bubbleY + bubbleHeight + 6);
    ctx.lineTo(x + 6, bubbleY + bubbleHeight + 6);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Draw text
    ctx.fillStyle = '#333';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    lines.forEach((line, i) => {
        ctx.fillText(line, x, bubbleY + padding + i * lineHeight);
    });
}

// Creature drag and drop state
// ============================================================
// 13. Drag & Drop
// ============================================================

let draggedCreature = null;
let dragOffsetX = 0;
let dragOffsetY = 0;
let dragCurrentX = 0;
let dragCurrentY = 0;
let clickStartTime = 0;
const CLICK_THRESHOLD = 200;  // ms - distinguish click from drag

// Mouse interaction for creature dragging and clicking
canvas.addEventListener('mousedown', (e) => {
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    clickStartTime = Date.now();

    // Find clicked creature
    const creature = findCreatureAtPosition(clickX, clickY);
    if (creature) {
        e.preventDefault();
        draggedCreature = creature;
        // Calculate offset from creature center to mouse position
        dragOffsetX = clickX - (creature.x + viewOffsetX);
        dragOffsetY = clickY - (creature.y + viewOffsetY);
        dragCurrentX = clickX;
        dragCurrentY = clickY;
        canvas.style.cursor = 'grabbing';
    }
});

canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (draggedCreature) {
        // Update drag position
        dragCurrentX = mouseX;
        dragCurrentY = mouseY;
        drawWorld();

        // Draw the dragged creature at cursor position with highlight
        drawDraggedCreature(mouseX - dragOffsetX, mouseY - dragOffsetY, draggedCreature);
    } else {
        // Check if hovering over creature
        const creature = findCreatureAtPosition(mouseX, mouseY);
        canvas.style.cursor = creature ? 'grab' : 'default';
    }
});

canvas.addEventListener('mouseup', (e) => {
    if (draggedCreature) {
        const clickDuration = Date.now() - clickStartTime;

        if (clickDuration < CLICK_THRESHOLD) {
            // Short click - open interaction modal
            openInteractionModal(draggedCreature);
        } else {
            // Drag ended - calculate new world position and move creature
            const rect = canvas.getBoundingClientRect();
            const dropX = e.clientX - rect.left - dragOffsetX;
            const dropY = e.clientY - rect.top - dragOffsetY;

            // Convert screen position to world coordinates
            const worldPos = screenToWorld(dropX - viewOffsetX, dropY - viewOffsetY);

            if (worldPos) {
                moveCreatureToPosition(draggedCreature.agent_id, worldPos.x, worldPos.y);
            }
        }

        draggedCreature = null;
        canvas.style.cursor = 'default';
        drawWorld();
    }
});

canvas.addEventListener('mouseleave', () => {
    if (draggedCreature) {
        // Cancel drag if mouse leaves canvas
        draggedCreature = null;
        canvas.style.cursor = 'default';
        drawWorld();
    }
    tooltip.style.display = 'none';
});

// Draw creature being dragged with visual feedback
function drawDraggedCreature(x, y, creature) {
    ctx.save();

    // Apply zoom transformation
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    ctx.translate(centerX, centerY);
    ctx.scale(zoomLevel, zoomLevel);
    ctx.translate(-centerX, -centerY);

    // Draw semi-transparent version at original position
    ctx.globalAlpha = 0.3;
    drawCreature(
        creature.x + viewOffsetX,
        creature.y + viewOffsetY,
        creature.name,
        creature.color,
        null,
        creature.agent_id,
        creature.energy,
        creature.max_energy,
        creature.money
    );

    ctx.restore();

    // Draw creature at drag position (outside zoom transform, at screen coords)
    ctx.save();
    ctx.globalAlpha = 0.9;

    // Draw glow effect
    ctx.shadowColor = '#3498db';
    ctx.shadowBlur = 20;

    // Simple creature representation at cursor
    const tileSize = TILE_SIZE;
    ctx.fillStyle = creature.color;
    ctx.beginPath();
    ctx.arc(x, y - tileSize * 0.3, tileSize * 0.3, 0, Math.PI * 2);
    ctx.fill();

    // Draw name label
    ctx.shadowBlur = 0;
    ctx.fillStyle = 'white';
    ctx.font = 'bold 12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(creature.name, x, y - tileSize * 0.7);

    ctx.restore();
}

// Convert screen coordinates to world grid coordinates
function screenToWorld(screenX, screenY) {
    const tileSize = TILE_SIZE;
    const halfTile = tileSize / 2;

    // Account for zoom
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const unzoomedX = (screenX - centerX) / zoomLevel + centerX;
    const unzoomedY = (screenY - centerY) / zoomLevel + centerY;

    // Remove the initial canvas offset
    const adjustedX = unzoomedX - (canvas.width / 4);
    const adjustedY = unzoomedY - (canvas.height / 8);

    // Inverse isometric transformation
    // iso_x = (x - y) * halfTile
    // iso_y = (x + y) * halfTile / 2
    // Solving for x, y:
    // x = (iso_x / halfTile + iso_y / (halfTile/2)) / 2
    // y = (iso_y / (halfTile/2) - iso_x / halfTile) / 2

    const gridX = (adjustedX / halfTile + adjustedY / (halfTile / 2)) / 2;
    const gridY = (adjustedY / (halfTile / 2) - adjustedX / halfTile) / 2;

    // Add view start offset to get world coordinates
    const worldX = Math.round(gridX) + viewStartX;
    const worldY = Math.round(gridY) + viewStartY;

    // Validate bounds
    if (worldX >= 0 && worldX < worldWidth && worldY >= 0 && worldY < worldHeight) {
        return { x: worldX, y: worldY };
    }
    return null;
}

// Move creature via API
// ============================================================
// 14. Sidebar & Creatures List
// ============================================================

const expandedCreatures = new Set();

function toggleCreature(el, agentId) {
    el.classList.toggle('expanded');
    if (el.classList.contains('expanded')) {
        expandedCreatures.add(agentId);
        centerOnCreature(agentId);
    } else {
        expandedCreatures.delete(agentId);
    }
}

function centerOnCreature(agentId) {
    const creature = creatures.find(c => c.agent_id === agentId);
    if (!creature) return;
    viewOffsetX = canvas.width / 2 - creature.x;
    viewOffsetY = canvas.height / 2 - creature.y;
    drawWorld();
}

async function leaveWorld() {
    if (!confirm('Leave this world and return to the menu?')) return;
    try {
        const res = await fetch('/api/leave', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            window.location.href = '/';
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Error leaving world: ' + e.message);
    }
}

function moveCreatureToPosition(agentId, newX, newY) {
    console.log(`Moving creature ${agentId} to (${newX}, ${newY})`);

    fetch('/api/move_creature', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            agent_id: agentId,
            x: newX,
            y: newY
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Creature moved successfully:', data);
            // Update local creature data
            const creature = creatures.find(c => c.agent_id === agentId);
            if (creature) {
                creature.position = [newX, newY];
                // Recalculate screen position
                const relX = newX - viewStartX;
                const relY = newY - viewStartY;
                const tileSize = TILE_SIZE;
                const halfTile = tileSize / 2;
                creature.x = (relX - relY) * halfTile + (canvas.width / 4);
                creature.y = (relX + relY) * halfTile / 2 + (canvas.height / 8);
            }
            drawWorld();
        } else {
            console.error('Failed to move creature:', data.error);
            alert('Failed to move creature: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error moving creature:', error);
        alert('Error moving creature. Check console for details.');
    });
}

function showTooltip(x, y) {
    // Find what's at this position
    // Simple implementation - could be improved
    tooltip.style.display = 'none';
}

function resetView() {
    viewOffsetX = 0;
    viewOffsetY = 0;
    zoomLevel = 1.0;
    drawWorld();
}

// ============================================================
// 15. World Update & API
// ============================================================

function startAutoUpdate() {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
    updateInterval = setInterval(() => {
        updateWorld();
    }, currentUpdateSpeed * 1000);
}

function updateSpeed(value) {
    currentUpdateSpeed = parseFloat(value);
    document.getElementById('speedValue').textContent = currentUpdateSpeed.toFixed(1) + 's';
    // Restart auto-update with new speed
    startAutoUpdate();
    console.log('Update speed changed to:', currentUpdateSpeed, 'seconds');
}

function updateWorld() {
    console.log('Updating world...');
    // Fetch world tick and creatures/actions together
    Promise.all([
        fetch('/api/world'),
        fetch('/api/creatures'),
        fetch('/api/actions?count=50')
    ])
        .then(([worldResponse, creaturesResponse, actionsResponse]) => {
            if (!worldResponse.ok || !creaturesResponse.ok || !actionsResponse.ok) {
                throw new Error('Network response was not ok');
            }
            return Promise.all([
                worldResponse.json(),
                creaturesResponse.json(),
                actionsResponse.json()
            ]);
        })
        .then(([worldData, creaturesData, actionsData]) => {
            // Update world tick
            worldTick = worldData.tick;
            const tickElement = document.getElementById('tick');
            if (tickElement) {
                tickElement.textContent = worldData.tick;
            }
            console.log('Creatures data received:', creaturesData);
            console.log('Actions data received:', actionsData);

            // Build map of last action per creature
            const lastActionsByCreature = {};
            for (let action of actionsData) {
                if (!lastActionsByCreature[action.agent_id] ||
                    action.timestamp > lastActionsByCreature[action.agent_id].timestamp) {
                    lastActionsByCreature[action.agent_id] = action;
                }
            }

            // Rebuild creatures array with updated positions
            // IMPORTANT: Use the same calculation as initial render
            const newCreatures = [];
            for (let agentId in creaturesData) {
                const c = creaturesData[agentId];
                // Get world coordinates
                let worldX = c.position[0];
                let worldY = c.position[1];

                // Clamp world coordinates to valid range
                worldX = Math.max(0, Math.min(worldWidth - 1, worldX));
                worldY = Math.max(0, Math.min(worldHeight - 1, worldY));

                // Calculate relative to view start (same as initial server-side calculation)
                // viewStartX and viewStartY are the top-left corner of the initial view window
                const relativeX = worldX - viewStartX;
                const relativeY = worldY - viewStartY;

                // Convert to isometric coordinates (relative to view start)
                const isoPos = worldToIsometric(relativeX, relativeY, TILE_SIZE);

                // Convert to screen coordinates (same as initial render)
                // Position so view window starts from top-left area
                const targetScreenX = isoPos[0] + (CANVAS_WIDTH / 4);
                const targetScreenY = isoPos[1] + (CANVAS_HEIGHT / 8);

                // Check if creature position changed (movement detected)
                const existingCreature = creatures.find(cr => cr.agent_id === agentId);
                const hasMoved = !existingCreature ||
                    existingCreature.world_x !== worldX ||
                    existingCreature.world_y !== worldY;

                // If creature moved, start animation
                let currentScreenX = targetScreenX;
                let currentScreenY = targetScreenY;

                if (hasMoved && existingCreature) {
                    // Record footprint at old position
                    if (!creatureFootprints[agentId]) {
                        creatureFootprints[agentId] = [];
                    }
                    creatureFootprints[agentId].push({
                        x: existingCreature.x,
                        y: existingCreature.y,
                        time: performance.now(),
                        color: existingCreature.color
                    });
                    if (creatureFootprints[agentId].length > MAX_FOOTPRINTS) {
                        creatureFootprints[agentId].shift();
                    }

                    // Start new animation from current animated position (or previous position)
                    const anim = creatureAnimations[agentId];
                    const startX = anim && anim.progress < 1 ?
                        anim.startX + (anim.targetX - anim.startX) * anim.progress :
                        existingCreature.x;
                    const startY = anim && anim.progress < 1 ?
                        anim.startY + (anim.targetY - anim.startY) * anim.progress :
                        existingCreature.y;

                    creatureAnimations[agentId] = {
                        startX: startX,
                        startY: startY,
                        targetX: targetScreenX,
                        targetY: targetScreenY,
                        progress: 0,
                        duration: 600 // 600ms walking animation
                    };

                    currentScreenX = startX;
                    currentScreenY = startY;

                    // Start animation loop if not already running
                    if (!animationFrameId) {
                        startAnimationLoop();
                    }
                } else if (creatureAnimations[agentId]) {
                    // Continue existing animation
                    const anim = creatureAnimations[agentId];
                    currentScreenX = anim.startX + (anim.targetX - anim.startX) * anim.progress;
                    currentScreenY = anim.startY + (anim.targetY - anim.startY) * anim.progress;
                }

                // Find last action for this creature
                const lastAction = lastActionsByCreature[agentId];

                newCreatures.push({
                    x: currentScreenX,
                    y: currentScreenY,
                    name: c.name,
                    agent_id: agentId,
                    world_x: worldX,
                    world_y: worldY,
                    color: creatureColors[c.name] || getCreatureColor(c.name),
                    last_action: lastAction ? {
                        description: lastAction.description,
                        action_type: lastAction.action_type,
                        timestamp: lastAction.timestamp,
                        reason: lastAction.reason || null
                    } : null,
                    energy: c.energy !== undefined ? c.energy : 100,
                    max_energy: 100,
                    money: c.money !== undefined ? c.money : 50
                });
            }
            creatures = newCreatures;

            console.log('Updated creatures array:', creatures.length, 'creatures');
            if (creatures.length > 0) {
                console.log('First creature:', creatures[0].name, 'at screen (${creatures[0].x}, ${creatures[0].y}) from world (${creatures[0].world_x}, ${creatures[0].world_y})');
            }

            // Update creatures list in sidebar with inventory
            updateCreaturesList(creaturesData);

            // Redraw the world with updated creature positions
            // Animation loop handles continuous redraws

            // Update actions list
            updateActionsList();
        })
        .catch(error => {
            console.error('Error updating world:', error);
        });
}

function worldToIsometric(x, y, tileSize) {
    const isoX = (x - y) * (tileSize / 2);
    const isoY = (x + y) * (tileSize / 4);
    return [isoX, isoY];
}

function updateCreaturesList(creaturesData) {
    const creaturesList = document.getElementById('creaturesList');
    if (!creaturesList) {
        console.error('Creatures list element not found');
        return;
    }

    let html = '';
    for (let agentId in creaturesData) {
        const c = creaturesData[agentId];
        const inventory = c.inventory || [];

        // Generate inventory HTML
        let inventoryHtml = '';
        if (inventory.length > 0) {
            const inventoryItems = inventory.map(item =>
                `<div class="inventory-item">${escapeHtml(item.name)}</div>`
            ).join('');
            inventoryHtml = `<div class="inventory-items">${inventoryItems}</div>`;
        } else {
            inventoryHtml = '<div class="inventory-empty">Empty</div>';
        }

        const goalsHtml = (c.goals || []).map(g => {
            const label = escapeHtml(g.type || g);
            const done = g.completed ? ' (done)' : '';
            return `<div class="creature-detail">- ${label}${done}</div>`;
        }).join('');

        const lastActionReason = c.last_action && c.last_action.reason
            ? `<div class="creature-detail action-reason"><em>${escapeHtml(c.last_action.reason)}</em></div>`
            : '';
        const lastAction = c.last_action
            ? `<div class="creature-detail" style="margin-top:6px;"><strong>Last Action:</strong> ${escapeHtml(c.last_action.description)}</div>${lastActionReason}`
            : '';

        // Energy and money
        const energy = c.energy !== undefined ? c.energy : 100;
        const money = c.money !== undefined ? c.money : 50;
        const energyPercent = energy / 100;
        let energyColor;
        if (energyPercent > 0.5) {
            energyColor = '#4caf50';  // Green
        } else if (energyPercent > 0.25) {
            energyColor = '#ff9800';  // Orange
        } else {
            energyColor = '#f44336';  // Red
        }

        // Pending trades
        const tradesCount = (c.pending_trades || []).length;
        const tradesHtml = tradesCount > 0
            ? `<div class="creature-detail" style="color: #2196f3;"><strong>Pending Trades:</strong> ${tradesCount}</div>`
            : '';

        const isExpanded = expandedCreatures.has(agentId) ? ' expanded' : '';
        const spriteKey = `creature_${c.name.toLowerCase()}`;
        const spriteSrc = spritePaths[spriteKey] || '';
        const safeName = escapeHtml(c.name);
        const avatarHtml = spriteSrc
            ? `<img class="creature-avatar" src="${escapeHtml(spriteSrc)}" alt="${safeName}">`
            : '';
        html += `
            <div class="creature-info${isExpanded}" onclick="toggleCreature(this, '${escapeHtml(agentId)}')">
                <h3><div class="creature-header">${avatarHtml}${safeName}</div> <span class="expand-indicator">&#9654;</span></h3>
                <div class="creature-stats">
                    <div class="stat-bar">
                        <span class="stat-label">Energy</span>
                        <div class="stat-bar-bg">
                            <div class="stat-bar-fill" style="width: ${energy}%; background: ${energyColor};"></div>
                        </div>
                        <span class="stat-value">${energy}</span>
                    </div>
                    <div class="stat-money">
                        <span style="color: #ffd700;">$</span> ${money}
                    </div>
                </div>
                <div class="creature-detail"><strong>Position:</strong> (${c.position[0]}, ${c.position[1]})</div>
                <div class="creature-details-full">
                    ${lastAction}
                    ${tradesHtml}
                    <div class="creature-detail"><strong>Description:</strong> ${escapeHtml(c.description || '')}</div>
                    <div class="creature-detail"><strong>Personality:</strong> ${escapeHtml(c.personality)}</div>
                    ${goalsHtml ? `<div class="creature-detail" style="margin-top:6px;"><strong>Goals:</strong></div>${goalsHtml}` : ''}
                    <div class="inventory">
                        <div class="creature-detail"><strong>Inventory (${inventory.length}):</strong></div>
                        ${inventoryHtml}
                    </div>
                </div>
            </div>
        `;
    }
    creaturesList.innerHTML = html;
}

// ============================================================
// 16. Action Log Filtering
// ============================================================
const activeActionFilters = new Set(); // active action_type filters
const activeCreatureFilters = new Set(); // active creature_name filters
let lastActionsData = []; // cache for re-filtering

function buildFilterButtons(actions) {
    const filtersDiv = document.getElementById('actionFilters');
    if (!filtersDiv) return;

    // Collect unique action types and creature names
    const types = new Set();
    const names = new Set();
    actions.forEach(a => {
        if (a.action_type) types.add(a.action_type);
        if (a.creature_name) names.add(a.creature_name);
    });

    let html = '';
    // Action type buttons
    types.forEach(type => {
        const active = activeActionFilters.has(type) ? ' active' : '';
        const safeType = escapeHtml(type);
        html += `<button class="action-filter-btn${active}" data-filter-type="${safeType}" onclick="toggleActionFilter('${safeType}')">${safeType}</button>`;
    });
    // Creature name buttons
    names.forEach(name => {
        const active = activeCreatureFilters.has(name) ? ' active' : '';
        const color = creatureColors[name] || getCreatureColor(name);
        const safeName = escapeHtml(name);
        html += `<button class="action-filter-btn creature-filter${active}" data-filter-creature="${safeName}" style="border-left-color: ${color};" onclick="toggleCreatureFilter('${safeName}')">${safeName}</button>`;
    });
    filtersDiv.innerHTML = html;
}

function toggleActionFilter(type) {
    if (activeActionFilters.has(type)) {
        activeActionFilters.delete(type);
    } else {
        activeActionFilters.add(type);
    }
    renderFilteredActions();
    // Update button state
    document.querySelectorAll('.action-filter-btn[data-filter-type]').forEach(btn => {
        btn.classList.toggle('active', activeActionFilters.has(btn.dataset.filterType));
    });
}

function toggleCreatureFilter(name) {
    if (activeCreatureFilters.has(name)) {
        activeCreatureFilters.delete(name);
    } else {
        activeCreatureFilters.add(name);
    }
    renderFilteredActions();
    document.querySelectorAll('.action-filter-btn[data-filter-creature]').forEach(btn => {
        btn.classList.toggle('active', activeCreatureFilters.has(btn.dataset.filterCreature));
    });
}

function renderFilteredActions() {
    const actionsList = document.getElementById('actionsList');
    if (!actionsList) return;

    let filtered = lastActionsData;
    if (activeActionFilters.size > 0) {
        filtered = filtered.filter(a => activeActionFilters.has(a.action_type));
    }
    if (activeCreatureFilters.size > 0) {
        filtered = filtered.filter(a => activeCreatureFilters.has(a.creature_name));
    }

    if (filtered.length === 0) {
        actionsList.innerHTML = '<div class="action-item">No matching actions...</div>';
        return;
    }

    let html = '';
    for (let i = filtered.length - 1; i >= 0; i--) {
        const action = filtered[i];
        const reasonHtml = action.reason
            ? `<div class="action-reason"><em>${escapeHtml(action.reason)}</em></div>`
            : '';
        html += `
            <div class="action-item ${escapeHtml(action.action_type)}">
                <div>
                    <span class="action-creature">${escapeHtml(action.creature_name)}</span>
                    <span class="action-description">${escapeHtml(action.description)}</span>
                </div>
                ${reasonHtml}
                <div class="action-time">Tick ${action.timestamp}</div>
            </div>
        `;
    }
    actionsList.innerHTML = html;
}

function updateActionsList() {
    fetch('/api/actions?count=30')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(actions => {
            lastActionsData = actions;
            buildFilterButtons(actions);
            renderFilteredActions();
        })
        .catch(error => {
            console.error('Error updating actions:', error);
        });
}

function getCreatureColor(name) {
    const colors = [
        "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#34495e", "#c0392b", "#16a085"
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
}

// ============================================================
// 17. Animation Loop
// ============================================================

function startAnimationLoop() {
    let lastTime = performance.now();

    function animate(currentTime) {
        const deltaTime = currentTime - lastTime;
        lastTime = currentTime;

        // Update all creature animations
        for (let agentId in creatureAnimations) {
            const anim = creatureAnimations[agentId];
            if (anim.progress < 1) {
                // Update progress (ease-out cubic for smooth deceleration)
                anim.progress += deltaTime / anim.duration;
                if (anim.progress > 1) {
                    anim.progress = 1;
                }

                // Update creature position in creatures array
                const creature = creatures.find(c => c.agent_id === agentId);
                if (creature) {
                    // Ease-in-out quadratic easing function
                    const t = anim.progress;
                    const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

                    creature.x = anim.startX + (anim.targetX - anim.startX) * eased;
                    creature.y = anim.startY + (anim.targetY - anim.startY) * eased;
                }

                if (anim.progress >= 1) {
                    // Animation complete, remove it
                    delete creatureAnimations[agentId];
                }
            }
        }

        // Always redraw — terrain animations (water shimmer, tree sway)
        // need continuous rendering
        drawWorld();
        animationFrameId = requestAnimationFrame(animate);
    }

    animationFrameId = requestAnimationFrame(animate);
}

// Start the continuous animation loop immediately
startAnimationLoop();

// ============================================================
// 18. Interaction & Modals
// ============================================================

function findCreatureAtPosition(x, y) {
    // Check each creature to see if click is within its bounds
    // Account for view offset (panning) and zoom
    const creatureSize = TILE_SIZE * 0.9;
    const clickRadius = creatureSize / 2 + 15; // Add some padding for easier clicking

    // Convert click position from screen space to world space (accounting for zoom)
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;

    // Inverse of the zoom transformation
    const worldX = (x - centerX) / zoomLevel + centerX;
    const worldY = (y - centerY) / zoomLevel + centerY;

    for (let creature of creatures) {
        // Creatures are drawn at creature.x + viewOffsetX, so we need to account for that
        const creatureScreenX = creature.x + viewOffsetX;
        const creatureScreenY = creature.y + viewOffsetY;

        const dx = worldX - creatureScreenX;
        const dy = worldY - creatureScreenY;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance <= clickRadius) {
            console.log('Clicked on creature:', creature.name, 'at screen (', creatureScreenX, ',', creatureScreenY, '), click was (', x, ',', y, '), world (', worldX, ',', worldY, ')');
            return creature;
        }
    }
    return null;
}

function openInteractionModal(creature) {
    selectedCreature = creature;
    const modal = document.getElementById('interactionModal');
    const nameElement = document.getElementById('interactionCreatureName');
    const inputElement = document.getElementById('interactionInput');

    nameElement.textContent = `Interact with ${creature.name}`;
    inputElement.value = '';
    modal.classList.add('active');
    inputElement.focus();

    // Pause simulation
    pauseSimulation();
}

function cancelInteraction() {
    const modal = document.getElementById('interactionModal');
    modal.classList.remove('active');
    selectedCreature = null;

    // Resume simulation
    resumeSimulation();
}

function sendInteraction() {
    const inputElement = document.getElementById('interactionInput');
    const message = inputElement.value.trim();

    if (!message || !selectedCreature) {
        return;
    }

    // Send interaction to server
    fetch('/api/human_interaction', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            agent_id: selectedCreature.agent_id,
            message: message
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        console.log('Interaction sent:', data);
        // Close modal
        cancelInteraction();
        // Update world to show the interaction
        updateWorld();
    })
    .catch(error => {
        console.error('Error sending interaction:', error);
        alert('Failed to send interaction. Please try again.');
    });
}

function pauseSimulation() {
    isSimulationPaused = true;
    const pausedElement = document.getElementById('simulationPaused');
    if (pausedElement) {
        pausedElement.classList.add('active');
    }

    // Stop auto-update
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }

    // Notify server to pause
    fetch('/api/pause_simulation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    }).catch(error => {
        console.error('Error pausing simulation:', error);
    });
}

function resumeSimulation() {
    isSimulationPaused = false;
    const pausedElement = document.getElementById('simulationPaused');
    if (pausedElement) {
        pausedElement.classList.remove('active');
    }

    // Resume auto-update
    startAutoUpdate();

    // Notify server to resume
    fetch('/api/resume_simulation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    }).catch(error => {
        console.error('Error resuming simulation:', error);
    });
}

// Keyboard controls for navigation and interactions
// ============================================================
// 19. Keyboard Controls
// ============================================================

function handleKeyboardPan() {
    const modal = document.getElementById('interactionModal');
    if (modal.classList.contains('active')) return;

    const baseSpeed = keysPressed.has('Shift') ? PAN_SPEED_FAST : PAN_SPEED;
    const speed = baseSpeed / zoomLevel;
    let moved = false;

    // Arrow keys and WASD for panning
    if (keysPressed.has('ArrowUp') || keysPressed.has('w') || keysPressed.has('W')) {
        viewOffsetY += speed;
        moved = true;
    }
    if (keysPressed.has('ArrowDown') || keysPressed.has('s') || keysPressed.has('S')) {
        viewOffsetY -= speed;
        moved = true;
    }
    if (keysPressed.has('ArrowLeft') || keysPressed.has('a') || keysPressed.has('A')) {
        viewOffsetX += speed;
        moved = true;
    }
    if (keysPressed.has('ArrowRight') || keysPressed.has('d') || keysPressed.has('D')) {
        viewOffsetX -= speed;
        moved = true;
    }

    if (moved) {
        drawWorld();
    }
}

function startKeyboardPan() {
    if (keyboardPanInterval) return;
    handleKeyboardPan();  // Immediate first move
    keyboardPanInterval = setInterval(handleKeyboardPan, 50);  // Smooth continuous movement
}

function stopKeyboardPan() {
    if (keyboardPanInterval) {
        clearInterval(keyboardPanInterval);
        keyboardPanInterval = null;
    }
}

document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('interactionModal');

    // Modal-specific controls
    if (modal.classList.contains('active')) {
        if (e.key === 'Enter' && e.ctrlKey) {
            sendInteraction();
        } else if (e.key === 'Escape') {
            cancelInteraction();
        }
        return;
    }

    // Prevent default for navigation keys
    const navKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', '+', '-', '=', '_', 'Home', 'r', 'R', '?'];
    if (navKeys.includes(e.key)) {
        e.preventDefault();
    }

    // Track key state for smooth panning
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'W', 'a', 'A', 's', 'S', 'd', 'D', 'Shift'].includes(e.key)) {
        keysPressed.add(e.key);
        startKeyboardPan();
    }

    // Zoom controls: +/= to zoom in, -/_ to zoom out
    if (e.key === '+' || e.key === '=') {
        const newZoom = Math.min(MAX_ZOOM, zoomLevel + ZOOM_KEY_STEP);
        if (newZoom !== zoomLevel) {
            zoomLevel = newZoom;
            drawWorld();
        }
    }
    if (e.key === '-' || e.key === '_') {
        const newZoom = Math.max(MIN_ZOOM, zoomLevel - ZOOM_KEY_STEP);
        if (newZoom !== zoomLevel) {
            zoomLevel = newZoom;
            drawWorld();
        }
    }

    // Reset view: Home or R
    if (e.key === 'Home' || e.key === 'r' || e.key === 'R') {
        resetView();
    }

    // Toggle minimap: M
    if (e.key === 'm' || e.key === 'M') {
        toggleMinimap();
    }

    // Show help: ?
    if (e.key === '?') {
        toggleHelp();
    }
});

document.addEventListener('keyup', (e) => {
    keysPressed.delete(e.key);

    // Stop continuous pan if no movement keys are pressed
    const movementKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'W', 'a', 'A', 's', 'S', 'd', 'D'];
    const stillMoving = movementKeys.some(k => keysPressed.has(k));
    if (!stillMoving) {
        stopKeyboardPan();
    }
});

// Help overlay toggle
let helpVisible = false;
function toggleHelp() {
    const helpOverlay = document.getElementById('helpOverlay');
    helpVisible = !helpVisible;
    helpOverlay.style.display = helpVisible ? 'flex' : 'none';
}

let legendVisible = false;
function toggleLegend() {
    const legendBar = document.getElementById('legendBar');
    const legendToggle = document.querySelector('.legend-toggle');
    legendVisible = !legendVisible;
    legendBar.style.display = legendVisible ? 'flex' : 'none';
    legendToggle.textContent = legendVisible ? 'Legend ▲' : 'Legend ▼';
}

// Resize canvas to fill container
// ============================================================
// 20. Initialization
// ============================================================

function resizeCanvas() {
    const container = canvas.parentElement;
    const containerWidth = container.clientWidth;
    const containerHeight = container.clientHeight;

    // Set canvas size to fill container
    canvas.width = containerWidth;
    canvas.height = containerHeight;

    // Re-center and redraw
    centerWorld();
    drawWorld();
}

// Center the world in the canvas
function centerWorld() {
    if (cells.length === 0) return;
    const tileSize = TILE_SIZE;
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    cells.forEach(cell => {
        const sx = cell.x;
        const sy = cell.y;
        minX = Math.min(minX, sx - tileSize / 2);
        maxX = Math.max(maxX, sx + tileSize / 2);
        minY = Math.min(minY, sy - tileSize);
        maxY = Math.max(maxY, sy);
    });
    const worldCenterX = (minX + maxX) / 2;
    const worldCenterY = (minY + maxY) / 2;
    viewOffsetX = (canvas.width / 2 - worldCenterX);
    viewOffsetY = (canvas.height / 2 - worldCenterY);
}

// Initial resize and center (draws without sprites as fallback)
resizeCanvas();

// Wait for sprites to load, then redraw with proper sprites
if (spriteLoadPromises.length > 0) {
    Promise.all(spriteLoadPromises).then(() => {
        console.log('All sprites loaded, redrawing...');
        drawWorld();
    });
}

// Handle window resize
window.addEventListener('resize', resizeCanvas);

// Start auto-update immediately
startAutoUpdate();
console.log('World visualization loaded - auto-update started');
console.log('Cells:', cells.length);
console.log('Creatures:', creatures.length);
console.log('Items:', items.length);

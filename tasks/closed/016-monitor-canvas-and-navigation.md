---
title: Monitor canvas, inter-agent arrows, and zoom/pan
state: OPEN
labels: [enhancement, monitor, ui]
priority: high
---

# Monitor Canvas and Navigation Enhancements

Three related improvements to the monitor's visual capabilities, building from specific to broad.

## 1. Inter-Agent Communication Arrows (Multi-Agent Flowchart)

When viewing a session with multiple agents, the flowchart should visually show how agents communicate.

- Draw arrows between interactions across agent columns when one agent sends a message to another (e.g. `AgentCall`, `message_agent`, `Waiting` resolved by child completion)
- Arrows should connect the specific triggering interaction on the sender to the receiving interaction on the target
- Label arrows with the communication type (message, agent call, result return)
- Arrows should be visually distinct from the existing intra-agent flow arrows (e.g. dashed, different color)

### Success Criteria

- [ ] `AgentCall` on parent draws arrow to child agent's `TaskDefinition`
- [ ] `Waiting` resolution draws arrow from child's `TaskResult` back to parent
- [ ] `message_agent` calls draw arrows between agent columns
- [ ] Arrows render correctly with varying numbers of agents and interaction counts

## 2. Zoom and Pan on Flowchart Views

Add zoom and pan to all flowchart views (session-level and individual agent).

- Mouse wheel / pinch to zoom
- Click-and-drag to pan
- Zoom controls (buttons or slider) in the corner
- "Fit to view" / reset button
- Smooth transitions on zoom/pan
- Works on both the session multi-agent flowchart and the single-agent flowchart

### Success Criteria

- [ ] Zoom in/out with scroll wheel and pinch gestures
- [ ] Pan by click-and-drag on the canvas background
- [ ] Zoom control buttons visible in corner (zoom in, zoom out, fit)
- [ ] Works on session flowchart view
- [ ] Works on individual agent flowchart view
- [ ] Does not interfere with clicking interactions or scrolling the page

## 3. Global Sessions Canvas (Live Overview)

A new top-level view showing all currently live sessions/agents on a single pannable, zoomable canvas.

- Each session is rendered as a card/region on the canvas containing its agent flowcharts
- Sessions can be positioned freely on the canvas (drag to arrange)
- Real-time updates via SSE show interactions appearing as agents run
- Clicking a session/agent card navigates to the detailed view
- Canvas persists layout positions across page reloads (localStorage)
- Overview minimap or bird's-eye navigation for large canvases

### Success Criteria

- [ ] New route/view accessible from the monitor main page
- [ ] All active sessions rendered on a single canvas
- [ ] Sessions are draggable to arrange spatially
- [ ] Live updates show new interactions appearing in real-time
- [ ] Click-through to session/agent detail views
- [ ] Zoom and pan on the global canvas
- [ ] Layout positions persist across reloads

## Implementation Notes

- Features build on each other: (1) inter-agent arrows are needed for (3) to be useful
- Zoom/pan (2) is a prerequisite for (3) since the global canvas will be large
- Consider using a canvas/SVG layer for arrows and zoom rather than pure CSS transforms
- The existing SSE update mechanism can power the real-time updates in (3)
- Session positioning in (3) could use a simple `{session_id: {x, y}}` in localStorage

## Files Likely Involved

| Area | Files |
|------|-------|
| Monitor server | `src/gimle/hugin/cli/monitor_agents.py` |
| HTML templates | `src/gimle/hugin/ui/templates/monitor.html`, `agent.html` |
| JavaScript | `src/gimle/hugin/ui/static/js/monitor.js` |
| CSS | `src/gimle/hugin/ui/static/css/monitor.css` |
| New template | `src/gimle/hugin/ui/templates/canvas.html` (for global view) |

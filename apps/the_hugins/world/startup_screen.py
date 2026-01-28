"""Startup screen for loading or creating new worlds."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def get_saved_sessions(
    save_dir: str = "./data/worlds", storage_dir: str = "./data/sessions"
) -> List[Dict[str, Any]]:
    """Get list of saved sessions with metadata."""
    sessions: List[Dict[str, Any]] = []

    save_path = Path(save_dir)
    # storage_path = Path(storage_dir)

    if not save_path.exists():
        return sessions

    # Look for world files
    for world_file in save_path.glob("world_*.json"):
        try:
            session_id = world_file.stem.replace("world_", "")

            # Try to load session metadata
            # session_file = storage_path / session_id
            # session_data = None
            # if session_file.exists():
            #     with open(session_file, "r") as f:
            #         session_data = json.load(f)

            # Load world metadata
            with open(world_file, "r") as f:
                world_data = json.load(f)

            # Get creature names
            creature_names = []
            for creature_data in world_data.get("creatures", {}).values():
                creature_names.append(creature_data.get("name", "Unknown"))

            sessions.append(
                {
                    "session_id": session_id,
                    "world_id": world_data.get("id", "unknown"),
                    "tick": world_data.get("tick", 0),
                    "creatures": creature_names,
                    "num_creatures": len(world_data.get("creatures", {})),
                    "world_size": f"{world_data.get('width', 0)}x{world_data.get('height', 0)}",
                    "last_modified": world_file.stat().st_mtime,
                }
            )
        except Exception as e:
            # Skip corrupted files
            logger.error(f"Error loading session: {e}")
            continue

    # Sort by last modified (newest first)
    sessions.sort(key=lambda x: x["last_modified"], reverse=True)
    return sessions


def generate_startup_html(sessions: List[Dict[str, Any]]) -> str:
    """Generate HTML for the startup screen."""
    sessions_html = ""
    if sessions:
        for session in sessions:
            creatures_str = ", ".join(session["creatures"][:3])
            if len(session["creatures"]) > 3:
                creatures_str += f" +{len(session['creatures']) - 3} more"

            from datetime import datetime

            last_modified = datetime.fromtimestamp(
                session["last_modified"]
            ).strftime("%Y-%m-%d %H:%M:%S")

            sessions_html += f"""
            <div class="session-card" onclick="loadSession('{session['session_id']}')">
                <div class="session-header">
                    <h3>{session['world_id']}</h3>
                    <div class="session-header-right">
                        <span class="session-tick">Tick {session['tick']}</span>
                        <button class="delete-btn" onclick="deleteWorld(event, '{session['session_id']}')" title="Delete this world">🗑️</button>
                    </div>
                </div>
                <div class="session-info">
                    <div class="session-detail">
                        <strong>Creatures:</strong> {creatures_str}
                    </div>
                    <div class="session-detail">
                        <strong>World Size:</strong> {session['world_size']}
                    </div>
                    <div class="session-detail">
                        <strong>Last Modified:</strong> {last_modified}
                    </div>
                </div>
            </div>
            """
    else:
        sessions_html = '<div class="no-sessions">No saved sessions found. Create a new world to get started!</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Hugins</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #111;
            background-image:
                radial-gradient(circle at 20% 30%, rgba(255,255,255,0.03) 0%, transparent 50%),
                radial-gradient(circle at 80% 70%, rgba(255,255,255,0.03) 0%, transparent 50%),
                repeating-linear-gradient(
                    0deg,
                    transparent,
                    transparent 59px,
                    rgba(255,255,255,0.04) 59px,
                    rgba(255,255,255,0.04) 60px
                ),
                repeating-linear-gradient(
                    90deg,
                    transparent,
                    transparent 59px,
                    rgba(255,255,255,0.04) 59px,
                    rgba(255,255,255,0.04) 60px
                );
            color: #1a1a1a;
            min-height: 100vh;
            padding: 60px 20px 40px;
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }}

        .container {{
            max-width: 600px;
            width: 100%;
            background: #fff;
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            border: none;
        }}

        .hero {{
            text-align: center;
            margin-bottom: 32px;
        }}

        .hero h1 {{
            font-size: 2.5em;
            font-weight: 700;
            margin-bottom: 8px;
            color: #1a1a1a;
        }}

        .hero p {{
            color: #888;
            font-size: 1em;
            font-weight: 400;
        }}

        .actions {{
            display: flex;
            gap: 12px;
            margin-bottom: 32px;
        }}

        .action-button {{
            flex: 1;
            padding: 12px 16px;
            background: #1a1a1a;
            border: 1px solid #1a1a1a;
            border-radius: 8px;
            color: #fff;
            font-size: 0.9em;
            font-weight: 500;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.15s;
            text-align: center;
        }}

        .action-button:hover {{
            background: #333;
        }}

        .action-button.create {{
            background: #1a1a1a;
            border-color: #1a1a1a;
        }}

        .action-button.create:hover {{
            background: #333;
        }}

        .sessions-section {{
            margin-top: 24px;
        }}

        .sessions-section h2 {{
            margin-bottom: 14px;
            font-size: 0.75em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #888;
        }}

        .sessions-list {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .session-card {{
            background: #fff;
            border: 1px solid #e5e5e5;
            border-radius: 8px;
            padding: 14px 16px;
            cursor: pointer;
            transition: all 0.15s;
        }}

        .session-card:hover {{
            background: #fafafa;
            border-color: #ccc;
        }}

        .session-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}

        .session-header h3 {{
            font-size: 0.95em;
            font-weight: 600;
        }}

        .session-header-right {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .session-tick {{
            background: #f0f0f0;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.78em;
            color: #666;
        }}

        .delete-btn {{
            background: none;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 4px 8px;
            cursor: pointer;
            font-size: 0.85em;
            transition: all 0.15s;
            color: #999;
        }}

        .delete-btn:hover {{
            background: #fef2f2;
            border-color: #fca5a5;
            color: #dc2626;
        }}

        .session-info {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .session-detail {{
            font-size: 0.82em;
            color: #666;
        }}

        .session-detail strong {{
            color: #333;
            font-weight: 500;
        }}

        .no-sessions {{
            text-align: center;
            padding: 32px;
            color: #aaa;
            font-size: 0.9em;
        }}

        .form-row {{
            display: flex;
            gap: 12px;
            margin-bottom: 10px;
        }}

        .form-row label {{
            flex: 1;
            display: flex;
            flex-direction: column;
            font-size: 0.82em;
            font-weight: 500;
            color: #555;
            gap: 4px;
        }}

        .form-row input, #config-form input, #config-form textarea {{
            padding: 7px 10px;
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            font-size: 0.92em;
            font-family: inherit;
            outline: none;
            transition: border-color 0.15s;
        }}

        .form-row input:focus, #config-form input:focus, #config-form textarea:focus {{
            border-color: #999;
        }}

        #config-form textarea {{
            resize: vertical;
            min-height: 40px;
        }}

        .creature-card {{
            border: 1px solid #e5e5e5;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 8px;
            background: #fafafa;
        }}

        .creature-card .creature-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}

        .creature-card .creature-header strong {{
            font-size: 0.9em;
        }}

        .creature-card .form-row {{
            margin-bottom: 6px;
        }}

        .goals-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 4px;
        }}

        .goals-row label {{
            flex: none;
            flex-direction: row;
            align-items: center;
            gap: 4px;
            font-size: 0.8em;
            cursor: pointer;
        }}

        .small-btn {{
            font-size: 0.82em;
            padding: 4px 12px;
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            background: #fff;
            cursor: pointer;
            font-family: inherit;
            transition: all 0.15s;
        }}

        .small-btn:hover {{
            background: #f0f0f0;
        }}

        .remove-btn {{
            font-size: 0.78em;
            padding: 2px 8px;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            background: none;
            cursor: pointer;
            color: #999;
            font-family: inherit;
        }}

        .remove-btn:hover {{
            background: #fef2f2;
            border-color: #fca5a5;
            color: #dc2626;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>The Hugins</h1>
            <p>Load an existing world or create a new one</p>
        </div>

        <div class="actions" id="actions-bar">
            <div class="action-button create" onclick="showConfigForm()">
                Create New World
            </div>
        </div>

        <div id="config-form" style="display:none;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
                <h2 style="font-size:0.75em;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:#888;margin:0;">World Configuration</h2>
                <label style="font-size:0.82em;color:#666;cursor:pointer;display:flex;align-items:center;gap:6px;">
                    <input type="checkbox" id="advanced-toggle" onchange="toggleAdvanced()"> Advanced
                </label>
            </div>

            <!-- Standard fields -->
            <div class="form-row">
                <label>Width <input type="number" id="cfg-width" value="50" min="10" max="200"></label>
                <label>Height <input type="number" id="cfg-height" value="50" min="10" max="200"></label>
            </div>
            <div class="form-row">
                <label>Creatures <input type="number" id="cfg-num-creatures" value="2" min="1" max="20"></label>
                <label>Items <input type="number" id="cfg-items" value="30" min="0" max="100"></label>
            </div>

            <!-- Advanced fields (hidden by default) -->
            <div id="advanced-section" style="display:none;">
                <div class="form-row" style="margin-top:6px;">
                    <label>Seed <input type="number" id="cfg-seed" placeholder="random"></label>
                    <label style="flex:1;">&nbsp;</label>
                </div>

                <div style="display:flex;justify-content:space-between;align-items:center;margin:18px 0 10px;">
                    <span style="font-size:0.75em;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:#888;">Creatures</span>
                    <div style="display:flex;gap:6px;">
                        <select id="preset-select" style="font-size:0.82em;padding:4px 8px;border:1px solid #e5e5e5;border-radius:6px;font-family:inherit;">
                            <option value="fluffy">Fluffy (bunny)</option>
                            <option value="spike">Spike (hedgehog)</option>
                            <option value="bloom">Bloom (flower sprite)</option>
                            <option value="grit">Grit (beetle)</option>
                            <option value="wisp">Wisp (firefly)</option>
                            <option value="chomp">Chomp (caterpillar)</option>
                            <option value="custom">Custom...</option>
                        </select>
                        <button class="small-btn" onclick="addCreature()">Add</button>
                    </div>
                </div>
                <div id="creatures-list"></div>
            </div>

            <div style="display:flex;gap:10px;margin-top:18px;">
                <div class="action-button create" onclick="submitConfig()" style="flex:1;">Start World</div>
                <div class="action-button" onclick="hideConfigForm()" style="flex:0.5;background:#fff;color:#1a1a1a;border:1px solid #e5e5e5;">Cancel</div>
            </div>
        </div>

        <div class="sessions-section">
            <h2>Saved Sessions</h2>
            <div class="sessions-list">
                {sessions_html}
            </div>
        </div>
    </div>

    <script>
        const PRESETS = {{
            fluffy: {{
                name: 'Fluffy',
                description: 'A friendly bunny that loves to explore',
                personality: "Curious, adventurous, friendly. You love exploring new places and meeting other creatures. You are always eager to see what is around the next corner.",
                goals: ['explore', 'meet']
            }},
            spike: {{
                name: 'Spike',
                description: 'A cautious hedgehog who thinks before acting',
                personality: 'Cautious, thoughtful, methodical. You prefer to observe your surroundings carefully before making decisions. You value safety and planning.',
                goals: ['explore', 'collect']
            }},
            bloom: {{
                name: 'Bloom',
                description: 'A cheerful flower sprite who radiates positivity',
                personality: 'Optimistic, social, nurturing. You love helping others and spreading joy wherever you go.',
                goals: ['meet', 'explore']
            }},
            grit: {{
                name: 'Grit',
                description: 'A determined beetle who never gives up',
                personality: 'Stubborn, resourceful, brave. You tackle every challenge head-on and never back down.',
                goals: ['collect', 'reach']
            }},
            wisp: {{
                name: 'Wisp',
                description: 'A mysterious firefly drawn to hidden places',
                personality: 'Quiet, perceptive, enigmatic. You seek out secrets and hidden corners of the world.',
                goals: ['explore', 'avoid']
            }},
            chomp: {{
                name: 'Chomp',
                description: 'A hungry caterpillar always searching for food',
                personality: 'Eager, single-minded, friendly. You are always on the lookout for tasty items to collect.',
                goals: ['collect', 'explore']
            }},
            custom: {{
                name: '',
                description: '',
                personality: '',
                goals: ['explore']
            }}
        }};

        const ALL_GOALS = ['explore', 'collect', 'meet', 'avoid', 'reach', 'custom'];
        let creatureIndex = 0;
        let advancedMode = false;

        function showConfigForm() {{
            document.getElementById('actions-bar').style.display = 'none';
            document.getElementById('config-form').style.display = 'block';
        }}

        function hideConfigForm() {{
            document.getElementById('actions-bar').style.display = 'flex';
            document.getElementById('config-form').style.display = 'none';
        }}

        function toggleAdvanced() {{
            advancedMode = document.getElementById('advanced-toggle').checked;
            document.getElementById('advanced-section').style.display = advancedMode ? 'block' : 'none';
            document.getElementById('cfg-num-creatures').closest('.form-row').style.display = advancedMode ? 'none' : 'flex';
            if (advancedMode && document.getElementById('creatures-list').children.length === 0) {{
                addCreatureFromPreset('fluffy');
                addCreatureFromPreset('spike');
            }}
        }}

        function addCreature() {{
            const sel = document.getElementById('preset-select');
            addCreatureFromPreset(sel.value);
        }}

        function addCreatureFromPreset(presetKey) {{
            const p = PRESETS[presetKey];
            const idx = creatureIndex++;
            const goalsHtml = ALL_GOALS.map(g => {{
                const checked = p.goals.includes(g) ? 'checked' : '';
                return `<label><input type="checkbox" data-goal="${{g}}" ${{checked}}> ${{g}}</label>`;
            }}).join('');

            const html = `
                <div class="creature-card" id="creature-${{idx}}">
                    <div class="creature-header">
                        <strong>Creature #${{idx + 1}}</strong>
                        <button class="remove-btn" onclick="removeCreature(${{idx}})">Remove</button>
                    </div>
                    <div class="form-row">
                        <label>Name <input type="text" data-field="name" value="${{p.name}}" required></label>
                    </div>
                    <div class="form-row">
                        <label>Description <input type="text" data-field="description" value="${{p.description}}" required></label>
                    </div>
                    <div class="form-row">
                        <label>Personality<textarea data-field="personality" rows="2">${{p.personality}}</textarea></label>
                    </div>
                    <div class="form-row">
                        <label>Starting X <input type="number" data-field="x" placeholder="auto" min="0"></label>
                        <label>Starting Y <input type="number" data-field="y" placeholder="auto" min="0"></label>
                    </div>
                    <div style="font-size:0.82em;font-weight:500;color:#555;margin-bottom:4px;">Goals</div>
                    <div class="goals-row">
                        ${{goalsHtml}}
                    </div>
                </div>
            `;
            document.getElementById('creatures-list').insertAdjacentHTML('beforeend', html);
        }}

        function removeCreature(idx) {{
            const el = document.getElementById('creature-' + idx);
            if (el) el.remove();
        }}

        function gatherConfig() {{
            const seedVal = document.getElementById('cfg-seed').value;
            const config = {{
                world_width: parseInt(document.getElementById('cfg-width').value) || 50,
                world_height: parseInt(document.getElementById('cfg-height').value) || 50,
                seed: seedVal ? parseInt(seedVal) : null,
                num_items: parseInt(document.getElementById('cfg-items').value) || 30,
            }};

            if (advancedMode) {{
                config.creatures = [];
                document.querySelectorAll('.creature-card').forEach(card => {{
                    const get = (field) => {{
                        const el = card.querySelector(`[data-field="${{field}}"]`);
                        return el ? el.value : '';
                    }};
                    const xVal = get('x');
                    const yVal = get('y');
                    const goals = [];
                    card.querySelectorAll('[data-goal]').forEach(cb => {{
                        if (cb.checked) goals.push(cb.dataset.goal);
                    }});
                    config.creatures.push({{
                        name: get('name'),
                        description: get('description'),
                        personality: get('personality'),
                        x: xVal ? parseInt(xVal) : null,
                        y: yVal ? parseInt(yVal) : null,
                        goals: goals.length > 0 ? goals : ['explore']
                    }});
                }});
            }} else {{
                config.num_creatures = parseInt(document.getElementById('cfg-num-creatures').value) || 2;
            }}

            return config;
        }}

        async function submitConfig() {{
            const config = gatherConfig();
            if (advancedMode && Array.isArray(config.creatures)) {{
                if (config.creatures.length === 0) {{
                    alert('Add at least one creature.');
                    return;
                }}
                for (const c of config.creatures) {{
                    if (!c.name || !c.description || !c.personality) {{
                        alert('All creature fields (name, description, personality) are required.');
                        return;
                    }}
                }}
            }} else if (!advancedMode) {{
                const n = config.num_creatures || 0;
                if (n < 1) {{
                    alert('Need at least one creature.');
                    return;
                }}
            }}

            const btn = event.target.closest('.action-button');
            if (btn) {{ btn.style.opacity = '0.6'; btn.textContent = 'Creating...'; }}

            try {{
                const response = await fetch('/api/create', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(config)
                }});
                const data = await response.json();
                if (response.ok && data.success) {{
                    window.location.href = '/';
                }} else {{
                    alert('Error creating world: ' + (data.error || 'Unknown error'));
                    if (btn) {{ btn.style.opacity = '1'; btn.textContent = 'Start World'; }}
                }}
            }} catch (error) {{
                console.error('Error:', error);
                alert('Error creating world: ' + error.message);
                if (btn) {{ btn.style.opacity = '1'; btn.textContent = 'Start World'; }}
            }}
        }}

        async function loadSession(sessionId) {{
            const card = event.target.closest('.session-card');
            if (card) {{
                card.style.opacity = '0.6';
                card.style.pointerEvents = 'none';
            }}

            try {{
                const response = await fetch('/api/load', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{ session_id: sessionId }})
                }});

                const data = await response.json();

                if (response.ok && data.success) {{
                    // Redirect to main page
                    window.location.href = '/';
                }} else {{
                    alert('Error loading session: ' + (data.error || 'Unknown error'));
                    if (card) {{
                        card.style.opacity = '1';
                        card.style.pointerEvents = 'auto';
                    }}
                }}
            }} catch (error) {{
                console.error('Error:', error);
                alert('Error loading session: ' + error.message);
                if (card) {{
                    card.style.opacity = '1';
                    card.style.pointerEvents = 'auto';
                }}
            }}
        }}

        async function deleteWorld(event, sessionId) {{
            // Prevent card click from triggering
            event.stopPropagation();

            // Confirm deletion
            if (!confirm('Are you sure you want to delete this world? This action cannot be undone.')) {{
                return;
            }}

            const button = event.target.closest('.delete-btn');
            if (button) {{
                button.style.opacity = '0.5';
                button.disabled = true;
            }}

            try {{
                const response = await fetch('/api/delete', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{ session_id: sessionId }})
                }});

                const data = await response.json();

                if (response.ok && data.success) {{
                    // Remove the card from the page with animation
                    const card = event.target.closest('.session-card');
                    if (card) {{
                        card.style.transition = 'opacity 0.3s, transform 0.3s';
                        card.style.opacity = '0';
                        card.style.transform = 'translateX(-20px)';
                        setTimeout(() => {{
                            card.remove();
                            // Check if there are no more sessions
                            const sessionsList = document.querySelector('.sessions-list');
                            if (sessionsList && sessionsList.children.length === 0) {{
                                sessionsList.innerHTML = '<div class="no-sessions">No saved sessions found. Create a new world to get started!</div>';
                            }}
                        }}, 300);
                    }}
                }} else {{
                    alert('Error deleting world: ' + (data.error || 'Unknown error'));
                    if (button) {{
                        button.style.opacity = '1';
                        button.disabled = false;
                    }}
                }}
            }} catch (error) {{
                console.error('Error:', error);
                alert('Error deleting world: ' + error.message);
                if (button) {{
                    button.style.opacity = '1';
                    button.disabled = false;
                }}
            }}
        }}
    </script>
</body>
</html>
"""
    return html

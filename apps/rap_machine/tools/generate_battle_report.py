"""Tool for generating static HTML report of completed battle."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from arena.battle import Battle
from battle_utils import get_battle

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def generate_battle_report(
    battle_id: str, stack: Stack, branch: Optional[str] = None
) -> ToolResponse:
    """
    Generate a static HTML report of the completed rap battle.

    Args:
        battle_id: ID of the battle to generate report for
        stack: Agent stack (auto-injected)

    Returns:
        Dict with file path to generated HTML report
    """
    # Get battle from session state
    battle = get_battle(stack, battle_id)

    if battle is None:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Battle {battle_id} not found",
                "status": "error",
            },
        )

    # Generate HTML content (works for both finished and in-progress battles)
    html_content = _generate_html(battle)

    # Save HTML file
    report_dir = "data/rap_battles/reports"
    os.makedirs(report_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"battle_{battle.id}_{timestamp}.html"
    filepath = os.path.join(report_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Also save as latest.html for easy access
    latest_path = os.path.join(report_dir, "latest.html")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    abs_filepath = str(Path(filepath).absolute())

    return ToolResponse(
        is_error=False,
        content={
            "status": "report_generated",
            "message": "Battle report generated successfully",
            "filepath": abs_filepath,
            "filename": filename,
            "battle_id": battle.id,
        },
    )


def _generate_html(battle: Battle) -> str:
    """Generate the complete HTML content matching the live dashboard."""
    # Generate metadata
    generation_time = datetime.now()
    generation_timestamp = generation_time.strftime("%Y-%m-%d %H:%M:%S")

    # Calculate battle duration if finished
    duration_text = "N/A"
    if battle.started_at and battle.finished_at:
        duration_seconds = battle.finished_at - battle.started_at
        duration_minutes = int(duration_seconds / 60)
        duration_text = f"{duration_minutes}m {int(duration_seconds % 60)}s"

    # Generate verses HTML (speech bubbles)
    verses_html = ""
    for verse in battle.verses:
        rapper_name = verse.rapper_name
        content = verse.verse

        # Determine if this is rapper 1 or 2 for styling
        is_rapper_1 = verse.rapper_id == battle.rapper_1_id
        bubble_class = "rapper1" if is_rapper_1 else "rapper2"

        verses_html += f"""
        <div class="speech-bubble {bubble_class}">
            <div class="bubble-rapper-name">{rapper_name}</div>
            <div class="bubble-text">{content}</div>
        </div>
        """

    # Get winner info
    winner_name = ""
    winner_reasoning = ""
    winner_is_rapper_1 = False
    battle_status_text = battle.status.value.upper()
    winner_display = ""

    if battle.result:
        winner_name = battle.result.winner_name
        winner_reasoning = battle.result.reasoning
        winner_is_rapper_1 = battle.result.winner_id == battle.rapper_1_id
        winner_display = f"Winner: {winner_name}"
    else:
        winner_display = "Battle in Progress"

    # Show crown on winner
    rapper1_crown_class = "show" if winner_is_rapper_1 else ""
    rapper2_crown_class = (
        "show" if (battle.result and not winner_is_rapper_1) else ""
    )

    # Judge speech HTML
    if battle.result:
        judge_speech_html = f"""
            <div class="judge-bubble winner-announcement">
                <strong>🏆 Winner: {winner_name} 🏆</strong><br><br>
                {winner_reasoning}
            </div>
        """
    else:
        judge_speech_html = """
            <div class="judge-bubble">
                <em>Battle still in progress... Stay tuned!</em>
            </div>
        """

    # Generate complete HTML matching the live dashboard
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAP MACHINE ARENA - {battle.topic}</title>
    <style>
/* Retro ASCII Light Mode - Matches Live Dashboard */
body {{
    margin: 0;
    padding: 20px;
    font-family: 'Courier New', monospace;
    background: #f5f5dc;
    color: #333;
    min-height: 100vh;
}}

.arena-container {{
    max-width: 1400px;
    margin: 0 auto;
}}

/* Main Banner */
.main-banner {{
    text-align: center;
    padding: 20px;
    margin-bottom: 20px;
    background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
    border: 4px solid #8b4513;
    border-radius: 12px;
    box-shadow: 6px 6px 0px #d2691e;
}}

.banner-title {{
    font-size: 3em;
    font-weight: bold;
    color: #fff;
    text-shadow: 3px 3px 0px #8b4513;
    letter-spacing: 4px;
    margin-bottom: 10px;
}}

.banner-subtitle {{
    font-size: 1.2em;
    color: #fff8e1;
    font-weight: bold;
}}

/* Battle State Display */
.battle-state {{
    text-align: center;
    padding: 12px;
    background: #fff8e1;
    border: 2px solid #8b4513;
    border-radius: 6px;
    margin-bottom: 20px;
    box-shadow: 3px 3px 0px #d2691e;
    font-size: 1em;
}}

.separator {{
    margin: 0 15px;
    color: #d2691e;
}}

#battle-status {{
    color: #2e7d32;
    text-transform: uppercase;
    font-weight: bold;
}}

/* Battle Arena */
.battle-arena {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 20px;
    margin-bottom: 30px;
    padding: 20px;
}}

/* Rapper Sections */
.rapper {{
    flex: 0 0 200px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 15px;
    border-radius: 12px;
    border: 3px solid #8b4513;
    box-shadow: 4px 4px 0px #d2691e;
}}

.rapper-left {{
    background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
}}

.rapper-right {{
    background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%);
}}

.rapper-info {{
    text-align: center;
    margin-bottom: 10px;
    position: relative;
}}

.rapper-name {{
    font-size: 1.2em;
    font-weight: bold;
    color: #8b4513;
    margin-bottom: 5px;
}}

.rapper-model {{
    font-size: 0.75em;
    color: #666;
    background: #ffe4b5;
    padding: 3px 6px;
    border: 1px solid #d2691e;
    border-radius: 4px;
}}

/* Winner Crown */
.winner-crown {{
    font-size: 2em;
    position: absolute;
    top: -40px;
    left: 50%;
    transform: translateX(-50%);
    display: none;
    animation: crownBounce 1s infinite;
}}

.winner-crown.show {{
    display: block;
}}

@keyframes crownBounce {{
    0%, 100% {{ transform: translateX(-50%) translateY(0); }}
    50% {{ transform: translateX(-50%) translateY(-10px); }}
}}

/* ASCII Art */
.rapper-ascii {{
    font-size: 0.9em;
    line-height: 1.1;
    color: #8b4513;
    background: #fff8e1;
    padding: 12px;
    border: 2px solid #d2691e;
    border-radius: 8px;
    box-shadow: 3px 3px 0px #d2691e;
}}

/* Center Stage for Speech Bubbles */
.center-stage {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
}}

/* Speech Bubbles */
.speech-bubbles {{
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
    max-height: 500px;
    overflow-y: auto;
    padding: 10px;
}}

.speech-bubble {{
    position: relative;
    background: #ffffff;
    border: 2px solid #8b4513;
    border-radius: 10px;
    padding: 12px 15px;
    box-shadow: 3px 3px 0px #d2691e;
    line-height: 1.5;
    font-size: 0.85em;
    max-width: 80%;
}}

/* Rapper 1 bubbles (pointing left) - Blue theme */
.speech-bubble.rapper1 {{
    align-self: flex-start;
    background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
    margin-left: 20px;
}}

.speech-bubble.rapper1::before {{
    content: '';
    position: absolute;
    left: -15px;
    top: 15px;
    width: 0;
    height: 0;
    border-top: 10px solid transparent;
    border-bottom: 10px solid transparent;
    border-right: 15px solid #8b4513;
}}

.speech-bubble.rapper1::after {{
    content: '';
    position: absolute;
    left: -11px;
    top: 17px;
    width: 0;
    height: 0;
    border-top: 8px solid transparent;
    border-bottom: 8px solid transparent;
    border-right: 12px solid #e3f2fd;
}}

/* Rapper 2 bubbles (pointing right) - Pink theme */
.speech-bubble.rapper2 {{
    align-self: flex-end;
    background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%);
    margin-right: 20px;
}}

.speech-bubble.rapper2::before {{
    content: '';
    position: absolute;
    right: -15px;
    top: 15px;
    width: 0;
    height: 0;
    border-top: 10px solid transparent;
    border-bottom: 10px solid transparent;
    border-left: 15px solid #8b4513;
}}

.speech-bubble.rapper2::after {{
    content: '';
    position: absolute;
    right: -11px;
    top: 17px;
    width: 0;
    height: 0;
    border-top: 8px solid transparent;
    border-bottom: 8px solid transparent;
    border-left: 12px solid #fce4ec;
}}

.bubble-rapper-name {{
    font-size: 0.7em;
    color: #8b4513;
    font-weight: bold;
    margin-bottom: 5px;
}}

.bubble-text {{
    color: #333;
    white-space: pre-wrap;
}}

/* Judge Section */
.judge-section {{
    text-align: center;
    padding: 20px;
    background: linear-gradient(135deg, #f5f5f5 0%, #e0e0e0 100%);
    border: 3px solid #8b4513;
    border-radius: 12px;
    margin: 0 auto 20px auto;
    max-width: 400px;
    box-shadow: 4px 4px 0px #d2691e;
}}

.judge-info {{
    text-align: center;
    margin-bottom: 10px;
}}

.judge-name {{
    font-size: 1.2em;
    font-weight: bold;
    color: #8b4513;
    margin-bottom: 5px;
}}

.judge-model {{
    font-size: 0.75em;
    color: #666;
    background: #f5f5dc;
    padding: 3px 6px;
    border: 1px solid #d2691e;
    border-radius: 4px;
    display: inline-block;
}}

.judge-ascii {{
    font-size: 0.9em;
    line-height: 1.1;
    color: #8b4513;
    background: #fff8e1;
    padding: 12px;
    border: 2px solid #d2691e;
    border-radius: 8px;
    box-shadow: 3px 3px 0px #d2691e;
    margin: 0 auto 15px auto;
}}

.judge-speech {{
    margin-top: 15px;
}}

.judge-bubble {{
    display: inline-block;
    max-width: 600px;
    background: #f5f5dc;
    border: 2px solid #8b4513;
    border-radius: 10px;
    padding: 15px;
    box-shadow: 3px 3px 0px #d2691e;
    line-height: 1.5;
    font-size: 0.9em;
    text-align: left;
    position: relative;
    margin-top: 20px;
}}

.judge-bubble::before {{
    content: '';
    position: absolute;
    top: -15px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 10px solid transparent;
    border-right: 10px solid transparent;
    border-bottom: 15px solid #8b4513;
}}

.judge-bubble::after {{
    content: '';
    position: absolute;
    top: -11px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 8px solid transparent;
    border-right: 8px solid transparent;
    border-bottom: 12px solid #f5f5dc;
}}

.winner-announcement {{
    background: #ffd700 !important;
    border-color: #ff6347 !important;
    font-weight: bold;
    animation: celebration 1.5s ease-in-out infinite;
}}

@keyframes celebration {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.05); }}
}}

/* Scrollbar Styling */
.speech-bubbles::-webkit-scrollbar {{
    width: 8px;
}}

.speech-bubbles::-webkit-scrollbar-track {{
    background: #f5f5dc;
    border-radius: 4px;
}}

.speech-bubbles::-webkit-scrollbar-thumb {{
    background: #d2691e;
    border-radius: 4px;
}}

.speech-bubbles::-webkit-scrollbar-thumb:hover {{
    background: #8b4513;
}}

/* Metadata Section */
.metadata-section {{
    margin: 20px auto;
    max-width: 800px;
}}

.metadata-details {{
    background: #fff8e1;
    border: 2px solid #8b4513;
    border-radius: 8px;
    box-shadow: 3px 3px 0px #d2691e;
}}

.metadata-summary {{
    padding: 12px 20px;
    cursor: pointer;
    font-weight: bold;
    color: #8b4513;
    font-size: 0.9em;
    user-select: none;
    list-style: none;
}}

.metadata-summary::-webkit-details-marker {{
    display: none;
}}

.metadata-summary::before {{
    content: '▶ ';
    display: inline-block;
    transition: transform 0.2s;
}}

.metadata-details[open] .metadata-summary::before {{
    transform: rotate(90deg);
}}

.metadata-content {{
    padding: 15px 20px 20px 20px;
    border-top: 1px solid #d2691e;
    font-size: 0.85em;
    line-height: 1.6;
}}

.metadata-grid {{
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 15px;
}}

.metadata-label {{
    font-weight: bold;
    color: #8b4513;
}}

.metadata-value {{
    color: #333;
    font-family: 'Courier New', monospace;
}}

/* Responsive design */
@media (max-width: 768px) {{
    .battle-arena {{
        flex-direction: column;
        gap: 20px;
    }}

    .speech-bubbles {{
        max-width: 100%;
    }}

    .rapper {{
        width: 100%;
        align-items: center !important;
    }}
}}
    </style>
</head>
<body>
    <div class="arena-container">
        <!-- Big Banner -->
        <div class="main-banner">
            <div class="banner-title">THE RAP MACHINE</div>
            <div class="banner-subtitle">
                <span id="battle-topic">{battle.topic}</span>
            </div>
        </div>

        <!-- Battle State -->
        <div class="battle-state" id="battle-state">
            <span id="battle-status">{battle_status_text}</span>
            <span class="separator">|</span>
            <span>{winner_display}</span>
        </div>

        <!-- Battle Arena -->
        <div class="battle-arena" id="battle-arena">
            <!-- Left Rapper -->
            <div class="rapper rapper-left" id="rapper1">
                <div class="rapper-info">
                    <div class="rapper-name" id="rapper1-name">{battle.rapper_1_name}</div>
                    <div class="rapper-model" id="rapper1-model">{battle.rapper_1_model}</div>
                    <div class="winner-crown {rapper1_crown_class}" id="rapper1-crown">👑</div>
                </div>
                <pre class="rapper-ascii rapper1-ascii" id="rapper1-ascii">
    _____
   /     \\
  | o   o |
  |   >   |
   \\_____/
     |||
    /||\\
   / || \\
     ||
    /  \\
   /    \\
                </pre>
            </div>

            <!-- Center Speech Bubbles Area -->
            <div class="center-stage">
                <div class="speech-bubbles" id="battle-verses">
                    {verses_html}
                </div>
            </div>

            <!-- Right Rapper -->
            <div class="rapper rapper-right" id="rapper2">
                <div class="rapper-info">
                    <div class="rapper-name" id="rapper2-name">{battle.rapper_2_name}</div>
                    <div class="rapper-model" id="rapper2-model">{battle.rapper_2_model}</div>
                    <div class="winner-crown {rapper2_crown_class}" id="rapper2-crown">👑</div>
                </div>
                <pre class="rapper-ascii rapper2-ascii" id="rapper2-ascii">
    _____
   /     \\
  | ^   ^ |
  |   <   |
   \\_____/
     |||
    /||\\
   / || \\
     ||
    /  \\
   /    \\
                </pre>
            </div>
        </div>

        <!-- Judge Section -->
        <div class="judge-section">
            <div class="judge-info">
                <div class="judge-name">THE JUDGE</div>
                <div class="judge-model" id="judge-model">{battle.judge_model}</div>
            </div>
            <pre class="judge-ascii">
     _______
    /       \\
   | @     @ |
   |    _    |
    \\_______/
       |||
      /|||\\
     / ||| \\
       |||
      /   \\
     /     \\
            </pre>
            <div class="judge-speech" id="judge-speech">
                {judge_speech_html}
            </div>
        </div>

        <!-- Metadata Section -->
        <div class="metadata-section">
            <details class="metadata-details">
                <summary class="metadata-summary">Page Metadata</summary>
                <div class="metadata-content">
                    <div class="metadata-grid">
                        <span class="metadata-label">Generated:</span>
                        <span class="metadata-value">{generation_timestamp}</span>

                        <span class="metadata-label">Battle ID:</span>
                        <span class="metadata-value">{battle.id}</span>

                        <span class="metadata-label">Status:</span>
                        <span class="metadata-value">{battle.status.value.upper()}</span>

                        <span class="metadata-label">Topic:</span>
                        <span class="metadata-value">{battle.topic}</span>

                        <span class="metadata-label">Verses:</span>
                        <span class="metadata-value">{len(battle.verses)} total</span>

                        <span class="metadata-label">Duration:</span>
                        <span class="metadata-value">{duration_text}</span>

                        <span class="metadata-label">Models Used:</span>
                        <span class="metadata-value">
                            {battle.rapper_1_name}: {battle.rapper_1_model}<br>
                            {battle.rapper_2_name}: {battle.rapper_2_model}<br>
                            Judge: {battle.judge_model}
                        </span>
                    </div>
                </div>
            </details>
        </div>
    </div>
</body>
</html>"""

    return html_content

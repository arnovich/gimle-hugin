"""UI component for rendering RapBattle artifacts in the agent monitor."""

from typing import cast

from artifacts.battle_artifact import RapBattleArtifact

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.ui.components import ArtifactComponent, ComponentRegistry


@ComponentRegistry.register("RapBattleArtifact")
class RapBattleComponent(ArtifactComponent):
    """UI component for RapBattle artifacts.

    Renders rap battles with a retro arcade style matching the RapMachine
    dashboard aesthetic.
    """

    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the battle."""
        battle = cast(RapBattleArtifact, artifact)
        winner = battle.winner_name or "In Progress"
        return (
            f"RAP {battle.rapper_1_name} vs {battle.rapper_2_name} - {winner}"
        )

    def render_detail(self, artifact: Artifact) -> str:
        """Render the full battle view."""
        battle = cast(RapBattleArtifact, artifact)

        # Build verses HTML
        verses_html = ""
        for verse in battle.verses:
            rapper_name = verse.get("rapper_name", "Unknown")
            content = self._escape_html(verse.get("verse", ""))
            is_rapper_1 = rapper_name == battle.rapper_1_name
            bubble_class = "rapper1" if is_rapper_1 else "rapper2"

            verses_html += f"""
            <div class="rap-verse {bubble_class}">
                <div class="verse-rapper">{self._escape_html(rapper_name)}</div>
                <div class="verse-content">{content}</div>
            </div>
            """

        # Winner section
        winner_html = ""
        if battle.winner_name:
            reasoning = self._escape_html(battle.winner_reasoning or "")
            winner_html = f"""
            <div class="rap-winner">
                <div class="winner-crown">WINNER</div>
                <div class="winner-name">{self._escape_html(battle.winner_name)}</div>
                <div class="winner-reasoning">{reasoning}</div>
            </div>
            """
        else:
            winner_html = """
            <div class="rap-winner in-progress">
                <div class="winner-crown">BATTLE IN PROGRESS</div>
            </div>
            """

        return f"""
<div class="rap-battle-artifact">
    <div class="rap-header">
        <div class="rap-title">RAP MACHINE ARENA</div>
        <div class="rap-topic">{self._escape_html(battle.topic)}</div>
    </div>

    <div class="rap-participants">
        <div class="rap-participant rapper1">
            <div class="participant-name">{self._escape_html(battle.rapper_1_name)}</div>
            <div class="participant-model">{self._escape_html(battle.rapper_1_model)}</div>
        </div>
        <div class="rap-vs">VS</div>
        <div class="rap-participant rapper2">
            <div class="participant-name">{self._escape_html(battle.rapper_2_name)}</div>
            <div class="participant-model">{self._escape_html(battle.rapper_2_model)}</div>
        </div>
    </div>

    <div class="rap-verses">
        {verses_html}
    </div>

    {winner_html}
</div>
"""

    def get_styles(self) -> str:
        """Return CSS styles for the RapBattle component."""
        return """
/* RapBattle Artifact Styles */
.rap-battle-artifact {
    font-family: 'Courier New', monospace;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 3px solid #e94560;
    border-radius: 12px;
    padding: 20px;
    color: #eee;
}

.rap-header {
    text-align: center;
    margin-bottom: 20px;
    padding-bottom: 15px;
    border-bottom: 2px dashed #e94560;
}

.rap-title {
    font-size: 1.5em;
    font-weight: bold;
    color: #e94560;
    text-shadow: 0 0 10px #e94560;
    letter-spacing: 3px;
}

.rap-topic {
    font-size: 1em;
    color: #ffd700;
    margin-top: 8px;
}

.rap-participants {
    display: flex;
    justify-content: space-around;
    align-items: center;
    margin-bottom: 20px;
    padding: 15px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
}

.rap-participant {
    text-align: center;
    padding: 10px 20px;
    border-radius: 8px;
}

.rap-participant.rapper1 {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%);
    border: 2px solid #4a9eff;
}

.rap-participant.rapper2 {
    background: linear-gradient(135deg, #5f1e3a 0%, #8e2d5a 100%);
    border: 2px solid #ff4a9e;
}

.participant-name {
    font-weight: bold;
    font-size: 1.1em;
    color: #fff;
}

.participant-model {
    font-size: 0.75em;
    color: #aaa;
    margin-top: 4px;
}

.rap-vs {
    font-size: 1.5em;
    font-weight: bold;
    color: #ffd700;
    text-shadow: 0 0 5px #ffd700;
}

.rap-verses {
    max-height: 400px;
    overflow-y: auto;
    padding: 10px;
    margin-bottom: 20px;
}

.rap-verse {
    padding: 12px 15px;
    margin-bottom: 12px;
    border-radius: 10px;
    position: relative;
}

.rap-verse.rapper1 {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%);
    border-left: 4px solid #4a9eff;
    margin-right: 20%;
}

.rap-verse.rapper2 {
    background: linear-gradient(135deg, #5f1e3a 0%, #8e2d5a 100%);
    border-right: 4px solid #ff4a9e;
    border-left: none;
    margin-left: 20%;
    text-align: right;
}

.verse-rapper {
    font-size: 0.8em;
    color: #ffd700;
    font-weight: bold;
    margin-bottom: 5px;
}

.verse-content {
    white-space: pre-wrap;
    line-height: 1.5;
    color: #eee;
}

.rap-winner {
    text-align: center;
    padding: 20px;
    background: linear-gradient(135deg, #ffd700 0%, #ff8c00 100%);
    border-radius: 12px;
    animation: winner-glow 2s ease-in-out infinite;
}

.rap-winner.in-progress {
    background: linear-gradient(135deg, #333 0%, #555 100%);
    animation: none;
}

@keyframes winner-glow {
    0%, 100% { box-shadow: 0 0 10px #ffd700; }
    50% { box-shadow: 0 0 30px #ffd700; }
}

.winner-crown {
    font-size: 0.9em;
    letter-spacing: 2px;
    color: #1a1a2e;
    font-weight: bold;
}

.winner-name {
    font-size: 1.5em;
    font-weight: bold;
    color: #1a1a2e;
    margin: 10px 0;
}

.winner-reasoning {
    font-size: 0.9em;
    color: #333;
    font-style: italic;
    max-width: 500px;
    margin: 0 auto;
}

/* Scrollbar styling for verses */
.rap-verses::-webkit-scrollbar {
    width: 8px;
}

.rap-verses::-webkit-scrollbar-track {
    background: #1a1a2e;
    border-radius: 4px;
}

.rap-verses::-webkit-scrollbar-thumb {
    background: #e94560;
    border-radius: 4px;
}
"""

    def _escape_html(self, content: str) -> str:
        """Escape HTML special characters."""
        return (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

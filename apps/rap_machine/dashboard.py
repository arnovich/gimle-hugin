"""Live battle dashboard for RapMachine.

Serves a self-contained HTML page that polls battle state JSON
and renders verses as they arrive in real time.
"""

import json
import os
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from arena.battle import Battle


class _QuietHandler(SimpleHTTPRequestHandler):
    """HTTP handler that suppresses request logging."""

    def log_message(self, format: str, *args: object) -> None:
        pass


def save_battle_state(battle: Battle, directory: str) -> None:
    """Save battle state as JSON for the live dashboard to poll."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "battle.json")
    with open(path, "w") as f:
        json.dump(battle.to_dict(), f, indent=2)


def start_dashboard_server(
    directory: str, port: int = 8888
) -> threading.Thread:
    """Start a local HTTP server in a daemon thread.

    Args:
        directory: Directory to serve files from.
        port: Port to listen on.

    Returns:
        The daemon thread running the server.
    """
    handler = partial(_QuietHandler, directory=directory)
    server = HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def write_live_dashboard(directory: str) -> None:
    """Write the live dashboard HTML file to the given directory."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "index.html")
    Path(path).write_text(_generate_live_html(), encoding="utf-8")


def _escape_js(s: str) -> str:
    """Escape a string for safe insertion into JavaScript."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _generate_live_html() -> str:
    """Generate self-contained live dashboard HTML with polling JS.

    Uses an XKCD-inspired black-and-white comic style with
    hand-drawn SVG stick figures and wobbly speech bubbles.
    """
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAP MACHINE ARENA - LIVE</title>
    <style>
@import url('https://fonts.googleapis.com/css2?family=Comic+Neue:wght@400;700&display=swap');

body {
    margin: 0;
    padding: 20px;
    font-family: 'Comic Neue', 'Comic Sans MS', cursive, sans-serif;
    background: #ffffff;
    color: #000;
    min-height: 100vh;
}

.arena-container {
    max-width: 900px;
    margin: 0 auto;
}

.main-banner {
    text-align: center;
    padding: 15px 20px 8px 20px;
    margin-bottom: 20px;
}

.banner-title {
    font-size: 3em;
    font-weight: 700;
    color: #000;
    letter-spacing: 4px;
    margin-bottom: 2px;
}

.banner-underline {
    width: 100%;
    height: 6px;
    margin-top: 4px;
}

.banner-subtitle {
    font-size: 1.2em;
    color: #444;
    font-weight: 400;
    font-style: italic;
    margin-top: 6px;
}

.battle-state {
    text-align: center;
    padding: 10px;
    border: 1.5px solid #000;
    border-radius: 18px 22px 20px 16px;
    margin-bottom: 20px;
    font-size: 1em;
}

.separator { margin: 0 15px; color: #888; }

#battle-status {
    color: #000;
    text-transform: uppercase;
    font-weight: bold;
}

.battle-arena {
    display: flex;
    justify-content: center;
    align-items: flex-end;
    gap: 0;
    margin-bottom: 0;
    padding: 20px 0 0 0;
    position: relative;
}

.ground-line {
    width: 100%;
    height: 8px;
    margin-bottom: 10px;
}

.rapper {
    flex: 0 0 150px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 10px 5px;
}

.rapper-info {
    text-align: center;
    margin-bottom: 5px;
    position: relative;
}

.rapper-name {
    font-size: 1.1em;
    font-weight: bold;
    color: #000;
    margin-bottom: 3px;
}

.rapper-model {
    font-size: 0.7em;
    color: #666;
    padding: 2px 6px;
    border: 1px solid #000;
    border-radius: 10px 12px 11px 13px;
}

.winner-crown {
    font-size: 2em;
    position: absolute;
    top: -40px;
    left: 50%;
    transform: translateX(-50%);
    display: none;
    animation: crownBounce 1s infinite;
}

.winner-crown.show { display: block; }

@keyframes crownBounce {
    0%, 100% { transform: translateX(-50%) translateY(0); }
    50% { transform: translateX(-50%) translateY(-10px); }
}

.rapper-svg {
    display: block;
    transform-origin: 50% 140px;
}

.rapper.active .rapper-svg {
    animation: rapWobble 0.4s ease-in-out infinite alternate;
}

.rapper.active .rapper-name {
    font-style: italic;
}

@keyframes rapWobble {
    0% { transform: rotate(-3deg) translateY(0); }
    50% { transform: rotate(2deg) translateY(-3px); }
    100% { transform: rotate(-2deg) translateY(0); }
}

.vs-label {
    font-size: 1.4em;
    font-weight: 700;
    color: #000;
    align-self: center;
    margin: 0 5px;
    letter-spacing: 2px;
}

.center-stage {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    max-width: 520px;
}

.speech-bubbles {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
    max-height: 500px;
    overflow-y: auto;
    padding: 10px;
}

.speech-bubble {
    position: relative;
    background: #fff;
    border: 1.5px solid #000;
    border-radius: 18px 22px 20px 16px;
    padding: 12px 15px;
    line-height: 1.6;
    font-size: 0.9em;
    max-width: 90%;
    opacity: 0;
    animation: fadeIn 0.5s ease forwards;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.speech-bubble.rapper1 {
    align-self: flex-start;
    margin-left: 20px;
}

.speech-bubble.rapper1::before {
    content: '';
    position: absolute;
    left: -14px;
    top: 14px;
    width: 0; height: 0;
    border-top: 8px solid transparent;
    border-bottom: 8px solid transparent;
    border-right: 14px solid #000;
}

.speech-bubble.rapper1::after {
    content: '';
    position: absolute;
    left: -11px;
    top: 16px;
    width: 0; height: 0;
    border-top: 6px solid transparent;
    border-bottom: 6px solid transparent;
    border-right: 11px solid #fff;
}

.speech-bubble.rapper2 {
    align-self: flex-end;
    margin-right: 20px;
}

.speech-bubble.rapper2::before {
    content: '';
    position: absolute;
    right: -14px;
    top: 14px;
    width: 0; height: 0;
    border-top: 8px solid transparent;
    border-bottom: 8px solid transparent;
    border-left: 14px solid #000;
}

.speech-bubble.rapper2::after {
    content: '';
    position: absolute;
    right: -11px;
    top: 16px;
    width: 0; height: 0;
    border-top: 6px solid transparent;
    border-bottom: 6px solid transparent;
    border-left: 11px solid #fff;
}

.bubble-rapper-name {
    font-size: 0.75em;
    color: #000;
    font-weight: bold;
    margin-bottom: 4px;
    text-decoration: underline;
}

.bubble-text {
    color: #000;
    white-space: pre-wrap;
}

.judge-section {
    text-align: center;
    padding: 15px;
    margin: 0 auto 20px auto;
    max-width: 400px;
}

.judge-name {
    font-size: 1.1em;
    font-weight: bold;
    color: #000;
    margin-bottom: 3px;
}

.judge-model {
    font-size: 0.7em;
    color: #666;
    padding: 2px 6px;
    border: 1px solid #000;
    border-radius: 12px 10px 13px 11px;
    display: inline-block;
}

.judge-svg {
    display: block;
    margin: 10px auto;
}

.judge-bubble {
    display: inline-block;
    max-width: 600px;
    background: #fff;
    border: 1.5px solid #000;
    border-radius: 20px 16px 18px 22px;
    padding: 15px;
    line-height: 1.6;
    font-size: 0.9em;
    text-align: left;
    position: relative;
    margin-top: 20px;
}

.judge-bubble::before {
    content: '';
    position: absolute;
    top: -14px;
    left: 50%;
    transform: translateX(-50%);
    width: 0; height: 0;
    border-left: 8px solid transparent;
    border-right: 8px solid transparent;
    border-bottom: 14px solid #000;
}

.judge-bubble::after {
    content: '';
    position: absolute;
    top: -11px;
    left: 50%;
    transform: translateX(-50%);
    width: 0; height: 0;
    border-left: 6px solid transparent;
    border-right: 6px solid transparent;
    border-bottom: 11px solid #fff;
}

.winner-announcement {
    border-width: 2.5px !important;
    font-weight: bold;
    animation: celebration 1.5s ease-in-out infinite;
}

@keyframes celebration {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.03); }
}

.waiting-message {
    text-align: center;
    padding: 40px;
    color: #888;
    font-size: 1.1em;
    font-style: italic;
}

.waiting-dots::after {
    content: '';
    animation: dots 1.5s steps(3, end) infinite;
}

@keyframes dots {
    0% { content: ''; }
    33% { content: '.'; }
    66% { content: '..'; }
    100% { content: '...'; }
}

.speech-bubbles::-webkit-scrollbar { width: 6px; }
.speech-bubbles::-webkit-scrollbar-track { background: #fff; }
.speech-bubbles::-webkit-scrollbar-thumb {
    background: #000; border-radius: 3px;
}

@media (max-width: 768px) {
    .battle-arena { flex-direction: column; align-items: center; gap: 20px; }
    .rapper { width: 100%; }
}
    </style>
</head>
<body>
    <div class="arena-container">
        <div class="main-banner">
            <div class="banner-title">THE RAP MACHINE</div>
            <!-- wobbly hand-drawn underline -->
            <svg class="banner-underline" viewBox="0 0 900 6"
                 preserveAspectRatio="none">
                <path d="M0,3 C40,1 80,5 160,3 C240,1 320,5 400,3
                         C480,2 560,5 640,3 C720,1 800,4 900,3"
                      fill="none" stroke="#000" stroke-width="2"/>
            </svg>
            <div class="banner-subtitle" id="battle-topic">Loading...</div>
        </div>

        <div class="battle-state">
            <span id="battle-status">WAITING</span>
            <span class="separator">&middot;</span>
            <span id="battle-info">Loading battle...</span>
        </div>

        <div class="battle-arena">
            <div class="rapper" id="rapper1-container">
                <div class="rapper-info">
                    <div class="rapper-name" id="rapper1-name">---</div>
                    <div class="rapper-model" id="rapper1-model">---</div>
                    <div class="winner-crown" id="rapper1-crown">&#128081;</div>
                </div>
                <!-- XKCD stick figure: rapper 1, mic in right hand -->
                <svg class="rapper-svg" width="100" height="160"
                     viewBox="0 0 100 160">
                    <!-- wobbly head -->
                    <path d="M34,28 C33,16 42,11 50,11 C58,11 67,16
                             66,28 C65,40 58,45 50,45 C42,45 35,40
                             34,28 Z"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- eyes -->
                    <circle cx="43" cy="26" r="1.5" fill="#000"/>
                    <circle cx="56" cy="26" r="1.5" fill="#000"/>
                    <!-- body (slight wobble) -->
                    <path d="M50,45 C49,60 51,80 50,100"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- left arm (relaxed) -->
                    <path d="M50,60 C42,66 30,74 24,80"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- right arm (mic up) -->
                    <path d="M50,60 C60,56 70,50 76,44"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- mic -->
                    <circle cx="79" cy="40" r="4.5" fill="none"
                            stroke="#000" stroke-width="1.5"/>
                    <line x1="76" y1="43" x2="79" y2="40"
                          stroke="#000" stroke-width="1.2"/>
                    <!-- left leg -->
                    <path d="M50,100 C44,112 36,128 32,140"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- right leg -->
                    <path d="M50,100 C56,112 64,128 68,140"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- feet -->
                    <path d="M32,140 C28,141 24,142 22,141"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <path d="M68,140 C72,141 76,142 78,141"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                </svg>
            </div>

            <div class="center-stage">
                <div class="vs-label">VS</div>
                <div class="speech-bubbles" id="battle-verses">
                    <div class="waiting-message">
                        waiting for the battle to begin<span class="waiting-dots"></span>
                    </div>
                </div>
            </div>

            <div class="rapper" id="rapper2-container">
                <div class="rapper-info">
                    <div class="rapper-name" id="rapper2-name">---</div>
                    <div class="rapper-model" id="rapper2-model">---</div>
                    <div class="winner-crown" id="rapper2-crown">&#128081;</div>
                </div>
                <!-- XKCD stick figure: rapper 2, mic in left hand -->
                <svg class="rapper-svg" width="100" height="160"
                     viewBox="0 0 100 160">
                    <!-- wobbly head -->
                    <path d="M34,28 C33,16 42,11 50,11 C58,11 67,16
                             66,28 C65,40 58,45 50,45 C42,45 35,40
                             34,28 Z"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- eyes -->
                    <circle cx="43" cy="26" r="1.5" fill="#000"/>
                    <circle cx="56" cy="26" r="1.5" fill="#000"/>
                    <!-- body -->
                    <path d="M50,45 C51,60 49,80 50,100"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- right arm (relaxed) -->
                    <path d="M50,60 C58,66 70,74 76,80"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- left arm (mic up) -->
                    <path d="M50,60 C40,56 30,50 24,44"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- mic -->
                    <circle cx="21" cy="40" r="4.5" fill="none"
                            stroke="#000" stroke-width="1.5"/>
                    <line x1="24" y1="43" x2="21" y2="40"
                          stroke="#000" stroke-width="1.2"/>
                    <!-- left leg -->
                    <path d="M50,100 C44,112 36,128 32,140"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- right leg -->
                    <path d="M50,100 C56,112 64,128 68,140"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <!-- feet -->
                    <path d="M32,140 C28,141 24,142 22,141"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                    <path d="M68,140 C72,141 76,142 78,141"
                          fill="none" stroke="#000" stroke-width="1.8"/>
                </svg>
            </div>
        </div>

        <!-- Hand-drawn ground line -->
        <svg class="ground-line" viewBox="0 0 900 8"
             preserveAspectRatio="none">
            <path d="M0,4 C30,2 60,6 120,4 C200,2 280,6 360,4
                     C440,3 520,5 600,4 C680,3 760,6 840,4
                     C870,3 890,5 900,4"
                  fill="none" stroke="#000" stroke-width="2"/>
        </svg>

        <div class="judge-section">
            <div class="judge-name">THE JUDGE</div>
            <div class="judge-model" id="judge-model">---</div>
            <!-- XKCD stick figure: judge with wig -->
            <svg class="judge-svg" width="90" height="140"
                 viewBox="0 0 90 140">
                <!-- wig / hat -->
                <path d="M24,16 C22,8 30,2 36,4 C38,1 42,0 45,0
                         C48,0 52,1 54,4 C60,2 68,8 66,16"
                      fill="none" stroke="#000" stroke-width="1.5"/>
                <!-- wobbly head -->
                <path d="M30,24 C29,14 37,10 45,10 C53,10 61,14
                         60,24 C59,34 53,38 45,38 C37,38 31,34
                         30,24 Z"
                      fill="none" stroke="#000" stroke-width="1.8"/>
                <!-- stern eyes (lines) -->
                <line x1="38" y1="22" x2="42" y2="22"
                      stroke="#000" stroke-width="1.5"/>
                <line x1="48" y1="22" x2="52" y2="22"
                      stroke="#000" stroke-width="1.5"/>
                <!-- flat mouth -->
                <path d="M41,29 C43,30 47,30 49,29"
                      fill="none" stroke="#000" stroke-width="1.2"/>
                <!-- body -->
                <path d="M45,38 C44,52 46,72 45,88"
                      fill="none" stroke="#000" stroke-width="1.8"/>
                <!-- arms crossed -->
                <path d="M25,54 C35,56 55,62 65,60"
                      fill="none" stroke="#000" stroke-width="1.8"/>
                <path d="M25,62 C35,58 55,54 65,56"
                      fill="none" stroke="#000" stroke-width="1.8"/>
                <!-- left leg -->
                <path d="M45,88 C40,98 34,110 30,122"
                      fill="none" stroke="#000" stroke-width="1.8"/>
                <!-- right leg -->
                <path d="M45,88 C50,98 56,110 60,122"
                      fill="none" stroke="#000" stroke-width="1.8"/>
                <!-- feet -->
                <path d="M30,122 C27,123 23,124 21,123"
                      fill="none" stroke="#000" stroke-width="1.8"/>
                <path d="M60,122 C63,123 67,124 69,123"
                      fill="none" stroke="#000" stroke-width="1.8"/>
            </svg>
            <div id="judge-speech"></div>
        </div>
    </div>

<script>
(function() {
    let knownVerseCount = 0;
    let finished = false;
    let rapper1Id = null;

    function escapeHtml(s) {
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function update(data) {
        // Update topic
        var topic = data.topic || 'Loading...';
        document.getElementById('battle-topic').textContent = topic;
        document.title = 'RAP MACHINE - ' + topic;

        // Update status
        var rawStatus = (data.status || 'waiting').toLowerCase();
        var statusLabels = {
            'waiting': 'Waiting for battle...',
            'in_progress': 'Battle in progress!',
            'finished': 'Battle over!'
        };
        document.getElementById('battle-status').textContent = statusLabels[rawStatus] || rawStatus;

        // Update participants
        document.getElementById('rapper1-name').textContent = data.rapper_1_name || '---';
        document.getElementById('rapper1-model').textContent = data.rapper_1_model || '---';
        document.getElementById('rapper2-name').textContent = data.rapper_2_name || '---';
        document.getElementById('rapper2-model').textContent = data.rapper_2_model || '---';
        document.getElementById('judge-model').textContent = data.judge_model || '---';

        rapper1Id = data.rapper_1_id;

        // Update info bar
        const verseCount = (data.verses || []).length;
        const round = data.turn_number || 0;
        const maxRounds = data.max_rounds || '?';
        if (data.result) {
            document.getElementById('battle-info').textContent =
                'Winner: ' + data.result.winner_name;
        } else {
            document.getElementById('battle-info').textContent =
                'Round ' + round + '/' + maxRounds + ' | Verses: ' + verseCount;
        }

        // Highlight active rapper (the one whose turn it is)
        var r1El = document.getElementById('rapper1-container');
        var r2El = document.getElementById('rapper2-container');
        var turn = data.current_turn || '';
        if (data.result) {
            // Battle over, no active rapper
            r1El.classList.remove('active');
            r2El.classList.remove('active');
        } else if (turn === 'rapper_1') {
            r1El.classList.add('active');
            r2El.classList.remove('active');
        } else if (turn === 'rapper_2') {
            r1El.classList.remove('active');
            r2El.classList.add('active');
        }

        // Add new verses
        const verses = data.verses || [];
        if (verses.length > knownVerseCount) {
            const container = document.getElementById('battle-verses');
            // Clear waiting message on first verse
            if (knownVerseCount === 0 && verses.length > 0) {
                container.innerHTML = '';
            }
            for (let i = knownVerseCount; i < verses.length; i++) {
                const v = verses[i];
                const isR1 = v.rapper_id === rapper1Id;
                const cls = isR1 ? 'rapper1' : 'rapper2';
                const bubble = document.createElement('div');
                bubble.className = 'speech-bubble ' + cls;
                bubble.innerHTML =
                    '<div class="bubble-rapper-name">' + escapeHtml(v.rapper_name) + '</div>' +
                    '<div class="bubble-text">' + escapeHtml(v.verse).replace(/\\n/g, '<br>') + '</div>';
                container.appendChild(bubble);
            }
            knownVerseCount = verses.length;
            // Auto-scroll
            container.scrollTop = container.scrollHeight;
        }

        // Winner
        if (data.result && !finished) {
            finished = true;
            const isR1Winner = data.result.winner_id === rapper1Id;
            document.getElementById('rapper1-crown').className =
                'winner-crown' + (isR1Winner ? ' show' : '');
            document.getElementById('rapper2-crown').className =
                'winner-crown' + (!isR1Winner ? ' show' : '');

            document.getElementById('judge-speech').innerHTML =
                '<div class="judge-bubble winner-announcement">' +
                '<strong>&#127942; Winner: ' + escapeHtml(data.result.winner_name) +
                ' &#127942;</strong><br><br>' +
                escapeHtml(data.result.reasoning) + '</div>';
        }
    }

    function poll() {
        fetch('battle.json?t=' + Date.now())
            .then(function(r) { return r.json(); })
            .then(function(data) {
                update(data);
                if (!finished) {
                    setTimeout(poll, 2000);
                }
            })
            .catch(function() {
                if (!finished) {
                    setTimeout(poll, 3000);
                }
            });
    }

    poll();
})();
</script>
</body>
</html>"""

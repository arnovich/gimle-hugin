#!/usr/bin/env python3
"""Run the RapMachine - Agent rap battle arena."""

import argparse
import logging
import os
import random
import sys
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Dict, Optional, Tuple

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.cli.helpers import (
    configure_logging,
    open_in_browser,
    start_monitor_dashboard,
)
from gimle.hugin.storage.local import LocalStorage

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from arena.battle import Battle, BattleStatus, TurnType  # noqa: E402
from dashboard import (  # noqa: E402
    save_battle_state,
    start_dashboard_server,
    write_live_dashboard,
)

# Configure logging - will be reconfigured after parsing args
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
)

logger = logging.getLogger(__name__)


# Use centralized storage (consistent with examples)
SAVE_DIR = "./storage/rap_machine"
SESSION_DIR = f"{SAVE_DIR}/sessions"
BATTLE_DIR = f"{SAVE_DIR}/battles"

# Rapper personalities for random agent battles
RAPPER_PERSONALITIES = [
    {
        "config": "mc_flow",
        "name": "MC Flow",
        "style": "smooth, melodic flow with clever wordplay and intricate metaphors",
        "description": "A skilled lyricist known for smooth delivery and clever punchlines that flow like water",
    },
    {
        "config": "rhyme_fire",
        "name": "Rhyme Fire",
        "style": "aggressive, hard-hitting style with powerful metaphors and fierce energy",
        "description": "An intense rapper who brings explosive energy and fire to every verse",
    },
    {
        "config": "verse_viper",
        "name": "Verse Viper",
        "style": "lightning-fast delivery with intricate wordplay and complex rhyme schemes",
        "description": "A rapid-fire lyricist with venomous bars and lightning-quick wit",
    },
    {
        "config": "beat_boss",
        "name": "Beat Boss",
        "style": "old-school style with heavy emphasis on rhythm and storytelling",
        "description": "A veteran MC who commands respect with classic beats and timeless storytelling",
    },
    {
        "config": "lyric_legend",
        "name": "Lyric Legend",
        "style": "conscious rap with deep philosophical themes and social commentary",
        "description": "A thoughtful artist who weaves wisdom and consciousness into powerful verses",
    },
    {
        "config": "mic_master",
        "name": "Mic Master",
        "style": "technical perfectionist with precise flow and mathematical rhyme patterns",
        "description": "A technical wizard who crafts mathematically perfect rhymes with surgical precision",
    },
]


def get_random_rappers() -> Tuple[Dict, Dict]:
    """Select two random rapper personalities for battle."""
    selected = random.sample(RAPPER_PERSONALITIES, 2)
    return selected[0], selected[1]


def update_model_in_configs(
    env: Environment, model_name: str, preserve_rapper_defaults: bool = False
) -> None:
    """Update the model in all config objects to use the specified model."""
    # Update rapper configs (but preserve defaults if requested)
    rapper_configs = [
        "rapper",
        "mc_flow",
        "rhyme_fire",
        "verse_viper",
        "beat_boss",
        "lyric_legend",
        "mic_master",
    ]
    for config_name in rapper_configs:
        try:
            config = env.config_registry.get(config_name)
            # Only update if not preserving defaults or if it's the generic 'rapper' config
            if not preserve_rapper_defaults or config_name == "rapper":
                config.llm_model = model_name
        except ValueError:
            # Config doesn't exist, skip
            pass

    # Update judge config (preserve default if requested)
    if not preserve_rapper_defaults:
        try:
            judge_config = env.config_registry.get("judge")
            judge_config.llm_model = model_name
        except ValueError:
            pass


def update_specific_model_in_config(
    env: Environment, config_name: str, model_name: str
) -> None:
    """Update the model in a specific config."""
    try:
        config = env.config_registry.get(config_name)
        config.llm_model = model_name
    except ValueError:
        pass


def create_battle_session(
    battle_topic: str,
    rapper_1_name: str = "MC Flow",
    rapper_1_style: str = "smooth, melodic flow with clever wordplay",
    rapper_1_desc: str = (
        "A skilled lyricist known for smooth delivery and clever punchlines"
    ),
    rapper_2_name: str = "Rhyme Fire",
    rapper_2_style: str = (
        "aggressive, hard-hitting style with powerful metaphors"
    ),
    rapper_2_desc: str = (
        "An intense rapper who brings energy and fire to every verse"
    ),
    model_name: str = "haiku-latest",
    rapper_1_config: str = "rapper",
    rapper_2_config: str = "rapper",
    rapper_1_model: Optional[str] = None,
    rapper_2_model: Optional[str] = None,
    judge_model: Optional[str] = None,
    use_config_defaults: bool = False,
    max_rounds: int = 10,
) -> Tuple[Session, LocalStorage, Battle]:
    """Create a rap battle session with two rappers and a judge."""
    # Create battle ID
    battle_id = f"battle_{uuid.uuid4().hex[:8]}"

    # Create storage
    storage = LocalStorage(base_path=SESSION_DIR)

    # Create environment first (without battle)
    env = Environment.load(str(Path(__file__).parent), storage=storage)

    # Update models in all configs (preserve rapper defaults if requested)
    update_model_in_configs(
        env, model_name, preserve_rapper_defaults=use_config_defaults
    )

    # Override specific models if provided
    if rapper_1_model:
        update_specific_model_in_config(env, rapper_1_config, rapper_1_model)
    if rapper_2_model:
        update_specific_model_in_config(env, rapper_2_config, rapper_2_model)
    if judge_model:
        update_specific_model_in_config(env, "judge", judge_model)

    # Get configs to determine actual models
    rapper_1_config_obj = env.config_registry.get(rapper_1_config)
    rapper_2_config_obj = env.config_registry.get(rapper_2_config)
    judge_config = env.config_registry.get("judge")

    # Store actual models used for later display
    if use_config_defaults:
        # Use the model from the config if not explicitly overridden
        actual_rapper_1_model = (
            rapper_1_model if rapper_1_model else rapper_1_config_obj.llm_model
        )
        actual_rapper_2_model = (
            rapper_2_model if rapper_2_model else rapper_2_config_obj.llm_model
        )
    else:
        # Use explicit model or fallback to base model
        actual_rapper_1_model = rapper_1_model if rapper_1_model else model_name
        actual_rapper_2_model = rapper_2_model if rapper_2_model else model_name
    actual_judge_model = (
        judge_model
        if judge_model
        else (judge_config.llm_model if use_config_defaults else model_name)
    )

    # Create battle instance with actual models
    # Note: rapper IDs will be set when judge creates them via AgentCall
    # Topic may be None if judge should decide
    battle = Battle(
        id=battle_id,
        topic=battle_topic if battle_topic else "To Be Decided",
        status=BattleStatus.WAITING,
        current_turn=TurnType.RAPPER_1,  # Set initial turn
        turn_number=0,
        rapper_1_id="",  # Will be set when call_rapper creates agent
        rapper_1_name=rapper_1_name,
        rapper_2_id="",
        rapper_2_name=rapper_2_name,
        judge_id="",
        rapper_1_model=actual_rapper_1_model,
        rapper_2_model=actual_rapper_2_model,
        judge_model=actual_judge_model,
        verses=[],
        max_rounds=max_rounds,
    )

    # Store rapper metadata for call_rapper tool to use
    battle_metadata = {
        "rapper_1_style": rapper_1_style,
        "rapper_1_desc": rapper_1_desc,
        "rapper_1_config": rapper_1_config,
        "rapper_2_style": rapper_2_style,
        "rapper_2_desc": rapper_2_desc,
        "rapper_2_config": rapper_2_config,
    }

    # Create session
    session = Session(environment=env)

    # Create namespaces for battle state
    session.state.create_namespace("battles")
    session.state.create_namespace("battle_metadata")

    judge_task_template = env.task_registry.get("judge_battle")

    # Create ONLY the judge agent - rappers will be created on-demand via AgentCall
    judge_params = deepcopy(judge_task_template.parameters)
    judge_params["battle_id"]["value"] = battle_id
    judge_params["battle_topic"]["value"] = battle_topic if battle_topic else ""

    judge_task = Task(
        name=judge_task_template.name,
        description=judge_task_template.description,
        parameters=judge_params,
        prompt=judge_task_template.prompt,
        tools=judge_task_template.tools,
        system_template=judge_task_template.system_template,
        llm_model=judge_task_template.llm_model,
    )

    session.create_agent_from_task(judge_config, judge_task)
    judge_agent = session.agents[-1]
    battle.judge_id = judge_agent.id

    # Now add battle and metadata to session state (using judge's agent ID)
    session.state.set("battles", battle_id, battle, judge_agent.id)
    session.state.set(
        "battle_metadata", battle_id, battle_metadata, judge_agent.id
    )

    return session, storage, battle


LIVE_DIR = f"{SAVE_DIR}/live"
DASHBOARD_PORT = 8888


def run_battle_simulation(
    session: Session,
    battle: Battle,
    max_rounds: int = 10,
    no_web: bool = False,
    dashboard_port: int = DASHBOARD_PORT,
) -> Battle:
    """Run the battle simulation."""
    # Start live dashboard
    write_live_dashboard(LIVE_DIR)
    save_battle_state(battle, LIVE_DIR)
    start_dashboard_server(LIVE_DIR, port=dashboard_port)

    dashboard_url = f"http://localhost:{dashboard_port}/"
    if not no_web:
        print(f"🌐 Live dashboard: {dashboard_url}")
        open_in_browser(dashboard_url)

    print("🎤" + "=" * 58 + "🎤")
    print(f"🔥 RAP BATTLE: {battle.topic.upper()} 🔥")
    print("🎤" + "=" * 58 + "🎤")
    print(f"🥊 {battle.rapper_1_name} VS {battle.rapper_2_name}")
    print(f"⏰ Session ID: {session.id}")
    print(f"🆔 Battle ID: {battle.id}")
    print("🎤" + "=" * 58 + "🎤")
    print()

    battle_id = battle.id
    judge_agent_id = battle.judge_id

    def _get_live_battle() -> Battle:
        """Re-read battle from session state to get latest updates."""
        live = session.state.get(
            "battles", battle_id, judge_agent_id, default=None
        )
        if isinstance(live, Battle):
            return live
        if isinstance(live, dict):
            return Battle.from_dict(live)
        return battle

    step_count = 0
    max_steps = 50 + max_rounds * 40  # Allow multiple steps per round
    prev_verse_count = 0

    while step_count < max_steps and battle.status != BattleStatus.FINISHED:
        # Print step in-place
        print(f"\r📍 Step {step_count + 1}...", end="", flush=True)

        # Let agents take their turns
        any_stepped = session.step()

        # Re-read battle from session state (tools may have replaced it)
        battle = _get_live_battle()

        # Save session after each step for monitoring
        if session.storage:
            session.storage.save_session(session)

        # Update live dashboard
        save_battle_state(battle, LIVE_DIR)

        if not any_stepped:
            print("\r⚠️  No agents stepped - ending simulation")
            break

        # Show battle progress - only print new verses
        if len(battle.verses) > prev_verse_count:
            latest_verse = battle.verses[-1]
            # Clear the step line and print verse on new line
            print(
                f"\r🎵 {latest_verse.rapper_name}: "
                f"{latest_verse.verse[:100]}..."
            )
            prev_verse_count = len(battle.verses)

        if battle.status == BattleStatus.FINISHED:
            print()
            print("🏁 BATTLE FINISHED! 🏁")
            if battle.result:
                print(f"🏆 WINNER: {battle.result.winner_name}")
                print(f"📝 Reasoning: {battle.result.reasoning}")
            break

        step_count += 1

    # Final re-read and save
    battle = _get_live_battle()
    save_battle_state(battle, LIVE_DIR)

    battle_save_path = Path(BATTLE_DIR) / f"{battle.id}.json"
    os.makedirs(BATTLE_DIR, exist_ok=True)
    battle.save(str(battle_save_path))

    print(f"💾 Battle saved to: {battle_save_path}")

    return battle


def main() -> int:
    """Run the RapMachine."""
    parser = argparse.ArgumentParser(description="Run RapMachine rap battles")
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Battle topic (default: None - judge will decide). Set to specify a topic.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=8,
        help="Maximum number of rounds (default: 8)",
    )
    parser.add_argument(
        "--rapper1-name",
        type=str,
        default="MC Flow",
        help="Name of first rapper",
    )
    parser.add_argument(
        "--rapper2-name",
        type=str,
        default="Rhyme Fire",
        help="Name of second rapper",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Run with the standard agent monitor for debugging",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Don't open the live battle dashboard in the browser",
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Monitor port (default: 8080)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="haiku-latest",
        help="Model to use for all agents (default: haiku-latest). Options: haiku-latest, sonnet-latest, llama3.1-8b, qwen3:8b, qwen2.5-0.5b",
    )
    parser.add_argument(
        "--rapper1-model",
        type=str,
        help="Model for rapper 1 (overrides --model for this rapper)",
    )
    parser.add_argument(
        "--rapper2-model",
        type=str,
        help="Model for rapper 2 (overrides --model for this rapper)",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        help="Model for judge (overrides --model for judge)",
    )
    parser.add_argument(
        "--random-agents",
        action="store_true",
        help="Use random rapper agent personalities instead of custom names",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Set the logging level (default: WARNING)",
    )

    args = parser.parse_args()

    # Reconfigure logging based on command line argument
    configure_logging(args.log_level)

    # Create directories
    os.makedirs(SAVE_DIR, exist_ok=True)
    os.makedirs(SESSION_DIR, exist_ok=True)
    os.makedirs(BATTLE_DIR, exist_ok=True)

    print("🎤 Initializing RapMachine...")

    # Model info is printed after session creation (when actual models are known)

    # Determine rappers to use
    if args.random_agents:
        rapper_1, rapper_2 = get_random_rappers()
        print("🎲 Random Battle Selected!")
        print(f"🥊 {rapper_1['name']} vs {rapper_2['name']}")
        print(f"   {rapper_1['name']}: {rapper_1['description']}")
        print(f"   {rapper_2['name']}: {rapper_2['description']}")

        session, storage, battle = create_battle_session(
            battle_topic=args.topic,
            rapper_1_name=rapper_1["name"],
            rapper_1_style=rapper_1["style"],
            rapper_1_desc=rapper_1["description"],
            rapper_2_name=rapper_2["name"],
            rapper_2_style=rapper_2["style"],
            rapper_2_desc=rapper_2["description"],
            model_name=args.model,
            rapper_1_config=rapper_1["config"],
            rapper_2_config=rapper_2["config"],
            rapper_1_model=args.rapper1_model,
            rapper_2_model=args.rapper2_model,
            judge_model=args.judge_model,
            use_config_defaults=True,
            max_rounds=args.rounds,
        )
    else:
        # Use custom names or defaults
        session, storage, battle = create_battle_session(
            battle_topic=args.topic,
            rapper_1_name=args.rapper1_name,
            rapper_2_name=args.rapper2_name,
            model_name=args.model,
            rapper_1_model=args.rapper1_model,
            rapper_2_model=args.rapper2_model,
            judge_model=args.judge_model,
            max_rounds=args.rounds,
        )

    print("🤖 Model Configuration:")
    print(f"   {battle.rapper_1_name}: {battle.rapper_1_model}")
    print(f"   {battle.rapper_2_name}: {battle.rapper_2_model}")
    print(f"   Judge: {battle.judge_model}")
    print(f"✅ Created battle session with {len(session.agents)} agent (judge)")
    print("   (Rappers will be created on-demand via AgentCall)")

    # Save initial session
    storage.save_session(session)

    # Optionally start the standard agent monitor
    monitor_process = None
    if args.monitor:
        print(f"🌐 Starting agent monitor at http://localhost:{args.port}/")
        print("⏳ Waiting for agent monitor to start...")
        monitor_process = start_monitor_dashboard(SESSION_DIR, args.port)
        print("🌐 Opening agent monitor in browser...")
        open_in_browser(f"http://localhost:{args.port}/")
        print()

    # Run battle simulation
    try:
        final_battle = run_battle_simulation(
            session, battle, args.rounds, no_web=args.no_web
        )

        print()
        print("🎉 RAP BATTLE COMPLETE! 🎉")

        if final_battle.status == BattleStatus.FINISHED and final_battle.result:
            print(f"👑 Champion: {final_battle.result.winner_name}")
            print(f"📊 Total verses: {len(final_battle.verses)}")
        else:
            print("⏰ Battle ended due to step limit")

        if monitor_process:
            print("\n🌐 Agent monitor still running - press Ctrl+C to exit")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down...")
                monitor_process.terminate()
                monitor_process.wait()

        return 0

    except KeyboardInterrupt:
        print("\n🛑 Battle interrupted by user")
        if monitor_process:
            monitor_process.terminate()
            monitor_process.wait()
        return 0
    except Exception as e:
        print(f"❌ Error during battle: {e}")
        if monitor_process:
            monitor_process.terminate()
            monitor_process.wait()
        raise e


if __name__ == "__main__":
    sys.exit(main())

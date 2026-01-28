"""Tool for judge to call a rapper to perform."""

from typing import Optional

from battle_utils import get_battle

from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.interaction.agent_result import AgentResult
from gimle.hugin.interaction.stack import Stack


def call_rapper(
    battle_id: str,
    rapper_number: int,
    stack: Stack,
    branch: Optional[str] = None,
) -> AgentCall:
    """
    Call a rapper to spit their verse.

    This tool creates an AgentCall to invoke a rapper agent. On the first call,
    a new rapper agent is created. On subsequent calls, the same rapper agent
    is reused, maintaining their context and memory of previous verses.

    Args:
        battle_id: ID of the battle
        rapper_number: Which rapper to call (1 or 2)
        stack: Agent stack (auto-injected)
        branch: Branch name (auto-injected)

    Returns:
        AgentCall interaction that will create or reuse the rapper agent
    """
    # Get battle and metadata from session state
    battle = get_battle(stack, battle_id)
    if battle is None:
        raise ValueError(f"Battle {battle_id} not found")

    metadata = stack.get_shared_state(battle_id, namespace="battle_metadata")
    if metadata is None:
        metadata = {}

    # Determine which rapper and get their info
    if rapper_number == 1:
        rapper_name = battle.rapper_1_name
        rapper_id_in_battle = battle.rapper_1_id
        config_name = metadata.get("rapper_1_config", "rapper")
        rapper_style = metadata.get(
            "rapper_1_style", "smooth, melodic flow with clever wordplay"
        )
        rapper_desc = metadata.get(
            "rapper_1_desc", f"{rapper_name} - A skilled lyricist"
        )
    elif rapper_number == 2:
        rapper_name = battle.rapper_2_name
        rapper_id_in_battle = battle.rapper_2_id
        config_name = metadata.get("rapper_2_config", "rapper")
        rapper_style = metadata.get(
            "rapper_2_style",
            "aggressive, hard-hitting style with powerful metaphors",
        )
        rapper_desc = metadata.get(
            "rapper_2_desc", f"{rapper_name} - An intense performer"
        )
    else:
        raise ValueError(
            f"Invalid rapper_number: {rapper_number}. Must be 1 or 2."
        )

    # Look for existing AgentCall/AgentResult interactions to find existing rapper agent
    existing_rapper_agent_id = None

    # Search through judge's stack for previous rapper calls
    for interaction in reversed(stack.interactions):
        # Check if this is an AgentResult from a rapper
        if isinstance(interaction, AgentResult):
            # Get the TaskResult to find the agent
            if interaction.task_result_id is None:
                raise ValueError("Task result id is required")
            task_result = stack.agent.session.get_interaction(
                interaction.task_result_id
            )
            if task_result:
                # Get the agent that completed this task
                result_agent_id = task_result.stack.agent.id
                # Check if this agent is the rapper we want
                if result_agent_id == rapper_id_in_battle:
                    existing_rapper_agent_id = result_agent_id
                    break

        # Also check AgentCall interactions to find rapper agents we created
        elif isinstance(interaction, AgentCall):
            if interaction.agent_id == rapper_id_in_battle:
                existing_rapper_agent_id = interaction.agent_id
                break

    # If we didn't find the rapper in our stack, check if they exist in the battle state
    # (This happens on the very first call when the rapper was pre-created in run.py)
    if existing_rapper_agent_id is None and rapper_id_in_battle:
        # Check if this agent exists in the session
        existing_agent = stack.agent.session.get_agent(rapper_id_in_battle)
        if existing_agent:
            existing_rapper_agent_id = rapper_id_in_battle

    # Get the rapper's configuration from environment
    try:
        # Try to find the specific personality config
        # The battle creation might have stored which config to use
        rapper_config = stack.agent.environment.config_registry.get(config_name)
    except ValueError:
        # Fall back to generic rapper config
        rapper_config = stack.agent.environment.config_registry.get("rapper")

    # Get the battle task template
    battle_task_template = stack.agent.environment.task_registry.get("battle")

    # Get opponent's last verse to provide context
    opponent_last_verse = None
    if battle.verses:
        # Find the most recent verse from the OTHER rapper
        for verse in reversed(battle.verses):
            if verse.rapper_name != rapper_name:
                opponent_last_verse = verse.verse
                break

    # Create task for the rapper
    rapper_task = battle_task_template.set_input_parameters(
        {
            "battle_id": battle_id,
            "battle_topic": battle.topic,
            "rapper_name": rapper_name,
            "rapper_description": rapper_desc,
            "rap_style": rapper_style,
            "opponent_last_verse": opponent_last_verse,  # Pass opponent's last verse
        }
    )

    # Create AgentCall - reuse existing rapper agent if found
    agent_call = AgentCall(
        stack=stack,
        config=rapper_config,
        task=rapper_task,
        agent_id=existing_rapper_agent_id,  # Will be None first time, then reused
    )

    # Note: The rapper agent ID will be set in the AgentCall after it's stepped
    # We can't update the battle state here because the agent hasn't been created yet
    # The battle state will be updated when the rapper uses spit_bars tool

    return agent_call

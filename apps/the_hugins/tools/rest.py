"""Rest tool for recovering energy without food."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from world.economy import ENERGY_RECOVERY_REST, MAX_ENERGY

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def rest_tool(
    world_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Rest to recover a small amount of energy.

    Args:
        world_id: The ID of the world
        reason: Why you are performing this action
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with success status and energy information
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    agent_id = stack.agent.id

    # Get world from environment
    env_vars = stack.agent.environment.env_vars
    if "worlds" not in env_vars:
        return ToolResponse(
            is_error=True, content={"error": "No worlds found in environment"}
        )

    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    if world_id not in worlds:
        return ToolResponse(
            is_error=True, content={"error": f"World '{world_id}' not found"}
        )

    world = cast("World", worlds[world_id])

    # Get creature
    creature = world.get_creature(agent_id)
    if not creature:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    # Restore energy
    old_energy = creature.energy
    actual_gained = creature.add_energy(ENERGY_RECOVERY_REST)

    # Log the action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="rest",
        description=f"Rested and gained {actual_gained} energy",
        timestamp=world.tick,
        location=creature.position,
        details={
            "energy_gained": actual_gained,
            "old_energy": old_energy,
            "new_energy": creature.energy,
        },
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "energy_gained": actual_gained,
            "old_energy": old_energy,
            "new_energy": creature.energy,
            "max_energy": MAX_ENERGY,
            "message": (
                f"You rested and gained {actual_gained} energy. "
                f"Energy: {creature.energy}/{MAX_ENERGY}"
            ),
        },
    )

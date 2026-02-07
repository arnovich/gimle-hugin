"""Share rumor tool for spreading information about others."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def share_rumor_tool(
    world_id: str,
    creature_name: str,
    about_creature: str,
    rumor: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Share a rumor about a third creature with a nearby creature.

    Args:
        world_id: The ID of the world
        creature_name: Name of the creature to share the rumor with
        about_creature: Name of the creature the rumor is about
        rumor: The rumor text to share
        reason: Why you are performing this action
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with rumor sharing result
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
            is_error=True,
            content={"error": "No worlds found in environment"},
        )

    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    if world_id not in worlds:
        return ToolResponse(
            is_error=True,
            content={"error": f"World '{world_id}' not found"},
        )

    world = cast("World", worlds[world_id])

    # Get speaker
    speaker = world.get_creature(agent_id)
    if not speaker:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    # Get listener
    listener = world.get_creature_by_name(creature_name)
    if not listener:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature '{creature_name}' not found"},
        )

    # Can't share with yourself
    if listener.agent_id == agent_id:
        return ToolResponse(
            is_error=True,
            content={"error": "You cannot share rumors with yourself."},
        )

    # Check proximity (within 2 cells)
    sx, sy = speaker.position
    lx, ly = listener.position
    if abs(sx - lx) > 2 or abs(sy - ly) > 2:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"'{creature_name}' is too far away. "
                    "Must be within 2 cells."
                )
            },
        )

    # Verify the subject creature exists
    subject = world.get_creature_by_name(about_creature)
    if not subject:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"Creature '{about_creature}' not found " "in this world."
                )
            },
        )

    # Can't share rumor about the listener
    if subject.agent_id == listener.agent_id:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "You cannot share a rumor about someone "
                    "with that same person."
                )
            },
        )

    # Add memory to listener about the subject
    world.add_memory_to_creature(
        listener.agent_id,
        "heard_rumor",
        f"{speaker.name} said about {about_creature}: '{rumor}'",
        location=(lx, ly),
        related_creature=about_creature,
        importance=5,
    )

    # Sharing rumors builds rapport between speaker and listener
    speaker.update_relationship(creature_name, "known", 1)
    listener.update_relationship(speaker.name, "known", 1)

    # Log the action
    world.action_log.add_action(
        creature_name=speaker.name,
        agent_id=agent_id,
        action_type="share_rumor",
        description=(
            f"Shared a rumor about {about_creature} " f"with {creature_name}"
        ),
        timestamp=world.tick,
        location=(sx, sy),
        details={
            "listener": creature_name,
            "about": about_creature,
            "rumor": rumor,
        },
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "listener": creature_name,
            "about": about_creature,
            "rumor": rumor,
            "message": (
                f"You shared a rumor about {about_creature} "
                f"with {creature_name}."
            ),
        },
    )

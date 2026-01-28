"""Tool for creatures to check their inventory."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def get_inventory_tool(
    world_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Check your inventory to see what items you are carrying.

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        List of items in the creature's inventory
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    agent_id = stack.agent.id

    # Get world from environment
    env_vars = stack.agent.environment.env_vars
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

    # Get inventory items
    inventory = creature.get_inventory()
    items = [
        {
            "name": item.name,
            "description": item.description,
            "id": item.id,
        }
        for item in inventory
    ]

    # Create summary
    if items:
        item_names = [item["name"] for item in items]
        summary = (
            f"You are carrying {len(items)} item(s): {', '.join(item_names)}"
        )
    else:
        summary = "Your inventory is empty. You are not carrying any items."

    return ToolResponse(
        is_error=False,
        content={
            "inventory": items,
            "count": len(items),
            "summary": summary,
        },
    )

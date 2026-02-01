"""Get status tool for checking energy and money."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from world.economy import FOOD_ENERGY, MAX_ENERGY

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def get_status_tool(
    world_id: str,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Check your current energy, money, and food in inventory.

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with energy, money, and food status
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

    # Get food items in inventory
    food_items = []
    for item in creature.inventory:
        if item.name in FOOD_ENERGY:
            food_items.append(
                {
                    "name": item.name,
                    "energy_value": FOOD_ENERGY[item.name],
                }
            )

    # Calculate total food energy available
    total_food_energy = sum(f["energy_value"] for f in food_items)

    # Get pending trades
    pending_trades = [
        {
            "id": t.id,
            "from": t.from_creature,
            "action": t.action,
            "item": t.item_name,
            "price": t.price,
        }
        for t in creature.pending_trades
    ]

    # Determine status messages
    energy_status = "good"
    if creature.energy < 20:
        energy_status = "critical"
    elif creature.energy < 50:
        energy_status = "low"

    return ToolResponse(
        is_error=False,
        content={
            "energy": creature.energy,
            "max_energy": MAX_ENERGY,
            "energy_status": energy_status,
            "money": creature.money,
            "food_in_inventory": food_items,
            "total_food_energy": total_food_energy,
            "pending_trades": pending_trades,
            "message": (
                f"Energy: {creature.energy}/{MAX_ENERGY} ({energy_status}), "
                f"Money: {creature.money}, "
                f"Food items: {len(food_items)} "
                f"(total energy: {total_food_energy})"
            ),
        },
    )

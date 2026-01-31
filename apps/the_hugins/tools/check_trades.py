"""Check trades tool for viewing pending trade offers."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def check_trades_tool(
    world_id: str,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Check your pending trade offers from other creatures.

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with pending trade offers
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

    # Format pending trades
    trades = []
    for offer in creature.pending_trades:
        # Explain what accepting means for the recipient
        if offer.action == "buy":
            # Proposer wants to buy -> recipient would sell
            explanation = (
                f"{offer.from_creature} wants to BUY your {offer.item_name} "
                f"for {offer.price} coins. If you accept, you give the item "
                f"and receive {offer.price} coins."
            )
        else:  # sell
            # Proposer wants to sell -> recipient would buy
            explanation = (
                f"{offer.from_creature} wants to SELL you a {offer.item_name} "
                f"for {offer.price} coins. If you accept, you pay {offer.price} "
                f"coins and receive the item."
            )

        trades.append({
            "trade_id": offer.id,
            "from_creature": offer.from_creature,
            "their_action": offer.action,
            "item": offer.item_name,
            "price": offer.price,
            "created_tick": offer.created_tick,
            "explanation": explanation,
        })

    if not trades:
        message = "You have no pending trade offers."
    else:
        message = f"You have {len(trades)} pending trade offer(s)."

    return ToolResponse(
        is_error=False,
        content={
            "pending_trades": trades,
            "count": len(trades),
            "your_money": creature.money,
            "message": message,
        },
    )

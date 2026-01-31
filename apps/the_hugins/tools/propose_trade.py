"""Propose trade tool for offering to buy/sell with another creature."""

import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from world.economy import ITEM_PRICES, TradeOffer

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def propose_trade_tool(
    world_id: str,
    creature_name: str,
    action: str,
    item_name: str,
    price: Optional[int] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Propose a trade with a nearby creature.

    Args:
        world_id: The ID of the world
        creature_name: Name of the creature to trade with
        action: "buy" or "sell" (from your perspective)
        item_name: Name of the item to trade
        price: Optional price (defaults to base item price)
        reason: Why you are performing this action
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with trade proposal status
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

    # Get proposer creature
    proposer = world.get_creature(agent_id)
    if not proposer:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    # Get target creature
    target = world.get_creature_by_name(creature_name)
    if not target:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature '{creature_name}' not found"},
        )

    # Check if target is nearby (within 2 cells)
    px, py = proposer.position
    tx, ty = target.position
    if abs(px - tx) > 2 or abs(py - ty) > 2:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"'{creature_name}' is too far away. "
                    "You can only trade with creatures within 2 cells."
                ),
                "your_position": {"x": px, "y": py},
                "their_position": {"x": tx, "y": ty},
            },
        )

    # Validate action
    action_lower = action.lower()
    if action_lower not in ("buy", "sell"):
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Invalid action '{action}'. Use 'buy' or 'sell'."
            },
        )

    # Determine price
    if price is None:
        price = ITEM_PRICES.get(item_name, 10)  # Default price if not known

    # Validate the trade can potentially happen
    if action_lower == "sell":
        # Check if proposer has the item
        has_item = any(obj.name == item_name for obj in proposer.inventory)
        if not has_item:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"You don't have '{item_name}' to sell. "
                        "Check your inventory."
                    ),
                    "your_inventory": [obj.name for obj in proposer.inventory],
                },
            )
    else:  # buy
        # Check if proposer has enough money
        if proposer.money < price:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"You don't have enough money to buy at price {price}. "
                        f"You have {proposer.money}."
                    ),
                    "your_money": proposer.money,
                    "required": price,
                },
            )

    # Create trade offer
    trade_id = str(uuid.uuid4())[:8]
    offer = TradeOffer(
        id=trade_id,
        from_creature=proposer.name,
        action=action_lower,
        item_name=item_name,
        price=price,
        created_tick=world.tick,
    )

    # Add to target's pending trades
    target.add_trade_offer(offer)

    # Log the action
    world.action_log.add_action(
        creature_name=proposer.name,
        agent_id=agent_id,
        action_type="propose_trade",
        description=(
            f"Proposed to {action_lower} {item_name} for {price} "
            f"with {creature_name}"
        ),
        timestamp=world.tick,
        location=proposer.position,
        details={
            "trade_id": trade_id,
            "target_creature": creature_name,
            "action": action_lower,
            "item": item_name,
            "price": price,
        },
        reason=reason,
    )

    # Update relationship
    proposer.update_relationship(creature_name, "trading_partner", 1)

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "trade_id": trade_id,
            "action": action_lower,
            "item": item_name,
            "price": price,
            "to_creature": creature_name,
            "message": (
                f"Trade offer sent to {creature_name}: "
                f"{action_lower} {item_name} for {price} coins. "
                f"They will need to accept or reject the offer."
            ),
        },
    )

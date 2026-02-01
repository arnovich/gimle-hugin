"""Respond trade tool for accepting or rejecting trade offers."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def respond_trade_tool(
    world_id: str,
    trade_id: str,
    accept: bool,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Accept or reject a pending trade offer.

    Args:
        world_id: The ID of the world
        trade_id: The ID of the trade offer
        accept: True to accept, False to reject
        reason: Why you are performing this action
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with trade result
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

    # Get responder creature
    responder = world.get_creature(agent_id)
    if not responder:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    # Find the trade offer
    offer = responder.get_trade_offer(trade_id)
    if not offer:
        available_trades = [t.id for t in responder.pending_trades]
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Trade offer '{trade_id}' not found.",
                "available_trade_ids": available_trades,
            },
        )

    # Get the proposer creature
    proposer = world.get_creature_by_name(offer.from_creature)
    if not proposer:
        # Proposer left the world, remove the trade
        responder.remove_trade_offer(trade_id)
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"Creature '{offer.from_creature}' is no longer in the world. "
                    "Trade cancelled."
                )
            },
        )

    # If rejecting, just remove the offer
    if not accept:
        responder.remove_trade_offer(trade_id)

        # Log the rejection
        world.action_log.add_action(
            creature_name=responder.name,
            agent_id=agent_id,
            action_type="reject_trade",
            description=f"Rejected trade offer from {offer.from_creature}",
            timestamp=world.tick,
            location=responder.position,
            details={
                "trade_id": trade_id,
                "from_creature": offer.from_creature,
                "action": offer.action,
                "item": offer.item_name,
                "price": offer.price,
            },
            reason=reason,
        )

        return ToolResponse(
            is_error=False,
            content={
                "success": True,
                "accepted": False,
                "message": (
                    f"Trade rejected. {offer.from_creature}'s offer to "
                    f"{offer.action} {offer.item_name} for {offer.price} "
                    "has been declined."
                ),
            },
        )

    # Accept the trade - validate and execute
    if offer.action == "buy":
        # Proposer wants to buy -> responder sells
        # Responder needs the item, proposer needs the money
        responder_item = responder.remove_from_inventory(offer.item_name)
        if not responder_item:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"You don't have '{offer.item_name}' to sell. "
                        "Trade cannot be completed."
                    ),
                    "your_inventory": [obj.name for obj in responder.inventory],
                },
            )

        if proposer.money < offer.price:
            # Return item to responder
            responder.add_to_inventory(responder_item)
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"{offer.from_creature} doesn't have enough money "
                        f"({proposer.money} < {offer.price}). "
                        "Trade cannot be completed."
                    ),
                },
            )

        # Execute the trade
        proposer.remove_money(offer.price)
        responder.add_money(offer.price)
        proposer.add_to_inventory(responder_item)

        trade_description = (
            f"Sold {offer.item_name} to {offer.from_creature} for {offer.price}"
        )

    else:  # sell
        # Proposer wants to sell -> responder buys
        # Responder needs the money, proposer needs the item
        if responder.money < offer.price:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"You don't have enough money to buy "
                        f"({responder.money} < {offer.price}). "
                        "Trade cannot be completed."
                    ),
                    "your_money": responder.money,
                    "required": offer.price,
                },
            )

        proposer_item = proposer.remove_from_inventory(offer.item_name)
        if not proposer_item:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"{offer.from_creature} no longer has '{offer.item_name}'. "
                        "Trade cannot be completed."
                    ),
                },
            )

        # Execute the trade
        responder.remove_money(offer.price)
        proposer.add_money(offer.price)
        responder.add_to_inventory(proposer_item)

        trade_description = (
            f"Bought {offer.item_name} from {offer.from_creature} "
            f"for {offer.price}"
        )

    # Remove the trade offer
    responder.remove_trade_offer(trade_id)

    # Log the acceptance
    world.action_log.add_action(
        creature_name=responder.name,
        agent_id=agent_id,
        action_type="accept_trade",
        description=trade_description,
        timestamp=world.tick,
        location=responder.position,
        details={
            "trade_id": trade_id,
            "from_creature": offer.from_creature,
            "action": offer.action,
            "item": offer.item_name,
            "price": offer.price,
        },
        reason=reason,
    )

    # Add memories for both creatures
    world.add_memory_to_creature(
        agent_id,
        "completed_trade",
        trade_description,
        location=responder.position,
        related_creature=offer.from_creature,
        related_item=offer.item_name,
        importance=5,
    )

    # Update relationships
    responder.update_relationship(offer.from_creature, "trading_partner", 2)
    proposer.update_relationship(responder.name, "trading_partner", 2)

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "accepted": True,
            "item": offer.item_name,
            "price": offer.price,
            "your_new_money": responder.money,
            "message": f"Trade completed! {trade_description}",
        },
    )

"""Tool for creatures to explore multiple options before deciding."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def explore_options_tool(
    world_id: str,
    options: List[str],
    question: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Explore multiple options by creating parallel branches.

    Use this when you face a decision and want to mentally simulate
    different choices before committing. Each option creates a branch
    that explores what would happen if you chose that path.

    Args:
        world_id: The ID of the world
        options: List of options to explore (2-3 options max)
        question: The question you're trying to answer
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Confirmation of branches created for exploration
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    if not options:
        return ToolResponse(
            is_error=True,
            content={
                "error": "You must provide at least one option to explore"
            },
        )

    # Limit to 3 branches to avoid overwhelming the system
    if len(options) > 3:
        options = options[:3]

    if len(options) < 2:
        return ToolResponse(
            is_error=True,
            content={
                "error": "You need at least 2 options to explore. "
                "For a single choice, just do it directly."
            },
        )

    # Get task definition for creating branches
    task_def_interaction = stack.get_task_definition_interaction()
    if task_def_interaction is None:
        return ToolResponse(
            is_error=True,
            content={"error": "No task definition found"},
        )

    # Get creature info for context
    agent_id = stack.agent.id
    env_vars = stack.agent.environment.env_vars
    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    world = cast("World", worlds.get(world_id))

    creature_name = "creature"
    if world:
        creature = world.get_creature(agent_id)
        if creature:
            creature_name = creature.name

    # Create branches for each option
    branches_created = []
    for i, option in enumerate(options):
        # Create a safe branch name
        safe_name = option.lower().replace(" ", "_")[:20]
        branch_name = f"option_{i}_{safe_name}"

        # Create task definition for this branch
        branch_prompt = f"""You are {creature_name}, exploring what would happen if you chose: "{option}"

Question being considered: {question}

Imagine you chose this option. Think through:
1. What would happen immediately?
2. What are the benefits of this choice?
3. What are the risks or downsides?
4. How does this align with your personality and goals?

After considering this option, use the `finish` tool to summarize your evaluation.
"""

        # Create a new task with the branch prompt
        original_task = task_def_interaction.task
        branch_task = Task(
            name=(
                f"{original_task.name}_{branch_name}"
                if original_task
                else branch_name
            ),
            description=f"Explore option: {option}",
            parameters=original_task.parameters if original_task else {},
            prompt=branch_prompt,
            tools=original_task.tools if original_task else None,
        )
        task_def = TaskDefinition.create_from_task(
            task=branch_task,
            stack=stack,
            caller=None,
        )

        stack.add_interaction(task_def, branch=branch_name)
        branches_created.append({"branch": branch_name, "option": option})

    # Log action if world available
    if world:
        creature = world.get_creature(agent_id)
        if creature:
            world.action_log.add_action(
                creature_name=creature.name,
                agent_id=agent_id,
                action_type="explore_options",
                description=f"Considering options: {', '.join(options)}",
                timestamp=world.tick,
                location=creature.position,
                details={"question": question, "options": options},
                reason=reason,
            )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "question": question,
            "branches_created": branches_created,
            "count": len(branches_created),
            "message": f"Created {len(branches_created)} branches to explore your options. "
            "Each branch will evaluate one option. Use `evaluate_options` "
            "when ready to compare results and decide.",
        },
    )

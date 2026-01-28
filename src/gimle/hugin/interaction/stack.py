"""Gimle Stack."""

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.external_input import ExternalInput
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.oracle_response import OracleResponse
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.llm.prompt.message import (
    render_assistant_message,
    render_user_message,
)
from gimle.hugin.tools.tool import Tool

if TYPE_CHECKING:
    from gimle.hugin.agent.agent import Agent
    from gimle.hugin.interaction.task_definition import TaskDefinition
    from gimle.hugin.interaction.tool_call import ToolCall
    from gimle.hugin.interaction.tool_result import ToolResult
    from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)

# TODO the stack manages branches


class Stack:
    """A stack is a collection of interactions.

    Attributes:
        interactions: The interactions on the stack.
        agent: The agent that owns the stack.
        branches: The branches on the stack.
        queued_interactions: The interactions that are queued to be added to the stack.
    """

    def __init__(
        self, agent: "Agent", interactions: Optional[List[Interaction]] = None
    ):
        """Initialize a stack."""
        self.interactions: List[Interaction] = (
            interactions if interactions else []
        )
        self.agent: Agent = agent
        self.branches: Dict[str, List[Interaction]] = {}
        self.queued_interactions: List[Interaction] = []
        self._step_lock: bool = False

    @property
    def artifacts(self) -> List[Artifact]:
        """Get the artifacts for the stack.

        Returns:
            The artifacts for the stack.
        """
        return [
            artifact
            for interaction in self.interactions
            for artifact in interaction.artifacts
        ]

    def pretty_rendered_context(self, branch: Optional[str] = None) -> str:
        """Pretty print the stack.

        Args:
            branch: The branch to render the context for.

        Returns:
            The pretty printed context.
        """
        rendered = self.render_stack_context(branch=branch)
        pretty_rendered = ""
        for interaction in rendered:
            pretty_rendered += (
                f"\n{interaction['role'].upper()}: {interaction['content']}"
            )
        return pretty_rendered

    def ninteractions(self) -> int:
        """Get the length of the stack.

        Returns:
            The length of the stack.
        """
        return len(self.interactions)

    def get_active_branches(self) -> List[Optional[str]]:
        """Get all active branch names from interactions.

        Returns a list of unique branch names. None represents the main branch.
        Branches are returned in order of first appearance.

        Returns:
            A list of unique branch names. None represents the main branch.
            Branches are returned in order of first appearance.
        """
        seen: set[Optional[str]] = set()
        branches: List[Optional[str]] = []
        for interaction in self.interactions:
            branch = interaction.branch
            if branch not in seen:
                seen.add(branch)
                branches.append(branch)
        return branches

    def get_branch_fork_index(self, branch: str) -> int:
        """Get the index where a branch forks from the main branch.

        The fork point is the index of the first interaction on that branch.
        All main branch (None) interactions before this point are visible
        to the branch.

        Args:
            branch: The branch name to find the fork point for

        Returns:
            The index of the first interaction on this branch

        Raises:
            ValueError: If the branch doesn't exist
        """
        for i, interaction in enumerate(self.interactions):
            if interaction.branch == branch:
                return i
        raise ValueError(f"Branch {branch} not found in stack")

    def get_branch_interactions(
        self, branch: Optional[str] = None
    ) -> List[Interaction]:
        """Get interactions visible to a specific branch.

        For the main branch (None): returns all interactions with branch=None.
        For a named branch: returns all main branch interactions up to the
        fork point, then all interactions on that branch.

        Args:
            branch: The branch name, or None for main branch

        Returns:
            List of interactions visible to this branch
        """
        if branch is None:
            # Main branch sees only main branch interactions
            return [i for i in self.interactions if i.branch is None]

        # Find the fork point for this branch
        try:
            fork_index = self.get_branch_fork_index(branch)
        except ValueError:
            # Branch doesn't exist, return empty list
            return []

        result = []
        for i, interaction in enumerate(self.interactions):
            if i < fork_index:
                # Before fork: include only main branch interactions
                if interaction.branch is None:
                    result.append(interaction)
            else:
                # At or after fork: include only this branch's interactions
                if interaction.branch == branch:
                    result.append(interaction)
        return result

    def get_last_interaction_for_branch(
        self, branch: Optional[str] = None
    ) -> Optional[Interaction]:
        """Get the last interaction for a specific branch.

        Args:
            branch: The branch name, or None for main branch

        Returns:
            The last interaction on this branch, or None if no interactions
        """
        for interaction in reversed(self.interactions):
            if interaction.branch == branch:
                return interaction
        return None

    def is_branch_complete(self, branch: Optional[str] = None) -> bool:
        """Check if a branch has completed and in Waiting state.

        Args:
            branch: The branch name, or None for main branch

        Returns:
            True if the branch's last interaction is a Waiting
        """
        last = self.get_last_interaction_for_branch(branch)
        return isinstance(last, Waiting)

    def render_stack_context(
        self, branch: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Render the stack context for a specific branch.

        Filters out interactions where include_in_context=False (for
        deterministic tool chaining that should be hidden from the LLM).

        Args:
            branch: The branch to render context for. If None, renders
                    the main branch context. If not specified, renders
                    all interactions (legacy behavior for backwards compat).

        Returns:
            A list of interactions rendered as a list of dictionaries.
            Each dictionary contains the role and content of the interaction.
            The list is reversed, so the last interaction is first.
        """
        # Get interactions for this branch
        interactions_to_render = self.get_branch_interactions(branch)
        interactions_messages = []
        append_to_context = True
        reduced = False
        message_groups = {}
        total_message_groups = 0
        finished = False
        # Track the last AskOracle's include_in_context for its OracleResponse
        last_ask_oracle_include = True
        logger.debug(f"Rendering stack context for branch: {branch}")
        for interaction in reversed(interactions_to_render):
            if isinstance(interaction, TaskResult):
                finished = True
                continue
            if isinstance(interaction, AskOracle):
                if interaction.prompt is None:
                    raise ValueError("AskOracle prompt is None")

                # Check explicit include_in_context flag first
                if not interaction.include_in_context:
                    append_to_context = False
                    last_ask_oracle_include = False
                else:
                    append_to_context = True
                    last_ask_oracle_include = True
                    reduced = False
                    tool_call = interaction.prompt.tool_name
                    if tool_call:
                        if tool_call not in message_groups:
                            message_groups[tool_call] = 0
                        message_groups[tool_call] += 1
                        total_message_groups += 1
                        if tool_call in self.get_tools():
                            tool = Tool.get_tool(tool_call)
                            if (
                                tool
                                and tool.options.include_only_in_context_window
                                and (
                                    tool.options.context_window
                                    < message_groups[tool_call]
                                    or finished
                                )
                            ):
                                append_to_context = False
                            elif (
                                tool
                                and tool.options.reduced_context_window_enabled
                                and tool.options.reduced_context_window
                                < total_message_groups
                            ):
                                if interaction.template_inputs is None:
                                    raise ValueError(
                                        "AskOracle template inputs is None"
                                    )
                                if "error" in interaction.template_inputs:
                                    append_to_context = False
                                else:
                                    reduced = True
            elif isinstance(interaction, OracleResponse):
                # OracleResponse inherits include_in_context from its AskOracle
                if not last_ask_oracle_include:
                    continue  # Skip this OracleResponse
            if (
                isinstance(interaction, (AskOracle, OracleResponse))
                and append_to_context
            ):
                if isinstance(interaction, AskOracle):
                    interactions_messages.append(
                        {
                            "role": "user",
                            "content": render_user_message(
                                interaction, reduced
                            ),
                        }
                    )
                else:
                    interactions_messages.append(
                        {
                            "role": "assistant",
                            "content": render_assistant_message(
                                interaction, reduced
                            ),
                        }
                    )
        return [i for i in reversed(interactions_messages)]

    def add_interaction(
        self, interaction: Interaction, branch: Optional[str] = None
    ) -> None:
        """Add an interaction to the stack.

        Args:
            interaction: The interaction to add.
            branch: The branch to add the interaction to.
        """
        if branch:
            interaction.branch = branch
        self.interactions.append(interaction)

        # Log interaction creation
        interaction_type = interaction.__class__.__name__
        interaction_id = getattr(interaction, "uuid", "unknown")
        agent_id = getattr(self.agent, "id", "unknown")

        # Add context for specific interaction types
        context = ""
        if hasattr(interaction, "tool"):
            context = f" tool={interaction.tool}"
        elif hasattr(interaction, "task"):
            context = f" task={interaction.task.name}"
        elif hasattr(interaction, "finish_type"):
            context = f" finish_type={interaction.finish_type}"

        logger.debug(
            f"Created interaction: {interaction_type} (id: {interaction_id}, agent: {agent_id}) branch: {branch} {context} "
            f"[stack size: {len(self.interactions)}]"
        )

        if self.queued_interactions and isinstance(interaction, AskOracle):
            logger.debug(
                f"Adding {len(self.queued_interactions)} queued interactions to the stack"
            )
            self.interactions.extend(self.queued_interactions)
            self.queued_interactions = []

    def step(self) -> bool:
        """Step all active branches in the stack.

        Steps the last interaction on each branch that hasn't completed.
        Returns True if any branch was stepped, False if all branches
        are complete or the stack is empty.

        Returns:
            True if any branch was stepped, False if all branches
            are complete or the stack is empty.
        """
        if self._step_lock:
            raise ValueError("Step lock is active")
        self._step_lock = True
        logger.debug(f"Stepping stack {self.agent.id}")

        if not self.interactions:
            self._step_lock = False
            return False

        # Get all active branches
        branches = self.get_active_branches()

        # Step each branch that isn't complete
        any_stepped = False
        for branch in branches:
            # if self.is_branch_complete(branch):
            #     logger.debug(f"Branch {branch} is complete, skipping")
            #     continue

            last_interaction = self.get_last_interaction_for_branch(branch)
            if last_interaction is None:
                continue

            logger.debug(
                f"Stepping branch {branch}: "
                f"{last_interaction.__class__.__name__}"
            )
            step_result = last_interaction.step()
            if step_result:
                any_stepped = True

        self._step_lock = False
        return any_stepped

    def insert_external_input(self, input: str) -> None:
        """Insert a human interaction into the stack.

        This creates a ExternalInput interaction with the input, which
        will then create an AskOracle to process the external input.

        Args:
            input: The input from the external source to the agent
        """
        external_input = ExternalInput(stack=self, input=input)
        self.queued_interactions.append(external_input)

    def _get_last_interaction_of_type(
        self,
        interaction_type: Type[Interaction],
        start_interaction_uuid: Optional[str] = None,
        end_interaction_uuid: Optional[str] = None,
        attr_name: Optional[str] = None,
        attr_value: Optional[Any] = None,
        filter_by_attr: bool = False,
    ) -> Optional[Interaction]:
        """Get the last interaction of a given type for the stack.

        Args:
            interaction_type: The type of interaction to find.
            start_interaction_uuid: UUID to start searching from.
            end_interaction_uuid: UUID to end searching at.
            attr_name: Name of attribute to filter by.
            attr_value: Value the attribute should have (can be None).
            filter_by_attr: If True, filter by attr_name/attr_value even if
                attr_value is None.

        Returns:
            The last interaction of the given type, or None if not found.
        """
        if not self.interactions:
            return None
        within_window = end_interaction_uuid is None
        for interaction in reversed(self.interactions):
            if (
                start_interaction_uuid is not None
                and interaction.uuid == start_interaction_uuid
            ):
                within_window = False
            if (
                end_interaction_uuid is not None
                and interaction.uuid == end_interaction_uuid
            ):
                within_window = True
            if not within_window:
                continue
            if isinstance(interaction, interaction_type):
                # Filter by attribute if requested
                if attr_name is not None and (
                    attr_value is not None or filter_by_attr
                ):
                    if getattr(interaction, attr_name) != attr_value:
                        continue
                return interaction
        return None

    def get_task_definition_interaction(
        self,
        current_interaction_uuid: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Optional["TaskDefinition"]:
        """Get the TaskDefinition interaction for the stack.

        If branch is specified (including None for main branch), looks for a
        TaskDefinition on that specific branch.

        Args:
            current_interaction_uuid: The UUID of the current interaction.
            branch: The branch to look for the TaskDefinition on.

        Returns:
            The TaskDefinition interaction, or None if not found.
        """
        from gimle.hugin.interaction.task_definition import TaskDefinition

        # Look for TaskDefinition on the specified branch (including None for main)
        # Use filter_by_attr=True to match even when branch=None
        interaction = self._get_last_interaction_of_type(
            TaskDefinition,
            end_interaction_uuid=current_interaction_uuid,
            attr_name="branch",
            attr_value=branch,
            filter_by_attr=True,
        )
        if interaction is not None:
            if not isinstance(interaction, TaskDefinition):
                raise ValueError("Last interaction is not a TaskDefinition")
            return interaction

        # If looking for a specific branch (not main) and not found,
        # fall back to main branch's TaskDefinition
        if branch is not None:
            interaction = self._get_last_interaction_of_type(
                TaskDefinition,
                end_interaction_uuid=current_interaction_uuid,
                attr_name="branch",
                attr_value=None,
                filter_by_attr=True,
            )
            if interaction is not None:
                if not isinstance(interaction, TaskDefinition):
                    raise ValueError("Last interaction is not a TaskDefinition")
                return interaction

        return None

    def get_last_tool_call_interaction(self) -> Optional["ToolCall"]:
        """Get the last ToolCall interaction for the stack.

        Returns:
            The last ToolCall interaction, or None if not found.
        """
        from gimle.hugin.interaction.tool_call import ToolCall

        interaction = self._get_last_interaction_of_type(ToolCall)
        if interaction is not None and not isinstance(interaction, ToolCall):
            # should never happen, purely for type checking
            raise ValueError("Last interaction is not a ToolCall")
        return interaction

    def get_last_tool_result_interaction(
        self, tool_name: Optional[str] = None
    ) -> Optional["ToolResult"]:
        """Get the last ToolResult interaction for the stack.

        Args:
            tool_name: The name of the tool to look for.

        Returns:
            The last ToolResult interaction, or None if not found.
        """
        from gimle.hugin.interaction.tool_result import ToolResult

        interaction = self._get_last_interaction_of_type(
            ToolResult, attr_name="tool_name", attr_value=tool_name
        )
        if interaction is not None and not isinstance(interaction, ToolResult):
            # should never happen, purely for type checking
            raise ValueError("Last interaction is not a ToolResult")
        return interaction

    def get_task_definition(
        self,
        current_interaction_uuid: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Optional[Task]:
        """Get the task definition for the stack.

        If branch is specified, looks for a TaskDefinition on that branch first.

        Args:
            current_interaction_uuid: The UUID of the current interaction.
            branch: The branch to look for the TaskDefinition on.

        Returns:
            The task definition, or None if not found.
        """
        task_def = self.get_task_definition_interaction(
            current_interaction_uuid=current_interaction_uuid,
            branch=branch,
        )
        if task_def is None:
            # If we have interactions but no TaskDefinition, raise an error
            if self.interactions:
                raise ValueError("No task definition found on the stack")
            # Empty stack returns None
            logger.warning("No interactions found on the stack")
            return None
        return task_def.task

    def get_tools(
        self,
        current_interaction_uuid: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[Tool]:
        """Get the tools for the stack.

        If a branch is specified, looks for a TaskDefinition on that branch first.
        If the task has tools defined, those REPLACE the config tools (not extend).

        Args:
            current_interaction_uuid: The UUID of the current interaction.
            branch: The branch to look for the TaskDefinition on.

        Returns:
            A list of tools.
        """
        task_definition = self.get_task_definition(
            current_interaction_uuid=current_interaction_uuid,
            branch=branch,
        )
        tool_names = []
        if task_definition and task_definition.tools:
            # Task has tools defined - use ONLY those (replace config tools)
            tool_names = list(task_definition.tools)
        elif self.agent.config.tools:
            # No task tools - fall back to config tools
            tool_names = list(self.agent.config.tools)

        if not tool_names:
            logger.warning("No tools found on the stack")
        tools = [
            Tool.get_tool(tool_name, throw_error=False)
            for tool_name in set(tool_names)
        ]
        return [
            tool
            for tool in tools
            if tool
            and (self.agent.config.interactive or not tool.is_interactive)
        ]

    def get_system_template(
        self,
        current_interaction_uuid: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> str:
        """Get the system template for the stack.

        If branch is specified, looks for a TaskDefinition on that branch first.

        Args:
            current_interaction_uuid: The UUID of the current interaction.
            branch: The branch to look for the TaskDefinition on.

        Returns:
            The system template, or None if not found.
        """
        task_definition = self.get_task_definition(
            current_interaction_uuid=current_interaction_uuid,
            branch=branch,
        )
        system_template = None
        if task_definition:
            system_template = task_definition.system_template
        if system_template is None:
            system_template = self.agent.config.system_template
        return system_template

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the stack to a dictionary.

        Returns:
            A dictionary representation of the stack.
        """
        return {
            "interactions": [
                interaction.id for interaction in self.interactions
            ],
            "artifacts": [artifact.id for artifact in self.artifacts],
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        agent: "Agent",
        storage: Optional["Storage"] = None,
    ) -> "Stack":
        """Deserialize the stack from a dictionary.

        Args:
            data: The dictionary to deserialize the stack from.
            agent: The agent to use for the stack.
            storage: The storage to use for the stack.

        Returns:
            The deserialized stack.
        """
        # Create stack first (with empty interactions)
        stack = cls(agent=agent, interactions=[])

        if storage:
            # Deserialize interactions (they need stack reference)
            interactions_data = data.get("interactions", [])
            for interaction_uuid in interactions_data:
                try:
                    interaction = storage.load_interaction(
                        interaction_uuid, stack
                    )
                    stack.interactions.append(interaction)
                    # Rebuild branches dict if interaction has a branch
                    if interaction.branch:
                        if interaction.branch not in stack.branches:
                            stack.branches[interaction.branch] = []
                        stack.branches[interaction.branch].append(interaction)
                except (
                    ValueError,
                    FileNotFoundError,
                    json.JSONDecodeError,
                ) as e:
                    # Log warning but continue loading - corrupted interaction is skipped
                    logger.warning(
                        f"Skipping corrupted interaction {interaction_uuid}: {e}"
                    )
                except Exception as e:
                    # Log other errors but also continue
                    logger.warning(
                        f"Error loading interaction {interaction_uuid}: {e}"
                    )
        else:
            stack.interactions = data.get("interactions", [])

        return stack

    def rewind_to(
        self, index: int, storage: Optional["Storage"] = None
    ) -> List[Interaction]:
        """Rewind the stack to a specific interaction index.

        Removes all interactions after the given index and deletes them from
        storage. Also updates the branches dictionary to remove any branch
        references to deleted interactions.

        Args:
            index: The index to rewind to (0-based). Interactions at this
                   index and before are kept.
            storage: Optional storage to delete interactions from. If not
                     provided, interactions are only removed from the stack.

        Returns:
            List of interactions that were removed.

        Raises:
            ValueError: If index is out of bounds.
        """
        if index < 0 or index >= len(self.interactions):
            raise ValueError(
                f"Index {index} out of bounds for stack with "
                f"{len(self.interactions)} interactions"
            )

        # Get interactions to remove (everything after index)
        removed_interactions = self.interactions[index + 1 :]

        if not removed_interactions:
            return []

        # Log the rewind
        logger.info(
            f"Rewinding stack from {len(self.interactions)} to {index + 1} "
            f"interactions (removing {len(removed_interactions)})"
        )

        # Delete from storage first (before modifying in-memory state)
        if storage:
            for interaction in removed_interactions:
                try:
                    storage.delete_interaction(interaction)
                    logger.debug(
                        f"Deleted interaction {interaction.uuid} from storage"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to delete interaction {interaction.uuid} "
                        f"from storage: {e}"
                    )

        # Truncate the interactions list
        self.interactions = self.interactions[: index + 1]

        # Clean up branches dictionary - remove references to deleted interactions
        removed_uuids = {i.uuid for i in removed_interactions}
        for branch_name, branch_interactions in list(self.branches.items()):
            # Filter out removed interactions
            remaining = [
                i for i in branch_interactions if i.uuid not in removed_uuids
            ]
            if remaining:
                self.branches[branch_name] = remaining
            else:
                # Branch is now empty, remove it entirely
                del self.branches[branch_name]

        return removed_interactions

    # Session state convenience methods

    def get_shared_state(
        self, key: str, namespace: str = "common", default: Any = None
    ) -> Any:
        """Get a value from session shared state.

        Args:
            key: Key to retrieve
            namespace: Namespace to read from (default: "common")
            default: Default value if key doesn't exist

        Returns:
            The value associated with the key, or default if not found

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
        """
        return self.agent.session.state.get(
            namespace=namespace,
            key=key,
            agent_id=self.agent.id,
            default=default,
        )

    def get_all_shared_state(self, namespace: str = "common") -> Dict[str, Any]:
        """Get all key-value pairs from session shared state.

        Args:
            namespace: Namespace to read from (default: "common")

        Returns:
            Dictionary of all key-value pairs in the namespace

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
        """
        return self.agent.session.state.get_all(
            namespace=namespace, agent_id=self.agent.id
        )

    def set_shared_state(
        self, key: str, value: Any, namespace: str = "common"
    ) -> None:
        """Set a value in session shared state.

        Args:
            key: Key to set
            value: Value to store
            namespace: Namespace to write to (default: "common")

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
        """
        self.agent.session.state.set(
            namespace=namespace,
            key=key,
            value=value,
            agent_id=self.agent.id,
        )

    def delete_shared_state(self, key: str, namespace: str = "common") -> None:
        """Delete a key from session shared state.

        Args:
            key: Key to delete
            namespace: Namespace to delete from (default: "common")

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
            KeyError: If key doesn't exist in namespace
        """
        self.agent.session.state.delete(
            namespace=namespace, key=key, agent_id=self.agent.id
        )

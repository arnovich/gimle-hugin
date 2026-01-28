"""Gimle Ask Oracle Interaction."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.interaction.ask_human import AskHuman
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.artifacts.artifact import Artifact
    from gimle.hugin.interaction.human_response import HumanResponse
    from gimle.hugin.interaction.external_input import ExternalInput
    from gimle.hugin.interaction.stack import Stack
    from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.tool_result import ToolResult

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class AskOracle(Interaction):
    """Ask an oracle a question.

    In the LLM lingo this is a User Message.

    Attributes:
        prompt: The prompt to send to the oracle.
        template_inputs: Template variables for rendering.
        include_in_context: Whether to include in LLM context rendering.
    """

    prompt: Optional[Prompt] = None
    template_inputs: Optional[Dict[str, Any]] = None
    include_in_context: bool = True

    @staticmethod
    def create_from_external_input(
        external_input: "ExternalInput",
    ) -> "AskOracle":
        """Create an ask oracle interaction from an external input.

        Args:
            external_input: The external input to create the ask oracle interaction from.

        Returns:
            The created ask oracle interaction.
        """
        return AskOracle(
            stack=external_input.stack,
            branch=external_input.branch,
            prompt=Prompt(
                type="text",
                text=external_input.input,
            ),
            template_inputs={},
        )

    @staticmethod
    def create_from_human_response(
        human_response: "HumanResponse",
    ) -> "AskOracle":
        """Create an ask oracle interaction from a human response.

        Args:
            human_response: The human response to create the ask oracle interaction from.

        Returns:
            The created ask oracle interaction.
        """
        # Get branch-filtered interactions

        branch_interactions = human_response.stack.get_branch_interactions(
            human_response.branch
        )
        if len(branch_interactions) > 1 and isinstance(
            branch_interactions[-2], AskHuman
        ):
            template_inputs = {
                "response": human_response.response,
                "question": branch_interactions[-2].question,
            }
            respond_with_text = True
            tool_call_id = None
            tool_name = None

            if len(branch_interactions) > 2 and isinstance(
                branch_interactions[-3], ToolResult
            ):
                tool_name = branch_interactions[-3].tool_name
                tool = next(
                    (
                        tool
                        for tool in human_response.stack.get_tools()
                        if tool.name == tool_name
                    ),
                    None,
                )
                if tool:
                    respond_with_text = tool.options.respond_with_text
                    tool_call_id = branch_interactions[-3].tool_call_id
                    tool_name = branch_interactions[-3].tool_name
            if respond_with_text:
                prompt = Prompt(
                    type="template",
                    template_name=branch_interactions[
                        -2
                    ].response_template_name,
                )
            else:
                prompt = Prompt(
                    type="tool_result",
                    tool_use_id=tool_call_id,
                    tool_name=tool_name,
                )
        else:
            template_inputs = {}
            prompt = Prompt(
                type="text",
                text=human_response.response,
            )

        return AskOracle(
            stack=human_response.stack,
            branch=human_response.branch,
            prompt=prompt,
            template_inputs=template_inputs,
        )

    @staticmethod
    def create_from_tool_result(
        tool_result: "ToolResult",
    ) -> "AskOracle":
        """Create an ask oracle interaction from a tool result.

        Args:
            tool_result: The tool result to create the ask oracle interaction from.

        Returns:
            The created ask oracle interaction.
        """
        if tool_result.tool_call_id is None:
            prompt = Prompt(type="text")
        else:
            prompt = Prompt(
                type="tool_result",
                tool_use_id=tool_result.tool_call_id,
                tool_name=tool_result.tool_name,
            )
        template_inputs = {
            **(tool_result.result or {}),
            **{"is_error": tool_result.is_error},
        }
        logger.debug(
            f"Rendering user interaction for agent: {tool_result.stack.agent.id} as type={prompt.type}"
        )
        return AskOracle(
            stack=tool_result.stack,
            branch=tool_result.branch,
            prompt=prompt,
            template_inputs=template_inputs,
            include_in_context=tool_result.include_in_context,
        )

    @staticmethod
    def create_from_task_definition(
        task_definition: "TaskDefinition",
    ) -> "AskOracle":
        """Create an ask oracle interaction from a task result.

        Args:
            task_definition: The task definition to create the ask oracle interaction from.

        Returns:
            The created ask oracle interaction.
        """
        prompt = Prompt(
            type="template",
            text=task_definition.task.prompt if task_definition.task else "",
        )
        template_inputs = (
            task_definition.task.parameters if task_definition.task else {}
        )
        logger.debug(
            f"Rendering user interaction for agent: {task_definition.stack.agent.id} as type={prompt.type}"
        )
        return AskOracle(
            stack=task_definition.stack,
            branch=task_definition.branch,
            prompt=prompt,
            template_inputs=template_inputs,
        )

    @classmethod
    def _from_dict(
        cls, data: Dict[str, Any], stack: "Stack", artifacts: List["Artifact"]
    ) -> "AskOracle":
        """Construct from dictionary, handling Prompt deserialization.

        Args:
            data: The data to construct the ask oracle interaction from.
            stack: The stack to use for the ask oracle interaction.
            artifacts: The artifacts to use for the ask oracle interaction.

        Returns:
            The constructed ask oracle interaction.
        """
        # Extract uuid and created_at if present (they're not dataclass fields, so pass to __init__)
        uuid_value = data.pop("uuid", None)
        created_at_value = data.pop("created_at", None)

        # Prompt is serialized as a dict, use Prompt.from_dict to reconstruct it
        prompt_data = data.get("prompt", {})
        prompt = Prompt.from_dict(prompt_data)

        # Create instance, passing uuid and created_at to avoid generating new ones
        kwargs = {
            "stack": stack,
            "branch": data.get("branch"),
            "prompt": prompt,
            "template_inputs": data.get("template_inputs", {}),
            "include_in_context": data.get("include_in_context", True),
        }
        if uuid_value is not None:
            kwargs["uuid"] = uuid_value
        if created_at_value is not None:
            kwargs["created_at"] = created_at_value

        instance = cls(**kwargs)
        instance.artifacts = artifacts

        return instance

    def step(self) -> bool:
        """Step the ask oracle interaction.

        Returns:
            True if the ask oracle interaction was successful, False otherwise.
        """
        from gimle.hugin.interaction.oracle_response import OracleResponse
        from gimle.hugin.llm.completion import chat_completion

        if self.prompt is None:
            raise ValueError("AskOracle prompt is None")
        if self.template_inputs is None:
            raise ValueError("AskOracle template inputs is None")

        tools = self.stack.get_tools(branch=self.branch)
        interaction_messages = self.stack.render_stack_context(
            branch=self.branch
        )

        logger.debug(f"Number of interactions: {len(interaction_messages)}")
        logger.debug(self.stack.pretty_rendered_context(branch=self.branch))
        from gimle.hugin.llm.prompt.renderer import PromptRenderer

        renderer = PromptRenderer(self.stack.agent, branch=self.branch)
        system_prompt = renderer.render_system_prompt(self.template_inputs)
        llm_model = self.stack.agent.config.llm_model

        assistant_response = chat_completion(
            system_prompt=system_prompt,
            messages=interaction_messages,
            tools=tools,
            llm_model=llm_model,
        )
        logger.debug(f"Assistant response: {assistant_response}")
        self.stack.add_interaction(
            OracleResponse(
                stack=self.stack,
                branch=self.branch,
                response=assistant_response,
            )
        )
        return True

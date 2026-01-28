"""Message rendering module."""

import logging
from typing import Any, Dict, List

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.oracle_response import OracleResponse
from gimle.hugin.llm.prompt.renderer import PromptRenderer
from gimle.hugin.tools.tool import Tool

logger = logging.getLogger(__name__)


def render_user_message(
    interaction: AskOracle, reduced: bool = False
) -> List[Dict[str, Any]]:
    """Render a user message from an AskOracle interaction."""
    return_prompt: List[Dict[str, Any]] = []
    if interaction.prompt is None:
        raise ValueError("AskOracle prompt is None")
    if interaction.prompt.type == "template":
        logger.debug(
            f"Rendering user interaction({interaction.uuid}) for agent: {interaction.stack.agent.id} as template prompt"
        )
        if interaction.template_inputs is None:
            raise ValueError("AskOracle template inputs is None")
        if interaction.prompt.template_name is None:
            return_prompt = [
                {
                    "type": "text",
                    "text": PromptRenderer(
                        interaction.stack.agent,
                        interaction_uuid=interaction.uuid,
                        branch=interaction.branch,
                    ).render_task_prompt(interaction.template_inputs, reduced),
                }
            ]
        else:
            template_name = interaction.prompt.template_name
            template = (
                interaction.stack.agent.environment.template_registry.get(
                    template_name
                )
            )
            return_prompt = [
                {
                    "type": "text",
                    "text": PromptRenderer(
                        interaction.stack.agent,
                        interaction_uuid=interaction.uuid,
                        branch=interaction.branch,
                    ).render_prompt(
                        template.template, interaction.template_inputs, reduced
                    ),
                }
            ]
    elif interaction.prompt.type == "tool_result":
        logger.debug(
            f"Rendering user interaction({interaction.uuid}) for agent: {interaction.stack.agent.id} as tool result"
        )
        if interaction.prompt.tool_name is None:
            raise ValueError("AskOracle tool name is None")
        if interaction.template_inputs is None:
            raise ValueError("AskOracle template inputs is None")
        return_prompt = [
            {
                "type": "tool_result",
                "name": interaction.prompt.tool_name,
                "is_error": interaction.template_inputs.get("is_error", False),
                "tool_use_id": interaction.prompt.tool_use_id,
                "content": [
                    {
                        "type": "text",
                        "text": f"{k}: {v}",
                    }
                    for k, v in PromptRenderer.render_template_inputs(
                        interaction.template_inputs, reduced
                    ).items()
                ],
                # + [
                #     {
                #         "type": "text",
                #         "text": "tool_use_id: " + interaction.prompt.tool_use_id,
                #     }
                # ],
            }
        ]
    elif interaction.prompt.type == "text":
        logger.debug(
            f"Rendering user interaction for agent: {interaction.stack.agent.id} as text"
        )
        prompt_text = (
            str(interaction.template_inputs)
            if interaction.prompt.text is None
            else interaction.prompt.text
        )
        return_prompt = [{"type": "text", "text": prompt_text}]
    else:
        raise ValueError(f"Unknown prompt type: {interaction.prompt.type}")
    # image_ids = self._prompt.get("images")
    # if image_ids is None and self.template_inputs:
    #     image_ids = self.template_inputs.get("image_ids")
    # with self.agent.with_branch_interactions(self.branch):
    #     is_latest_interaction = self.agent.interactions[-1].id == self.id
    # if image_ids and is_latest_interaction:
    #     logging.info(f"Loading images into context from {self.agent}")
    #     for image_id in image_ids:
    #         logging.info(f"Loading image {image_id} into context from {self.agent}")
    #         image_data = self.agent.session.load_artifact(
    #             image_id
    #         ).get_content_base64()
    #         return_prompt.append(
    #             {
    #                 "type": "image",
    #                 "source": {
    #                     "type": "base64",
    #                     "media_type": "image/png",
    #                     "data": image_data,
    #                 },
    #             }
    #         )

    return return_prompt


def render_assistant_message(
    interaction: OracleResponse, reduced: bool = False
) -> List[Dict[str, Any]]:
    """Render an assistant message from an OracleResponse interaction."""
    logger.debug(
        f"Rendering assistant message for agent: {interaction.stack.agent.id}"
    )
    if interaction.response is None:
        raise ValueError("OracleResponse response is None")
    content = interaction.response["content"]
    if reduced and isinstance(content, dict):
        tool = Tool.get_tool(interaction.response["tool_call"])
        if tool:
            ignore_list = tool.options.reduced_context_window_ignore_list
        else:
            ignore_list = None
        if not ignore_list:
            ignore_list = ["id", "code_str", "insights", "reason", "summary"]

        content = {
            k: f"<{k}>" if k in ignore_list else v for k, v in content.items()
        }
    if interaction.tool_call_id is None:
        return [
            {
                "type": "text",
                "text": str(content),
            }
        ]
    else:
        return [
            {
                "type": "tool_use",
                "id": interaction.tool_call_id,
                "name": interaction.response["tool_call"],
                "input": content,
            }
        ]

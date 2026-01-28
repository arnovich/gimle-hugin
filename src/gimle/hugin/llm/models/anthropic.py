"""Anthropic model implementation module."""

import logging
from typing import Any, Dict, List, Optional

import anthropic

from gimle.hugin.tools.tool import Tool

from .model import Model, ModelResponse


class AnthropicModel(Model):
    """Anthropic model implementation."""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0,
        max_tokens: int = 5000,
        tool_choice: Dict[str, Any] = {
            "type": "any",
            "disable_parallel_tool_use": True,
        },
    ):
        """Initialize the Anthropic model."""
        super().__init__(
            config={
                "model": model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tool_choice": tool_choice,
            }
        )

    def chat_completion(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Tool]] = None,
    ) -> ModelResponse:
        """Generate a chat completion using Anthropic API."""
        if tools is None:
            tools = []
        logging.debug(
            f"Using Anthropic with {self.config=} tools={[t.name for t in tools]}"
        )
        client = anthropic.Anthropic()

        tools_to_use = []
        for tool in tools:
            tools_to_use.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            name: {
                                "type": params["type"],
                                "description": params["description"],
                            }
                            for name, params in tool.parameters.items()
                        },
                        "required": [
                            name
                            for name, params in tool.parameters.items()
                            if params.get("required")
                        ],
                    },
                }
            )

        for message in messages:
            if isinstance(message["content"], list):
                for part in message["content"]:
                    if part["type"] == "tool_result":
                        del part["name"]

        Model.log_messages(messages)
        try:
            if tools_to_use:
                response = client.with_options(max_retries=5).messages.create(
                    messages=messages,  # type: ignore[arg-type]
                    temperature=(
                        self.temperature if self.temperature is not None else 0
                    ),
                    max_tokens=self.max_tokens,
                    model=self.model_name,
                    system=system_prompt,
                    tools=tools_to_use,  # type: ignore[arg-type]
                    tool_choice=self.tool_choice,
                )
            else:
                response = client.with_options(max_retries=5).messages.create(
                    messages=messages,  # type: ignore[arg-type]
                    temperature=(
                        self.temperature if self.temperature is not None else 0
                    ),
                    max_tokens=self.max_tokens,
                    model=self.model_name,
                    system=system_prompt,
                )
        except anthropic.APIError as error:
            logging.error(
                f"""Anthropic Error: {error}\n
MESSAGES:\n{"\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages])}
TOOLS:\n{"\n".join([f"{t.name}: {t.description}" for t in tools])}
TOOL CHOICE:\n{self.tool_choice}
SYSTEM PROMPT:\n{system_prompt}
MODEL:\n{self.model_name}
TEMPERATURE:\n{self.temperature}
MAX TOKENS:\n{self.max_tokens}"""
            )
            raise error
        logging.debug(f"Received response {response.content[0]}")
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        logging.debug(
            f"Token usage {input_tokens=} {output_tokens=} for {response.id=}"
        )
        # TODO support multiple tool calls in a single response

        tool_use_content = None
        extra_content = []
        for content in response.content:
            if content.type == "tool_use":
                tool_use_content = content
            elif hasattr(content, "text"):
                extra_content.append(content.text)

        if tool_use_content:
            return ModelResponse(
                role="assistant",
                content=tool_use_content.input,
                tool_call=tool_use_content.name,
                tool_call_id=tool_use_content.id,
                extra_content=extra_content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        first_content = response.content[0]
        text_content = getattr(first_content, "text", "") or ""
        return ModelResponse(
            role="assistant",
            content=text_content.replace("\n", " "),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

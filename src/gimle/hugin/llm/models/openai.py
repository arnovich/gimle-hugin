"""OpenAI model implementation module."""

import logging
from typing import Any, Dict, List, Optional

from gimle.hugin.tools.tool import ParameterSchema, Tool

from .model import Model, ModelResponse


class OpenAIModel(Model):
    """OpenAI model implementation."""

    def __init__(
        self,
        model_name: str,
        temperature: Optional[float] = 0,
        max_tokens: int = 4096,
        tool_choice: str = "required",
    ):
        """Initialize the OpenAI model.

        Args:
            model_name: The OpenAI model name (e.g., "gpt-4o", "gpt-4o-mini")
            temperature: Sampling temperature (0 for deterministic).
                Set to None for models that don't support it
                (e.g. reasoning models like gpt-5-nano).
            max_tokens: Maximum tokens in response
            tool_choice: Tool choice mode. "required" forces the model
                to call a tool, "auto" lets it decide. Defaults to
                "required" to match Anthropic's "any" behavior.
        """
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
        """Generate a chat completion using OpenAI API."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )

        if tools is None:
            tools = []

        logging.debug(
            f"Using OpenAI with {self.config=} tools={[t.name for t in tools]}"
        )

        client = openai.OpenAI()

        # Build tools in OpenAI format
        tools_to_use = []
        for tool in tools:
            tools_to_use.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                name: self._build_param_schema(params)
                                for name, params in tool.parameters.items()
                            },
                            "required": [
                                name
                                for name, params in tool.parameters.items()
                                if params.get("required")
                            ],
                        },
                    },
                }
            )

        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(system_prompt, messages)

        Model.log_messages(messages)

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model_name,
                "messages": openai_messages,
                "max_completion_tokens": self.max_tokens,
            }

            if self.temperature is not None:
                kwargs["temperature"] = self.temperature

            if tools_to_use:
                kwargs["tools"] = tools_to_use
                kwargs["tool_choice"] = self.tool_choice

            response = client.chat.completions.create(**kwargs)

        except openai.APIError as error:
            logging.error(
                f"OpenAI Error: {error}\n"
                f"MODEL: {self.model_name}\n"
                f"MESSAGES: {len(messages)} messages\n"
            )
            raise error

        choice = response.choices[0]
        message = choice.message

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = (
            response.usage.completion_tokens if response.usage else 0
        )

        logging.debug(
            f"Token usage {input_tokens=} {output_tokens=} for {response.id=}"
        )

        # Check for tool calls
        if message.tool_calls:
            tool_call = message.tool_calls[0]  # Handle first tool call
            import json

            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            return ModelResponse(
                role="assistant",
                content=tool_args,
                tool_call=tool_call.function.name,
                tool_call_id=tool_call.id,
                extra_content=[message.content] if message.content else [],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        # Text response
        text_content = message.content or ""
        return ModelResponse(
            role="assistant",
            content=text_content.replace("\n", " "),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _build_param_schema(self, params: ParameterSchema) -> Dict[str, Any]:
        """Build a JSON Schema property from tool parameter definition."""
        p = dict(params)
        schema: Dict[str, Any] = {
            "type": p["type"],
            "description": p.get("description", ""),
        }
        if p.get("items"):
            schema["items"] = p["items"]
        if p.get("enum"):
            schema["enum"] = p["enum"]
        return schema

    def _convert_messages(
        self, system_prompt: str, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert internal message format to OpenAI format."""
        openai_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content")

            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Handle structured content (tool results, etc.)
                converted = self._convert_content_list(content, role)
                openai_messages.extend(converted)
            else:
                openai_messages.append({"role": role, "content": str(content)})

        return openai_messages

    def _convert_content_list(
        self, content_list: List[Dict[str, Any]], role: str
    ) -> List[Dict[str, Any]]:
        """Convert a list of content items to OpenAI message format."""
        result = []

        for item in content_list:
            item_type = item.get("type")

            if item_type == "text":
                result.append({"role": role, "content": item.get("text", "")})

            elif item_type == "tool_use":
                # Assistant made a tool call
                import json

                result.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": item.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": item.get("name", ""),
                                    "arguments": json.dumps(
                                        item.get("input", {})
                                    ),
                                },
                            }
                        ],
                    }
                )

            elif item_type == "tool_result":
                # Result from a tool call
                import json

                content_value = item.get("content", "")
                if isinstance(content_value, dict):
                    content_value = json.dumps(content_value)

                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": item.get("tool_use_id", ""),
                        "content": content_value,
                    }
                )

        return result

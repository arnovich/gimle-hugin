"""Prompt renderer module."""

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from pandas import DataFrame, read_parquet

from gimle.hugin.llm.prompt.jinja import render_jinja_recursive

if TYPE_CHECKING:
    from gimle.hugin.agent.agent import Agent

logger = logging.getLogger(__name__)


def format_df_to_string(
    df_dict: Union[Dict[str, Any], DataFrame],
    shorten: Optional[int] = None,
    index: Optional[bool] = False,
    reduced: Optional[bool] = False,
) -> str:
    """Format a DataFrame to a string representation."""
    if reduced:
        return "<dataframe>"
    if isinstance(df_dict, dict):
        if df_dict.get("_type") != "parquet_dataframe":
            raise ValueError("Unknown dataframe type")
        parquet_buffer = BytesIO(df_dict.get("data"))  # type: ignore
        df = read_parquet(parquet_buffer)
    else:
        df = df_dict
    df_str = str(df.to_string(index=index))
    if shorten is not None and len(df_str) > shorten:
        return df_str[: (shorten - 3)] + "..."
    return df_str


class PromptRenderer:
    """Renderer for prompts with template support."""

    def __init__(
        self,
        agent: "Agent",
        interaction_uuid: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> None:
        """Initialize the prompt renderer."""
        self.agent = agent
        # this is a cutoff interaction - if set the `interactions` in the template are only up to this
        self.interaction_uuid = interaction_uuid
        self.branch = branch

    @staticmethod
    def render_template_inputs(
        template_inputs: Dict[str, Any], reduced: Optional[bool] = False
    ) -> Dict[str, Any]:
        """Render template inputs.

        If a DataFrame then it is formatted to a string.
        If the reduced then all dataframes removed.
        If a key is flagged as shortened then the string value is shortened.

        Args:
            template_inputs: The template inputs to render.
            reduced: Whether to reduce the template inputs.

        Returns:
            The rendered template inputs.
        """
        template_inputs = template_inputs.copy()
        # TODO figure out a way to have "errors" as a general key
        # maybe _error to make that easy
        # or we have an object of state or something
        for k, v in template_inputs.items():
            # TODO make this more extensible
            # so that you can define reduction schemas for certain keys
            if isinstance(v, DataFrame):
                template_inputs[k] = format_df_to_string(
                    v, shorten=3000, index=True, reduced=reduced
                )
        return template_inputs

    def __getattr__(self, name: str) -> Any:
        """Get attribute, handling special 'interactions' attribute."""
        if name == "stack":
            from gimle.hugin.interaction.stack import Stack

            interactions = []
            for interaction in self.agent.stack.interactions:
                if (
                    self.interaction_uuid
                    and interaction.uuid == self.interaction_uuid
                ):
                    interactions.append(interaction)
                    break
                interactions.append(interaction)
            return Stack(interactions=interactions, agent=self.agent)

        return getattr(self.agent, name)

    def render_prompt(
        self,
        prompt_text: str,
        template_inputs: Dict[str, Any],
        reduced: Optional[bool] = False,
    ) -> str:
        """Render a prompt with template inputs."""
        template_inputs = {
            **template_inputs,
            **{
                k: v
                for k, v in self.agent.environment.template_registry.registered().items()
            },
            **PromptRenderer.render_template_inputs(template_inputs, reduced),
            **{
                "agent": self,
                "format_df_to_string": format_df_to_string,
            },
        }
        template_inputs = {
            k: v for k, v in template_inputs.items() if v is not None
        }
        return render_jinja_recursive(prompt_text, template_inputs)

    def render_task_prompt(
        self, template_inputs: Dict[str, Any], reduced: Optional[bool] = False
    ) -> str:
        """Render the task prompt with template inputs."""
        logger.debug(f"Rendering task prompt for agent: {self.agent.uuid}")
        task_definition = self.agent.stack.get_task_definition(
            current_interaction_uuid=self.interaction_uuid,
            branch=self.branch,
        )
        if task_definition is None:
            raise ValueError("Task definition not found")
        task_prompt = task_definition.prompt
        logger.debug(
            f"Task prompt={task_prompt} with template_inputs={template_inputs}"
        )
        task_prompt = self.render_prompt(task_prompt, template_inputs, reduced)
        logger.debug(f"Task prompt rendered={task_prompt}")
        return task_prompt

    def render_system_prompt(
        self, template_inputs: Optional[Dict[str, Any]] = None
    ) -> str:
        """Render the system prompt with template inputs."""
        template_inputs = template_inputs or {}
        system_template = self.agent.stack.get_system_template(
            current_interaction_uuid=self.interaction_uuid,
            branch=self.branch,
        )
        logger.debug(
            f"Rendering system prompt with template: {system_template}"
        )
        system_prompt = self.render_prompt(system_template, template_inputs)
        logger.debug(f"System prompt rendered={system_prompt}")
        return system_prompt

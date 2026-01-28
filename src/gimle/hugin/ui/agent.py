"""Agent renderer for converting agents to displayable formats."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gimle.hugin.agent.agent import Agent


class AgentRenderer:
    """Renderer for Agent objects."""

    def render(self, agent: "Agent", format: str = "html") -> str:
        """
        Render an agent to the specified format.

        Args:
            agent: The agent to render
            format: The target format (currently only "html" is supported)

        Returns:
            The rendered agent as a string

        Raises:
            ValueError: If the format is not supported
        """
        if format == "html":
            return self._render_to_html(agent)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _render_to_html(self, agent: "Agent") -> str:
        """
        Render an agent to HTML.

        Args:
            agent: The agent to render

        Returns:
            The agent rendered as HTML string
        """
        # TODO: Implement agent HTML rendering
        # This could include:
        # - Agent configuration
        # - Available tools
        # - Session history
        # - Performance metrics
        html_parts = ["<div class='agent'>"]
        html_parts.append("<h2>Agent</h2>")

        # Add agent information
        if hasattr(agent, "config") and agent.config:
            html_parts.append("<div class='config'>")
            html_parts.append("<h3>Configuration</h3>")
            # Render config details
            html_parts.append("</div>")

        html_parts.append("</div>")
        return "\n".join(html_parts)


def render_agent(agent: "Agent", format: str = "html") -> str:
    """
    Render an agent to the specified format.

    Args:
        agent: The agent to render
        format: The target format (currently only "html" is supported)

    Returns:
        The rendered agent as a string
    """
    renderer = AgentRenderer()
    return renderer.render(agent, format=format)

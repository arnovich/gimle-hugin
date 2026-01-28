"""Stack renderer for converting stacks to displayable formats."""

from typing import TYPE_CHECKING, Dict, List, Optional

from gimle.hugin.interaction.interaction import Interaction

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


class StackRenderer:
    """Renderer for Stack objects."""

    def render(self, stack: "Stack", format: str = "html") -> str:
        """
        Render a stack to the specified format.

        Args:
            stack: The stack to render
            format: The target format (currently only "html" is supported)

        Returns:
            The rendered stack as a string

        Raises:
            ValueError: If the format is not supported
        """
        if format == "html":
            return self._render_to_html(stack)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _render_to_html(self, stack: "Stack") -> str:
        """
        Render a stack to HTML with flowchart-style visualization.

        Args:
            stack: The stack to render

        Returns:
            The stack rendered as HTML string
        """
        html_parts = []

        if not stack.interactions:
            html_parts.append("<div class='stack-visualization'>")
            html_parts.append(
                f"<h2>Stack Flow ({stack.ninteractions()} interactions)</h2>"
            )
            html_parts.append("<p>No interactions yet.</p>")
            html_parts.append("</div>")
            return "\n".join(html_parts)

        # Add timeline view (collapsible, collapsed by default)
        html_parts.append(self._render_timeline(stack))

        # Create flowchart visualization (collapsible, expanded by default)
        html_parts.append("<div class='stack-visualization'>")
        html_parts.append(
            f"<h2 class='expanded'>Stack Flow ({stack.ninteractions()} interactions)</h2>"
        )
        html_parts.append("<div class='flowchart expanded'>")

        # Group interactions by branch for visualization
        main_branch: List[Interaction] = []
        branches: Dict[str, List[Interaction]] = {}
        branch_fork_indices: Dict[str, int] = (
            {}
        )  # Track where each branch forks

        for idx, interaction in enumerate(stack.interactions):
            branch = getattr(interaction, "branch", None)
            if branch:
                if branch not in branches:
                    branches[branch] = []
                    # Record the main branch index where this branch was created
                    branch_fork_indices[branch] = len(main_branch)
                branches[branch].append(interaction)
            else:
                main_branch.append(interaction)

        # Use multi-column layout for branches
        html_parts.append("<div class='flowchart-columns'>")

        # Render main branch column
        html_parts.append(
            "<div class='flowchart-column flowchart-column-main'>"
        )
        html_parts.append("<div class='flowchart-column-header'>main</div>")
        html_parts.append("<div class='flowchart-column-content'>")
        for i, interaction in enumerate(main_branch):
            html_parts.append(
                self._render_interaction_box(interaction, i, len(main_branch))
            )
        html_parts.append("</div>")  # Close column-content
        html_parts.append("</div>")  # Close column

        # Render branch columns
        for branch_name, branch_interactions in branches.items():
            fork_index = branch_fork_indices.get(branch_name, 0)
            html_parts.append(
                f"<div class='flowchart-column flowchart-column-branch' "
                f"data-branch='{branch_name}' data-fork-index='{fork_index}'>"
            )
            html_parts.append(
                f"<div class='flowchart-column-header'>{branch_name}</div>"
            )
            html_parts.append("<div class='flowchart-column-content'>")
            # Add spacer to align with fork point
            if fork_index > 0:
                html_parts.append(
                    f"<div class='flowchart-branch-spacer' "
                    f"data-height='{fork_index}'></div>"
                )
            for i, interaction in enumerate(branch_interactions):
                html_parts.append(
                    self._render_interaction_box(
                        interaction,
                        i,
                        len(branch_interactions),
                        branch_name,
                    )
                )
            html_parts.append("</div>")  # Close column-content
            html_parts.append("</div>")  # Close column

        html_parts.append("</div>")  # Close flowchart-columns
        html_parts.append("</div>")  # Close flowchart

        html_parts.append("</div>")  # Close stack-visualization
        return "\n".join(html_parts)

    def _render_timeline(self, stack: "Stack") -> str:
        """Render a timeline view showing time gaps between interactions."""
        from datetime import datetime

        html_parts = []
        html_parts.append("<div class='timeline-section'>")
        html_parts.append(
            f"<h2>Timeline ({stack.ninteractions()} interactions)</h2>"
        )
        html_parts.append("<div class='timeline-view'>")
        html_parts.append("<div class='timeline-container'>")

        # Get interactions with timestamps
        interactions_with_time = []
        for interaction in stack.interactions:
            created_at = getattr(interaction, "created_at", None)
            if created_at:
                try:
                    dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                    interactions_with_time.append((interaction, dt))
                except Exception:
                    pass

        if not interactions_with_time:
            html_parts.append(
                "<p style='color: #7f8c8d; font-size: 0.9em;'>No timestamp data available</p>"
            )
            html_parts.append(
                "</div></div></div>"
            )  # Close timeline-container, timeline-view, timeline-section
            return "\n".join(html_parts)

        # Calculate time gaps
        for i, (interaction, dt) in enumerate(interactions_with_time):
            interaction_type = interaction.__class__.__name__
            interaction_id = getattr(interaction, "id", f"interaction-{i}")
            time_str = dt.strftime("%H:%M:%S")

            # Get branch info
            branch = getattr(interaction, "branch", None)
            branch_display = branch if branch else "main"
            branch_class = "branch-main" if not branch else "branch-alt"

            # Calculate gap from previous interaction
            gap_html = ""
            if i > 0:
                prev_dt = interactions_with_time[i - 1][1]
                gap = (dt - prev_dt).total_seconds()
                if gap > 0.1:  # Only show gaps > 100ms
                    if gap < 1:
                        gap_str = f"{gap*1000:.0f}ms"
                    elif gap < 60:
                        gap_str = f"{gap:.1f}s"
                    else:
                        gap_str = f"{gap/60:.1f}m"
                    gap_html = f'<span class="timeline-gap">+{gap_str}</span>'

            # Color based on interaction type
            color_class = self._get_interaction_color_class(interaction_type)

            # Get detail label (tool name for ToolCall, task name for TaskDef)
            detail_html = self._get_timeline_detail(interaction)

            html_parts.append(
                f"""
            <div class="timeline-item {color_class}" data-interaction-id="{interaction_id}" onclick="selectInteraction('{interaction_id}'); showInteractionDetails('{interaction_id}')" style="cursor: pointer;">
                <span class="timeline-time">{time_str}</span>
                {gap_html}
                <span class="timeline-type">{interaction_type}</span>
                {detail_html}
                <span class="timeline-branch {branch_class}">{branch_display}</span>
            </div>
            """
            )

        html_parts.append(
            "</div></div></div>"
        )  # Close timeline-container, timeline-view, timeline-section
        return "\n".join(html_parts)

    def _render_interaction_box(
        self,
        interaction: Interaction,
        index: int,
        total: int,
        branch: Optional[str] = None,
    ) -> str:
        """Render a single interaction as a flowchart box."""
        interaction_type = interaction.__class__.__name__
        interaction_id = getattr(interaction, "id", f"interaction-{index}")

        # Determine color class based on interaction type
        color_class = self._get_interaction_color_class(interaction_type)

        # Get interaction details
        details = self._get_interaction_details(interaction)

        # Get timestamp if available
        timestamp = self._format_timestamp(
            getattr(interaction, "created_at", None)
        )

        # Check if this is the last interaction
        is_last = index == total - 1

        # Build the box HTML - very compact version
        # Make it clickable if it has artifacts
        has_artifacts = bool(interaction.artifacts)
        clickable_class = "flowchart-box-clickable" if has_artifacts else ""
        artifact_count = len(interaction.artifacts) if has_artifacts else 0

        # Display branch name - "main" for None, otherwise the branch name
        branch_display = branch if branch else "main"

        box_html = f"""
        <div class="flowchart-item {color_class}" data-interaction-id="{interaction_id}">
            <div class="flowchart-box {clickable_class}" data-has-artifacts="{str(has_artifacts).lower()}">
                <div class="flowchart-box-header">
                    <span class="flowchart-box-type" onclick="showInteractionDetails('{interaction_id}')" style="cursor: pointer;">{interaction_type}</span>
                    <span class="flowchart-box-branch">{branch_display}</span>
                    {f'<span class="flowchart-box-artifacts-badge" onclick="scrollToArtifacts(\'{interaction_id}\'); event.stopPropagation();" style="cursor: pointer;">📎 {artifact_count}</span>' if has_artifacts else ''}
                    {f'<span class="flowchart-box-timestamp">{timestamp}</span>' if timestamp else ''}
                </div>
                {f'<div class="flowchart-box-details">{details}</div>' if details else ''}
            </div>
        </div>
        """

        # Add arrow if not last
        if not is_last:
            box_html += '<div class="flowchart-arrow">↓</div>'

        return box_html

    def _get_interaction_color_class(self, interaction_type: str) -> str:
        """Get CSS color class for interaction type."""
        color_map = {
            "TaskDefinition": "flowchart-purple",
            "TaskChain": "flowchart-purple",
            "AskOracle": "flowchart-yellow",
            "OracleResponse": "flowchart-yellow",
            "ToolCall": "flowchart-blue",
            "ToolResult": "flowchart-blue",
            "AskHuman": "flowchart-yellow",
            "HumanResponse": "flowchart-yellow",
            "ExternalInput": "flowchart-yellow",
            "TaskResult": "flowchart-green",
            "AgentCall": "flowchart-purple",
            "AgentResult": "flowchart-green",
            "Waiting": "flowchart-gray",
        }
        return color_map.get(interaction_type, "flowchart-gray")

    def _get_interaction_details(self, interaction: Interaction) -> str:
        """Get details string for an interaction."""
        details_parts = []
        interaction_type = interaction.__class__.__name__

        # AgentCall - show config and task name
        if interaction_type == "AgentCall":
            config = getattr(interaction, "config", None)
            if config and hasattr(config, "name"):
                details_parts.append(f"Config: {config.name}")
            task = getattr(interaction, "task", None)
            if task and hasattr(task, "name"):
                details_parts.append(f"Task: {task.name}")
            agent_id = getattr(interaction, "agent_id", None)
            if agent_id:
                details_parts.append(f"Agent: {agent_id[:8]}...")
            return " | ".join(details_parts)

        # AgentResult - show task result id
        if interaction_type == "AgentResult":
            task_result_id = getattr(interaction, "task_result_id", None)
            if task_result_id:
                details_parts.append(f"Result: {task_result_id[:8]}...")
            return " | ".join(details_parts)

        if hasattr(interaction, "task") and interaction.task:
            details_parts.append(f"Task: {interaction.task.name}")

        if hasattr(interaction, "tool") and interaction.tool:
            details_parts.append(f"Tool: {interaction.tool}")

        if hasattr(interaction, "finish_type") and interaction.finish_type:
            details_parts.append(f"Finish: {interaction.finish_type}")

        if hasattr(interaction, "summary") and interaction.summary:
            summary = (
                interaction.summary[:50] + "..."
                if len(interaction.summary) > 50
                else interaction.summary
            )
            details_parts.append(f"Summary: {summary}")

        return " | ".join(details_parts)

    def _get_timeline_detail(self, interaction: Interaction) -> str:
        """Get detail HTML for timeline view (tool name, task name, etc.)."""
        interaction_type = interaction.__class__.__name__

        # ToolCall - show tool name
        if interaction_type == "ToolCall":
            tool = getattr(interaction, "tool", None)
            if tool:
                return f'<span class="timeline-detail timeline-detail-tool">{tool}</span>'

        # ToolResult - show tool name
        if interaction_type == "ToolResult":
            tool_name = getattr(interaction, "tool_name", None)
            if tool_name:
                return f'<span class="timeline-detail timeline-detail-tool">{tool_name}</span>'

        # TaskDefinition - show task name
        if interaction_type == "TaskDefinition":
            task = getattr(interaction, "task", None)
            if task and hasattr(task, "name"):
                return f'<span class="timeline-detail timeline-detail-task">{task.name}</span>'

        # TaskResult - show finish type
        if interaction_type == "TaskResult":
            finish_type = getattr(interaction, "finish_type", None)
            if finish_type:
                return f'<span class="timeline-detail timeline-detail-result">{finish_type}</span>'

        # AgentCall - show config name if available
        if interaction_type == "AgentCall":
            config = getattr(interaction, "config", None)
            if config and hasattr(config, "name"):
                return f'<span class="timeline-detail timeline-detail-task">{config.name}</span>'

        # AgentResult - show task result id
        if interaction_type == "AgentResult":
            task_result_id = getattr(interaction, "task_result_id", None)
            if task_result_id:
                return f'<span class="timeline-detail timeline-detail-result">{task_result_id[:8]}...</span>'

        # TaskChain - show next task name
        if interaction_type == "TaskChain":
            next_task = getattr(interaction, "next_task_name", None)
            if next_task:
                return f'<span class="timeline-detail timeline-detail-task">{next_task}</span>'
            # If no next_task_name, try task_sequence
            sequence = getattr(interaction, "task_sequence", None)
            idx = getattr(interaction, "sequence_index", 0)
            if sequence and idx < len(sequence):
                return f'<span class="timeline-detail timeline-detail-task">{sequence[idx]}</span>'

        return ""

    def _format_timestamp(self, timestamp: Optional[str]) -> Optional[str]:
        """Format timestamp for display in small font."""
        if not timestamp:
            return None

        try:
            from datetime import datetime

            # Parse ISO format timestamp
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            # Format as HH:MM:SS
            return dt.strftime("%H:%M:%S")
        except Exception:
            # If parsing fails, return original or None
            return None


def render_stack(stack: "Stack", format: str = "html") -> str:
    """
    Render a stack to the specified format.

    Args:
        stack: The stack to render
        format: The target format (currently only "html" is supported)

    Returns:
        The rendered stack as a string
    """
    renderer = StackRenderer()
    return renderer.render(stack, format=format)

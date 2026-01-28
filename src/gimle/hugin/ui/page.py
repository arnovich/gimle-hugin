"""HTML page generator for rendering complete agent views."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

from gimle.hugin.ui.static import render_template

if TYPE_CHECKING:
    from gimle.hugin.agent.agent import Agent


def generate_agent_page(agent: "Agent", title: str = "Agent View") -> str:
    """
    Generate a complete HTML page with agent, stack, and artifacts.

    Args:
        agent: The agent to render
        title: Title for the HTML page

    Returns:
        Complete HTML page as a string
    """
    from gimle.hugin.ui import render_stack
    from gimle.hugin.ui.components.base import ComponentRegistry

    # Render components
    stack_html = render_stack(agent.stack)

    # Prepare artifact data for JavaScript (hidden, will be shown in side panel)
    artifacts_data: Dict[str, List[Dict[str, Any]]] = {}
    for interaction in agent.stack.interactions:
        interaction_id = getattr(interaction, "id", None)
        if interaction_id and interaction.artifacts:
            artifacts_data[interaction_id] = []
            for i, artifact in enumerate(interaction.artifacts):
                try:
                    # Use ComponentRegistry for rendering (supports custom components)
                    component = ComponentRegistry.get_component(artifact)
                    artifact_html = component.render_detail(artifact)
                    artifact_type = artifact.__class__.__name__
                    # Use try-except because artifact.id property may raise
                    try:
                        artifact_id = artifact.id
                    except Exception:
                        artifact_id = f"artifact-{i}"

                    # Get created_at timestamp
                    created_at = getattr(artifact, "created_at", None)

                    # Get content preview using component
                    preview = component.render_preview(artifact)

                    # Get format if available
                    artifact_format = getattr(artifact, "format", None)

                    artifacts_data[interaction_id].append(
                        {
                            "id": artifact_id,
                            "type": artifact_type,
                            "html": artifact_html,
                            "created_at": created_at,
                            "preview": preview,
                            "format": artifact_format,
                        }
                    )
                except Exception as e:
                    artifacts_data[interaction_id].append(
                        {
                            "id": f"artifact-{i}",
                            "type": "Error",
                            "html": f"<p>Error rendering artifact: {str(e)}</p>",
                            "created_at": None,
                            "preview": "",
                            "format": None,
                        }
                    )

    # Convert to JSON for JavaScript
    import json

    artifacts_json = json.dumps(artifacts_data)

    # Generate artifacts list HTML for the Artifacts section
    artifacts_list_html = ""
    if not artifacts_data:
        artifacts_list_html = (
            '<p class="artifacts-list-empty">No artifacts in this session.</p>'
        )
    else:
        import html as html_module

        artifacts_list_parts = []
        for interaction_id, artifacts in artifacts_data.items():
            # Get interaction info for display
            interaction_type = "Unknown"
            tool_name = None
            for interaction in agent.stack.interactions:
                if getattr(interaction, "id", None) == interaction_id:
                    interaction_type = interaction.__class__.__name__
                    tool_name = getattr(
                        interaction, "tool_name", None
                    ) or getattr(interaction, "tool", None)
                    break

            for artifact_dict in artifacts:
                artifact_id = artifact_dict["id"]
                artifact_type = artifact_dict["type"]
                created_at = artifact_dict.get("created_at", "")
                preview = artifact_dict.get("preview", "")
                artifact_format = artifact_dict.get("format", "")

                # Truncate IDs for display
                short_artifact_id = (
                    artifact_id[:8] + "..."
                    if len(artifact_id) > 8
                    else artifact_id
                )
                short_interaction_id = (
                    interaction_id[:8] + "..."
                    if len(interaction_id) > 8
                    else interaction_id
                )

                # Build timestamp display (formatted to seconds)
                timestamp_html = ""
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            dt = datetime.fromisoformat(
                                created_at.replace("Z", "+00:00")
                            )
                        else:
                            dt = created_at
                        formatted_time = dt.strftime("%b %d, %H:%M:%S")
                    except (ValueError, AttributeError):
                        formatted_time = str(created_at)[:19]
                    timestamp_html = f'<span class="artifacts-list-item-time">{html_module.escape(formatted_time)}</span>'

                # Build format badge if available
                format_html = ""
                if artifact_format:
                    format_html = f'<span class="artifacts-list-item-format">{html_module.escape(str(artifact_format))}</span>'

                # Build preview if available
                preview_html = ""
                if preview:
                    escaped_preview = html_module.escape(preview)
                    preview_html = f'<div class="artifacts-list-item-preview">{escaped_preview}</div>'

                # Build tool info
                tool_html = ""
                if tool_name:
                    tool_html = f'<span class="artifacts-list-item-tool">{html_module.escape(str(tool_name))}</span>'

                artifacts_list_parts.append(
                    f"""<div class="artifacts-list-item" data-artifact-id="{artifact_id}" data-interaction-id="{interaction_id}">
                        <div class="artifacts-list-item-header">
                            <div class="artifacts-list-item-title">
                                <span class="artifacts-list-item-type">{artifact_type}</span>
                                {format_html}
                                {tool_html}
                            </div>
                            <div class="artifacts-list-item-meta">
                                {timestamp_html}
                                <span class="artifacts-list-item-id">{short_artifact_id}</span>
                                <button class="artifacts-list-item-open" onclick="openArtifactModal('{artifact_id}', '{interaction_id}'); event.stopPropagation();" title="Open in modal">Open</button>
                            </div>
                        </div>
                        {preview_html}
                        <div class="artifacts-list-item-interaction" onclick="showInteractionDetails('{interaction_id}', true); event.stopPropagation();">
                            <span class="artifacts-list-item-interaction-label">From:</span>
                            <span class="artifacts-list-item-interaction-type">{interaction_type}</span>
                            <span class="artifacts-list-item-interaction-id">{short_interaction_id}</span>
                        </div>
                    </div>"""
                )
        artifacts_list_html = "\n".join(artifacts_list_parts)

    # Generate compact agent configuration and info section
    config_html = ""
    if agent.config:
        config = agent.config
        config_items = []

        config_items.append(f"<strong>{config.name}</strong>")

        if hasattr(config, "llm_model") and config.llm_model:
            config_items.append(f"Model: {config.llm_model}")

        if hasattr(config, "system_template") and config.system_template:
            config_items.append(f"Template: {config.system_template}")

        if hasattr(config, "tools") and config.tools:
            # Convert tools to strings (handles both str and dict/Tool objects)
            tool_names = config.tools

            tools_list = (
                ", ".join(tool_names[:3])
                if len(tool_names) > 3
                else ", ".join(tool_names)
            )
            if len(tool_names) > 3:
                tools_list += f" (+{len(tool_names) - 3} more)"
            config_items.append(f"Tools: {tools_list}")

        if hasattr(config, "interactive"):
            interactive_value = "Yes" if config.interactive else "No"
            config_items.append(f"Interactive: {interactive_value}")

        config_html = f"<div class='compact-header'><div class='compact-config'>{' • '.join(config_items)}</div></div>\n"

    # Get agent info
    agent_id = getattr(agent, "id", "unknown")
    num_interactions = agent.stack.ninteractions()
    num_artifacts = len(agent.stack.artifacts)

    # Render the template with all the data
    return render_template(
        "agent.html",
        title=title,
        config_html=config_html,
        agent_id=agent_id,
        num_interactions=str(num_interactions),
        num_artifacts=str(num_artifacts),
        stack_html=stack_html,
        artifacts_list_html=artifacts_list_html,
        artifacts_json=artifacts_json,
    )

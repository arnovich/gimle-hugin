"""Gimle UI module for rendering artifacts, stacks, and agents."""

# Agent rendering
from gimle.hugin.ui.agent import AgentRenderer, render_agent

# Artifact renderers (legacy, for backwards compatibility)
from gimle.hugin.ui.artifacts.base import ArtifactRenderer
from gimle.hugin.ui.artifacts.text import TextArtifactRenderer

# Component system (new, preferred)
from gimle.hugin.ui.components import (
    ArtifactComponent,
    ComponentRegistry,
    FileComponent,
    GenericComponent,
    TextComponent,
)

# Page generation
from gimle.hugin.ui.page import generate_agent_page
from gimle.hugin.ui.renderer import render_artifact, render_artifact_to_html

# Stack rendering
from gimle.hugin.ui.stack import StackRenderer, render_stack

__all__ = [
    # Main rendering functions
    "render_artifact",
    "render_artifact_to_html",
    "render_stack",
    "render_agent",
    # Component system (preferred for custom artifacts)
    "ArtifactComponent",
    "ComponentRegistry",
    "TextComponent",
    "FileComponent",
    "GenericComponent",
    # Legacy renderer classes (for backwards compatibility)
    "StackRenderer",
    "AgentRenderer",
    "ArtifactRenderer",
    "TextArtifactRenderer",
    # Page generation
    "generate_agent_page",
]

# Custom Artifacts Example

This example demonstrates how to **extend the artifact system** by creating:

1. A **custom artifact type** with domain-specific fields
2. A **UI component** for rendering the artifact in the monitor
3. A **tool** that creates instances of the custom artifact

## Directory Structure

```
custom_artifacts/
├── artifact_types/         # Custom artifact definitions
│   ├── __init__.py
│   └── research_note.py    # ResearchNote artifact type
├── ui_components/          # UI components for rendering
│   ├── __init__.py
│   └── research_note.py    # ResearchNoteComponent
├── tools/                  # Tools that create artifacts
│   ├── save_research_note.py
│   └── save_research_note.yaml
├── configs/                # Agent configurations
│   └── note_taker.yaml
├── tasks/                  # Task definitions
│   └── take_notes.yaml
├── templates/              # System prompt templates
│   └── note_taker_system.yaml
└── README.md
```

## Running the Example

```bash
uv run hugin run \
  --task take_notes \
  --task-path examples/custom_artifacts \
  --parameters '{"topic": "Quantum Computing", "tags": ["physics", "computing"]}'
```

## Creating Custom Artifacts - Step by Step

### Step 1: Define the Artifact Type

Create a new artifact by extending the `Artifact` base class:

```python
# artifact_types/research_note.py
from dataclasses import dataclass, field
from typing import List, Optional

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.utils.uuid import with_uuid


@with_uuid                           # Adds UUID support
@Artifact.register("ResearchNote")   # Register with the artifact system
@dataclass
class ResearchNote(Artifact):
    """A structured research note artifact."""

    # Custom fields for your domain
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    source: Optional[str] = None
    confidence: str = "medium"

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        valid_confidence = ["low", "medium", "high"]
        if self.confidence not in valid_confidence:
            raise ValueError(
                f"Invalid confidence '{self.confidence}'. "
                f"Must be one of: {', '.join(valid_confidence)}"
            )
```

**Key points:**
- Use `@Artifact.register("TypeName")` to register with the system
- Use `@with_uuid` for automatic UUID generation
- Use `@dataclass` for automatic serialization
- Add `__post_init__` for validation
- All fields must be JSON-serializable

### Step 2: Create the UI Component

Create a component to render your artifact in the monitor:

```python
# ui_components/research_note.py
from typing import cast

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry


@ComponentRegistry.register("ResearchNote")  # Match the artifact type name
class ResearchNoteComponent(ArtifactComponent):
    """UI component for ResearchNote artifacts."""

    def render_preview(self, artifact: Artifact) -> str:
        """Compact view for lists and badges."""
        note = cast("ResearchNote", artifact)
        return f"📝 {note.title}"

    def render_detail(self, artifact: Artifact) -> str:
        """Full view when expanded."""
        note = cast("ResearchNote", artifact)
        return f'''
        <div class="research-note">
            <h3>{note.title}</h3>
            <div class="tags">{', '.join(note.tags)}</div>
            <div class="content">{note.content}</div>
        </div>
        '''

    def get_styles(self) -> str:
        """CSS for your component."""
        return '''
        .research-note { padding: 1rem; }
        .research-note h3 { margin: 0 0 0.5rem 0; }
        .research-note .tags { color: #666; font-size: 0.875rem; }
        '''

    def get_scripts(self) -> str:
        """Optional JavaScript for interactivity."""
        return ""
```

**Key points:**
- Use `@ComponentRegistry.register("TypeName")` matching your artifact
- Implement `render_preview()` for compact views
- Implement `render_detail()` for full views
- Use `get_styles()` for custom CSS
- Use `get_scripts()` for custom JavaScript

### Step 3: Create a Tool to Produce the Artifact

Create a tool that lets agents create your artifact:

```python
# tools/save_research_note.py
from typing import TYPE_CHECKING, List, Optional

from gimle.hugin.tools.tool import Tool, ToolResponse
from examples.custom_artifacts.artifact_types.research_note import ResearchNote

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="save_research_note",
    description="Save a structured research note as an artifact.",
    parameters={
        "title": {
            "type": "string",
            "description": "Title for the research note",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Main content (markdown supported)",
            "required": True,
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tags for categorization",
            "required": False,
        },
        # ... more parameters
    },
    is_interactive=False,
)
def save_research_note(
    title: str,
    content: str,
    stack: "Stack",
    tags: Optional[List[str]] = None,
    # ... more parameters
) -> ToolResponse:
    """Save a research note as a ResearchNote artifact."""

    # Create the artifact
    artifact = ResearchNote(
        interaction=stack.interactions[-1],
        title=title,
        content=content,
        tags=tags or [],
    )

    # Attach to current interaction
    stack.interactions[-1].add_artifact(artifact)

    return ToolResponse(
        is_error=False,
        content={"artifact_id": artifact.id, "title": title},
    )
```

**Key points:**
- Use `@Tool.register()` with parameters matching your artifact fields
- Create the artifact instance with `interaction=stack.interactions[-1]`
- Attach using `stack.interactions[-1].add_artifact(artifact)`
- Return the artifact ID in the response

### Step 4: Use in Agent Configuration

Reference your tool in the agent config:

```yaml
# configs/note_taker.yaml
name: note_taker
description: Note-taking assistant that creates structured research notes
system_template: note_taker_system
llm_model: haiku-latest
tools:
  - save_research_note           # Your custom tool
  - builtins.query_artifacts:query_artifacts
  - builtins.finish:finish
```

## The ResearchNote Artifact

This example implements a `ResearchNote` artifact with:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Note title (required) |
| `content` | string | Main content in markdown |
| `tags` | list[str] | Categorization tags |
| `source` | string | Source URL/reference |
| `confidence` | string | low/medium/high |

### UI Component Features

The `ResearchNoteComponent` provides:

- **Preview**: Shows title with confidence indicator and tag count
- **Detail**: Full note with styled header, tags, source link, and content
- **Dark mode**: Automatic dark mode support
- **Markdown**: Content rendered as markdown

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Monitor                            │
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │  Artifact    │────▶│  Component   │────▶│   Rendered   │   │
│  │  (data)      │     │  (renderer)  │     │   (HTML)     │   │
│  └──────────────┘     └──────────────┘     └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        ▲
        │
┌───────┴───────┐
│    Tool       │
│ (creates)     │
└───────────────┘
        ▲
        │
┌───────┴───────┐
│    Agent      │
│ (calls tool)  │
└───────────────┘
```

## Best Practices

### Artifact Design
- Keep fields JSON-serializable (strings, numbers, lists, dicts)
- Add validation in `__post_init__`
- Include `Optional` defaults for non-required fields
- Document field purposes in docstrings

### Component Design
- Keep `render_preview()` compact (< 50 chars ideal)
- Handle missing/None values gracefully
- Use CSS variables for theming (e.g., `var(--text-primary)`)
- Support dark mode with `[data-theme="dark"]` selectors
- Escape user content to prevent XSS

### Tool Design
- Validate input before creating artifacts
- Return the artifact ID for tracking
- Use descriptive error messages
- Handle exceptions gracefully

## Extending Further

### Adding More Artifact Types

Follow the same pattern:
1. Create `artifact_types/my_artifact.py` with `@Artifact.register()`
2. Create `ui_components/my_artifact.py` with `@ComponentRegistry.register()`
3. Create `tools/my_tool.py` with `@Tool.register()`

### Integration with Existing Systems

Your custom artifacts automatically work with:
- `builtins.query_artifacts` - Search across all artifact types
- `builtins.get_artifact_content` - Retrieve full artifact content
- Storage persistence - Artifacts are saved and loaded automatically
- Agent monitor - Your UI component renders in the artifact views

## See Also

- `examples/artifacts/` - Basic artifact usage (query, save, retrieve)
- `src/gimle/hugin/artifacts/` - Built-in artifact types
- `src/gimle/hugin/ui/components/` - Built-in UI components
- `apps/rap_machine/artifacts/` - Another custom artifact example

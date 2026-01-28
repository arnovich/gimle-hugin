"""Preview generated files."""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def preview_files(
    stack: "Stack",
) -> ToolResponse:
    """Display all generated files for review.

    Args:
        stack: Agent stack (auto-injected)

    Returns:
        ToolResponse with preview of all generated files
    """
    generated_files = stack.agent.environment.env_vars.get(
        "generated_files", {}
    )

    if not generated_files:
        return ToolResponse(
            is_error=True,
            content={"error": "No files have been generated yet"},
        )

    # Format preview
    preview_lines = [
        "=" * 60,
        "GENERATED FILES PREVIEW",
        "=" * 60,
        "",
    ]

    for file_path in sorted(generated_files.keys()):
        content = generated_files[file_path]
        preview_lines.append(f"--- {file_path} ---")
        preview_lines.append(content)
        preview_lines.append("")

    preview_lines.append("=" * 60)
    preview_lines.append(f"Total files: {len(generated_files)}")

    preview_text = "\n".join(preview_lines)

    return ToolResponse(
        is_error=False,
        content={
            "preview": preview_text,
            "file_count": len(generated_files),
            "files": list(sorted(generated_files.keys())),
        },
    )

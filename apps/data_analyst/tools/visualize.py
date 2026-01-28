"""Visualization Tool for Data Analyst Agent."""

import base64
import io
import json
import os
from typing import TYPE_CHECKING, Optional

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from gimle.hugin.artifacts.image import Image
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

matplotlib.use("Agg")  # Use non-interactive backend


def visualize_tool(
    data: str,
    chart_type: str,
    x_column: Optional[str],
    y_column: Optional[str],
    title: Optional[str],
    x_label: Optional[str],
    y_label: Optional[str],
    stack: Optional["Stack"],
) -> ToolResponse:
    """
    Create a visualization from data.

    Args:
        data: JSON string of data (list of dictionaries)
        chart_type: Type of chart to create
        x_column: Column name for x-axis
        y_column: Column name for y-axis
        title: Chart title
        x_label: X-axis label
        y_label: Y-axis label
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with visualization file path and metadata
    """
    try:
        try:
            data_dict = json.loads(data)
        except json.JSONDecodeError:
            # If it's not valid JSON, try to interpret it as a file path
            # For now, just raise an error
            return ToolResponse(
                is_error=True,
                content={"error": f"Invalid JSON string: {data[:100]}"},
            )

        df = pd.DataFrame(data_dict)

        # Determine output directory from storage if available
        output_dir = "./storage/visualizations"  # fallback
        if stack and stack.agent.session.storage:
            storage = stack.agent.session.storage
            if hasattr(storage, "base_path") and storage.base_path:
                output_dir = str(storage.base_path / "visualizations")
        os.makedirs(output_dir, exist_ok=True)

        # Generate filename
        import uuid

        filename = f"chart_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(output_dir, filename)

        # Create the plot
        plt.figure(figsize=(10, 6))

        if chart_type == "line":
            if not x_column or not y_column:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": "x_column and y_column required for line chart"
                    },
                )
            plt.plot(df[x_column], df[y_column])
            plt.xlabel(x_label or x_column)
            plt.ylabel(y_label or y_column)

        elif chart_type == "bar":
            if not x_column or not y_column:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": "x_column and y_column required for bar chart"
                    },
                )
            plt.bar(df[x_column], df[y_column])
            plt.xlabel(x_label or x_column)
            plt.ylabel(y_label or y_column)
            plt.xticks(rotation=45, ha="right")

        elif chart_type == "scatter":
            if not x_column or not y_column:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": "x_column and y_column required for scatter chart"
                    },
                )
            plt.scatter(df[x_column], df[y_column])
            plt.xlabel(x_label or x_column)
            plt.ylabel(y_label or y_column)

        elif chart_type == "histogram":
            if not y_column:
                return ToolResponse(
                    is_error=True,
                    content={"error": "y_column required for histogram"},
                )
            plt.hist(df[y_column], bins=20)
            plt.xlabel(x_label or y_column)
            plt.ylabel("Frequency")

        elif chart_type == "pie":
            if not x_column or not y_column:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": "x_column and y_column required for pie chart"
                    },
                )
            plt.pie(df[y_column], labels=df[x_column], autopct="%1.1f%%")

        elif chart_type == "box":
            if not y_column:
                return ToolResponse(
                    is_error=True,
                    content={"error": "y_column required for box plot"},
                )
            plt.boxplot(df[y_column])
            plt.ylabel(y_label or y_column)

        else:
            return ToolResponse(
                is_error=True,
                content={"error": f"Unsupported chart type: {chart_type}"},
            )

        if title:
            plt.title(title)

        plt.tight_layout()

        # Save to buffer for artifact
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")

        # Also save to file
        plt.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close()

        # Create Image artifact if stack is available
        artifact_id = None
        if stack and stack.interactions and stack.agent.session.storage:
            storage = stack.agent.session.storage
            artifact = Image.create_from_base64(
                interaction=stack.interactions[-1],
                content=img_base64,
                storage=storage,
                content_type="image/png",
                name=title or filename,
                description=f"{chart_type} chart"
                + (f": {title}" if title else ""),
            )
            stack.interactions[-1].add_artifact(artifact)
            artifact_id = artifact.id

        return ToolResponse(
            is_error=False,
            content={
                "filepath": filepath,
                "filename": filename,
                "chart_type": chart_type,
                "title": title,
                "artifact_id": artifact_id,
            },
        )

    except Exception as e:
        return ToolResponse(is_error=True, content={"error": str(e)})

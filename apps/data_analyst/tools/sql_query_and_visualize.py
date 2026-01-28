"""Tool that chains SQL query execution with automatic visualization."""

import json
from typing import Optional

from sql_query import sql_query_tool

from gimle.hugin.tools.tool import ToolResponse


def sql_query_and_visualize(
    query: str,
    data_source: str,
    chart_type: str,
    x_column: Optional[str],
    y_column: Optional[str],
    title: Optional[str],
    x_label: Optional[str],
    y_label: Optional[str],
) -> ToolResponse:
    """
    Execute a SQL query and automatically visualize the results.

    This tool chains sql_query -> visualize, reducing LLM calls for the common
    pattern of querying data and then creating a chart from the results.

    The intermediate SQL results are hidden from the LLM context since the
    visualization tool will handle them directly.

    Args:
        query: The SQL query to execute
        data_source: Path to the data source (SQLite, CSV)
        chart_type: Type of chart ('line', 'bar', 'scatter', 'histogram', 'pie', 'box')
        x_column: Column name for x-axis (optional)
        y_column: Column name for y-axis (optional, required for line/bar/scatter)
        title: Chart title (optional)
        x_label: X-axis label (optional)
        y_label: Y-axis label (optional)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        ToolResponse that chains to visualize tool
    """
    # First, execute the SQL query
    sql_result: ToolResponse = sql_query_tool(
        query=query, data_source=data_source
    )

    # If SQL query failed, return the error
    if sql_result.is_error:
        return sql_result

    # Extract the data from SQL results
    sql_content = sql_result.content
    if not sql_content.get("success") or "data" not in sql_content:
        return ToolResponse(
            is_error=True,
            content={
                "error": "SQL query returned no data",
                "sql_result": sql_content,
            },
        )

    # Prepare data as JSON string for visualize tool
    data_json = json.dumps(sql_content["data"])

    # Build args for visualize tool
    visualize_args = {
        "data": data_json,
        "chart_type": chart_type,
    }

    # Add optional parameters if provided
    if x_column:
        visualize_args["x_column"] = x_column
    if y_column:
        visualize_args["y_column"] = y_column
    if title:
        visualize_args["title"] = title
    if x_label:
        visualize_args["x_label"] = x_label
    if y_label:
        visualize_args["y_label"] = y_label

    # Chain to visualize tool, hiding intermediate SQL results from context
    return ToolResponse(
        is_error=False,
        content={
            "status": "chaining",
            "message": f"Query returned {sql_content['row_count']} rows, chaining to visualization",
            "columns": sql_content["columns"],
        },
        next_tool="visualize",
        next_tool_args=visualize_args,
        include_in_context=False,  # Hide intermediate result from LLM
    )

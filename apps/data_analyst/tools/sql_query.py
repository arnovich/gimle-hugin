"""SQL Query Tool for Data Analyst Agent."""

import pandas as pd
from data_utils import get_connection

from gimle.hugin.tools.tool import ToolResponse


def sql_query_tool(query: str, data_source: str) -> ToolResponse:
    """
    Execute a SQL query on a data source.

    Supports:
    - SQLite databases (.db, .sqlite files)
    - CSV files (converted to temporary SQLite database)

    Args:
        query: The SQL query to execute
        data_source: Path to the data source

    Returns:
        Dictionary with query results and metadata
    """
    try:
        conn, _ = get_connection(data_source)

        # Execute query
        df = pd.read_sql_query(query, conn)
        conn.close()

        # Convert to dictionary format
        result = {
            "success": True,
            "row_count": len(df),
            "columns": list(df.columns),
            "data": df.to_dict("records"),  # List of dictionaries
            "query": query,
        }

        # If result is small enough, include full data
        # Otherwise, include sample
        if len(df) > 100:
            result["data"] = df.head(100).to_dict("records")
            result["truncated"] = True
            result["message"] = (
                f"Results truncated to first 100 rows. Total rows: {len(df)}"
            )
        else:
            result["truncated"] = False

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        return ToolResponse(
            is_error=True, content={"error": str(e), "query": query}
        )

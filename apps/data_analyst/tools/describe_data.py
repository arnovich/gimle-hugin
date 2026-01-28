"""Data Profiling Tool for Data Analyst Agent."""

from typing import Any, Optional, Union

import pandas as pd
from data_utils import list_tables, load_dataframe

from gimle.hugin.tools.tool import ToolResponse


def describe_data_tool(
    data_source: str,
    table_name: Optional[str] = None,
) -> ToolResponse:
    """
    Generate a comprehensive profile of a dataset.

    Provides statistics about columns, data types, missing values,
    unique counts, and basic distributions to help understand the data
    before analysis.

    Args:
        data_source: Path to CSV file or SQLite database
        table_name: Table name (required for SQLite databases)

    Returns:
        Dictionary with comprehensive data profile
    """
    try:
        # Load data using shared utility
        try:
            df, inferred_table = load_dataframe(data_source, table_name)
        except ValueError as e:
            # Handle case where table_name is required
            error_msg = str(e)
            if "table_name required" in error_msg:
                tables = list_tables(data_source)
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": "table_name required for SQLite database",
                        "available_tables": tables,
                    },
                )
            raise

        # Basic info
        profile = {
            "table_name": inferred_table,
            "row_count": len(df),
            "column_count": len(df.columns),
            "memory_usage_mb": round(
                df.memory_usage(deep=True).sum() / 1024 / 1024, 2
            ),
            "columns": {},
        }

        # Column-level profiling
        for col in df.columns:
            col_data = df[col]
            col_profile = {
                "dtype": str(col_data.dtype),
                "non_null_count": int(col_data.count()),
                "null_count": int(col_data.isna().sum()),
                "null_percentage": round(
                    col_data.isna().sum() / len(df) * 100, 2
                ),
                "unique_count": int(col_data.nunique()),
                "unique_percentage": round(
                    col_data.nunique() / len(df) * 100, 2
                ),
            }

            # Numeric columns: add statistics
            if pd.api.types.is_numeric_dtype(col_data):
                col_profile["is_numeric"] = True
                col_profile["min"] = _safe_value(col_data.min())
                col_profile["max"] = _safe_value(col_data.max())
                col_profile["mean"] = _safe_value(col_data.mean())
                col_profile["median"] = _safe_value(col_data.median())
                col_profile["std"] = _safe_value(col_data.std())
                col_profile["sum"] = _safe_value(col_data.sum())

                # Quartiles
                col_profile["q25"] = _safe_value(col_data.quantile(0.25))
                col_profile["q75"] = _safe_value(col_data.quantile(0.75))

            else:
                col_profile["is_numeric"] = False

                # For categorical/string columns: top values
                if col_data.nunique() <= 20:
                    value_counts = col_data.value_counts().head(10)
                    col_profile["top_values"] = {
                        str(k): int(v) for k, v in value_counts.items()
                    }
                else:
                    value_counts = col_data.value_counts().head(5)
                    col_profile["top_5_values"] = {
                        str(k): int(v) for k, v in value_counts.items()
                    }

            # Check for potential date columns
            if col_data.dtype == "object":
                sample = col_data.dropna().head(5).tolist()
                col_profile["sample_values"] = [str(v) for v in sample]

            profile["columns"][col] = col_profile

        # Identify potential issues
        issues = []
        for col, stats in profile["columns"].items():
            if stats["null_percentage"] > 50:
                issues.append(f"'{col}' has {stats['null_percentage']}% nulls")
            if stats["unique_count"] == 1:
                issues.append(f"'{col}' has only one unique value")
            if stats["unique_count"] == profile["row_count"]:
                issues.append(f"'{col}' might be an ID column (all unique)")

        profile["potential_issues"] = issues

        # Suggest analysis approaches
        numeric_cols = [
            c
            for c, s in profile["columns"].items()
            if s.get("is_numeric", False)
        ]
        categorical_cols = [
            c
            for c, s in profile["columns"].items()
            if not s.get("is_numeric", False)
        ]

        profile["suggestions"] = {
            "numeric_columns": numeric_cols,
            "categorical_columns": categorical_cols,
            "recommended_analyses": [],
        }

        if len(numeric_cols) >= 2:
            profile["suggestions"]["recommended_analyses"].append(
                "Correlation analysis between numeric columns"
            )
        if categorical_cols and numeric_cols:
            profile["suggestions"]["recommended_analyses"].append(
                "Group-by analysis: aggregate numeric columns by categories"
            )
        if any("date" in c.lower() for c in df.columns):
            profile["suggestions"]["recommended_analyses"].append(
                "Time series analysis on date columns"
            )

        return ToolResponse(is_error=False, content=profile)

    except Exception as e:
        return ToolResponse(is_error=True, content={"error": str(e)})


def _safe_value(val: Any) -> Union[int, float, str, None]:
    """Convert numpy/pandas values to Python native types."""
    if pd.isna(val):
        return None
    try:
        if hasattr(val, "item"):
            return val.item()  # type: ignore[no-any-return]
        return float(val) if isinstance(val, (int, float)) else val
    except (ValueError, TypeError):
        return str(val)

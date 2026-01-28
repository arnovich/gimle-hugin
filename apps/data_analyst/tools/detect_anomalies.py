"""Anomaly Detection Tool for Data Analyst Agent."""

import json
from typing import Any, Dict, List, Optional

import pandas as pd
from scipy import stats

from gimle.hugin.tools.tool import ToolResponse


def detect_anomalies_tool(
    data: str,
    columns: List[str],
    method: str = "iqr",
    threshold: Optional[float] = None,
) -> ToolResponse:
    """
    Detect anomalies/outliers in data using various methods.

    Args:
        data: JSON string of data (list of dictionaries)
        columns: Column names to check for anomalies
        method: Detection method - 'iqr', 'zscore', or 'modified_zscore'
        threshold: Custom threshold (default varies by method)
        stack: The stack (passed automatically)

    Returns:
        Dictionary with detected anomalies and statistics
    """
    try:
        # Parse data
        try:
            data_dict = json.loads(data)
        except json.JSONDecodeError:
            return ToolResponse(
                is_error=True,
                content={"error": f"Invalid JSON: {data[:100]}..."},
            )

        df = pd.DataFrame(data_dict)

        # Validate columns
        missing_cols = [c for c in columns if c not in df.columns]
        if missing_cols:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Columns not found: {missing_cols}",
                    "available_columns": list(df.columns),
                },
            )

        # Filter to numeric columns only
        numeric_cols = [
            c for c in columns if pd.api.types.is_numeric_dtype(df[c])
        ]
        if not numeric_cols:
            return ToolResponse(
                is_error=True,
                content={
                    "error": "No numeric columns found in selection",
                    "selected_columns": columns,
                },
            )

        result: Dict[str, Any] = {
            "method": method,
            "columns_analyzed": numeric_cols,
            "total_rows": len(df),
            "anomalies_by_column": {},
            "summary": {},
        }

        all_anomaly_indices = set()

        for col in numeric_cols:
            col_data = df[col].dropna()

            if method == "iqr":
                # Interquartile Range method
                q1 = col_data.quantile(0.25)
                q3 = col_data.quantile(0.75)
                iqr = q3 - q1
                multiplier = threshold if threshold else 1.5

                lower_bound = q1 - (multiplier * iqr)
                upper_bound = q3 + (multiplier * iqr)

                anomalies_mask = (df[col] < lower_bound) | (
                    df[col] > upper_bound
                )
                anomaly_indices = df[anomalies_mask].index.tolist()

                col_result = {
                    "method_details": {
                        "q1": _safe_float(q1),
                        "q3": _safe_float(q3),
                        "iqr": _safe_float(iqr),
                        "multiplier": multiplier,
                        "lower_bound": _safe_float(lower_bound),
                        "upper_bound": _safe_float(upper_bound),
                    },
                    "anomaly_count": len(anomaly_indices),
                    "anomaly_percentage": round(
                        len(anomaly_indices) / len(df) * 100, 2
                    ),
                }

            elif method == "zscore":
                # Z-score method
                z_threshold = threshold if threshold else 3.0
                z_scores = stats.zscore(col_data)

                # Map z-scores back to original dataframe
                z_score_series = pd.Series(index=col_data.index, data=z_scores)
                anomalies_mask = z_score_series.abs() > z_threshold
                anomaly_indices = col_data[anomalies_mask].index.tolist()

                col_result = {
                    "method_details": {
                        "threshold": z_threshold,
                        "mean": _safe_float(col_data.mean()),
                        "std": _safe_float(col_data.std()),
                    },
                    "anomaly_count": len(anomaly_indices),
                    "anomaly_percentage": round(
                        len(anomaly_indices) / len(df) * 100, 2
                    ),
                }

            elif method == "modified_zscore":
                # Modified Z-score (more robust, uses median)
                z_threshold = threshold if threshold else 3.5
                median = col_data.median()
                mad = (col_data - median).abs().median()

                if mad == 0:
                    # All values are the same as median
                    anomaly_indices = []
                    modified_z = pd.Series(0, index=col_data.index)
                else:
                    modified_z = 0.6745 * (col_data - median) / mad
                    anomalies_mask = modified_z.abs() > z_threshold
                    anomaly_indices = col_data[anomalies_mask].index.tolist()

                col_result = {
                    "method_details": {
                        "threshold": z_threshold,
                        "median": _safe_float(median),
                        "mad": _safe_float(mad),
                    },
                    "anomaly_count": len(anomaly_indices),
                    "anomaly_percentage": round(
                        len(anomaly_indices) / len(df) * 100, 2
                    ),
                }

            else:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": f"Unknown method: {method}",
                        "available_methods": [
                            "iqr",
                            "zscore",
                            "modified_zscore",
                        ],
                    },
                )

            # Get anomaly details (limit to first 20)
            if anomaly_indices:
                anomaly_rows = df.loc[anomaly_indices[:20]].to_dict("records")
                col_result["anomaly_examples"] = anomaly_rows
                if len(anomaly_indices) > 20:
                    col_result["note"] = (
                        f"Showing first 20 of {len(anomaly_indices)} anomalies"
                    )

                # Statistics about anomalies
                anomaly_values = df.loc[anomaly_indices, col]
                col_result["anomaly_stats"] = {
                    "min": _safe_float(anomaly_values.min()),
                    "max": _safe_float(anomaly_values.max()),
                    "mean": _safe_float(anomaly_values.mean()),
                }

            all_anomaly_indices.update(anomaly_indices)
            result["anomalies_by_column"][col] = col_result

        # Overall summary
        result["summary"] = {
            "total_anomaly_rows": len(all_anomaly_indices),
            "total_anomaly_percentage": round(
                len(all_anomaly_indices) / len(df) * 100, 2
            ),
            "columns_with_anomalies": [
                col
                for col, stats in result["anomalies_by_column"].items()
                if stats["anomaly_count"] > 0
            ],
        }

        # Recommendations
        recommendations = []
        for col, col_stats in result["anomalies_by_column"].items():
            pct = col_stats["anomaly_percentage"]
            if pct > 10:
                recommendations.append(
                    f"'{col}' has {pct}% anomalies - investigate data quality"
                )
            elif pct > 0:
                recommendations.append(
                    f"'{col}' has {col_stats['anomaly_count']} outliers - "
                    "review if these are valid extreme values"
                )

        result["recommendations"] = recommendations

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        return ToolResponse(is_error=True, content={"error": str(e)})


def _safe_float(val: Any) -> Optional[float]:
    """Convert to float safely, handling NaN and infinity."""
    if pd.isna(val):
        return None
    try:
        f = float(val)
        if pd.isna(f) or f == float("inf") or f == float("-inf"):
            return None
        return round(f, 6)
    except (ValueError, TypeError):
        return None

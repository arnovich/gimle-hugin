"""Statistical Analysis Tool for Data Analyst Agent."""

import json
from typing import Any, Dict, List, Optional

import pandas as pd
from scipy import stats

from gimle.hugin.tools.tool import ToolResponse


def calculate_statistics_tool(
    data: str,
    analysis_type: str,
    columns: List[str],
    group_by: Optional[str] = None,
) -> ToolResponse:
    """
    Perform statistical analysis on data.

    Supports various statistical analyses including descriptive statistics,
    correlation, distribution tests, and group comparisons.

    Args:
        data: JSON string of data (list of dictionaries)
        analysis_type: Type of analysis to perform
        columns: Column names to analyze
        group_by: Optional column to group by for comparisons
        stack: The stack (passed automatically)

    Returns:
        Dictionary with statistical results
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

        # Validate columns exist
        missing_cols = [c for c in columns if c not in df.columns]
        if missing_cols:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Columns not found: {missing_cols}",
                    "available_columns": list(df.columns),
                },
            )

        result: Dict[str, Any] = {
            "analysis_type": analysis_type,
            "columns": columns,
            "row_count": len(df),
        }

        if analysis_type == "descriptive":
            # Comprehensive descriptive statistics
            result["statistics"] = {}
            for col in columns:
                col_data = df[col].dropna()
                if pd.api.types.is_numeric_dtype(col_data):
                    result["statistics"][col] = {
                        "count": int(len(col_data)),
                        "mean": _safe_float(col_data.mean()),
                        "std": _safe_float(col_data.std()),
                        "min": _safe_float(col_data.min()),
                        "q25": _safe_float(col_data.quantile(0.25)),
                        "median": _safe_float(col_data.median()),
                        "q75": _safe_float(col_data.quantile(0.75)),
                        "max": _safe_float(col_data.max()),
                        "range": _safe_float(col_data.max() - col_data.min()),
                        "iqr": _safe_float(
                            col_data.quantile(0.75) - col_data.quantile(0.25)
                        ),
                        "variance": _safe_float(col_data.var()),
                        "skewness": _safe_float(col_data.skew()),
                        "kurtosis": _safe_float(col_data.kurtosis()),
                        "sum": _safe_float(col_data.sum()),
                    }
                else:
                    result["statistics"][col] = {
                        "count": int(len(col_data)),
                        "unique": int(col_data.nunique()),
                        "mode": (
                            str(col_data.mode().iloc[0])
                            if len(col_data.mode()) > 0
                            else None
                        ),
                        "mode_frequency": (
                            int(col_data.value_counts().iloc[0])
                            if len(col_data) > 0
                            else 0
                        ),
                    }

        elif analysis_type == "correlation":
            # Correlation matrix for numeric columns
            numeric_cols = [
                c for c in columns if pd.api.types.is_numeric_dtype(df[c])
            ]
            if len(numeric_cols) < 2:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": "Need at least 2 numeric columns for correlation"
                    },
                )

            corr_matrix = df[numeric_cols].corr()
            result["correlation_matrix"] = {
                col: {
                    c2: _safe_float(corr_matrix.loc[col, c2])
                    for c2 in numeric_cols
                }
                for col in numeric_cols
            }

            # Find strong correlations
            strong_correlations = []
            for i, col1 in enumerate(numeric_cols):
                for col2 in numeric_cols[i + 1 :]:  # noqa: E203
                    corr = corr_matrix.loc[col1, col2]
                    if abs(corr) >= 0.5:
                        strong_correlations.append(
                            {
                                "column1": col1,
                                "column2": col2,
                                "correlation": _safe_float(corr),
                                "strength": (
                                    "strong" if abs(corr) >= 0.7 else "moderate"
                                ),
                            }
                        )
            result["strong_correlations"] = strong_correlations

        elif analysis_type == "distribution":
            # Test for normality and describe distribution
            result["distributions"] = {}
            for col in columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    continue

                col_data = df[col].dropna()
                if len(col_data) < 8:
                    result["distributions"][col] = {
                        "error": "Not enough data points for distribution test"
                    }
                    continue

                # Shapiro-Wilk test for normality (sample if too large)
                sample = (
                    col_data.sample(5000) if len(col_data) > 5000 else col_data
                )
                shapiro_stat, shapiro_p = stats.shapiro(sample)

                result["distributions"][col] = {
                    "normality_test": {
                        "test": "shapiro-wilk",
                        "statistic": _safe_float(shapiro_stat),
                        "p_value": _safe_float(shapiro_p),
                        "is_normal": shapiro_p > 0.05,
                        "interpretation": (
                            "Data appears normally distributed"
                            if shapiro_p > 0.05
                            else "Data does not appear normally distributed"
                        ),
                    },
                    "skewness": _safe_float(col_data.skew()),
                    "kurtosis": _safe_float(col_data.kurtosis()),
                    "skew_interpretation": _interpret_skewness(col_data.skew()),
                }

        elif analysis_type == "group_comparison":
            # Compare groups
            if not group_by:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": "group_by parameter required for group_comparison"
                    },
                )

            if group_by not in df.columns:
                return ToolResponse(
                    is_error=True,
                    content={"error": f"Group column '{group_by}' not found"},
                )

            result["group_by"] = group_by
            result["groups"] = {}
            result["comparisons"] = []

            groups = df[group_by].unique()
            result["group_count"] = len(groups)

            # Statistics per group
            for col in columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    continue

                result["groups"][col] = {}
                for group in groups:
                    group_data = df[df[group_by] == group][col].dropna()
                    result["groups"][col][str(group)] = {
                        "count": int(len(group_data)),
                        "mean": _safe_float(group_data.mean()),
                        "std": _safe_float(group_data.std()),
                        "median": _safe_float(group_data.median()),
                    }

                # ANOVA or t-test between groups
                group_data_list = [
                    df[df[group_by] == g][col].dropna() for g in groups
                ]
                group_data_list = [g for g in group_data_list if len(g) >= 2]

                if len(group_data_list) >= 2:
                    if len(group_data_list) == 2:
                        # t-test for two groups
                        stat, p_value = stats.ttest_ind(
                            group_data_list[0], group_data_list[1]
                        )
                        test_name = "t-test"
                    else:
                        # ANOVA for multiple groups
                        stat, p_value = stats.f_oneway(*group_data_list)
                        test_name = "ANOVA"

                    result["comparisons"].append(
                        {
                            "column": col,
                            "test": test_name,
                            "statistic": _safe_float(stat),
                            "p_value": _safe_float(p_value),
                            "significant": p_value < 0.05,
                            "interpretation": (
                                f"Significant difference between groups (p={p_value:.4f})"
                                if p_value < 0.05
                                else f"No significant difference between groups (p={p_value:.4f})"
                            ),
                        }
                    )

        elif analysis_type == "percentiles":
            # Detailed percentile analysis
            result["percentiles"] = {}
            percentile_points = [1, 5, 10, 25, 50, 75, 90, 95, 99]

            for col in columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    continue

                col_data = df[col].dropna()
                result["percentiles"][col] = {
                    f"p{p}": _safe_float(col_data.quantile(p / 100))
                    for p in percentile_points
                }

        else:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Unknown analysis_type: {analysis_type}",
                    "available_types": [
                        "descriptive",
                        "correlation",
                        "distribution",
                        "group_comparison",
                        "percentiles",
                    ],
                },
            )

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


def _interpret_skewness(skew: float) -> str:
    """Interpret skewness value."""
    if abs(skew) < 0.5:
        return "Approximately symmetric"
    elif skew > 0:
        return "Right-skewed (positive skew) - tail extends to higher values"
    else:
        return "Left-skewed (negative skew) - tail extends to lower values"

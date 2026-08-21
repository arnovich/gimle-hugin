"""Pipeline tools demonstrating deterministic tool chaining."""

import json
from typing import Any

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def validate_data(data: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Validate input data and chain to transform_data if valid."""
    try:
        # Parse JSON data
        parsed = json.loads(data)

        # Basic validation
        if not isinstance(parsed, dict):
            return ToolResponse(
                is_error=True,
                content={"error": "Data must be a JSON object"},
            )

        # Store original for reference
        stack.set_shared_state("original_data", parsed)

        # Chain to transform_data - this happens automatically without LLM
        return ToolResponse(
            is_error=False,
            content={
                "status": "validated",
                "fields": list(parsed.keys()),
            },
            next_tool="transform_data",
            next_tool_args={"validated_data": json.dumps(parsed)},
            include_in_context=False,  # Hide intermediate step from LLM
        )

    except json.JSONDecodeError as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Invalid JSON: {e}"},
        )


def transform_data(
    validated_data: str, stack: Stack, **kwargs: Any
) -> ToolResponse:
    """Transform validated data and chain to store_data."""
    parsed = json.loads(validated_data)

    # Apply transformations
    transformed: dict[str, Any] = {}
    for key, value in parsed.items():
        # Normalize keys to lowercase
        new_key = key.lower().replace(" ", "_")

        # Transform values
        if isinstance(value, str):
            transformed[new_key] = value.strip().title()
        elif isinstance(value, (int, float)):
            transformed[new_key] = value
        else:
            transformed[new_key] = value

    # Chain to store_data
    return ToolResponse(
        is_error=False,
        content={
            "status": "transformed",
            "transformations_applied": ["normalize_keys", "title_case_strings"],
        },
        next_tool="store_data",
        next_tool_args={"transformed_data": json.dumps(transformed)},
        include_in_context=False,  # Hide intermediate step from LLM
    )


def store_data(
    transformed_data: str, stack: Stack, **kwargs: Any
) -> ToolResponse:
    """Store the transformed data. End of the chain."""
    parsed = json.loads(transformed_data)

    # Store in shared state (simulating database storage)
    stored_records = stack.get_shared_state("stored_records", default=[])
    record_id = len(stored_records) + 1
    stored_records.append(parsed)
    stack.set_shared_state("stored_records", stored_records)

    # End of chain - return to LLM with full result
    # include_in_context=True (default) so LLM sees the final result
    return ToolResponse(
        is_error=False,
        content={
            "status": "stored",
            "record_id": record_id,
            "stored_data": parsed,
            "message": "Data validated, transformed, and stored successfully.",
        },
    )


def get_stored_records(stack: Stack, **kwargs: Any) -> ToolResponse:
    """Retrieve all stored records."""
    records = stack.get_shared_state("stored_records", default=[])

    return ToolResponse(
        is_error=False,
        content={
            "count": len(records),
            "records": records,
        },
    )

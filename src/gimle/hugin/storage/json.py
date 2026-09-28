"""JSON normalization shared by storage snapshots and persisted records."""

import datetime
import json
from typing import Any


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles non-serializable types gracefully."""

    def default(self, o: Any) -> Any:
        """Convert non-serializable objects to strings."""
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        # Handle pandas Timestamp and other datetime-like objects
        if callable(getattr(o, "isoformat", None)):
            formatted = o.isoformat()
            if isinstance(formatted, str):
                return formatted
        if callable(getattr(o, "item", None)):
            # numpy scalar types
            value = o.item()
            if (
                isinstance(value, (str, int, float, bool, list, dict))
                or value is None
            ):
                return value
        return str(o)


def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert non-serializable dict keys and values."""
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    return obj

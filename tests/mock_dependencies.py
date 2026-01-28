"""Mock dependencies for testing.

This module provides mock implementations of missing dependencies.
"""

from typing import Any, Dict


class MockTool:
    """Mock Tool class for testing.

    This is a simple mock tool class for use in test fixtures.
    It does NOT replace the real Tool class - the real Tool class
    must be available for @Tool.register() decorators to work.
    """

    def __init__(self, name: str, description: str, parameters: Dict[str, Any]):
        """Initialize the mock tool."""
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_dict(self) -> Dict[str, Any]:
        """Convert tool to dictionary format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    name: {
                        "type": params["type"],
                        "description": params["description"],
                    }
                    for name, params in self.parameters.items()
                },
                "required": [
                    name
                    for name, params in self.parameters.items()
                    if params.get("required")
                ],
            },
        }

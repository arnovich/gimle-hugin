"""Agent configuration module."""

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from gimle.hugin.agent.config_state_machine import ConfigStateMachine


@dataclass
class Config:
    """Configuration for an agent.

    Attributes:
        name: Unique identifier for this configuration.
        description: Human-readable description of the agent's purpose.
        system_template: Name of the system prompt template to use.
        llm_model: LLM model identifier (default: "sonnet-latest").
        tools: List of tool names this agent can use.
        interactive: Whether this agent requires human interaction.
        options: Additional configuration options.
        state_namespaces: List of session state namespaces this agent can access.
                         All agents can access "common" namespace by default.
        state_machine: Optional state machine for config transitions.
    """

    name: str
    description: str
    system_template: str
    llm_model: str = "sonnet-latest"
    tools: Optional[List[str]] = field(default_factory=list)
    interactive: bool = False
    options: Dict[str, Any] = field(default_factory=dict)
    state_namespaces: List[str] = field(default_factory=lambda: ["common"])
    # Config state machine for dynamic transitions
    state_machine: Optional["ConfigStateMachine"] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the config to a dictionary.

        Returns:
            The dictionary representation of the config.
        """
        result = asdict(self)
        # Handle state_machine serialization
        if self.state_machine is not None:
            result["state_machine"] = self.state_machine.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Deserialize the config from a dictionary.

        Args:
            data: The dictionary to deserialize the config from.

        Returns:
            The deserialized config.
        """
        # Handle state_machine deserialization
        from gimle.hugin.agent.config_state_machine import ConfigStateMachine

        state_machine_data = data.pop("state_machine", None)
        state_machine = None
        if state_machine_data is not None:
            state_machine = ConfigStateMachine.from_dict(state_machine_data)

        config = cls(**data)
        config.state_machine = state_machine
        return config

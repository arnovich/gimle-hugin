"""Session state management with namespace support."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionState:
    """Manages shared state across agents in a session with namespace support.

    SessionState provides a namespace-based key-value store that agents can use
    to share state during execution. Each namespace can have optional access
    control to restrict which agents can read/write to it.

    The "common" namespace is always available to all agents.

    Access control works in two layers:
    1. Agent's config must declare the namespace in state_namespaces
    2. Namespace can optionally restrict access to specific agent IDs
    """

    def __init__(self, session: Optional["Any"] = None) -> None:
        """Initialize session state with default common namespace.

        Args:
            session: Optional reference to parent session (for agent config lookups)
        """
        self._state: Dict[str, Dict[str, Any]] = {"common": {}}
        self._permissions: Dict[str, List[str]] = {}
        self._session = session

    def create_namespace(
        self, namespace: str, agent_ids: Optional[List[str]] = None
    ) -> None:
        """Create a new namespace with optional access control.

        Args:
            namespace: Name of the namespace to create
            agent_ids: Optional list of agent IDs that can access this namespace.
                      If None, all agents can access (but must declare it in config).
        """
        if namespace in self._state:
            logger.warning(
                f"Namespace '{namespace}' already exists, skipping creation"
            )
            return

        self._state[namespace] = {}

        if agent_ids is not None:
            self._permissions[namespace] = agent_ids
            logger.info(
                f"Created namespace '{namespace}' with access for {len(agent_ids)} agents"
            )
        else:
            logger.info(f"Created namespace '{namespace}' with open access")

    def namespace_exists(self, namespace: str) -> bool:
        """Check if a namespace exists.

        Args:
            namespace: Name of the namespace to check

        Returns:
            True if namespace exists, False otherwise
        """
        return namespace in self._state

    def get(
        self, namespace: str, key: str, agent_id: str, default: Any = None
    ) -> Any:
        """Get a value from a namespace.

        Args:
            namespace: Namespace to read from
            key: Key to retrieve
            agent_id: ID of the agent requesting access
            default: Default value if key doesn't exist

        Returns:
            The value associated with the key, or default if not found

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
        """
        if not self.namespace_exists(namespace):
            raise ValueError(f"Namespace '{namespace}' does not exist")

        if not self._can_access(agent_id, namespace):
            raise PermissionError(
                f"Agent {agent_id} does not have access to namespace '{namespace}'"
            )

        return self._state[namespace].get(key, default)

    def get_all(self, namespace: str, agent_id: str) -> Dict[str, Any]:
        """Get all key-value pairs from a namespace.

        Args:
            namespace: Namespace to read from
            agent_id: ID of the agent requesting access

        Returns:
            Dictionary of all key-value pairs in the namespace

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
        """
        if not self.namespace_exists(namespace):
            raise ValueError(f"Namespace '{namespace}' does not exist")

        if not self._can_access(agent_id, namespace):
            raise PermissionError(
                f"Agent {agent_id} does not have access to namespace '{namespace}'"
            )

        return self._state[namespace].copy()

    def set(self, namespace: str, key: str, value: Any, agent_id: str) -> None:
        """Set a value in a namespace.

        Args:
            namespace: Namespace to write to
            key: Key to set
            value: Value to store
            agent_id: ID of the agent requesting access

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
        """
        if not self.namespace_exists(namespace):
            raise ValueError(f"Namespace '{namespace}' does not exist")

        if not self._can_access(agent_id, namespace):
            raise PermissionError(
                f"Agent {agent_id} does not have access to namespace '{namespace}'"
            )

        self._state[namespace][key] = value
        logger.debug(f"Agent {agent_id} set '{key}' in namespace '{namespace}'")

    def delete(self, namespace: str, key: str, agent_id: str) -> None:
        """Delete a key from a namespace.

        Args:
            namespace: Namespace to delete from
            key: Key to delete
            agent_id: ID of the agent requesting access

        Raises:
            PermissionError: If agent doesn't have access to namespace
            ValueError: If namespace doesn't exist
            KeyError: If key doesn't exist in namespace
        """
        if not self.namespace_exists(namespace):
            raise ValueError(f"Namespace '{namespace}' does not exist")

        if not self._can_access(agent_id, namespace):
            raise PermissionError(
                f"Agent {agent_id} does not have access to namespace '{namespace}'"
            )

        del self._state[namespace][key]
        logger.debug(
            f"Agent {agent_id} deleted '{key}' from namespace '{namespace}'"
        )

    def grant_access(self, namespace: str, agent_id: str) -> None:
        """Grant an agent access to a namespace.

        Args:
            namespace: Namespace to grant access to
            agent_id: ID of the agent to grant access

        Raises:
            ValueError: If namespace doesn't exist
        """
        if not self.namespace_exists(namespace):
            raise ValueError(f"Namespace '{namespace}' does not exist")

        if namespace not in self._permissions:
            self._permissions[namespace] = []

        if agent_id not in self._permissions[namespace]:
            self._permissions[namespace].append(agent_id)
            logger.info(
                f"Granted agent {agent_id} access to namespace '{namespace}'"
            )

    def revoke_access(self, namespace: str, agent_id: str) -> None:
        """Revoke an agent's access to a namespace.

        Args:
            namespace: Namespace to revoke access from
            agent_id: ID of the agent to revoke access

        Raises:
            ValueError: If namespace doesn't exist
        """
        if not self.namespace_exists(namespace):
            raise ValueError(f"Namespace '{namespace}' does not exist")

        if (
            namespace in self._permissions
            and agent_id in self._permissions[namespace]
        ):
            self._permissions[namespace].remove(agent_id)
            logger.info(
                f"Revoked agent {agent_id} access from namespace '{namespace}'"
            )

    def list_namespaces(self, agent_id: Optional[str] = None) -> List[str]:
        """List all namespaces, optionally filtered by agent access.

        Args:
            agent_id: If provided, only return namespaces this agent can access

        Returns:
            List of namespace names
        """
        if agent_id is None:
            return list(self._state.keys())

        return [
            ns for ns in self._state.keys() if self._can_access(agent_id, ns)
        ]

    def _can_access(self, agent_id: str, namespace: str) -> bool:
        """Check if an agent can access a namespace.

        Access is granted if:
        1. Namespace is "common" (always accessible), OR
        2. Agent's config declares the namespace in state_namespaces, AND
        3. If namespace has explicit permissions, agent ID is in the list

        Args:
            agent_id: ID of the agent
            namespace: Name of the namespace

        Returns:
            True if agent has access, False otherwise
        """
        # "common" namespace is always accessible
        if namespace == "common":
            return True

        # Check if agent's config declares this namespace
        if self._session is not None:
            agent = self._session.get_agent(agent_id)
            if agent is not None:
                # Check if namespace is in agent's declared namespaces
                if namespace not in agent.config.state_namespaces:
                    logger.debug(
                        f"Agent {agent_id} has not declared namespace '{namespace}' "
                        f"in config.state_namespaces"
                    )
                    return False

        # If namespace has explicit permissions, check them
        if namespace in self._permissions:
            return agent_id in self._permissions[namespace]

        # Otherwise, access is granted (agent declared it in config)
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary for storage.

        Objects in state that have a to_dict() method will be serialized
        using that method. A special __type__ field is added to track the
        class for deserialization.

        Returns:
            Dictionary representation of the state
        """
        serialized_state: Dict[str, Dict[str, Any]] = {}

        for namespace, namespace_data in self._state.items():
            serialized_state[namespace] = {}
            for key, value in namespace_data.items():
                # Check if value has to_dict method (custom serialization)
                if hasattr(value, "to_dict") and callable(
                    getattr(value, "to_dict")
                ):
                    serialized_value = value.to_dict()
                    # Store type information for deserialization
                    serialized_value["__type__"] = (
                        f"{value.__class__.__module__}.{value.__class__.__name__}"
                    )
                    serialized_state[namespace][key] = serialized_value
                else:
                    # Store value as-is (must be JSON serializable)
                    serialized_state[namespace][key] = value

        return {
            "state": serialized_state,
            "permissions": self._permissions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Deserialize state from dictionary.

        Note: Objects with __type__ metadata are stored as dicts.
        They will need to be reconstructed by the application code
        that uses them (e.g., Battle.from_dict()).

        Args:
            data: Dictionary representation of state

        Returns:
            SessionState instance
        """
        state = cls()
        state._state = data.get("state", {"common": {}})
        state._permissions = data.get("permissions", {})
        return state

"""Tests for SessionState."""

import pytest

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.session_state import SessionState
from gimle.hugin.agent.task import Task


@pytest.fixture
def session():
    """Create a test session."""
    env = Environment()
    return Session(environment=env)


@pytest.fixture
def agent_config():
    """Create a test agent config."""
    return Config(
        name="test_agent",
        description="Test agent",
        system_template="test_template",
        state_namespaces=["common", "test_namespace"],
    )


@pytest.fixture
def restricted_agent_config():
    """Create an agent config with only common namespace access."""
    return Config(
        name="restricted_agent",
        description="Restricted test agent",
        system_template="test_template",
        state_namespaces=["common"],  # No access to test_namespace
    )


def test_session_state_initialization():
    """Test SessionState initializes with common namespace."""
    state = SessionState()
    assert state.namespace_exists("common")
    assert state.list_namespaces() == ["common"]


def test_create_namespace():
    """Test creating new namespaces."""
    state = SessionState()
    state.create_namespace("test_ns")
    assert state.namespace_exists("test_ns")
    assert "test_ns" in state.list_namespaces()


def test_create_namespace_with_permissions():
    """Test creating namespace with agent ID restrictions."""
    state = SessionState()
    state.create_namespace("restricted", agent_ids=["agent1", "agent2"])
    assert state.namespace_exists("restricted")


def test_get_set_common_namespace(session, agent_config):
    """Test basic get/set on common namespace."""
    # Create an agent
    task = Task(
        name="test",
        description="test",
        prompt="test",
        parameters={},
    )
    agent = session.create_agent_from_task(agent_config, task)

    # Set and get value
    session.state.set("common", "key1", "value1", agent.id)
    result = session.state.get("common", "key1", agent.id)
    assert result == "value1"


def test_get_with_default(session, agent_config):
    """Test get with default value."""
    task = Task(
        name="test",
        description="test",
        prompt="test",
        parameters={},
    )
    agent = session.create_agent_from_task(agent_config, task)

    result = session.state.get(
        "common", "nonexistent", agent.id, default="default_val"
    )
    assert result == "default_val"


def test_get_all_namespace(session, agent_config):
    """Test getting all key-value pairs from namespace."""
    task = Task(
        name="test",
        description="test",
        prompt="test",
        parameters={},
    )
    agent = session.create_agent_from_task(agent_config, task)

    # Set multiple values
    session.state.set("common", "key1", "value1", agent.id)
    session.state.set("common", "key2", "value2", agent.id)

    # Get all
    all_data = session.state.get_all("common", agent.id)
    assert all_data == {"key1": "value1", "key2": "value2"}


def test_delete_key(session, agent_config):
    """Test deleting a key from namespace."""
    task = Task(
        name="test",
        description="test",
        prompt="test",
        parameters={},
    )
    agent = session.create_agent_from_task(agent_config, task)

    # Set and delete
    session.state.set("common", "key1", "value1", agent.id)
    session.state.delete("common", "key1", agent.id)

    # Key should not exist
    result = session.state.get("common", "key1", agent.id, default=None)
    assert result is None


def test_namespace_access_control_via_config(
    session, agent_config, restricted_agent_config
):
    """Test that agents can only access namespaces declared in their config."""
    # Create namespace
    session.state.create_namespace("test_namespace")

    # Create agents
    task = Task(name="test", description="test", prompt="test", parameters={})
    agent_with_access = session.create_agent_from_task(agent_config, task)

    task2 = Task(
        name="test2", description="test2", prompt="test2", parameters={}
    )
    agent_without_access = session.create_agent_from_task(
        restricted_agent_config, task2
    )

    # Agent with access can write
    session.state.set("test_namespace", "key1", "value1", agent_with_access.id)
    result = session.state.get("test_namespace", "key1", agent_with_access.id)
    assert result == "value1"

    # Agent without access cannot write
    with pytest.raises(PermissionError):
        session.state.set(
            "test_namespace", "key2", "value2", agent_without_access.id
        )

    # Agent without access cannot read
    with pytest.raises(PermissionError):
        session.state.get("test_namespace", "key1", agent_without_access.id)


def test_namespace_permission_list(
    session, agent_config, restricted_agent_config
):
    """Test that permission lists further restrict access."""
    # Update both agents to have access to "restricted" namespace in their config
    config1 = Config(
        name="agent1",
        description="Test agent 1",
        system_template="test",
        state_namespaces=["common", "restricted"],
    )
    config2 = Config(
        name="agent2",
        description="Test agent 2",
        system_template="test",
        state_namespaces=["common", "restricted"],
    )

    task1 = Task(
        name="test1", description="test1", prompt="test1", parameters={}
    )
    agent1 = session.create_agent_from_task(config1, task1)

    task2 = Task(
        name="test2", description="test2", prompt="test2", parameters={}
    )
    agent2 = session.create_agent_from_task(config2, task2)

    # Create namespace that only agent1 can access (permission list restriction)
    session.state.create_namespace("restricted", agent_ids=[agent1.id])

    # Agent1 can access
    session.state.set("restricted", "key1", "value1", agent1.id)
    result = session.state.get("restricted", "key1", agent1.id)
    assert result == "value1"

    # Agent2 cannot access (not in permission list)
    with pytest.raises(PermissionError):
        session.state.set("restricted", "key2", "value2", agent2.id)


def test_grant_revoke_access(session):
    """Test granting and revoking access to namespaces."""
    # Create agent with access to both namespaces
    config = Config(
        name="test_agent",
        description="Test agent",
        system_template="test",
        state_namespaces=["common", "dynamic_access", "restricted_access"],
    )
    task1 = Task(
        name="test1", description="test1", prompt="test1", parameters={}
    )
    agent = session.create_agent_from_task(config, task1)

    # Create namespace
    session.state.create_namespace("dynamic_access")

    # Create another namespace with empty permission list
    session.state.create_namespace("restricted_access", agent_ids=[])

    # Agent cannot access (not in permission list)
    with pytest.raises(PermissionError):
        session.state.get("restricted_access", "key1", agent.id)

    # Grant access
    session.state.grant_access("restricted_access", agent.id)

    # Now can access
    session.state.set("restricted_access", "key1", "value1", agent.id)
    result = session.state.get("restricted_access", "key1", agent.id)
    assert result == "value1"

    # Revoke access
    session.state.revoke_access("restricted_access", agent.id)

    # Cannot access again
    with pytest.raises(PermissionError):
        session.state.get("restricted_access", "key1", agent.id)


def test_list_namespaces_filtered_by_agent(
    session, agent_config, restricted_agent_config
):
    """Test listing namespaces filtered by agent access."""
    # Create namespaces
    session.state.create_namespace("test_namespace")
    session.state.create_namespace("restricted_namespace")

    # Create agents
    task1 = Task(
        name="test1", description="test1", prompt="test1", parameters={}
    )
    agent_with_access = session.create_agent_from_task(agent_config, task1)

    task2 = Task(
        name="test2", description="test2", prompt="test2", parameters={}
    )
    agent_without_access = session.create_agent_from_task(
        restricted_agent_config, task2
    )

    # Agent with access sees both namespaces (plus common)
    namespaces = session.state.list_namespaces(agent_with_access.id)
    assert "common" in namespaces
    assert "test_namespace" in namespaces

    # Restricted agent only sees common
    restricted_namespaces = session.state.list_namespaces(
        agent_without_access.id
    )
    assert "common" in restricted_namespaces
    assert "test_namespace" not in restricted_namespaces


def test_serialization():
    """Test SessionState can be serialized and deserialized."""
    state = SessionState()
    state.create_namespace("test_ns")

    # Create a mock session to set some values
    env = Environment()
    session = Session(environment=env, state=state)

    # Need an agent to set values
    config = Config(
        name="test",
        description="test",
        system_template="test",
        state_namespaces=["common", "test_ns"],
    )
    task = Task(name="test", description="test", prompt="test", parameters={})
    agent = session.create_agent_from_task(config, task)

    state.set("test_ns", "key1", "value1", agent.id)

    # Serialize
    state_dict = state.to_dict()
    assert "state" in state_dict
    assert "permissions" in state_dict

    # Deserialize
    new_state = SessionState.from_dict(state_dict)
    assert new_state.namespace_exists("test_ns")
    assert new_state.namespace_exists("common")


def test_nonexistent_namespace_error(session, agent_config):
    """Test that accessing non-existent namespace raises ValueError."""
    task = Task(name="test", description="test", prompt="test", parameters={})
    agent = session.create_agent_from_task(agent_config, task)

    with pytest.raises(ValueError, match="does not exist"):
        session.state.get("nonexistent", "key1", agent.id)

    with pytest.raises(ValueError, match="does not exist"):
        session.state.set("nonexistent", "key1", "value1", agent.id)


def test_stack_helper_methods(session, agent_config):
    """Test Stack convenience methods for state access."""
    # Create agent
    task = Task(name="test", description="test", prompt="test", parameters={})
    agent = session.create_agent_from_task(agent_config, task)

    # Use stack helpers
    agent.stack.set_shared_state("key1", "value1")
    result = agent.stack.get_shared_state("key1")
    assert result == "value1"

    # Test with custom namespace
    session.state.create_namespace("test_namespace")
    agent.stack.set_shared_state("key2", "value2", namespace="test_namespace")
    result = agent.stack.get_shared_state("key2", namespace="test_namespace")
    assert result == "value2"

    # Test get_all
    all_data = agent.stack.get_all_shared_state("test_namespace")
    assert all_data == {"key2": "value2"}

    # Test delete
    agent.stack.delete_shared_state("key2", namespace="test_namespace")
    result = agent.stack.get_shared_state(
        "key2", namespace="test_namespace", default=None
    )
    assert result is None

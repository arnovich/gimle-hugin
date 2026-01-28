"""Tests for Task serialization and deserialization."""

from gimle.hugin.agent.task import Task


class TestTaskSerialization:
    """Test Task serialization and deserialization."""

    def test_task_to_dict(self):
        """Test serializing a task."""
        task = Task(
            name="test_task",
            description="Test task",
            parameters={
                "param1": {
                    "type": "string",
                    "description": "",
                    "required": False,
                    "default": "value1",
                }
            },
            prompt="Do something",
            tools=["tool1", "tool2"],
            system_template="Custom system",
            llm_model="model1",
        )
        data = task.to_dict()

        assert data["name"] == "test_task"
        assert data["description"] == "Test task"
        assert data["parameters"] == {
            "param1": {
                "type": "string",
                "description": "",
                "required": False,
                "default": "value1",
                "value": "value1",
            }
        }
        assert data["prompt"] == "Do something"
        assert data["tools"] == ["tool1", "tool2"]
        assert data["system_template"] == "Custom system"
        assert data["llm_model"] == "model1"

    def test_task_from_dict(self):
        """Test deserializing a task."""
        data = {
            "name": "test_task",
            "description": "Test task",
            "parameters": {
                "param1": {
                    "type": "string",
                    "description": "",
                    "required": False,
                    "default": "value1",
                }
            },
            "prompt": "Do something",
            "tools": ["tool1"],
            "system_template": "Custom system",
            "llm_model": "model1",
        }
        task = Task.from_dict(data)

        assert task.name == "test_task"
        assert task.description == "Test task"
        assert task.parameters == {
            "param1": {
                "type": "string",
                "description": "",
                "required": False,
                "default": "value1",
                "value": "value1",
            }
        }
        assert task.prompt == "Do something"
        assert task.tools == ["tool1"]
        assert task.system_template == "Custom system"
        assert task.llm_model == "model1"

    def test_task_round_trip(self):
        """Test round-trip serialization/deserialization."""
        task = Task(
            name="round_trip_task",
            description="Round trip test",
            parameters={
                "key": {
                    "type": "string",
                    "description": "",
                    "required": False,
                    "default": "value",
                }
            },
            prompt="Test prompt",
            tools=["tool1", "tool2"],
            system_template="System template",
            llm_model="test-model",
        )

        data = task.to_dict()
        new_task = Task.from_dict(data)

        assert new_task.name == task.name
        assert new_task.description == task.description
        assert new_task.parameters == task.parameters
        assert new_task.prompt == task.prompt
        assert new_task.tools == task.tools
        assert new_task.system_template == task.system_template
        assert new_task.llm_model == task.llm_model

    def test_task_from_dict_with_existing_object(self):
        """Test that from_dict returns existing Task object if passed."""
        task = Task(
            name="test", description="Test", parameters={}, prompt="Test"
        )
        data = task.to_dict()
        result = Task.from_dict(data)

        assert result.name == task.name
        assert result.description == task.description
        assert result.parameters == task.parameters
        assert result.prompt == task.prompt
        assert result.tools == task.tools
        assert result.system_template == task.system_template
        assert result.llm_model == task.llm_model

    def test_task_with_optional_fields(self):
        """Test task serialization with optional fields set to None."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Test",
            tools=None,
            system_template=None,
            llm_model=None,
        )

        data = task.to_dict()
        new_task = Task.from_dict(data)

        assert new_task.tools is None
        assert new_task.system_template is None
        assert new_task.llm_model is None

"""Tests for prompt rendering, templates, and Jinja utilities."""

from io import BytesIO
from unittest.mock import Mock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pandas import DataFrame

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.llm.prompt.jinja import (
    contains_jinja,
    render_jinja,
    render_jinja_recursive,
)
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.llm.prompt.renderer import PromptRenderer, format_df_to_string
from gimle.hugin.llm.prompt.template import Template


class TestTemplate:
    """Test the Template class registration and retrieval."""

    def test_template_creation(self):
        """Test that a template can be created."""
        template = Template(name="test_template", template="Hello {{ name }}")
        assert template.name == "test_template"
        assert template.template == "Hello {{ name }}"

    def test_template_registration(self):
        """Test that templates can be registered."""
        environment = Environment()

        template = Template(name="test_template", template="Hello {{ name }}")
        environment.template_registry.register(template)

        assert "test_template" in environment.template_registry.registered()
        assert (
            environment.template_registry.registered()["test_template"]
            == template
        )

    def test_template_get_template(self):
        """Test that a registered template can be retrieved."""
        environment = Environment()

        template = Template(name="test_template", template="Hello {{ name }}")
        environment.template_registry.register(template)

        retrieved = environment.template_registry.get("test_template")
        assert retrieved == template
        assert retrieved.name == "test_template"
        assert retrieved.template == "Hello {{ name }}"

    def test_template_get_template_not_found(self):
        """Test that getting a non-existent template raises ValueError."""
        environment = Environment()

        with pytest.raises(
            ValueError, match="Item nonexistent not found in registry"
        ):
            environment.template_registry.get("nonexistent")

    def test_template_register_decorator(self):
        """Test the register method."""
        environment = Environment()

        template = Template(
            name="decorated_template", template="Hello {{ name }}"
        )
        environment.template_registry.register(template)

        assert (
            "decorated_template" in environment.template_registry.registered()
        )
        retrieved = environment.template_registry.get("decorated_template")
        assert retrieved.template == "Hello {{ name }}"

    def test_template_registered(self):
        """Test that registered templates can be retrieved."""
        environment = Environment()

        template1 = Template(name="template1", template="Template 1")
        template2 = Template(name="template2", template="Template 2")

        environment.template_registry.register(template1)
        environment.template_registry.register(template2)

        registered = environment.template_registry.registered()
        assert len(registered) == 2
        assert "template1" in registered
        assert "template2" in registered

    def test_template_multiple_registrations(self):
        """Test that registering the same template name overwrites."""
        environment = Environment()

        template1 = Template(name="test", template="First")
        template2 = Template(name="test", template="Second")

        environment.template_registry.register(template1)
        environment.template_registry.register(template2)

        registered = environment.template_registry.registered()
        assert len(registered) == 1
        retrieved = environment.template_registry.get("test")
        assert retrieved.template == "Second"


class TestJinja:
    """Test Jinja rendering utilities."""

    def test_contains_jinja_with_variable(self):
        """Test that contains_jinja detects Jinja variables."""
        assert contains_jinja("Hello {{ name }}") is True
        assert contains_jinja("Hello {{name}}") is True

    def test_contains_jinja_with_control_flow(self):
        """Test that contains_jinja detects Jinja control flow."""
        assert contains_jinja("{% if condition %}Yes{% endif %}") is True
        assert contains_jinja("{% for item in items %}{% endfor %}") is True

    def test_contains_jinja_with_comments(self):
        """Test that contains_jinja detects Jinja comments."""
        assert contains_jinja("Hello {# comment #}") is True

    def test_contains_jinja_no_jinja(self):
        """Test that contains_jinja returns False for non-Jinja text."""
        assert contains_jinja("Hello world") is False
        assert contains_jinja("") is False

    def test_render_jinja_simple(self):
        """Test simple Jinja rendering."""
        template = "Hello {{ name }}"
        inputs = {"name": "World"}
        result = render_jinja(template, inputs)
        assert result == "Hello World"

    def test_render_jinja_multiple_variables(self):
        """Test Jinja rendering with multiple variables."""
        template = "Hello {{ name }}, you are {{ age }} years old"
        inputs = {"name": "Alice", "age": 25}
        result = render_jinja(template, inputs)
        assert result == "Hello Alice, you are 25 years old"

    def test_render_jinja_control_flow(self):
        """Test Jinja rendering with control flow."""
        template = "{% if condition %}Yes{% else %}No{% endif %}"
        inputs = {"condition": True}
        result = render_jinja(template, inputs)
        assert result == "Yes"

    def test_render_jinja_loops(self):
        """Test Jinja rendering with loops."""
        template = "{% for item in items %}{{ item }} {% endfor %}"
        inputs = {"items": ["apple", "banana", "cherry"]}
        result = render_jinja(template, inputs)
        # Note: render_jinja uses .strip() so trailing spaces are removed
        assert result == "apple banana cherry"

    def test_render_jinja_filters(self):
        """Test Jinja rendering with filters."""
        template = "Hello {{ name|upper }}"
        inputs = {"name": "world"}
        result = render_jinja(template, inputs)
        assert result == "Hello WORLD"

    def test_render_jinja_recursive_simple(self):
        """Test recursive rendering with a simple template."""
        template = "Hello {{ name }}"
        inputs = {"name": "World"}
        result = render_jinja_recursive(template, inputs)
        assert result == "Hello World"

    def test_render_jinja_recursive_nested(self):
        """Test recursive rendering with nested templates."""
        template = "Hello {{ greeting }}"
        inputs = {"greeting": "{{ name }}", "name": "World"}
        result = render_jinja_recursive(template, inputs)
        assert result == "Hello World"

    def test_render_jinja_recursive_multiple_levels(self):
        """Test recursive rendering with multiple levels of nesting."""
        template = "{{ level1 }}"
        inputs = {
            "level1": "{{ level2 }}",
            "level2": "{{ level3 }}",
            "level3": "Final",
        }
        result = render_jinja_recursive(template, inputs)
        assert result == "Final"

    def test_render_jinja_recursive_no_jinja(self):
        """Test recursive rendering with no Jinja syntax."""
        template = "Hello World"
        inputs = {}
        result = render_jinja_recursive(template, inputs)
        assert result == "Hello World"

    def test_render_jinja_recursive_with_control_flow(self):
        """Test recursive rendering with control flow."""
        template = "{% if condition %}{{ message }}{% endif %}"
        inputs = {
            "condition": True,
            "message": "Hello {{ name }}",
            "name": "World",
        }
        result = render_jinja_recursive(template, inputs)
        assert result == "Hello World"

    def test_render_jinja_missing_variable(self):
        """Test that missing variables render as empty."""
        template = "Hello {{ name }}"
        inputs = {}
        result = render_jinja(template, inputs)
        # Note: render_jinja uses .strip() so trailing spaces are removed
        assert result == "Hello"


class TestFormatDataFrame:
    """Test DataFrame formatting utilities."""

    def test_format_df_to_string_basic(self):
        """Test basic DataFrame formatting."""
        df = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        result = format_df_to_string(df)
        assert "A" in result
        assert "B" in result
        assert "1" in result
        assert "4" in result

    def test_format_df_to_string_with_index(self):
        """Test DataFrame formatting with index."""
        df = DataFrame({"A": [1, 2, 3]})
        result = format_df_to_string(df, index=True)
        assert "0" in result or "1" in result  # Index should be present

    def test_format_df_to_string_without_index(self):
        """Test DataFrame formatting without index."""
        df = DataFrame({"A": [1, 2, 3]})
        result = format_df_to_string(df, index=False)
        # Should still contain data
        assert "A" in result

    def test_format_df_to_string_shortened(self):
        """Test DataFrame formatting with shortening."""
        df = DataFrame({"A": list(range(100))})
        result = format_df_to_string(df, shorten=50)
        assert len(result) <= 50
        assert "..." in result

    def test_format_df_to_string_reduced(self):
        """Test DataFrame formatting in reduced mode."""
        df = DataFrame({"A": [1, 2, 3]})
        result = format_df_to_string(df, reduced=True)
        assert result == "<dataframe>"

    def test_format_df_to_string_from_dict(self):
        """Test DataFrame formatting from dict format."""
        # Create a parquet buffer
        df = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        buffer = BytesIO()
        table = pa.Table.from_pandas(df)
        pq.write_table(table, buffer)
        buffer.seek(0)

        df_dict = {"_type": "parquet_dataframe", "data": buffer.getvalue()}

        result = format_df_to_string(df_dict)
        assert "A" in result
        assert "B" in result

    def test_format_df_to_string_from_dict_invalid_type(self):
        """Test that invalid dict type raises ValueError."""
        df_dict = {"_type": "invalid_type", "data": b""}

        with pytest.raises(ValueError, match="Unknown dataframe type"):
            format_df_to_string(df_dict)


class TestPromptRenderer:
    """Test the PromptRenderer class."""

    @pytest.fixture
    def mock_agent(self, mock_session):
        """Create a mock agent for testing."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="System: {{ system_message }}",
        )
        agent = Agent(session=mock_session, config=config)
        return agent

    @pytest.fixture
    def mock_interaction(self):
        """Create a mock interaction."""
        interaction = Mock()
        interaction.id = 1
        return interaction

    def test_prompt_renderer_initialization(self, mock_agent):
        """Test that PromptRenderer can be initialized."""
        renderer = PromptRenderer(mock_agent)
        assert renderer.agent == mock_agent
        assert renderer.interaction_uuid is None

    def test_prompt_renderer_with_interaction_id(self, mock_agent):
        """Test PromptRenderer with interaction_id."""
        renderer = PromptRenderer(mock_agent, interaction_uuid=5)
        assert renderer.interaction_uuid == 5

    def test_render_prompt_simple(self, mock_agent):
        """Test simple prompt rendering."""
        renderer = PromptRenderer(mock_agent)
        template = "Hello {{ name }}"
        inputs = {"name": "World"}

        result = renderer.render_prompt(template, inputs)
        assert result == "Hello World"

    def test_render_prompt_with_template(self, mock_agent):
        """Test prompt rendering with registered template."""
        # Register a template in the agent's environment
        template = Template(name="greeting", template="Hello")
        mock_agent.environment.template_registry.register(template)

        renderer = PromptRenderer(mock_agent)
        template_str = "{{ greeting.template }} {{ name }}"
        inputs = {"name": "World"}

        result = renderer.render_prompt(template_str, inputs)
        assert result == "Hello World"

    def test_render_prompt_with_dataframe(self, mock_agent):
        """Test prompt rendering with DataFrame."""
        renderer = PromptRenderer(mock_agent)
        template = "Data: {{ df }}"
        df = DataFrame({"A": [1, 2, 3]})
        inputs = {"df": df}

        result = renderer.render_prompt(template, inputs)
        assert "A" in result
        assert "1" in result or "2" in result or "3" in result

    def test_render_prompt_with_format_df_function(self, mock_agent):
        """Test prompt rendering with format_df_to_string function."""
        renderer = PromptRenderer(mock_agent)
        # format_df_to_string is available in templates, but we need to pass DataFrame directly
        # The function is already called automatically for DataFrames in template_inputs
        template = "Data: {{ df }}"
        df = DataFrame({"A": [1, 2, 3]})
        inputs = {"df": df}

        result = renderer.render_prompt(template, inputs)
        assert "A" in result

    def test_render_prompt_with_reduced(self, mock_agent):
        """Test prompt rendering in reduced mode."""
        renderer = PromptRenderer(mock_agent)
        template = "Data: {{ df }}"
        df = DataFrame({"A": [1, 2, 3]})
        inputs = {"df": df}

        result = renderer.render_prompt(template, inputs, reduced=True)
        assert result == "Data: <dataframe>"

    def test_render_prompt_recursive(self, mock_agent):
        """Test recursive prompt rendering."""
        renderer = PromptRenderer(mock_agent)
        template = "{{ greeting }}"
        inputs = {"greeting": "{{ name }}", "name": "World"}

        result = renderer.render_prompt(template, inputs)
        assert result == "World"

    def test_render_prompt_with_none_values(self, mock_agent):
        """Test that None values are filtered out."""
        renderer = PromptRenderer(mock_agent)
        template = "Hello {{ name }}"
        inputs = {"name": "World", "none_value": None}

        # Should not raise an error
        result = renderer.render_prompt(template, inputs)
        assert result == "Hello World"

    def test_render_prompt_agent_attribute_access(self, mock_agent):
        """Test that agent attributes are accessible in templates."""
        renderer = PromptRenderer(mock_agent)
        template = "Agent: {{ agent.config.name }}"
        inputs = {}

        result = renderer.render_prompt(template, inputs)
        assert result == "Agent: test-agent"

    def test_render_task_prompt(self, mock_agent):
        """Test rendering task prompt."""
        # Create a task definition
        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Task: {{ task_name }}",
            tools=[],
        )
        task_definition = TaskDefinition(stack=mock_agent.stack, task=task)
        mock_agent.stack.interactions = [task_definition]

        renderer = PromptRenderer(mock_agent)
        inputs = {"task_name": "test_task"}

        result = renderer.render_task_prompt(inputs)
        assert result == "Task: test_task"

    def test_render_task_prompt_with_recursive(self, mock_agent):
        """Test rendering task prompt with recursive templates."""
        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Task: {{ task_name }}",
            tools=[],
        )
        task_definition = TaskDefinition(stack=mock_agent.stack, task=task)
        mock_agent.stack.interactions = [task_definition]

        renderer = PromptRenderer(mock_agent)
        inputs = {"task_name": "{{ name }}", "name": "test_task"}

        result = renderer.render_task_prompt(inputs)
        assert result == "Task: test_task"

    def test_render_system_prompt(self, mock_agent):
        """Test rendering system prompt."""
        renderer = PromptRenderer(mock_agent)
        inputs = {"system_message": "test system"}

        result = renderer.render_system_prompt(inputs)
        assert result == "System: test system"

    def test_render_system_prompt_with_task_definition(self, mock_agent):
        """Test rendering system prompt with task definition."""
        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Task prompt",
            tools=[],
            system_template="Task System: {{ msg }}",
        )
        task_definition = TaskDefinition(stack=mock_agent.stack, task=task)
        mock_agent.stack.interactions = [task_definition]

        renderer = PromptRenderer(mock_agent)
        inputs = {"msg": "test"}

        result = renderer.render_system_prompt(inputs)
        assert result == "Task System: test"

    def test_render_system_prompt_no_inputs(self, mock_agent):
        """Test rendering system prompt without inputs."""
        renderer = PromptRenderer(mock_agent)

        result = renderer.render_system_prompt()
        assert "System:" in result

    def test_prompt_renderer_interactions_attribute(
        self, mock_agent, mock_interaction
    ):
        """Test that interactions attribute works correctly."""
        mock_agent.stack.interactions = [mock_interaction]
        renderer = PromptRenderer(mock_agent)

        interactions = renderer.stack.interactions
        assert len(interactions) == 1
        assert interactions[0] == mock_interaction

    def test_prompt_renderer_interactions_with_cutoff(self, mock_agent):
        """Test interactions attribute with interaction_id cutoff."""
        interaction1 = Mock()
        interaction1.id = 1
        interaction2 = Mock()
        interaction2.id = 2
        interaction3 = Mock()
        interaction3.id = 3

        mock_agent.stack.interactions = [
            interaction1,
            interaction2,
            interaction3,
        ]
        renderer = PromptRenderer(mock_agent, interaction_uuid=2)

        interactions = renderer.stack.interactions
        assert len(interactions) == 3
        assert interactions[0] == interaction1
        assert interactions[1] == interaction2

    def test_prompt_renderer_interactions_exact_match(self, mock_agent):
        """Test interactions attribute with exact interaction_id match."""
        interaction1 = Mock()
        interaction1.id = 1
        interaction2 = Mock()
        interaction2.id = 2

        mock_agent.stack.interactions = [interaction1, interaction2]
        renderer = PromptRenderer(mock_agent, interaction_uuid=2)

        interactions = renderer.stack.interactions
        assert len(interactions) == 2
        assert interactions[1] == interaction2

    def test_render_template_inputs_dataframe(self, mock_agent):
        """Test _render_template_inputs with DataFrame."""
        df = DataFrame({"A": [1, 2, 3]})
        inputs = {"df": df}

        result = PromptRenderer.render_template_inputs(inputs)
        assert isinstance(result["df"], str)
        assert "A" in result["df"]

    def test_render_template_inputs_reduced(self, mock_agent):
        """Test _render_template_inputs in reduced mode."""
        df = DataFrame({"A": [1, 2, 3]})
        inputs = {"df": df}

        result = PromptRenderer.render_template_inputs(inputs, reduced=True)
        assert result["df"] == "<dataframe>"

    def test_render_template_inputs_non_dataframe(self, mock_agent):
        """Test _render_template_inputs with non-DataFrame values."""
        inputs = {"name": "test", "count": 42}

        result = PromptRenderer.render_template_inputs(inputs)
        assert result["name"] == "test"
        assert result["count"] == 42


class TestPrompt:
    """Test the Prompt dataclass."""

    def test_prompt_creation_text(self):
        """Test creating a text prompt."""
        prompt = Prompt(type="text", text="Hello world")
        assert prompt.type == "text"
        assert prompt.text == "Hello world"
        assert prompt.tool_use_id is None

    def test_prompt_creation_tool_result(self):
        """Test creating a tool result prompt."""
        prompt = Prompt(
            type="tool_result", tool_use_id="tool_123", text="Result"
        )
        assert prompt.type == "tool_result"
        assert prompt.tool_use_id == "tool_123"
        assert prompt.text == "Result"

    def test_prompt_creation_template(self):
        """Test creating a template prompt."""
        prompt = Prompt(type="template", text="{{ name }}")
        assert prompt.type == "template"
        assert prompt.text == "{{ name }}"

    def test_prompt_default_values(self):
        """Test prompt default values."""
        prompt = Prompt()
        assert prompt.type == "text"
        assert prompt.text is None


class TestPromptSerialization:
    """Test Prompt serialization and deserialization."""

    def test_prompt_to_dict(self):
        """Test serializing a prompt."""
        prompt = Prompt(type="text", text="Hello world")
        data = prompt.to_dict()

        assert data["type"] == "text"
        assert data["text"] == "Hello world"
        assert data.get("tool_use_id") is None

    def test_prompt_from_dict(self):
        """Test deserializing a prompt."""
        data = {"type": "text", "text": "Hello world", "tool_use_id": None}
        prompt = Prompt.from_dict(data)

        assert prompt.type == "text"
        assert prompt.text == "Hello world"
        assert prompt.tool_use_id is None

    def test_prompt_round_trip(self):
        """Test round-trip serialization/deserialization."""
        prompt = Prompt(
            type="tool_result", tool_use_id="call_123", text="Result"
        )

        data = prompt.to_dict()
        new_prompt = Prompt.from_dict(data)

        assert new_prompt.type == "tool_result"
        assert new_prompt.tool_use_id == "call_123"
        assert new_prompt.text == "Result"

    def test_prompt_from_dict_with_existing_object(self):
        """Test that from_dict returns existing Prompt object if passed."""
        prompt = Prompt(type="text", text="Test")
        data = prompt.to_dict()
        result = Prompt.from_dict(data)

        assert result.type == prompt.type
        assert result.text == prompt.text
        assert result.tool_use_id == prompt.tool_use_id

"""Tests for Environment functionality."""

import pytest
import yaml

from gimle.hugin.agent.environment import Environment
from gimle.hugin.tools.tool import Tool


class TestEnvironment:
    """Test Environment class functionality."""

    def test_environment_initialization(self):
        """Test that Environment initializes with empty registries."""
        env = Environment()

        assert len(env.config_registry.registered()) == 0
        assert len(env.task_registry.registered()) == 0
        assert len(env.template_registry.registered()) == 0
        assert env.env_vars == {}

    def test_environment_initialization_with_env_vars(self):
        """Test that Environment initializes with environment variables."""
        env_vars = {
            "db_host": "localhost",
            "db_user": "admin",
            "db_password": "secret",
        }
        env = Environment(env_vars=env_vars)

        assert env.env_vars == env_vars
        assert env.env_vars["db_host"] == "localhost"
        assert env.env_vars["db_user"] == "admin"
        assert env.env_vars["db_password"] == "secret"

    def test_environment_load_with_env_vars(self, tmp_path):
        """Test that Environment.load accepts and stores env_vars."""
        env_vars = {"test_key": "test_value", "another_key": 123}
        env = Environment.load(str(tmp_path), env_vars=env_vars)

        assert env.env_vars == env_vars
        assert env.env_vars["test_key"] == "test_value"
        assert env.env_vars["another_key"] == 123

    def test_environment_load_configs(self, tmp_path):
        """Test loading configs from YAML files."""
        # Create configs directory
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()

        # Create a config YAML file
        config_data = {
            "name": "test_config",
            "description": "Test configuration",
            "system_template": "You are a helpful assistant.",
            "llm_model": "test-model",
            "tools": ["tool1", "tool2"],
            "interactive": False,
            "options": {"key": "value"},
        }
        config_file = configs_dir / "test_config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify config was loaded
        assert len(env.config_registry.registered()) == 1
        assert "test_config" in env.config_registry.registered()
        config = env.config_registry.get("test_config")
        assert config.name == "test_config"
        assert config.description == "Test configuration"
        assert config.system_template == "You are a helpful assistant."
        assert config.llm_model == "test-model"
        assert config.tools == ["tool1", "tool2"]
        assert config.interactive is False
        assert config.options == {"key": "value"}

    def test_environment_load_multiple_configs(self, tmp_path):
        """Test loading multiple configs from YAML files."""
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()

        # Create multiple config files
        for i in range(3):
            config_data = {
                "name": f"config_{i}",
                "description": f"Config {i}",
                "system_template": f"Template {i}",
            }
            config_file = configs_dir / f"config_{i}.yaml"
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify all configs were loaded
        assert len(env.config_registry.registered()) == 3
        for i in range(3):
            assert f"config_{i}" in env.config_registry.registered()
            config = env.config_registry.get(f"config_{i}")
            assert config.name == f"config_{i}"

    def test_environment_load_tasks(self, tmp_path):
        """Test loading tasks from YAML files."""
        # Create tasks directory
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # Create a task YAML file
        task_data = {
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
            "system_template": "System template",
            "llm_model": "test-model",
        }
        task_file = tasks_dir / "test_task.yaml"
        with open(task_file, "w") as f:
            yaml.dump(task_data, f)

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify task was loaded
        assert len(env.task_registry.registered()) == 1
        assert "test_task" in env.task_registry.registered()
        task = env.task_registry.get("test_task")
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

    def test_environment_load_templates(self, tmp_path):
        """Test loading templates from YAML files."""
        # Create templates directory
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()

        # Create a template YAML file
        template_data = {
            "name": "test_template",
            "template": "Hello {{ name }}",
        }
        template_file = templates_dir / "test_template.yaml"
        with open(template_file, "w") as f:
            yaml.dump(template_data, f)

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify template was loaded
        assert len(env.template_registry.registered()) == 1
        assert "test_template" in env.template_registry.registered()
        template = env.template_registry.get("test_template")
        assert template.name == "test_template"
        assert template.template == "Hello {{ name }}"

    def test_environment_load_all_types(self, tmp_path):
        """Test loading configs, tasks, and templates together."""
        # Create all directories
        configs_dir = tmp_path / "configs"
        tasks_dir = tmp_path / "tasks"
        templates_dir = tmp_path / "templates"
        configs_dir.mkdir()
        tasks_dir.mkdir()
        templates_dir.mkdir()

        # Create one of each type
        config_data = {
            "name": "my_config",
            "description": "My config",
            "system_template": "Template",
        }
        with open(configs_dir / "my_config.yaml", "w") as f:
            yaml.dump(config_data, f)

        task_data = {
            "name": "my_task",
            "description": "My task",
            "parameters": {},
            "prompt": "Do it",
        }
        with open(tasks_dir / "my_task.yaml", "w") as f:
            yaml.dump(task_data, f)

        template_data = {"name": "my_template", "template": "Template text"}
        with open(templates_dir / "my_template.yaml", "w") as f:
            yaml.dump(template_data, f)

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify all were loaded
        assert len(env.config_registry.registered()) == 1
        assert len(env.task_registry.registered()) == 1
        assert len(env.template_registry.registered()) == 1
        assert "my_config" in env.config_registry.registered()
        assert "my_task" in env.task_registry.registered()
        assert "my_template" in env.template_registry.registered()

    def test_environment_load_missing_directories(self, tmp_path):
        """Test loading when directories don't exist."""
        # Load environment from empty path
        env = Environment.load(str(tmp_path))

        # Verify registries are empty
        assert len(env.config_registry.registered()) == 0
        assert len(env.task_registry.registered()) == 0
        assert len(env.template_registry.registered()) == 0

    def test_environment_load_empty_directories(self, tmp_path):
        """Test loading when directories exist but are empty."""
        # Create empty directories
        (tmp_path / "configs").mkdir()
        (tmp_path / "tasks").mkdir()
        (tmp_path / "templates").mkdir()

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify registries are empty
        assert len(env.config_registry.registered()) == 0
        assert len(env.task_registry.registered()) == 0
        assert len(env.template_registry.registered()) == 0

    def test_environment_load_processes_all_files(self, tmp_path):
        """Test that all files in directories are processed (not just .yaml)."""
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()

        # Create a YAML file
        config_data = {
            "name": "test_config",
            "description": "Test",
            "system_template": "Template",
        }
        with open(configs_dir / "test_config.yaml", "w") as f:
            yaml.dump(config_data, f)

        # Create a text file with valid YAML content (will be processed)
        config_data2 = {
            "name": "test_config2",
            "description": "Test 2",
            "system_template": "Template 2",
        }
        with open(configs_dir / "readme.txt", "w") as f:
            yaml.dump(config_data2, f)

        with open(configs_dir / "test_config2.yaml", "w") as f:
            yaml.dump(config_data2, f)

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify both files were processed and loaded
        assert len(env.config_registry.registered()) == 2
        assert "test_config" in env.config_registry.registered()
        assert "test_config2" in env.config_registry.registered()

    def test_environment_load_handles_invalid_yaml(self, tmp_path):
        """Test that invalid YAML files raise appropriate errors."""
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()

        # Create an invalid YAML file
        invalid_file = configs_dir / "invalid.yaml"
        with open(invalid_file, "w") as f:
            f.write("invalid: yaml: content: [unclosed")

        # Loading should raise a YAMLError when parsing
        with pytest.raises(yaml.YAMLError):
            Environment.load(str(tmp_path))

    def test_environment_load_handles_missing_required_fields(self, tmp_path):
        """Test that missing required fields raise appropriate errors."""
        configs_dir = tmp_path / "configs"
        configs_dir.mkdir()

        # Create a config with missing required fields
        incomplete_data = {
            "name": "incomplete_config"
            # Missing description and system_template
        }
        config_file = configs_dir / "incomplete.yaml"
        with open(config_file, "w") as f:
            yaml.dump(incomplete_data, f)

        # Loading should raise a TypeError when trying to create Config
        # because required fields are missing
        with pytest.raises(TypeError):
            Environment.load(str(tmp_path))

    def test_environment_load_tools(self, tmp_path):
        """Test loading tools from YAML files."""
        import sys
        import types

        # Create a test module with a function
        test_module = types.ModuleType("test_env_tool_module")

        def env_test_function(x: str) -> dict:
            return {"result": f"Env processed {x}"}

        test_module.env_test_function = env_test_function
        sys.modules["test_env_tool_module"] = test_module

        # Create tools directory
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        # Create a tool YAML file
        tool_data = {
            "name": "env_tool",
            "description": "Environment tool",
            "parameters": {
                "x": {"type": "string", "description": "Input parameter"}
            },
            "is_interactive": False,
            "options": {},
            "implementation_path": "test_env_tool_module.env_test_function",
        }
        tool_file = tools_dir / "env_tool.yaml"
        with open(tool_file, "w") as f:
            yaml.dump(tool_data, f)

        # Load environment
        env = Environment.load(str(tmp_path))

        # Verify tool was loaded and registered
        # Check that the expected core tools are present rather than exact count,
        # since builtin agents (like agent_builder) add their own tools
        registered_tools = env.tool_registry.registered()
        expected_core_tools = [
            "builtins.ask_user",
            "builtins.finish",
            "builtins.get_artifact_content",
            "builtins.launch_agent",
            "builtins.list_agents",
            "builtins.list_files",
            "builtins.query_artifacts",
            "builtins.read_file",
            "builtins.save_code",
            "builtins.save_file",
            "builtins.save_insight",
            "builtins.save_text",
            "builtins.search_files",
            "env_tool",
        ]
        for tool_name in expected_core_tools:
            assert tool_name in registered_tools, f"Missing tool: {tool_name}"
        assert "env_tool" in env.tool_registry.registered()
        tool = env.tool_registry.get("env_tool")
        assert tool.name == "env_tool"
        assert tool.description == "Environment tool"
        assert tool.func is not None  # Should be loaded
        assert callable(tool.func)

        # Verify tool is also in Tool._registry (for backward compatibility)
        from gimle.hugin.tools.tool import Tool

        assert "env_tool" in Tool.registry.registered()

        # Cleanup
        del sys.modules["test_env_tool_module"]

    def test_environment_load_tools_with_colon_format(self, tmp_path):
        """Test loading tools with colon format implementation_path."""
        import sys
        import types

        test_module = types.ModuleType("test_colon_env_module")

        def colon_function(value: int) -> dict:
            return {"squared": value**2}

        test_module.colon_function = colon_function
        sys.modules["test_colon_env_module"] = test_module

        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        tool_data = {
            "name": "colon_env_tool",
            "description": "Tool with colon format",
            "parameters": {
                "value": {"type": "number", "description": "Value to square"}
            },
            "is_interactive": False,
            "options": {},
            "implementation_path": "test_colon_env_module:colon_function",
        }
        tool_file = tools_dir / "colon_tool.yaml"
        with open(tool_file, "w") as f:
            yaml.dump(tool_data, f)

        Environment.load(str(tmp_path))

        tool = Tool.get_tool("colon_env_tool")
        assert tool.func is not None
        # Can't easily test execution here without Tool.execute_tool, but func is loaded

        del sys.modules["test_colon_env_module"]

    def test_environment_load_tools_invalid_path(self, tmp_path):
        """Test that invalid implementation_path raises error during loading."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        tool_data = {
            "name": "invalid_tool",
            "description": "Tool with invalid path",
            "parameters": {},
            "is_interactive": False,
            "options": {},
            "implementation_path": "nonexistent.module.function",
        }
        tool_file = tools_dir / "invalid_tool.yaml"
        with open(tool_file, "w") as f:
            yaml.dump(tool_data, f)

        # Loading should raise ImportError
        with pytest.raises(ImportError):
            Environment.load(str(tmp_path))

    def test_environment_load_tools_without_implementation_path(self, tmp_path):
        """Test loading tool without implementation_path (func will be None)."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        tool_data = {
            "name": "no_path_tool",
            "description": "Tool without path",
            "parameters": {},
            "is_interactive": False,
            "options": {},
        }
        tool_file = tools_dir / "no_path_tool.yaml"
        with open(tool_file, "w") as f:
            yaml.dump(tool_data, f)

        # Loading should succeed, but tool won't be executable
        Environment.load(str(tmp_path))

        tool = Tool.registry.get("no_path_tool")
        assert tool.name == "no_path_tool"
        assert tool.implementation_path is None
        assert tool.func is None  # No implementation loaded

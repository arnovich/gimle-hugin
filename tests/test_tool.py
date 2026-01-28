"""Tests for tool functionality."""

import pytest

from gimle.hugin.tools.tool import Tool, ToolConfig, ToolResponse


class TestToolRegistration:
    """Test tool registration functionality."""

    def test_register_function(self):
        """Test that a function can be registered as a tool."""
        # Clear registry before test
        Tool.registry.clear()

        @Tool.register(
            name="test_tool",
            description="A test tool",
            parameters={
                "param1": {
                    "type": "string",
                    "description": "First parameter",
                    "required": True,
                }
            },
        )
        def test_tool(param1: str) -> dict:
            return {"result": f"Processed {param1}"}

        # Verify tool is registered
        assert "test_tool" in Tool.registry.registered()
        tool_info = Tool.registry.get("test_tool")
        assert tool_info.name == "test_tool"
        assert tool_info.description == "A test tool"
        assert tool_info.func is not None

        # Cleanup
        Tool.registry.clear()

    def test_register_multiple_tools(self):
        """Test registering multiple tools."""
        Tool.registry.clear()

        @Tool.register(
            name="tool1",
            description="First tool",
            parameters={"x": {"type": "string", "description": "Parameter x"}},
        )
        def tool1(x: str) -> dict:
            return {"x": x}

        @Tool.register(
            name="tool2",
            description="Second tool",
            parameters={"y": {"type": "number", "description": "Parameter y"}},
        )
        def tool2(y: int) -> dict:
            return {"y": y}

        assert len(Tool.registry.registered()) == 2
        assert "tool1" in Tool.registry.registered()
        assert "tool2" in Tool.registry.registered()

        Tool.registry.clear()

    def test_register_with_options(self):
        """Test registering a tool with options."""
        Tool.registry.clear()

        @Tool.register(
            name="tool_with_options",
            description="A tool with options",
            options={"context_window": 3},
        )
        def tool_with_options() -> dict:
            return {"result": "test"}

        tool_info = Tool.registry.get("tool_with_options")
        assert tool_info.options.context_window == 3

        Tool.registry.clear()


class TestToolLoading:
    """Test tool loading/retrieval functionality."""

    def test_get_tool_success(self):
        """Test that a registered tool can be loaded."""
        Tool.registry.clear()

        @Tool.register(
            name="loadable_tool",
            description="A tool that can be loaded",
            parameters={
                "input": {"type": "string", "description": "Input value"}
            },
        )
        def loadable_tool(input: str) -> dict:
            return {"output": input}

        tool_info = Tool.get_tool("loadable_tool")
        assert tool_info.name == "loadable_tool"
        assert tool_info.description == "A tool that can be loaded"
        assert tool_info.func is not None

        Tool.registry.clear()

    def test_get_tool_not_found(self):
        """Test getting a tool that doesn't exist raises ValueError."""
        Tool.registry.clear()

        with pytest.raises(ValueError, match="Tool nonexistent_tool not found"):
            Tool.get_tool("nonexistent_tool")

        Tool.registry.clear()

    def test_get_tool_returns_all_metadata(self):
        """Test that get_tool returns all registered metadata."""
        Tool.registry.clear()

        parameters = {
            "param1": {"type": "string", "description": "First param"},
            "param2": {
                "type": "number",
                "description": "Second param",
                "required": True,
            },
        }
        options = {"include_only_in_context_window": True}

        @Tool.register(
            name="metadata_tool",
            description="Tool with all metadata",
            parameters=parameters,
            options=options,
        )
        def metadata_tool(param1: str, param2: int) -> dict:
            return {"combined": f"{param1}_{param2}"}

        tool_info = Tool.get_tool("metadata_tool")
        assert tool_info.name == "metadata_tool"
        assert tool_info.description == "Tool with all metadata"
        assert tool_info.parameters == parameters
        assert tool_info.options.include_only_in_context_window
        assert callable(tool_info.func)

        Tool.registry.clear()


class TestToolExecution:
    """Test tool execution functionality."""

    def test_execute_tool_success(self):
        """Test that a registered tool can be executed."""
        Tool.registry.clear()

        @Tool.register(
            name="executable_tool",
            description="A tool that can be executed",
            parameters={
                "value": {"type": "string", "description": "Value to process"}
            },
        )
        def executable_tool(value: str) -> ToolResponse:
            return ToolResponse(
                is_error=False, content={"processed": value.upper()}
            )

        tool = Tool.get_tool("executable_tool")
        result = Tool.execute_tool(tool, value="hello", stack=None, branch=None)
        assert result.content == {"processed": "HELLO"}

        Tool.registry.clear()

    def test_execute_tool_with_multiple_parameters(self):
        """Test executing a tool with multiple parameters."""
        Tool.registry.clear()

        @Tool.register(
            name="multi_param_tool",
            description="Tool with multiple parameters",
            parameters={
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
        )
        def multi_param_tool(a: int, b: int) -> ToolResponse:
            return ToolResponse(is_error=False, content={"sum": a + b})

        tool = Tool.get_tool("multi_param_tool")
        result = Tool.execute_tool(tool, a=5, b=3, stack=None, branch=None)
        assert result.content == {"sum": 8}

        Tool.registry.clear()

    def test_execute_tool_with_mock_option(self):
        """Test executing a tool with options enabled."""
        Tool.registry.clear()

        @Tool.register(
            name="mock_tool",
            description="A mock tool",
            parameters={
                "test_param": {
                    "type": "string",
                    "description": "Test parameter",
                }
            },
        )
        def mock_tool(test_param: str, agent: str) -> ToolResponse:
            # This function should not actually be called
            return ToolResponse(
                is_error=False, content={"test_param": test_param}
            )

        tool = Tool.get_tool("mock_tool")
        result = Tool.execute_tool(
            tool, test_param="test", agent="some_agent", stack=None, branch=None
        )
        # Should return the kwargs with tool_call, and agent should be removed
        assert result.content == {"test_param": "test"}
        assert "agent" not in result.content

        Tool.registry.clear()

    def test_execute_tool_without_agent_in_mock(self):
        """Test mock tool execution when agent is not in kwargs."""
        Tool.registry.clear()

        @Tool.register(
            name="mock_tool_no_agent",
            description="Mock tool without agent",
            parameters={},
        )
        def mock_tool_no_agent(some_param: str) -> ToolResponse:
            return ToolResponse(is_error=False, content={"some_param": "value"})

        tool = Tool.get_tool("mock_tool_no_agent")
        result = Tool.execute_tool(
            tool, some_param="value", stack=None, branch=None
        )
        assert result.content == {"some_param": "value"}

        Tool.registry.clear()

    def test_execute_tool_not_found(self):
        """Test executing a tool that doesn't exist raises ValueError."""
        Tool.registry.clear()

        with pytest.raises(ValueError, match="Tool nonexistent not found"):
            Tool.get_tool("nonexistent")

        Tool.registry.clear()

    def test_execute_tool_returns_non_dict(self):
        """Test executing a tool that returns a non-dict value."""
        Tool.registry.clear()

        @Tool.register(
            name="string_return_tool",
            description="Tool that returns a string",
            parameters={},
        )
        def string_return_tool() -> ToolResponse:
            return ToolResponse(
                is_error=False, content={"result": "just a string"}
            )

        tool = Tool.get_tool("string_return_tool")
        result = Tool.execute_tool(tool, stack=None, branch=None)
        # When result is not a dict, it should be returned as-is (without tool_call key)
        assert result.content == {"result": "just a string"}

        Tool.registry.clear()

    def test_execute_tool_integration(self):
        """Integration test: register, load, and execute a tool."""
        Tool.registry.clear()

        # Register
        @Tool.register(
            name="integration_tool",
            description="Integration test tool",
            parameters={
                "message": {"type": "string", "description": "Message to echo"}
            },
        )
        def integration_tool(message: str) -> ToolResponse:
            return ToolResponse(
                is_error=False,
                content={"echo": message, "length": len(message)},
            )

        # Load
        tool_info = Tool.get_tool("integration_tool")
        assert tool_info.name == "integration_tool"

        # Execute
        tool = Tool.get_tool("integration_tool")
        result = Tool.execute_tool(
            tool, message="Hello World", stack=None, branch=None
        )
        assert result.content["echo"] == "Hello World"
        assert result.content["length"] == 11

        Tool.registry.clear()


class TestToolInstanceRegistration:
    """Test tool instance registration with implementation paths."""

    def test_register_instance_with_implementation_path(self):
        """Test registering a tool instance with implementation_path loads the function."""
        Tool.registry.clear()

        # Create a simple test function in a module we can import
        import sys
        import types

        # Create a mock module
        test_module = types.ModuleType("test_tool_module")

        def test_function(x: str) -> ToolResponse:
            return ToolResponse(
                is_error=False, content={"result": f"Processed {x}"}
            )

        test_module.test_function = test_function
        sys.modules["test_tool_module"] = test_module

        # Create tool instance with implementation_path
        tool = Tool(
            name="instance_tool",
            description="Tool registered as instance",
            parameters={"x": {"type": "string", "description": "Input"}},
            is_interactive=False,
            options=ToolConfig(),
            func=None,
            implementation_path="test_tool_module.test_function",
        )

        # Register - should load the implementation
        registered_tool = Tool.register_instance(tool)

        # Verify tool is registered and func is loaded
        assert "instance_tool" in Tool.registry.registered()
        assert registered_tool.func is not None
        assert callable(registered_tool.func)

        # Verify we can execute it
        tool = Tool.get_tool("instance_tool")
        result = Tool.execute_tool(tool, x="test", stack=None, branch=None)
        assert result.content == {"result": "Processed test"}

        # Cleanup
        Tool.registry.clear()
        del sys.modules["test_tool_module"]

    def test_register_instance_with_explicit_function_name(self):
        """Test registering with implementation_path using colon format."""
        Tool.registry.clear()

        import sys
        import types

        test_module = types.ModuleType("test_tool_module2")

        def my_custom_function(value: int) -> ToolResponse:
            return ToolResponse(is_error=False, content={"doubled": value * 2})

        test_module.my_custom_function = my_custom_function
        sys.modules["test_tool_module2"] = test_module

        tool = Tool(
            name="colon_format_tool",
            description="Tool with colon format path",
            parameters={
                "value": {"type": "number", "description": "Value to double"}
            },
            is_interactive=False,
            options=ToolConfig(),
            func=None,
            implementation_path="test_tool_module2:my_custom_function",
        )

        registered_tool = Tool.register_instance(tool)

        assert registered_tool.func is not None
        tool = Tool.get_tool("colon_format_tool")
        result = Tool.execute_tool(tool, value=5, stack=None, branch=None)
        assert result.content == {"doubled": 10}

        Tool.registry.clear()
        del sys.modules["test_tool_module2"]

    def test_register_instance_with_existing_func(self):
        """Test registering instance that already has func doesn't reload."""
        Tool.registry.clear()

        def existing_func(existing: str) -> ToolResponse:
            return ToolResponse(is_error=False, content={"existing": existing})

        tool = Tool(
            name="preloaded_tool",
            description="Tool with preloaded func",
            parameters={"existing": {"type": "string", "description": "Input"}},
            is_interactive=False,
            options=ToolConfig(),
            func=existing_func,
            implementation_path="some.path.that.doesnt.exist",
        )

        # Should not raise error even though path doesn't exist
        # because func is already provided
        registered_tool = Tool.register_instance(tool)

        assert registered_tool.func == existing_func
        tool = Tool.get_tool("preloaded_tool")
        result = Tool.execute_tool(
            tool, existing="test", stack=None, branch=None
        )
        assert result.content == {"existing": "test"}

        Tool.registry.clear()

    def test_register_instance_without_implementation_path_or_func(self):
        """Test registering instance without func or path raises error on execution."""
        Tool.registry.clear()

        tool = Tool(
            name="no_func_tool",
            description="Tool without func",
            parameters={},
            is_interactive=False,
            options={},
            func=None,
            implementation_path=None,
        )

        # Registration should succeed
        Tool.register_instance(tool)

        # But execution should fail
        with pytest.raises(
            ValueError, match="No implementation found for tool"
        ):
            tool = Tool.get_tool("no_func_tool")
            Tool.execute_tool(tool, stack=None, branch=None)

        Tool.registry.clear()

    def test_register_instance_invalid_implementation_path(self):
        """Test registering with invalid implementation_path raises error."""
        Tool.registry.clear()

        tool = Tool(
            name="invalid_path_tool",
            description="Tool with invalid path",
            parameters={},
            is_interactive=False,
            options={},
            func=None,
            implementation_path="nonexistent.module.function",
        )

        with pytest.raises(ImportError):
            Tool.register_instance(tool)

        Tool.registry.clear()

    def test_register_instance_missing_function(self):
        """Test registering with path to module that doesn't have the function."""
        Tool.registry.clear()

        import sys
        import types

        # Create module without the function
        test_module = types.ModuleType("test_empty_module")
        sys.modules["test_empty_module"] = test_module

        tool = Tool(
            name="missing_func_tool",
            description="Tool with missing function",
            parameters={},
            is_interactive=False,
            options={},
            func=None,
            implementation_path="test_empty_module.nonexistent_function",
        )

        with pytest.raises(
            AttributeError, match="Function 'nonexistent_function' not found"
        ):
            Tool.register_instance(tool)

        Tool.registry.clear()
        del sys.modules["test_empty_module"]

    def test_register_instance_invalid_path_format(self):
        """Test registering with invalid path format raises error."""
        Tool.registry.clear()

        tool = Tool(
            name="invalid_format_tool",
            description="Tool with invalid format",
            parameters={},
            is_interactive=False,
            options={},
            func=None,
            implementation_path="justonepart",  # Too short
        )

        with pytest.raises(ValueError, match="Invalid implementation path"):
            Tool.register_instance(tool)

        Tool.registry.clear()


class TestToolFromDict:
    """Test Tool.from_dict() deserialization."""

    def test_from_dict_basic(self):
        """Test deserializing a tool from dictionary."""
        tool_data = {
            "name": "dict_tool",
            "description": "Tool from dict",
            "parameters": {
                "param1": {"type": "string", "description": "First param"}
            },
            "is_interactive": False,
            "options": {"include_reason": True},
            "implementation_path": "some.module.function",
        }

        tool = Tool.from_dict(tool_data)

        assert tool.name == "dict_tool"
        assert tool.description == "Tool from dict"
        assert tool.parameters == tool_data["parameters"]
        assert tool.is_interactive is False
        assert tool.options.include_reason is True
        assert tool.implementation_path == "some.module.function"
        assert tool.func is None  # Should be None until registered

    def test_from_dict_without_implementation_path(self):
        """Test deserializing tool without implementation_path."""
        tool_data = {
            "name": "no_path_tool",
            "description": "Tool without path",
            "parameters": {},
            "is_interactive": True,
            "options": {},
        }

        tool = Tool.from_dict(tool_data)

        assert tool.name == "no_path_tool"
        assert tool.implementation_path is None
        assert tool.func is None

    def test_from_dict_with_optional_fields(self):
        """Test deserializing with optional fields missing."""
        tool_data = {
            "name": "minimal_tool",
            "description": "Minimal tool",
            "parameters": {},
        }

        tool = Tool.from_dict(tool_data)

        assert tool.name == "minimal_tool"
        assert tool.is_interactive is False  # Default
        assert tool.options.include_reason is False
        assert tool.options.include_only_in_context_window is False
        assert tool.options.context_window == 5
        assert tool.options.reduced_context_window_enabled is True
        assert tool.options.reduced_context_window == 5
        assert tool.options.reduced_context_window_ignore_list == []
        assert tool.implementation_path is None
        assert tool.func is None


class TestToolLoadImplementation:
    """Test _load_implementation() method."""

    def test_load_implementation_dot_format(self):
        """Test loading implementation using dot format."""
        import sys
        import types

        test_module = types.ModuleType("test_load_module")

        def target_function(x: int) -> int:
            return x * 2

        test_module.target_function = target_function
        sys.modules["test_load_module"] = test_module

        func = Tool._load_implementation("test_load_module.target_function")

        assert callable(func)
        assert func(5) == 10

        del sys.modules["test_load_module"]

    def test_load_implementation_colon_format(self):
        """Test loading implementation using colon format."""
        import sys
        import types

        test_module = types.ModuleType("test_colon_module")

        def different_name(y: str) -> str:
            return y.upper()

        test_module.different_name = different_name
        sys.modules["test_colon_module"] = test_module

        func = Tool._load_implementation("test_colon_module:different_name")

        assert callable(func)
        assert func("hello") == "HELLO"

        del sys.modules["test_colon_module"]

    def test_load_implementation_standard_library(self):
        """Test loading from standard library."""
        # Test with a standard library function
        func = Tool._load_implementation("os.path:join")

        assert callable(func)
        assert func("a", "b") == "a/b"

    def test_load_implementation_invalid_module(self):
        """Test loading from non-existent module raises ImportError."""
        with pytest.raises(ImportError):
            Tool._load_implementation("nonexistent.module.function")

    def test_load_implementation_invalid_format(self):
        """Test invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid implementation path"):
            Tool._load_implementation("tooshort")

    def test_load_implementation_non_callable(self):
        """Test loading non-callable raises TypeError."""
        import sys
        import types

        test_module = types.ModuleType("test_noncallable_module")
        test_module.not_a_function = "just a string"
        sys.modules["test_noncallable_module"] = test_module

        with pytest.raises(TypeError, match="is not callable"):
            Tool._load_implementation("test_noncallable_module.not_a_function")

        del sys.modules["test_noncallable_module"]

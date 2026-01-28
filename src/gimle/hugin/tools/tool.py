"""Gimle Tool."""

import copy
import importlib
import inspect
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    TypedDict,
    TypeVar,
    Union,
    cast,
)

if TYPE_CHECKING:
    from gimle.hugin.interaction.interaction import Interaction
    from gimle.hugin.interaction.stack import Stack

from typing_extensions import NotRequired

from gimle.hugin.utils.registry import Registry

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Tool")


class ParameterSchema(TypedDict):
    """Schema for a single parameter in a tool."""

    type: str
    description: str
    required: NotRequired[bool]
    default: NotRequired[Any]


@dataclass
class ToolConfig:
    """Config for a tool."""

    include_only_in_context_window: bool = False
    context_window: int = 5
    reduced_context_window_enabled: bool = True
    reduced_context_window: int = 5
    reduced_context_window_ignore_list: List[str] = field(default_factory=list)
    include_reason: bool = False
    respond_with_text: bool = False


@dataclass
class ToolResponse:
    """Result of a tool call.

    Attributes:
        is_error: Whether the tool call resulted in an error.
        content: The result data from the tool.
        reason: Optional reason for the tool call (if include_reason enabled).
        response_interaction: Override the default interaction to create next.
        next_tool: Name of tool to call next (deterministic chaining).
        next_tool_args: Arguments for the next tool call.
        include_in_context: Whether this result appears in LLM context.
    """

    is_error: bool
    content: Dict[str, Any]
    reason: Optional[str] = None
    response_interaction: Optional[Union[str, "Interaction"]] = None
    # Deterministic tool chaining
    next_tool: Optional[str] = None
    next_tool_args: Optional[Dict[str, Any]] = None
    include_in_context: bool = True


@dataclass
class Tool:
    """A tool is a function that can be called by an agent.

    Attributes:
        registry: The registry of tools.
        name: The name of the tool.
        description: The description of the tool.
        parameters: The parameters of the tool.
        is_interactive: Whether the tool is interactive.
        options: The options of the tool.
    """

    registry: ClassVar[Registry["Tool"]] = (
        Registry()
    )  # Class variable, not a field

    name: str
    description: str
    parameters: Dict[str, ParameterSchema]
    is_interactive: bool
    options: ToolConfig
    func: Optional[Callable] = None
    implementation_path: Optional[str] = (
        None  # e.g., "mypackage.mymodule.myfunction" or "mypackage.mymodule:function_name"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the tool to a dictionary.

        Returns:
            A dictionary representation of the tool.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "options": self.options,
        }

    @staticmethod
    def _load_implementation(implementation_path: str) -> Any:
        """Load a function from an implementation path.

        Args:
            implementation_path: Path to the function, either:
                - "module.path.to.function" (function is the last component)
                - "module.path:function_name" (explicit function name)

        Returns:
            The callable function

        Raises:
            ImportError: If the module or function cannot be imported
            AttributeError: If the function is not found in the module
        """
        if ":" in implementation_path:
            # Format: "module.path:function_name"
            module_path, function_name = implementation_path.rsplit(":", 1)
        else:
            # Format: "module.path.to.function" - function is the last component
            parts = implementation_path.split(".")
            if len(parts) < 2:
                raise ValueError(
                    f"Invalid implementation path: {implementation_path}"
                )
            module_path = ".".join(parts[:-1])
            function_name = parts[-1]

        # Import the module
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            raise ImportError(
                "Module '{module_path}' not found. "
                "cwd='{cwd}', sys.path={sys_path}".format(
                    module_path=module_path,
                    cwd=os.getcwd(),
                    sys_path=sys.path,
                )
            )

        # Get the function from the module
        if not hasattr(module, function_name):
            raise AttributeError(
                f"Function '{function_name}' not found in module '{module_path}'"
            )

        func = getattr(module, function_name)
        if not callable(func):
            raise TypeError(
                f"'{function_name}' in module '{module_path}' is not callable"
            )

        return func

    @classmethod
    def register_instance(cls, tool: "Tool") -> "Tool":
        """Register a Tool instance, loading its implementation if needed.

        If the tool has an implementation_path but no func, the implementation
        will be loaded from the path. The func field will be set before registration.

        Args:
            tool: Tool instance to register

        Returns:
            The registered tool instance

        Raises:
            ImportError: If the implementation cannot be loaded
            ValueError: If the tool already has a func and implementation_path
        """
        # If tool has implementation_path but no func, load the implementation
        if tool.implementation_path and not tool.func:
            tool.func = cls._load_implementation(tool.implementation_path)
        elif tool.implementation_path and tool.func:
            # Both provided - this might be intentional (pre-loaded), so we allow it
            pass

        # Register the tool
        cls.registry.register(tool)
        return tool

    @staticmethod
    def _include_reason(
        params: Dict[str, Any], config: ToolConfig
    ) -> Dict[str, Any]:
        """Include the reason in the result if the tool config includes it."""
        if config.include_reason:
            params["reason"] = ParameterSchema(
                type="string",
                description="Give reason for the tool call.",
                required=True,
            )
        return params

    @classmethod
    def register(
        cls,
        name: str,
        description: str,
        parameters: Optional[Dict[str, ParameterSchema]] = None,
        is_interactive: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> Callable[[Callable], Callable]:
        """Register a function as a tool with metadata (decorator style).

        This is used for internal tools or for programmatic registration.

        Args:
            name: The name of the tool.
            description: The description of the tool.
            parameters: The parameters of the tool.
            is_interactive: Whether the tool is interactive.
            options: The options of the tool.

        Returns:
            A decorator function that registers the tool.
        """

        def decorator(func: Callable) -> Callable:
            config = ToolConfig(**(options or {}))
            params = Tool._include_reason(parameters or {}, config)
            cls.registry.register(
                Tool(
                    name=name,
                    description=description,
                    parameters=params,
                    is_interactive=is_interactive,
                    options=config,
                    func=func,
                )
            )
            return func

        return decorator

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tool":
        """Deserialize a tool from a dictionary.

        The dictionary should contain tool metadata. If implementation_path is provided,
        the func will be None and should be loaded during registration.

        Args:
            data: The data to deserialize the tool from.

        Returns:
            The deserialized tool.
        """
        # Extract func if present (shouldn't be in YAML, but handle it)
        func = data.pop("func", None)
        config = ToolConfig(**data.get("options", {}))
        params = Tool._include_reason(data.get("parameters", {}), config)
        return cls.registry.register(
            Tool(
                name=data["name"],
                description=data["description"],
                parameters=params,
                is_interactive=data.get("is_interactive", False),
                options=config,
                func=func,
                implementation_path=data.get("implementation_path"),
            )
        )

    @classmethod
    def get_tool(cls, name: str, throw_error: bool = True) -> Optional["Tool"]:
        """Get a tool metadata by name.

        Args:
            name: The name of the tool.
            throw_error: Whether to throw an error if the tool is not found.

        Returns:
            The tool metadata.
        """
        if ":" in name:
            registered_name = name.split(":")[0]
        else:
            registered_name = name
        if registered_name not in cls.registry.registered():
            if throw_error:
                raise ValueError(
                    f"Tool {registered_name} not found. Options are: {list(cls.registry.registered().keys())}"
                )
            return None
        tool = cls.registry.get(registered_name)
        if ":" in name:
            tool = copy.deepcopy(tool)
            tool.name = name.split(":")[1]
        return tool

    @classmethod
    def execute_tool(
        cls,
        tool: "Tool",
        stack: Optional["Stack"],
        branch: Optional[str],
        **kwargs: Any,
    ) -> Union[ToolResponse, "Interaction"]:
        """Execute a tool.

        Args:
            tool: The tool to execute.
            stack: The stack to use for the tool.
            branch: The branch to use for the tool.
            **kwargs: Additional arguments to pass to the tool.

        Returns:
            The result of the tool execution as a ToolResponse or Interaction.
        """
        func = tool.func
        if not func:
            raise ValueError(f"No implementation found for tool: {tool.name}")

        extra_result = {}
        if tool.options.include_reason and "reason" in kwargs:
            extra_result["reason"] = kwargs.pop("reason")

        try:
            sig = inspect.signature(func)
            params = sig.parameters
            accepts_varkw = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
            # ToolCall provides stack/branch out-of-band (as explicit args to
            # execute_tool). Pass them through if the tool declares them OR if it
            # accepts arbitrary kwargs (**kwargs).
            if "stack" in params or accepts_varkw:
                kwargs["stack"] = stack
            if "branch" in params or accepts_varkw:
                kwargs["branch"] = branch
        except (TypeError, ValueError):
            # In case the tool function doesn't have an inspectable signature
            pass

        for param_name, param in tool.parameters.items():
            if param_name == "reason":
                continue
            if param_name not in kwargs:
                if param.get("required", False):
                    logger.error(
                        f"Parameter {param_name} is required by tool {tool.name} but not provided"
                    )
                    return ToolResponse(
                        is_error=True,
                        content={
                            "error": f"Parameter {param_name} is required by tool {tool.name} but not provided"
                        },
                    )
                else:
                    if "default" in param:
                        kwargs[param_name] = param["default"]
                    else:
                        kwargs[param_name] = None

        result = func(**kwargs)
        if isinstance(result, dict):
            result = ToolResponse(
                is_error=result.get("is_error", False),
                content=result.get("content", {}),
                response_interaction=result.get("response_interaction", None),
                next_tool=result.get("next_tool", None),
                next_tool_args=result.get("next_tool_args", None),
                include_in_context=result.get("include_in_context", True),
            )
        if tool.options.include_reason:
            if not isinstance(result, ToolResponse):
                raise ValueError(
                    f"Reason can only be included in ToolResponse for now, not {type(result)}"
                )
            result.reason = extra_result.get("reason")
        # Result is ToolResponse, Interaction, or was converted from dict above
        # The func() returns Any, but we trust implementations return valid types
        return cast(Union[ToolResponse, "Interaction"], result)

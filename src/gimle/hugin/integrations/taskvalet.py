"""Scope Taskvalet participant tools to one concrete Hugin agent."""

import copy
import logging
import re
from contextlib import contextmanager
from threading import RLock
from typing import Any, Callable, Dict, Iterator, List, Optional, Protocol
from uuid import uuid4
from weakref import WeakKeyDictionary

from gimle.hugin.agent.agent import Agent
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import Tool, ToolConfig, ToolResponse

_LOG = logging.getLogger(__name__)
_LOCK = RLock()
_BOUND: WeakKeyDictionary[Agent, object] = WeakKeyDictionary()


class TaskvaletProvider(Protocol):
    """The public ParticipantTools contract, without a Taskvalet dependency."""

    def definitions(self) -> List[Dict[str, Any]]:
        """Return tool names, descriptions and complete JSON input schemas."""
        ...

    def invoke_result(
        self, name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return sanitized errors or results in an is_error/content envelope."""
        ...


@contextmanager
def bind_taskvalet_tools(
    agent: Agent, provider: TaskvaletProvider
) -> Iterator[List[str]]:
    """Yield explicit config/task aliases for this agent's live participant.

    Keep the provider connection open throughout this scope. Task-specific tool
    lists replace config tools, so the caller chooses where to attach the aliases.
    Children and restored sessions require their own explicit binding. Teardown
    revokes local references, not server claims or already accepted compute jobs.
    """
    definitions = copy.deepcopy(provider.definitions())
    if not definitions or not callable(
        getattr(provider, "invoke_result", None)
    ):
        raise ValueError("Use a Taskvalet provider with invoke_result support")
    names: List[str] = []
    for definition in definitions:
        name = definition.get("name")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"taskvalet_[A-Za-z0-9_]{1,54}", name)
            or name in names
        ):
            raise ValueError(
                "Taskvalet tool names must be distinct bounded identifiers"
            )
        names.append(name)

    token = object()
    active = True
    registered: List[Tool] = []

    def implementation(name: str) -> Callable[..., ToolResponse]:
        def invoke(
            *,
            stack: Optional[Stack] = None,
            branch: Optional[str] = None,
            **arguments: Any,
        ) -> ToolResponse:
            if not active or stack is None or stack.agent is not agent:
                return ToolResponse(
                    True,
                    {
                        "error": "participant_binding",
                        "message": "This tool belongs to another agent or its binding is closed.",
                    },
                )
            try:
                response = provider.invoke_result(name, arguments)
                if type(response.get("is_error")) is not bool or not isinstance(
                    response.get("content"), dict
                ):
                    raise ValueError("Invalid provider result")
                return ToolResponse(response["is_error"], response["content"])
            except Exception as error:
                # Plugin errors must neither crash the scheduler nor echo secrets.
                _LOG.error(
                    "Taskvalet provider failed (%s)", type(error).__name__
                )
                return ToolResponse(
                    True,
                    {
                        "error": "provider_failure",
                        "message": "Taskvalet invocation failed. Preserve the journal and ask the operator to inspect the provider.",
                    },
                )

        return invoke

    with _LOCK:
        if agent in _BOUND:
            raise ValueError("This Hugin agent is already bound to Taskvalet")
        _BOUND[agent] = token
    try:
        prefix = "taskvalet_binding_" + uuid4().hex
        aliases = []
        for definition in definitions:
            name = definition["name"]
            tool = Tool(
                name=prefix + "_" + name,
                description=definition["description"],
                parameters={},
                is_interactive=False,
                options=ToolConfig(
                    include_only_in_context_window=True,
                    context_window=2,
                    context_group="taskvalet",
                ),
                input_schema=definition["input_schema"],
                func=implementation(name),
            )
            Tool.register_instance(tool, replace=False)
            registered.append(tool)
            aliases.append(tool.name + ":" + name)
        yield aliases
    finally:
        # This also rolls back partial registration when a definition is invalid.
        active = False
        with _LOCK:
            for tool in registered:
                Tool.registry.unregister(tool.name, tool)
            if _BOUND.get(agent) is token:
                del _BOUND[agent]

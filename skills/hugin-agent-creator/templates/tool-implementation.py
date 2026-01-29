"""Hugin Tool Implementation Template.

Copy and customize for your tool.
Pair with tool-definition.yaml.
"""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="my_tool",
    description="What this tool does",
    parameters={
        "data": {
            "type": "string",
            "description": "Data to process",
            "required": True,
        },
        # Add more parameters as needed:
        # "count": {
        #     "type": "integer",
        #     "description": "Number of items",
        #     "required": False,
        # },
    },
    is_interactive=False,  # True if tool uses AskHuman
)
def my_tool(stack: "Stack", data: str) -> ToolResponse:
    """Process data and return result.

    Args:
        stack: The stack (auto-injected by framework)
        data: Data to process

    Returns:
        ToolResponse with the result
    """
    # TODO: Implement your tool logic here
    result = f"Processed: {data}"

    # Access shared state if needed:
    # env_vars = stack.agent.environment.env_vars
    # shared_data = env_vars.get("key")

    # Return success
    return ToolResponse(
        is_error=False,
        content={
            "result": result,
            "message": "Processing complete",
        },
    )

    # Return error if something goes wrong:
    # return ToolResponse(
    #     is_error=True,
    #     content={"error": "Description of what went wrong"},
    # )


# For tools that spawn sub-agents, return AgentCall instead:
#
# from gimle.hugin.interaction.agent_call import AgentCall
# from gimle.hugin.agent.task import Task, TaskParameter
#
# def delegate_tool(stack: "Stack", task_desc: str) -> AgentCall:
#     config = stack.agent.environment.config_registry.get("child_config")
#     task = Task(
#         name="delegated_task",
#         description=task_desc,
#         parameters={},
#         prompt=task_desc,
#         tools=config.tools,
#         system_template=config.system_template,
#         llm_model=config.llm_model,
#     )
#     return AgentCall(stack=stack, config=config, task=task)


# For tools that request human input:
#
# from gimle.hugin.interaction.ask_human import AskHuman
#
# def request_input_tool(stack: "Stack", question: str) -> ToolResponse:
#     ask_human = AskHuman(
#         stack=stack,
#         question=question,
#         response_template_name="response_template",
#     )
#     return ToolResponse(
#         is_error=False,
#         content={"message": "Waiting for input..."},
#         response_interaction=ask_human,
#     )

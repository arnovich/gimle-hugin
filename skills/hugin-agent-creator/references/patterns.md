# Common Agent Patterns

This reference covers six common patterns for building Hugin agents.

## 1. Minimal Agent

The simplest pattern: config + task + template, using only built-in tools.

**Use when:** Simple tasks that don't need custom functionality.

### Structure

```
minimal_agent/
├── configs/minimal.yaml
├── tasks/simple_task.yaml
└── templates/minimal_system.yaml
```

### Files

**configs/minimal.yaml:**
```yaml
name: minimal
description: Simple agent for basic tasks
system_template: minimal_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
interactive: false
options: {}
```

**tasks/simple_task.yaml:**
```yaml
name: simple_task
description: Answer a question
parameters:
  question:
    type: string
    description: Question to answer
    required: false
    default: "What is 2+2?"
prompt: |
  Please answer: {{ question.value }}

  Use finish with your answer.
```

**templates/minimal_system.yaml:**
```yaml
name: minimal_system
template: |
  You are a helpful assistant.
  When done, use the finish tool.
```

### Run

```bash
uv run hugin run --task simple_task --task-path ./minimal_agent
```

---

## 2. Tool Agent

Agent with custom tools for specific capabilities.

**Use when:** Need functionality beyond built-in tools.

### Structure

```
tool_agent/
├── configs/processor.yaml
├── tasks/process.yaml
├── templates/processor_system.yaml
└── tools/
    ├── custom_tool.yaml
    └── custom_tool.py
```

### Key Files

**configs/processor.yaml:**
```yaml
name: processor
description: Agent with custom processing tool
system_template: processor_system
llm_model: haiku-latest
tools:
  - custom_tool:process
  - builtins.finish:finish
interactive: false
options: {}
```

**tools/custom_tool.yaml:**
```yaml
name: custom_tool
description: Custom data processing
parameters:
  data:
    type: string
    description: Data to process
implementation_path: custom_tool:custom_tool
```

**tools/custom_tool.py:**
```python
from typing import TYPE_CHECKING
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="custom_tool",
    description="Custom data processing",
    parameters={
        "data": {"type": "string", "description": "Data to process", "required": True},
    },
    is_interactive=False,
)
def custom_tool(stack: "Stack", data: str) -> ToolResponse:
    result = data.upper()  # Your logic here
    return ToolResponse(is_error=False, content={"result": result})
```

---

## 3. Pipeline Agent

Multi-stage processing with result passing.

**Use when:** Task requires sequential processing stages.

### Structure

```
pipeline_agent/
├── configs/pipeline.yaml
├── tasks/
│   ├── stage_1.yaml
│   ├── stage_2.yaml
│   └── stage_3.yaml
└── templates/pipeline_system.yaml
```

### Key Pattern

**tasks/stage_1.yaml:**
```yaml
name: stage_1
description: First stage
parameters:
  input:
    type: string
    required: false
    default: "raw data"
task_sequence:
  - stage_2
  - stage_3
pass_result_as: stage_1_result
prompt: |
  Process: {{ input.value }}
  Use finish with your result.
```

**tasks/stage_2.yaml:**
```yaml
name: stage_2
description: Second stage
parameters:
  stage_1_result:
    type: string
    required: false
    default: ""
pass_result_as: stage_2_result
prompt: |
  Transform: {{ stage_1_result.value }}
  Use finish with your result.
```

**tasks/stage_3.yaml:**
```yaml
name: stage_3
description: Final stage
parameters:
  stage_2_result:
    type: string
    required: false
    default: ""
prompt: |
  Finalize: {{ stage_2_result.value }}
  Use finish with final output.
```

### Run

```bash
uv run hugin run --task stage_1 --task-path ./pipeline_agent
# Automatically runs stage_2 and stage_3
```

---

## 4. Human-in-the-Loop Agent

Agent that requests human input during execution.

**Use when:** Decisions require human approval or input.

### Structure

```
approval_agent/
├── configs/approval.yaml
├── tasks/decide.yaml
├── templates/
│   ├── approval_system.yaml
│   └── approval_response.yaml
└── tools/
    ├── request_approval.yaml
    └── request_approval.py
```

### Key Pattern

**configs/approval.yaml:**
```yaml
name: approval
description: Agent requiring human approval
system_template: approval_system
llm_model: haiku-latest
tools:
  - request_approval:request
  - builtins.finish:finish
interactive: true  # Required for AskHuman
options: {}
```

**tools/request_approval.py:**
```python
from gimle.hugin.interaction.ask_human import AskHuman
from gimle.hugin.tools.tool import ToolResponse


def request_approval(stack, action: str, reason: str) -> ToolResponse:
    ask_human = AskHuman(
        stack=stack,
        question=f"Approve {action}? Reason: {reason}",
        response_template_name="approval_response",
    )
    return ToolResponse(
        is_error=False,
        content={"message": "Waiting..."},
        response_interaction=ask_human,
    )
```

**templates/approval_response.yaml:**
```yaml
name: approval_response
template: |
  Human response: {{ response }}

  Proceed based on this feedback.
```

---

## 5. Agent Delegation

Parent agent that spawns specialized sub-agents.

**Use when:** Complex tasks need specialized expertise.

### Structure

```
delegation_agent/
├── configs/
│   ├── orchestrator.yaml
│   └── specialist.yaml
├── tasks/
│   ├── main_task.yaml
│   └── specialist_task.yaml
└── templates/
    ├── orchestrator_system.yaml
    └── specialist_system.yaml
```

### Key Pattern

**configs/orchestrator.yaml:**
```yaml
name: orchestrator
description: Delegates to specialists
system_template: orchestrator_system
llm_model: sonnet-latest
tools:
  - builtins.launch_agent:launch
  - builtins.list_agent_configs:list_configs
  - builtins.finish:finish
interactive: false
options: {}
```

**templates/orchestrator_system.yaml:**
```yaml
name: orchestrator_system
template: |
  You coordinate specialized sub-agents.

  Use list_configs to see available specialists.
  Use launch to delegate tasks.
  Synthesize results and finish when done.
```

### Alternative: Custom Delegation Tool

Return `AgentCall` from a custom tool:

```python
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.agent.task import Task


def delegate(stack, description: str) -> AgentCall:
    config = stack.agent.environment.config_registry.get("specialist")
    task = Task(
        name="delegated",
        description=description,
        parameters={},
        prompt=description,
        tools=config.tools,
        system_template=config.system_template,
        llm_model=config.llm_model,
    )
    return AgentCall(stack=stack, config=config, task=task)
```

---

## 6. Multi-Agent with Shared State

Multiple agents sharing data via environment variables.

**Use when:** Agents need to coordinate or share state.

### Structure

```
multi_agent/
├── configs/
│   ├── producer.yaml
│   └── consumer.yaml
├── tasks/
│   ├── produce.yaml
│   └── consume.yaml
├── templates/
│   └── shared_system.yaml
└── tools/
    ├── write_shared.yaml
    ├── write_shared.py
    ├── read_shared.yaml
    └── read_shared.py
```

### Key Pattern

**Programmatic setup with shared state:**
```python
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.storage.local import LocalStorage

# Shared state container
shared_state = {"data": [], "counter": 0}

# Load environment with shared state
storage = LocalStorage(base_path="./storage")
env = Environment.load(
    "multi_agent",
    storage=storage,
    env_vars={"shared": shared_state},
)
session = Session(environment=env)

# Create multiple agents
producer_config = env.config_registry.get("producer")
producer_task = env.task_registry.get("produce")
session.create_agent_from_task(producer_config, producer_task)

consumer_config = env.config_registry.get("consumer")
consumer_task = env.task_registry.get("consume")
session.create_agent_from_task(consumer_config, consumer_task)

# Run session
session.run()
```

**Tool accessing shared state:**
```python
def write_shared(stack, key: str, value: str) -> ToolResponse:
    shared = stack.agent.environment.env_vars.get("shared", {})
    shared[key] = value
    return ToolResponse(is_error=False, content={"written": key})


def read_shared(stack, key: str) -> ToolResponse:
    shared = stack.agent.environment.env_vars.get("shared", {})
    value = shared.get(key, None)
    return ToolResponse(is_error=False, content={"value": value})
```

### CLI Run

```bash
# Run multiple agents with shared namespace
uv run hugin run -p multi_agent -n shared_state \
  -a produce:producer -a consume:consumer
```

---

## Pattern Selection Guide

| Need | Pattern |
|------|---------|
| Simple Q&A or text processing | Minimal |
| Custom functionality | Tool |
| Sequential processing stages | Pipeline |
| Human decisions during execution | Human-in-the-Loop |
| Specialized sub-tasks | Delegation |
| Coordinated multiple agents | Multi-Agent |

## Combining Patterns

Patterns can be combined:

- **Pipeline + Tool**: Each stage uses custom tools
- **Delegation + Human**: Orchestrator requests approval before delegating
- **Multi-Agent + Pipeline**: Agents hand off pipeline stages

Choose the simplest pattern that meets your needs, then add complexity only as required.

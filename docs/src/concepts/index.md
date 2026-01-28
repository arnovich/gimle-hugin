---
layout: base.njk
title: Core Concepts
---

# Core Concepts

Hugin is built around a state machine architecture where agents execute tasks by reading instructions from the top of the stack and pushing results onto a stack.
This model enables powerful features like step-through debugging, branching for parallel exploration, and easy replay.

## Philosophy

Hugin is built around three core principles:

- **LLMs are oracles, not agents.** LLMs make it easy to work with unstructured data and incorporate adaptive learning, but they're just one component. In Hugin they are just treated as a particular type of oracle that agents consult.

- **Agentic reasoning is fundamentally different from agentic workflows.** Most frameworks are built for process automation (like RPA). Hugin is designed for open-ended, creative tasks like coding, research, and analysis.

- **Immutability enables powerful debugging.** An agent's history is represented as a stack of states. This makes replay, step-through, and branching trivial.

## Building Blocks

<div class="features">
  <div class="feature">
    <h3><a href="/concepts/agents/">Sessions & Agents</a></h3>
    <p>The main entity that executes tasks. Contains a stack of interactions and references to config and session.</p>
  </div>
  <div class="feature">
    <h3><a href="/concepts/stacks/">Stacks & Interactions</a></h3>
    <p>The interaction stack is the heart of Hugin. Every agent step is an interaction pushed onto the stack.</p>
  </div>
  <div class="feature">
    <h3><a href="/concepts/tools/">Tools</a></h3>
    <p>Functions that agents can call. Built-in tools for common operations, plus easy custom tool development.</p>
  </div>
</div>

## Architecture Overview

```
Session (manages multiple agents)
├── Environment (registries + storage)
│   ├── ConfigRegistry (agent configurations)
│   ├── TaskRegistry (task definitions)
│   ├── TemplateRegistry (Jinja2 templates)
│   └── ToolRegistry (available tools)
└── Agents
    └── Agent
        ├── Config (behavior definition)
        ├── Task (initial prompt + parameters)
        └── Stack (interaction history)
            ├── TaskDefinition
            ├── AskOracle
            ├── OracleResponse
            ├── ToolCall
            ├── ToolResult
            └── ...
```

## Key Features

### Dynamic Configuration
Change an agent's tools, task, or even its system prompt at runtime. The context is rendered fresh with each LLM call.

### Branching
Create parallel exploration paths from any point in the stack. Each branch has its own isolated context while sharing the history up to the branch point.

### Multi-Agent Support
Run multiple agents in a session with shared state via namespaces. Agents can communicate through the session's state system with fine-grained access control.

### Memory Model
- **Dynamic Context** (short-term): The interaction stack itself, rendered at each LLM call
- **Artifacts** (long-term): Persistent storage via `save_insight`, `query_artifacts`, and `get_artifact_content` tools

### Visual Debugging
The agent monitor provides real-time visualization of agent flows, tool calls, and decision trees.

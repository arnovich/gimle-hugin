# Taskvalet participation

Install Taskvalet alongside Hugin to let an agent participate in shared tasks,
research and swarms, and submit checks to prepared compute workers. Hugin does
not depend on Taskvalet: the adapter accepts its public `ParticipantTools`
provider contract (`definitions` and `invoke_result`). Use a Taskvalet build that
provides both methods.

The operator first enrolls a distinct Taskvalet run for each agent. Keep its
credential and journal private, outside prompts, tool arguments, serialized
configs and shared environment variables. Bind the live provider to the concrete
Hugin Agent object:

```python
from dataclasses import replace
from pathlib import Path

from gimle.hugin.integrations.taskvalet import bind_taskvalet_tools
from taskvalet.agent_tools import ParticipantTools
from taskvalet.participation import Participant
from taskvalet.participation_compute import ComputeBinding

# Prepare agent/session using your application's usual task and config.
binding = ComputeBinding.model_validate_json(Path("prepared-target.json").read_text())
with Participant.connect(Path("private/run.json"), compute=binding) as participant:
    with bind_taskvalet_tools(agent, ParticipantTools(participant)) as names:
        agent.config = replace(agent.config, tools=[*agent.config.tools, *names])
        session.run(max_llm_calls=20)
```

Omit `compute` to expose participation without compute tools. Taskvalet's operator
prepares the target environment, candidate path, checker/context digests, timeout
and memory. The agent can submit source with `taskvalet_compute_submit`, continue
other work, then call `taskvalet_compute_job` once to inspect status/results.
Neither tool waits for Lean completion. On an interrupted submission, use
`taskvalet_resume` to recover the same request and job ID before another mutation.
Compute reports are evidence for review, not automatically shared knowledge or
proof authority.

Task-specific tool lists replace config lists: attach the yielded names to that
task if it declares tools. Clone shared configs/tasks rather than editing them
in place. Child agents need their own enrollment and binding. Two agents can
advertise the same public tool names while retaining separate private registry
entries; the adapter checks exact agent identity at execution.

Closing the scope removes its entries and invalidates old references. It does
not release Taskvalet claims, stop swarms or cancel accepted jobs. Perform those
explicit workflow operations before teardown when desired. Keep the participant
connection open for the entire binding scope. Restored sessions require explicit
rebinding; providers and credentials are not serialized. This is an application
boundary, not a sandbox against arbitrary Python code running in the same process.

Hugin's optional `Tool.input_schema` preserves a complete object JSON schema
through serialization and all supported provider adapters. It cannot be combined
with legacy parameters or `include_reason`, and `stack`/`branch` are reserved.
The implementation/provider remains responsible for runtime argument validation.

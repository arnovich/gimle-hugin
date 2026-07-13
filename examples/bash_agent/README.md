# bash_agent

An agent that can run shell commands in a sandboxed workspace via the
`builtins.bash` tool.

```bash
uv run hugin run --task explore --task-path examples/bash_agent
```

## What it shows

- Wiring the `bash` tool into a config with `tools: [builtins.bash:bash]`.
- Configuring the sandbox under `options.bash`: which `backend` runs the shell
  and the `policy` that guards it.

## The backend is a choice — and `local` is not a sandbox

`options.bash.backend` names *where* the shell runs. The three backends are
peers:

- `local` (used here) runs on the host and has **no isolation boundary**. Fine
  for a trusted, illustrative task like this one; do not point it at untrusted
  work.
- `docker` runs in a hardened container (the boundary is the container).
- `ssh` runs on a remote machine (the boundary is that disposable machine).

The `policy` block is a guardrail against *accidents* (it blocks `rm -rf /`,
`dd`, `git push --force`, …), not a security boundary. It deliberately does not
try to stop interpreter-based execution — the runtime does that. See
`tasks/open/023-bash-tool` for the full design.

## Per-agent, per-branch workspaces

Each agent (and each branch) gets its own working directory under the session's
sandbox, so parallel agents don't clobber each other. Command output is
truncated tail-biased if large, with the full output written to
`.hugin/last_output.txt` in the workspace.

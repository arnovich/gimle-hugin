# Spec: bash tool + sandbox

> Revised after panel review, then adjusted per direction. `review.md` records
> what changed and why. The headline: **the isolation boundary is whichever
> backend you choose** (`local` = none, `docker` = container, `ssh` = the remote
> machine), the three backends are peers with **no Docker dependency**, and the
> policy engine is a guardrail against accidents — never sold as isolation.

## Module layout

```
src/gimle/hugin/sandbox/
├── __init__.py
├── sandbox.py       # Sandbox ABC + ExecResult + SandboxSpec + enforcement
├── policy.py        # Policy + evaluate() -> Decision   (pure, no I/O)
├── manager.py       # SandboxManager: lifecycle, per-(agent,branch) workspaces
├── reaper.py        # out-of-band, dead-owner-scoped container/dir reaping
├── audit.py         # structured append-only command log + counters
├── local.py         # LocalSandbox (local backend; subprocess; no isolation)
├── docker.py        # DockerSandbox  (opt-in container boundary)
├── ssh.py           # SSHSandbox     (remote/VPS boundary; phase 2)
└── fake.py          # FakeSandbox    (tests)

src/gimle/hugin/tools/builtins/bash.py         # the tool
src/gimle/hugin/tools/builtins/bash_output.py  # poll a backgrounded command (phase 2/3)
```

`sandbox.py` deliberately mirrors `storage/storage.py`: a small ABC, concrete
backends beside it, no knowledge of agents or tools.

## 1. Execution backend

```python
@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    truncated: bool      # output exceeded max_output_bytes
    timed_out: bool
    oom_killed: bool     # container hit its memory cap (exit 137)


class Sandbox(ABC):
    @abstractmethod
    def start(self) -> None:
        """Create/pull/connect. Idempotent. Lazy on first exec."""

    @abstractmethod
    def exec(
        self,
        command: str,
        *,
        policy: "Policy",              # enforcement lives HERE, fail-closed
        cwd: str,
        timeout_s: int,
        max_output_bytes: int = 16_000,
    ) -> ExecResult:
        """Run `command`. Enforce `policy` before running (raise PolicyDenied
        on violation — every caller is checked by construction). Execute via
        `bash -c` so the run dialect matches the parsed dialect. Never raise
        for a non-zero exit."""

    @abstractmethod
    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Absolute cwd for this (agent, branch); created if absent."""

    @abstractmethod
    def put_file(self, path: str, content: bytes) -> None: ...

    @abstractmethod
    def get_file(self, path: str) -> bytes:
        """realpath-confine + O_NOFOLLOW — a container-planted symlink must not
        read the host out of the workspace mount."""

    @abstractmethod
    def stop(self) -> None:
        """Tear down. Idempotent. Safe on an unstarted sandbox."""
```

Note: `evaluate()` is called in two places — inside `exec` for **hard
enforcement** (fail-closed, raises), and in the tool for **friendly rendering**
(turn a denial into a readable `ToolResponse`/escalation). Enforcement is not
the tool's job alone; a future `git` tool or the phase-5 harvest layer must not
be able to reach `exec` unchecked.

```python
@dataclass(frozen=True)
class SandboxSpec:
    backend: Literal["local", "docker", "ssh"]                    # no default — must be named
    image: str = "gimle/hugin-sandbox@sha256:<pinned-digest>"     # docker only; digest, not tag
    host: Optional[str] = None                                    # ssh only
    network: bool = False
    cpu: float = 2.0                                              # container backends only
    memory: str = "2g"                                            # container backends only
    pids: int = 512                                              # container backends only

def create_sandbox(spec: SandboxSpec, session_id: str, owner_pid: int) -> Sandbox:
    """Validate the chosen backend up front and fail with a remediation message
    — e.g. docker selected but daemon unreachable, or ssh host unreachable —
    never surface a raw DockerException 30 steps into a run. On `local`, raise if
    any boundary-only knob (network/cpu/memory/pids) was set to a non-default
    value: the local backend cannot enforce them and must not pretend to."""
```

### DockerSandbox (opt-in container boundary)

Selected by `backend: docker`; not required for the package to install or for
`bash` to run. The `docker` SDK is a **lazy import inside `docker.py`**, so a
user who never selects it needs neither the library nor a daemon. One long-lived
container per session, `docker exec` per command (or a persistent shell — see
§Statefulness). When chosen, all of these flags are mandatory:

- `--network=none` unless `network: true`
- `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`
- `--read-only` root, `--tmpfs /tmp:rw,noexec,nosuid,size=256m`
- `--cpus`, `--memory`, `--pids-limit` from spec; `--ulimit nproc/nofile`
- `--init` so PID 1 reaps double-forked children
- default seccomp + apparmor profiles kept (never `--privileged`, never
  `--security-opt seccomp=unconfined`)
- userns-remap so container-root is not host-root
- `HOME=/workspace/...`, empty env by default (no inherited secrets)
- workspace = a **named/bind volume keyed by session-id** so a resumed session
  reattaches its filesystem instead of getting an empty new one
- labels `hugin.session`, `hugin.owner_pid`, `hugin.created`, `hugin.ttl`;
  a heartbeat file touched each step
- no docker socket mount, ever

`network: true` must not be an open egress cliff: block link-local / metadata
(`169.254.0.0/16`) and RFC1918 by default, ideally via an egress-allowlist
proxy — otherwise an injected `curl http://169.254.169.254/...` exfiltrates
cloud IAM credentials.

Image is **thick and boring** (a thin image is a false economy — every missing
binary is a wasted turn): Debian slim + `bash coreutils findutils git curl
ca-certificates ripgrep jq less` + `python3` + `uv` + `node`. Pinned by digest,
scanned (Trivy/Grype), signed (cosign), verified on pull. **No Hugin source,
no credentials** — the sandbox is dumb; stack/interactions/artifacts stay
host-side.

### LocalSandbox (`local` backend)

`subprocess` on the host — the zero-dependency backend, and a legitimate choice
for iterating or trusted tasks (it's what `examples/bash_agent` uses). **No
isolation boundary**, and the design says so rather than dressing it up.
`create_sandbox` raises if any boundary-only knob (`network`/`cpu`/`memory`/
`pids`) was set — a `network:false` a bare subprocess can't enforce is a lie, so
asking for it here is an error, not a silent no-op. `HOME` is set to the
workspace and the env scrubbed, but the docs state plainly that
`cat ~/.aws/credentials` and `/dev/tcp` egress remain reachable. Process group
started with `start_new_session=True`; timeout kills the group — with the
documented caveat that `setsid`/daemonized children escape it.

### SSHSandbox (`ssh` backend — the remote machine is the boundary; phase 2)

A peer to Docker, not a footnote to it: for many users a disposable VPS is the
most natural isolation story (a throwaway box you don't mind the agent
breaking). Shell out to `ssh`/`scp` (no `paramiko` dep). Dedicated throwaway key
per session, `-o ForwardAgent=no -o BatchMode=yes -o ConnectTimeout=... -o
ServerAliveInterval=...`. Run the remote command under `systemd-run --scope` /
`timeout` / a named tmux so Hugin can kill the *remote* job, not just the local
client (remote commands are not idempotent to retry). Own the ControlMaster
socket path; clean it in `stop()`. Preferably target a hardened container on the
remote (`ssh host docker run …`) rather than the bare host. Provisioning /
ownership / cost / secrets written before build, not during.

Shell out to `ssh`/`scp` (no `paramiko` dep). Dedicated throwaway key per
session, `-o ForwardAgent=no -o BatchMode=yes -o ConnectTimeout=... -o
ServerAliveInterval=...`. Run the remote command under `systemd-run --scope` /
`timeout` / a named tmux so Hugin can kill the *remote* job, not just the local
client (remote commands are not idempotent to retry). Own the ControlMaster
socket path; clean it in `stop()`. Preferably target a hardened container on
the remote (`ssh host docker run …`) rather than the bare host. Provisioning /
ownership / cost / secrets written before build, not during.

## 2. Workspace layout (worktree hybrid)

```
/workspace/                         # the only writable location
├── common/                         # shared across agents; deliberate hand-offs
├── .hugin/last_output.txt          # full output of the last command (spill target)
└── agents/
    ├── <agent-id-a>/<branch>/      # keyed by (agent, branch) — branches don't collide
    └── <agent-id-b>/<branch>/
```

- Default `cwd` for a `bash` call is `workspace_for(agent.id, branch)`.
- `AgentCall` gets an `inherit_workspace` option so a delegated child can start
  in a populated dir (or a pointer to `common/`) instead of an empty one.
- `workspace_only: true` (default) denies resolved paths outside `/workspace`.
  On Docker the mount enforces it; on `local` it is best-effort only and
  documented as such.

## 3. Policy engine

Pure function, no I/O, trivially testable. **Permissive-by-default inside the
container**, because the container is the boundary:

```python
@dataclass(frozen=True)
class Policy:
    mode: Literal["denylist", "allowlist", "unrestricted"] = "denylist"
    deny: List[str] = field(default_factory=lambda: DEFAULT_DENY)
    allow: List[str] = field(default_factory=list)   # only used in allowlist mode
    allow_shell_features: bool = True                # container contains it
    workspace_only: bool = True
    network: bool = False
    timeout_s: int = 15                              # interactive default (short!)
    max_timeout_s: int = 600                         # policy cap for explicit long cmds
    max_output_bytes: int = 16_000
    on_violation: Literal["deny", "ask_human"] = "deny"

    @classmethod
    def from_dict(cls, raw: dict) -> "Policy":
        """Reject unknown keys, validate every Literal, raise LOUDLY on a
        malformed options.bash block — never silently fall back to default."""


Decision = Union[Allow, Deny, Escalate]   # Deny/Escalate carry reason: str

def evaluate(command: str, policy: Policy) -> Decision: ...
```

`evaluate()`:

1. Parse with `bashlex` into an AST. **Parse failure → `Deny`** (fail closed).
2. Walk the AST through pipes, `&&`, `;`, subshells, process substitution.
3. **Descend into wrapper binaries that run their argument** — `timeout`,
   `env`, `xargs`, `nice`, `nohup`, `setsid`, `command`, `stdbuf` — don't treat
   the nested command as an opaque arg.
4. **Reject dangerous assignment prefixes** — `LD_PRELOAD`, `LD_LIBRARY_PATH`,
   `BASH_ENV`, `ENV`, `IFS`, `GIT_*`, `PATH=` overrides.
5. Apply `deny` (or `allow` in allowlist mode) to each command word.
6. Check path-looking args / redirection targets against `workspace_only`.
7. Violation → `Deny` or `Escalate` per `on_violation`.

`DEFAULT_DENY` is blunt and about *accidents*, not capability control:
`rm -rf` at `/` or `~`, `dd`, `mkfs`, `shutdown`, `reboot`, fork bombs,
`git push --force`, raw writes to `/dev/*`, `chmod -R 777 /`. The design
**does not** pretend this stops a determined or injected agent — the chosen
runtime (container or disposable remote) does, or on `local`, nothing does.

`allowlist` mode still exists for the paranoid / `local` case, but the
docs state explicitly: **once any interpreter (`python3`, `uv`, `node`) or
code-exec-capable tool (`git`, `awk`, `sed`, `find`, `curl`) is on the allow
list, the allowlist is not a capability boundary.** No allowlist is ever
described as isolation.

Tests (the bypasses are the *first* cases written): `python3 -c`, `uv run`,
`awk 'BEGIN{system()}'`, `find -exec`, `git -c core.pager='!sh'`, `sed` `e`
flag, `curl file://`, `timeout bash -c`, `env bash`, `xargs sh`,
`LD_PRELOAD=./x ls`, `$'\x72\x6d'` ANSI-C quoting, symlink escape, `> /dev/tcp`,
parse failure.

## 4. The tool

`builtins.bash`, referenced as `builtins.bash:bash`.

```yaml
parameters:
  command: {type: string, description: "Shell command to run", required: true}
  cwd:     {type: string, description: "Dir relative to your workspace", required: false}
  # NOTE: no `timeout` param and no `include_reason` — see below.
options:
  include_only_in_context_window: true   # actually drops old outputs (reduced_context_window does NOT)
  context_window: 5
```

- **No `include_reason`.** It forbids returning an Interaction
  (`tool.py:391-395`), taxes a high-frequency tool, and produces restated
  intent. A justification is required only on the escalation path (phase 3),
  where a human reads it.
- **No `timeout` param** while execution is synchronous and the cap is hidden.
  Policy owns the timeout; `max_timeout_s` bounds an explicit long command once
  background exec exists.

### Tool description carries the environment (v1)

The description is the one thing the model always sees. Generate the allow/deny
line and the network flag **from the `Policy` object** so they cannot drift:

> Run a shell command in your sandboxed workspace; returns stdout, stderr, exit
> code. **Working dir:** `/workspace/agents/<you>/<branch>` (private).
> `/workspace/common/` is shared with sibling agents. Nothing outside
> `/workspace` is readable/writable. **Installed:** bash, coreutils, git,
> ripgrep (`rg`), jq, python3, uv, node. **No network** (when
> `network:false`) — `curl`/`uv` cannot reach the internet. **Each call is a
> fresh shell:** `cd`/`export`/`source`/background jobs do NOT persist across
> calls unless a persistent shell is enabled; persist state by writing files
> under your workspace. **Output is truncated to ~16 KB (tail-biased);** full
> output is in `/workspace/.hugin/last_output.txt` — inspect with `rg`/`sed -n`.
> **Refused commands** (e.g. `rm -rf /`, `git push --force`) come back with a
> reason — that's information, not a failure.

### Flow

1. Resolve `Policy` + `SandboxSpec` from `config.options["bash"]`
   (`Policy.from_dict` — fail loud on malformed), falling back to session
   defaults, then the built-in default.
2. `sandbox.exec(command, policy=..., cwd=workspace_for(agent.id, branch), ...)`
   — enforcement happens inside `exec`; a `PolicyDenied` is caught here and
   rendered.
3. Map to `ToolResponse`:
   - **Denial / timeout / infra failure → `is_error=True`** with a distinct
     `denied` / `timed_out` / `infra_error` field.
   - **A process that ran to completion → `is_error=False`**, `exit_code` in
     content. (`grep`-no-match and `diff`-differences exit 1 and are *not*
     errors — reserving `is_error` for them mis-signals the model.)
   - `content = {command, exit_code, stdout, stderr, truncated, timed_out,
     oom_killed, duration_s}`.
   - Output is **tail-biased** truncated to `max_output_bytes` (the actionable
     error is usually last; head+tail hands the model invalid JSON and elides
     pytest tracebacks), full copy spilled to `/workspace/.hugin/last_output.txt`,
     with a marker telling the model how to read more. Never claim structured
     output survived truncation.

### Return type / deferral — the real contract

`ToolCall.step` (`interaction/tool_call.py:54-60`) accepts only `ToolResponse`
and `AgentCall`; a bare `Waiting`/`AskHuman` raises. So **all deferral routes
through `ToolResponse.response_interaction`**, which `ToolResult.step`
(`tool_result.py:107-108`) already honors — never a bare Interaction. Phase 3
escalation and phase-6 background exec both use this path. This is the concrete
mechanism the earlier "return type stays open" hand-wave lacked.

### Hard dependency: one-tool-call-per-turn

`anthropic.py:125` keeps only the *last* `tool_use` block in a response
(`# TODO support multiple tool calls`). Bash agents batch heavily, so batched
calls are silently dropped and the model proceeds on phantom results. Until
task 006 lands: **detect >1 `tool_use` and return an explicit error for the
dropped ones.** Note 006 as a blocking dependency for good bash UX.

## 5. Config surface

`Config.options` is already free-form, so no `Config` schema change — but the
policy dict is validated strictly (`Policy.from_dict`), because a typo'd key
(`mode: allowlst`) or a mis-indented `policy:` block silently dropping the
policy is a security bug.

```yaml
name: coder
system_template: coder_system
tools:
  - builtins.bash:bash
  - builtins.finish:finish
  # NOTE: read_file/list_files/search_files deliberately absent — they read the
  # HOST filesystem while bash runs in the sandbox; shipping both = two
  # filesystems the model can't reconcile.
options:
  bash:
    backend: docker
    network: false
    policy:
      mode: denylist
      timeout_s: 15
      max_timeout_s: 600
      workspace_only: true
      on_violation: ask_human
```

Precedence: config `options.bash` > session default > built-in default, as an
explicit **key-level merge** (not whole-object replace).

## 6. Lifecycle — Phase 1, out-of-band-primary

`Session` owns a typed, lazily-created `session.sandbox` (`SandboxManager`).
The tool reads `stack.agent.session.sandbox` — not an `env_vars` convention a
builtin can't satisfy. Lazy `start()` on first `bash` call, so a session that
never runs a command never pays.

Teardown is **primarily out-of-band**, because `atexit`/`finally` skip SIGTERM,
SIGKILL, OOM-kill and laptop-sleep:

- Every sandbox stamped `hugin.session` / `hugin.owner_pid` / `hugin.ttl` +
  heartbeat.
- A **reaper runs at the start of every `hugin` invocation** and kills only
  dead-owner or stale sandboxes (never by session label alone — that races live
  peers). GCs stale `storage/sandboxes/<id>/` dirs on the same pass.
- `Session.close()` (new; **Phase 1**) tears down `session.sandbox`
  idempotently. Called from a context manager (`with Session(...) as s:`), the
  CLI `finally`, the interactive TUI's agent-thread completion + app exit
  (daemon threads don't run `finally` reliably), and apps'
  (`financial_newspaper/run.py`) `finally`.
- A `SIGTERM`/`SIGINT` handler calls `close()`. `atexit` is the last line.
- Docker workspace is a session-keyed volume so resume reattaches, not recreates.
- `hugin sandbox list|prune` — scoped to dead-owner/stale, safe to run beside
  live peers.

## 7. Concurrency

`Session.run` is single-threaded round-robin (`session.py:170-195`) and
`execute_tool` is synchronous (`tool.py:381`), so one long `bash` freezes every
sibling agent and branch. Mitigations, in order:

- v1: short default `timeout_s` (15s), loud doc note that bash blocks siblings.
- Phase 2/3: background exec — `bash` returns
  `ToolResponse(response_interaction=Waiting)` for long commands + a
  `bash_output` poll tool. (Requires running the subprocess off the step
  thread; scoped as its own work, not a free "return a Waiting".)

## 8. Observability (Phase 1)

`audit.py`: append-only log (session, agent, command, decision, exit_code,
duration, `truncated`/`timed_out`/`oom` flags) + counters (run / denied /
timed-out / container-starts / start-failures). `hugin monitor` and
`hugin interactive` get a per-session commands view rendering denials/timeouts
distinctly.

## 9. Statefulness

Per-agent **persistent shell** (pexpect/coprocess, one per `workspace_for`)
*inside* the disposable container, so `cd`/`export`/`source` behave as the model
expects. This resolves the security-vs-usability tension: persistent shell,
disposable container. If not shipped in v1, `cd` must be *removed* from any
allowlist and the stateless contract stated in bold in the description — an
allowed-but-silently-ineffective `cd` is worse than a denied one.

## 10. Dependencies

`bashlex` is **core** (policy applies everywhere; a policy engine that can
vanish when an extra is missing is worse than a dependency). `docker` SDK in an
optional `sandbox` group.

```toml
dependencies = [ ..., "bashlex>=0.18" ]
[project.optional-dependencies]
sandbox = ["docker>=7.1"]
```

## 11. Testing

- **`FakeSandbox`** — records commands, returns canned `ExecResult`s. Tool,
  precedence, truncation, workspace routing, deferral (`response_interaction`),
  the >1-tool-call error path — all tested here. No subprocess, no docker.
- **Policy engine** — table-driven, pure; the interpreter/wrapper/assignment
  bypasses are the headline cases.
- **DockerSandbox** — `slow` marker, skipped without a daemon; asserts the
  hardening flags are actually set and that `python3 -c 'os.system("id")'` is
  *contained* (not that it's denied — it isn't, the container is the boundary).
- **Reaper** — dead-owner detection, TTL, and that it never kills a live peer.
- **Multi-agent / multi-branch** — distinct `workspace_for` paths; hand-off via
  `common/`; two branches of one agent don't collide.

# Spec: Persist the rendered prompt sent to the LLM

Date: 2026-05-11
Task: 018
Status: implemented in PR #45

## Goal

When something goes wrong with prompt rendering (e.g. the bare-template-name
silent failure fixed in #42), the persisted session should show what was
actually sent to the LLM, without anyone having to monkey-patch
`chat_completion`. We do this by optionally capturing, on each
`OracleResponse`, the rendered system prompt and the rendered user message
that this turn contributed.

Opt-in (off by default): a `Environment.capture_rendered_prompts` flag,
defaulting from the `HUGIN_CAPTURE_RENDERED_PROMPTS` environment variable.

## What is captured

On `AskOracle.step()`, *only when capture is enabled*, the `OracleResponse`
created for this turn is given:

- `rendered_system_prompt: Optional[str]` — the exact string passed to
  `chat_completion` (i.e. the result of `renderer.render_system_prompt(...)`).
- `rendered_user_message: Optional[List[Dict[str, Any]]]` — the rendered
  content blocks this `AskOracle` contributes, i.e.
  `render_user_message(self, reduced=False)` (the task / tool-result / text
  block). **Not** the whole conversation history — just this turn's message.

When capture is disabled (the default), both stay `None` and nothing changes
on disk.

### Explicitly out of scope

- Persisting the full `interaction_messages` list (the entire conversation
  context) on every `OracleResponse` — large, quadratic over a session, and
  reconstructible from the other interactions. (Could be a separate debug
  feature later.)
- A per-agent / `Config`-level toggle.
- Replaying or diffing rendered prompts in the UI.

## Data model changes

### `OracleResponse` (`src/gimle/hugin/interaction/oracle_response.py`)

Add two optional dataclass fields, both defaulting to `None`:

```python
rendered_system_prompt: Optional[str] = None
rendered_user_message: Optional[List[Dict[str, Any]]] = None
```

Serialization needs no special handling:

- `Interaction.to_dict()` iterates `fields(self)`, so the new fields are
  included automatically; their values are plain `str` / `list[dict]`, so
  JSON-serializable.
- `OracleResponse` uses the base `Interaction._from_dict()`, which does
  `kwargs = {"stack": stack, **data}`. A session saved before this change
  has no `rendered_*` keys → not passed → dataclass default `None` applies.
  Forward/backward compatible.

`OracleResponse.step()` and `tool_call_id` are unaffected.

### `Environment` (`src/gimle/hugin/agent/environment.py`)

`Environment` is a plain class. Add:

- An `__init__` parameter `capture_rendered_prompts: Optional[bool] = None`.
  Stored as `self.capture_rendered_prompts`: if the arg is not `None`, use it;
  otherwise derive it from the `HUGIN_CAPTURE_RENDERED_PROMPTS` env var
  (truthy values: `1`, `true`, `yes`, `on`, case-insensitive; everything else,
  including unset, is `False`).
- Thread the same optional param through `Environment.load(...)` so callers
  can pass it explicitly; `load` forwards it to the `Environment(...)`
  constructor (where the env-var default still applies if `None`).

A small truthy-parsing helper (`_env_truthy(name: str) -> bool`) — local to
`environment.py` unless an equivalent already exists in `gimle.hugin.utils`.

## Behaviour change

### `AskOracle.step()` (`src/gimle/hugin/interaction/ask_oracle.py`)

Today (abridged):

```python
renderer = PromptRenderer(self.stack.agent, branch=self.branch)
system_prompt = renderer.render_system_prompt(self.template_inputs)
...
assistant_response = chat_completion(system_prompt=system_prompt, messages=interaction_messages, tools=tools, llm_model=llm_model)
self.stack.add_interaction(OracleResponse(stack=self.stack, branch=self.branch, response=assistant_response))
```

After:

```python
rendered_system_prompt = None
rendered_user_message = None
if self.stack.agent.environment.capture_rendered_prompts:
    from gimle.hugin.llm.prompt.message import render_user_message
    rendered_system_prompt = system_prompt
    rendered_user_message = render_user_message(self, reduced=False)
...
self.stack.add_interaction(OracleResponse(
    stack=self.stack, branch=self.branch, response=assistant_response,
    rendered_system_prompt=rendered_system_prompt,
    rendered_user_message=rendered_user_message,
))
```

Notes:
- `system_prompt` is captured verbatim — it is exactly what `chat_completion`
  received.
- `render_user_message(self, ...)` is called separately rather than indexing
  into `interaction_messages`; the slight `reduced`-mode mismatch is
  irrelevant because the latest message is never reduced.
- Import of `render_user_message` is local to `step()` (mirrors the existing
  local imports there) to avoid an import cycle.

## UI surfacing (minimal)

### Web monitor (`src/gimle/hugin/cli/monitor_agents.py`)

- Add `("rendered_system_prompt", "rendered_system_prompt")` and
  `("rendered_user_message", "rendered_user_message")` to the `field_mappings`
  list in `_extract_interaction_fields` so they reach the interaction's
  `details` JSON.
- Surface them in the `OracleResponse` detail view next to where `response`
  is shown. Exact frontend hookup (generic `details` rendering vs. a
  hardcoded per-field block) to be determined during implementation by
  following the existing pattern for `response` / `template_inputs`.

### TUI (`src/gimle/hugin/ui/page.py`)

- Show the two fields in the interaction detail when present, following the
  pattern used for the existing interaction fields.

Both UIs render these read-only and only when populated.

## Docs

Add `HUGIN_CAPTURE_RENDERED_PROMPTS` to the "Monitoring & Debugging" section
of `CLAUDE.md` (what it does, how to set it, where the captured data shows up).

## Testing

- **Serialization round-trip:** an `OracleResponse` with `rendered_*` set
  survives `to_dict()` → `from_dict()`; a dict without those keys deserializes
  to `None` for both.
- **Capture on:** with `capture_rendered_prompts=True` (set on the
  `Environment`), an `AskOracle.step()` with a patched `chat_completion`
  produces an `OracleResponse` whose `rendered_system_prompt` equals the
  `system_prompt` argument the patched `chat_completion` received, and whose
  `rendered_user_message` equals `render_user_message(ask_oracle, reduced=False)`.
- **Capture off (default):** same flow, both fields `None`.
- **Environment flag:** `HUGIN_CAPTURE_RENDERED_PROMPTS` truthy values →
  `Environment().capture_rendered_prompts is True`; unset / other values →
  `False`; explicit `Environment(capture_rendered_prompts=...)` overrides the
  env var; `Environment.load(..., capture_rendered_prompts=...)` forwards it.
- **Regression bonus:** extend `TestSystemPromptReachesModel` so that with
  capture on, the `OracleResponse` for a bare-template-name agent records the
  rendered body (and would have recorded the literal name pre-#42).

## Success criteria

- [ ] With `HUGIN_CAPTURE_RENDERED_PROMPTS` set, a persisted session shows the
      literal-vs-rendered system/user prompt per `OracleResponse` with no
      monkey-patching.
- [ ] Web monitor and TUI surface the rendered prompt for an `OracleResponse`.
- [ ] With the flag unset (default), behaviour and on-disk format are
      unchanged; old sessions still load.
- [ ] `uv run pytest -q` and the pre-commit hooks (modulo the pre-existing
      mypy/openai internal error) pass.

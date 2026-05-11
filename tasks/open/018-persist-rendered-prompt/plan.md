# Persist Rendered Prompt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optionally persist, on each `OracleResponse`, the rendered system prompt and the rendered user message that this turn sent to the LLM, so prompt-rendering bugs are visible in the saved session without monkey-patching `chat_completion`.

**Architecture:** Add two optional fields to `OracleResponse` (serialize/deserialize for free via the base `Interaction` machinery). Add an opt-in `Environment.capture_rendered_prompts` flag, defaulting from the `HUGIN_CAPTURE_RENDERED_PROMPTS` env var. When the flag is on, `AskOracle.step()` stashes the values onto the `OracleResponse` it creates. Surface them in the web monitor's interaction-detail panel; the curses TUI already shows them via its generic field formatter.

**Tech Stack:** Python 3.12, dataclasses, pytest (with `monkeypatch`), `unittest.mock.patch`; vanilla JS for the monitor frontend.

**Branch:** `task/018_persist_rendered_prompt` (already created; the spec commit lives here). All task commits go on this branch.

**Spec:** `tasks/open/018-persist-rendered-prompt/spec.md`

---

## File structure

| File | Change |
|------|--------|
| `src/gimle/hugin/agent/environment.py` | Add module-level `_env_truthy()`; add `capture_rendered_prompts` param to `Environment.__init__` and `Environment.load` |
| `src/gimle/hugin/interaction/oracle_response.py` | Add `rendered_system_prompt` and `rendered_user_message` dataclass fields |
| `src/gimle/hugin/interaction/ask_oracle.py` | In `step()`, capture the rendered prompt onto the new `OracleResponse` when the flag is set |
| `src/gimle/hugin/ui/static/js/monitor.js` | In `renderInteractionTypeDetails`, render the two fields in the `OracleResponse` block |
| `CLAUDE.md` | Document `HUGIN_CAPTURE_RENDERED_PROMPTS` under "Monitoring & Debugging" |
| `tests/test_environment.py` | Tests for the `capture_rendered_prompts` flag / env var |
| `tests/test_interaction.py` | Tests for `OracleResponse` round-trip + `AskOracle.step()` capture on/off |
| `tests/test_prompt.py` | Extend `TestSystemPromptReachesModel` with a capture-on regression test |

---

## Task 1: `Environment.capture_rendered_prompts` flag + `_env_truthy` helper

**Files:**
- Modify: `src/gimle/hugin/agent/environment.py` (the module-level area near the top; `__init__` at lines ~37-56; `load` at lines ~169-258)
- Test: `tests/test_environment.py`

- [ ] **Step 1: Write the failing tests**

Append to the end of `class TestEnvironment` in `tests/test_environment.py`:

```python
    def test_capture_rendered_prompts_default_false(self, monkeypatch):
        """Defaults to False when the env var is unset."""
        monkeypatch.delenv("HUGIN_CAPTURE_RENDERED_PROMPTS", raising=False)
        assert Environment().capture_rendered_prompts is False

    @pytest.mark.parametrize("value", ["1", "true", "True", "yes", "on", " ON "])
    def test_capture_rendered_prompts_env_truthy(self, monkeypatch, value):
        """Truthy env-var values enable capture."""
        monkeypatch.setenv("HUGIN_CAPTURE_RENDERED_PROMPTS", value)
        assert Environment().capture_rendered_prompts is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
    def test_capture_rendered_prompts_env_falsy(self, monkeypatch, value):
        """Non-truthy env-var values leave capture off."""
        monkeypatch.setenv("HUGIN_CAPTURE_RENDERED_PROMPTS", value)
        assert Environment().capture_rendered_prompts is False

    def test_capture_rendered_prompts_explicit_overrides_env(self, monkeypatch):
        """An explicit constructor arg overrides the env var either way."""
        monkeypatch.setenv("HUGIN_CAPTURE_RENDERED_PROMPTS", "1")
        assert Environment(capture_rendered_prompts=False).capture_rendered_prompts is False
        monkeypatch.delenv("HUGIN_CAPTURE_RENDERED_PROMPTS", raising=False)
        assert Environment(capture_rendered_prompts=True).capture_rendered_prompts is True

    def test_load_forwards_capture_rendered_prompts(self, tmp_path, monkeypatch):
        """Environment.load forwards the flag to the constructed Environment."""
        monkeypatch.delenv("HUGIN_CAPTURE_RENDERED_PROMPTS", raising=False)
        env = Environment.load(str(tmp_path), capture_rendered_prompts=True)
        assert env.capture_rendered_prompts is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_environment.py -q -k capture`
Expected: FAIL — `AttributeError: 'Environment' object has no attribute 'capture_rendered_prompts'` (and `TypeError` for the explicit-arg / `load` cases).

- [ ] **Step 3: Add the `_env_truthy` helper**

In `src/gimle/hugin/agent/environment.py`, after the `logger = logging.getLogger(__name__)` line (≈ line 22), add:

```python
def _env_truthy(name: str) -> bool:
    """Return True if the environment variable is set to a truthy value."""
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")
```

(`os` is already imported at the top of the file.)

- [ ] **Step 4: Add the `capture_rendered_prompts` param to `Environment.__init__`**

Change the `__init__` signature and body:

```python
    def __init__(
        self,
        storage: Optional["Storage"] = None,
        env_vars: Optional[Dict[str, Any]] = None,
        package_path: Optional[str] = None,
        capture_rendered_prompts: Optional[bool] = None,
    ) -> None:
        """Initialize an environment with empty registries.

        Args:
            storage: Optional storage instance
            env_vars: Optional dictionary of environment variables accessible to tools
            package_path: Optional path to the package directory this env was loaded from
            capture_rendered_prompts: If set, overrides the
                HUGIN_CAPTURE_RENDERED_PROMPTS env var; when truthy, each
                OracleResponse records the rendered system + user prompt.
        """
        self.config_registry: Registry[Config] = Registry()
        self.task_registry: Registry[Task] = Registry()
        self.template_registry: Registry[Template] = Registry()
        self.storage = storage
        self.env_vars: Dict[str, Any] = env_vars or {}
        self._query_engine: Optional[ArtifactQueryEngine] = None
        self.package_path: Optional[str] = package_path
        self.capture_rendered_prompts: bool = (
            capture_rendered_prompts
            if capture_rendered_prompts is not None
            else _env_truthy("HUGIN_CAPTURE_RENDERED_PROMPTS")
        )
```

- [ ] **Step 5: Thread the param through `Environment.load`**

Change the `load` signature and the `Environment(...)` construction inside it:

```python
    @staticmethod
    def load(
        package_path: str,
        storage: Optional["Storage"] = None,
        env_vars: Optional[Dict[str, Any]] = None,
        capture_rendered_prompts: Optional[bool] = None,
    ) -> "Environment":
        """Load the environment from a path.

        Args:
            package_path: Path to the package directory
            storage: Optional storage instance
            env_vars: Optional dictionary of environment variables accessible to tools
            capture_rendered_prompts: Forwarded to the Environment constructor
                (see Environment.__init__).

        Returns:
            The environment.
        """
```

…and where it does `env = Environment(storage=storage, env_vars=env_vars, package_path=str(package_path_obj))`, add the kwarg:

```python
        env = Environment(
            storage=storage,
            env_vars=env_vars,
            package_path=str(package_path_obj),
            capture_rendered_prompts=capture_rendered_prompts,
        )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_environment.py -q`
Expected: PASS (all environment tests, including the new ones).

- [ ] **Step 7: Commit**

```bash
git add src/gimle/hugin/agent/environment.py tests/test_environment.py
git commit -m "Add Environment.capture_rendered_prompts flag (HUGIN_CAPTURE_RENDERED_PROMPTS)"
```

---

## Task 2: `OracleResponse.rendered_system_prompt` / `rendered_user_message` fields

**Files:**
- Modify: `src/gimle/hugin/interaction/oracle_response.py`
- Test: `tests/test_interaction.py` (add to `class TestOracleResponse`)

- [ ] **Step 1: Write the failing tests**

Add these methods to `class TestOracleResponse` in `tests/test_interaction.py`:

```python
    def test_oracle_response_rendered_fields_default_none(self, mock_stack):
        """The new rendered_* fields default to None."""
        oracle_response = OracleResponse(
            stack=mock_stack, response={"role": "assistant", "content": "hi"}
        )
        assert oracle_response.rendered_system_prompt is None
        assert oracle_response.rendered_user_message is None

    def test_oracle_response_rendered_fields_round_trip(self, mock_stack):
        """rendered_* survive to_dict() -> from_dict()."""
        oracle_response = OracleResponse(
            stack=mock_stack,
            response={"role": "assistant", "content": "hi"},
            rendered_system_prompt="You are a helpful assistant.",
            rendered_user_message=[{"type": "text", "text": "Hello there"}],
        )
        data = oracle_response.to_dict()
        assert data["data"]["rendered_system_prompt"] == "You are a helpful assistant."
        assert data["data"]["rendered_user_message"] == [
            {"type": "text", "text": "Hello there"}
        ]

        restored = Interaction.from_dict(data, mock_stack)
        assert isinstance(restored, OracleResponse)
        assert restored.rendered_system_prompt == "You are a helpful assistant."
        assert restored.rendered_user_message == [
            {"type": "text", "text": "Hello there"}
        ]

    def test_oracle_response_from_dict_without_rendered_fields(self, mock_stack):
        """A session saved before this change deserializes with None."""
        data = {
            "type": "OracleResponse",
            "data": {"response": {"role": "assistant", "content": "hi"}},
        }
        restored = Interaction.from_dict(data, mock_stack)
        assert isinstance(restored, OracleResponse)
        assert restored.rendered_system_prompt is None
        assert restored.rendered_user_message is None
```

`Interaction` is already imported in `tests/test_interaction.py` (it imports `OracleResponse`); add `from gimle.hugin.interaction.interaction import Interaction` to the imports if it is not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_interaction.py -q -k rendered`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'rendered_system_prompt'`.

- [ ] **Step 3: Add the fields to `OracleResponse`**

In `src/gimle/hugin/interaction/oracle_response.py`, change the imports (add `List`) and the dataclass body. The full file top becomes:

```python
"""Oracle response interaction module."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.tool_call import ToolCall
from gimle.hugin.utils.uuid import with_uuid


@Interaction.register()
@dataclass
@with_uuid
class OracleResponse(Interaction):
    """Oracle response interaction.

    Attributes:
        response: The response from the oracle.
        rendered_system_prompt: The system prompt actually sent to the LLM for
            this turn. Populated only when capture is enabled
            (Environment.capture_rendered_prompts); otherwise None.
        rendered_user_message: The rendered content blocks this turn's
            AskOracle contributed to the LLM (task / tool-result / text).
            Populated only when capture is enabled; otherwise None.
    """

    response: Optional[Dict[str, Any]] = None
    rendered_system_prompt: Optional[str] = None
    rendered_user_message: Optional[List[Dict[str, Any]]] = None
```

Leave the `tool_call_id` property and the `step()` method unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_interaction.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gimle/hugin/interaction/oracle_response.py tests/test_interaction.py
git commit -m "Add rendered_system_prompt / rendered_user_message fields to OracleResponse"
```

---

## Task 3: Capture the rendered prompt in `AskOracle.step()`

**Files:**
- Modify: `src/gimle/hugin/interaction/ask_oracle.py` (the `step()` method, lines ≈238-279)
- Test: `tests/test_interaction.py` (add to `class TestAskOracle` — the class containing `test_ask_oracle_step`)

- [ ] **Step 1: Write the failing tests**

Add to `class TestAskOracle` in `tests/test_interaction.py`:

```python
    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_ask_oracle_step_captures_rendered_prompt_when_enabled(
        self, mock_chat_completion, mock_agent, mock_stack
    ):
        """With capture enabled, the OracleResponse records the rendered prompt."""
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": "Hello, world!",
            "tool_call": None,
        }
        mock_agent.session.environment.capture_rendered_prompts = True

        ask_oracle = AskOracle(
            stack=mock_stack,
            prompt=Prompt(type="text", text="Hello"),
            template_inputs={},
        )
        ask_oracle.step()

        oracle_response = mock_stack.interactions[0]
        assert isinstance(oracle_response, OracleResponse)
        # mock_agent's config.system_template is "system", which is not a
        # registered template, so it renders to itself.
        assert oracle_response.rendered_system_prompt == "system"
        assert oracle_response.rendered_user_message == [
            {"type": "text", "text": "Hello"}
        ]

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_ask_oracle_step_does_not_capture_when_disabled(
        self, mock_chat_completion, mock_agent, mock_stack
    ):
        """With capture disabled (default), the rendered_* fields stay None."""
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": "Hello, world!",
            "tool_call": None,
        }
        assert mock_agent.session.environment.capture_rendered_prompts is False

        ask_oracle = AskOracle(
            stack=mock_stack,
            prompt=Prompt(type="text", text="Hello"),
            template_inputs={},
        )
        ask_oracle.step()

        oracle_response = mock_stack.interactions[0]
        assert isinstance(oracle_response, OracleResponse)
        assert oracle_response.rendered_system_prompt is None
        assert oracle_response.rendered_user_message is None
```

Note: `mock_agent.session.environment` is the `Environment` created by the `mock_session` fixture; `capture_rendered_prompts` defaults to `False` there (env var not set in the test process). `Prompt`, `AskOracle`, `OracleResponse`, `patch` are already imported in `tests/test_interaction.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_interaction.py -q -k "captures_rendered_prompt or does_not_capture"`
Expected: the "enabled" test FAILs with `AssertionError` (`rendered_system_prompt` is `None`, not `"system"`); the "disabled" test PASSES already (fields default to `None`). That's expected — only the new behaviour needs implementing.

- [ ] **Step 3: Implement the capture in `step()`**

Replace the body of `AskOracle.step()` in `src/gimle/hugin/interaction/ask_oracle.py` (from the line after the docstring through the `return True`) with:

```python
        from gimle.hugin.interaction.oracle_response import OracleResponse
        from gimle.hugin.llm.completion import chat_completion

        if self.prompt is None:
            raise ValueError("AskOracle prompt is None")
        if self.template_inputs is None:
            raise ValueError("AskOracle template inputs is None")

        tools = self.stack.get_tools(branch=self.branch)
        interaction_messages = self.stack.render_stack_context(
            branch=self.branch
        )

        logger.debug(f"Number of interactions: {len(interaction_messages)}")
        logger.debug(self.stack.pretty_rendered_context(branch=self.branch))
        from gimle.hugin.llm.prompt.renderer import PromptRenderer

        renderer = PromptRenderer(self.stack.agent, branch=self.branch)
        system_prompt = renderer.render_system_prompt(self.template_inputs)
        llm_model = self.stack.agent.config.llm_model

        rendered_system_prompt = None
        rendered_user_message = None
        if self.stack.agent.environment.capture_rendered_prompts:
            from gimle.hugin.llm.prompt.message import render_user_message

            rendered_system_prompt = system_prompt
            rendered_user_message = render_user_message(self, reduced=False)

        assistant_response = chat_completion(
            system_prompt=system_prompt,
            messages=interaction_messages,
            tools=tools,
            llm_model=llm_model,
        )
        logger.debug(f"Assistant response: {assistant_response}")
        self.stack.add_interaction(
            OracleResponse(
                stack=self.stack,
                branch=self.branch,
                response=assistant_response,
                rendered_system_prompt=rendered_system_prompt,
                rendered_user_message=rendered_user_message,
            )
        )
        return True
```

(The `render_user_message` import is local to `step()` to avoid the import cycle — `gimle.hugin.llm.prompt.message` imports `AskOracle`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_interaction.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gimle/hugin/interaction/ask_oracle.py tests/test_interaction.py
git commit -m "Capture rendered system/user prompt onto OracleResponse when enabled"
```

---

## Task 4: End-to-end regression test (capture would have caught #42)

**Files:**
- Modify: `tests/test_prompt.py` (the `class TestSystemPromptReachesModel` added in PR #42)

- [ ] **Step 1: Write the test**

In `tests/test_prompt.py`, add to the imports:

```python
from gimle.hugin.interaction.oracle_response import OracleResponse
```

Add this method to `class TestSystemPromptReachesModel`:

```python
    def test_bare_system_template_captured_in_oracle_response(self, mock_session):
        """With capture on, the OracleResponse records the rendered system body.

        This is the check that would have surfaced the #42 silent failure:
        before that fix the recorded value would have been the literal name
        'e2e_system'.
        """
        mock_session.environment.capture_rendered_prompts = True
        mock_session.environment.template_registry.register(
            Template(
                name="e2e_system",
                template="You are the e2e system for {{ agent.config.name }}.",
            )
        )
        config = Config(
            name="e2e-agent",
            description="agent under e2e test",
            system_template="e2e_system",
            tools=[],
        )
        task = Task(
            name="e2e_task",
            description="task under e2e test",
            prompt="Do the e2e thing.",
            tools=[],
        )
        mock_session.create_agent_from_task(config, task)
        agent = mock_session.agents[0]

        def fake_chat_completion(system_prompt, messages, tools, llm_model):
            return {
                "role": "assistant",
                "content": "ok",
                "tool_call": None,
                "tool_call_id": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "extra_content": [],
            }

        with patch(
            "gimle.hugin.llm.completion.chat_completion",
            side_effect=fake_chat_completion,
        ):
            for _ in range(5):
                if any(
                    isinstance(i, OracleResponse) for i in agent.stack.interactions
                ):
                    break
                if not agent.step():
                    break

        oracle_responses = [
            i for i in agent.stack.interactions if isinstance(i, OracleResponse)
        ]
        assert oracle_responses, "no OracleResponse was created"
        assert (
            oracle_responses[0].rendered_system_prompt
            == "You are the e2e system for e2e-agent."
        )
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_prompt.py -q -k captured_in_oracle_response`
Expected: PASS (Tasks 1-3 are already done, so the field is populated). If it fails, the prior tasks are incomplete — fix those, do not weaken this test.

- [ ] **Step 3: Run the whole prompt test file**

Run: `uv run pytest tests/test_prompt.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_prompt.py
git commit -m "Add e2e regression test: rendered system prompt recorded on OracleResponse"
```

---

## Task 5: Surface the rendered prompt in the web monitor

**Files:**
- Modify: `src/gimle/hugin/ui/static/js/monitor.js` (the `OracleResponse` block inside `renderInteractionTypeDetails`, ≈ lines 1912-1940)

No automated test (the repo has no JS test harness); verification is manual. The data already reaches the frontend: the `/api/interaction` lazy-load returns the full persisted interaction `data`, which now includes `rendered_system_prompt` / `rendered_user_message`, and `loadInteractionDetail` merges that `data` into `interactionsData[id]`.

- [ ] **Step 1: Add the display**

In `src/gimle/hugin/ui/static/js/monitor.js`, inside `renderInteractionTypeDetails`, in the `if (interaction.type === 'OracleResponse') { ... }` block, immediately AFTER the closing of the `if (interaction.response) { ... }` section and BEFORE the `html += '</div>';` that closes the OracleResponse box, insert:

```javascript
        if (interaction.rendered_system_prompt) {
            html += `<div style="margin-top: 8px;">
                <strong>System prompt (rendered):</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(interaction.rendered_system_prompt)}</pre>
            </div>`;
        }
        if (interaction.rendered_user_message) {
            const userMsgStr = typeof interaction.rendered_user_message === 'string'
                ? interaction.rendered_user_message
                : JSON.stringify(interaction.rendered_user_message, null, 2);
            html += `<div style="margin-top: 8px;">
                <strong>User message (rendered):</strong>
                <pre class="detail-code" style="margin-top: 4px; max-height: 200px; overflow-y: auto;">${escapeHtml(userMsgStr)}</pre>
            </div>`;
        }
```

(Match the surrounding indentation in the file. The `escapeHtml`, `detail-code` class, and `<pre>` styling are exactly what the adjacent `response.content` / `template_inputs` rendering already uses.)

- [ ] **Step 2: Manual verification**

```bash
HUGIN_CAPTURE_RENDERED_PROMPTS=1 uv run hugin run --task hello_world --task-path examples/basic_agent --max-steps 3
uv run hugin monitor --storage-path ./storage --no-browser --port 8765
```

Open `http://localhost:8765`, select the agent, click the `OracleResponse` interaction in the timeline. Expected: the detail panel shows "System prompt (rendered): You are a helpful AI assistant. ..." and "User message (rendered): [ ... ]". Stop the monitor with Ctrl-C. (If the run fails at the LLM call for lack of an API key, that's fine — the `OracleResponse` is still created and the captured fields are still recorded; verify via the monitor or via the interaction JSON under `./storage/interactions/`.)

- [ ] **Step 3: Commit**

```bash
git add src/gimle/hugin/ui/static/js/monitor.js
git commit -m "Show rendered system/user prompt in the monitor OracleResponse detail"
```

---

## Task 6: Document the env var and final verification

**Files:**
- Modify: `CLAUDE.md` ("### Monitoring & Debugging" section, ≈ lines 213-229)

- [ ] **Step 1: Add the doc note**

In `CLAUDE.md`, at the end of the "### Monitoring & Debugging" section (after the "Interactive TUI ..." block, before "## Architecture Overview"), add:

```markdown

### Capturing rendered prompts

Set `HUGIN_CAPTURE_RENDERED_PROMPTS=1` to have each `OracleResponse` record
the system prompt and the user message that were actually rendered and sent to
the LLM for that turn (`rendered_system_prompt` / `rendered_user_message`).
Off by default. Useful for diagnosing prompt-rendering issues (e.g. a template
reference that didn't resolve) — the values show up in the `OracleResponse`
detail in `hugin monitor` and `hugin interactive`, and in the persisted
interaction JSON under `storage/interactions/`.

```bash
HUGIN_CAPTURE_RENDERED_PROMPTS=1 uv run hugin run --task hello_world --task-path examples/basic_agent
```
```

- [ ] **Step 2: Run pre-commit**

Run: `uv run pre-commit run --all-files`
Expected: `black`, `isort`, `flake8`, `check-yaml`, `trailing-whitespace`, `end-of-file-fixer`, `detect-secrets` PASS. The `mypy` hook FAILs with an internal mypy error inside `openai/_client.py` — this is **pre-existing on `main`** and unrelated; ignore it. If `black`/`isort` modified any files, re-stage and re-run until clean.

- [ ] **Step 3: Confirm types on the changed source files**

Run: `uv run mypy src/gimle/hugin/agent/environment.py src/gimle/hugin/interaction/oracle_response.py src/gimle/hugin/interaction/ask_oracle.py`
Expected: `Success: no issues found in 3 source files`.

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests PASS (was 605 passed / 12 skipped on `main` before this work — expect ~+9 more passing).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "Document HUGIN_CAPTURE_RENDERED_PROMPTS"
```

- [ ] **Step 6: Push and open the PR**

```bash
git push -u origin task/018_persist_rendered_prompt
gh pr create --title "Persist the rendered prompt sent to the LLM (opt-in)" --body "$(cat <<'EOF'
## Summary
Optionally capture, on each `OracleResponse`, the system prompt and the user message that were actually rendered and sent to the LLM for that turn — so prompt-rendering bugs (like the bare-template-name silent failure fixed in #42) are visible in the saved session without monkey-patching `chat_completion`. Off by default. Implements task 018.

## Changes
- `Environment.capture_rendered_prompts` flag (new `__init__`/`load` param), defaulting from `HUGIN_CAPTURE_RENDERED_PROMPTS` (truthy: `1/true/yes/on`).
- `OracleResponse` gains `rendered_system_prompt: str | None` and `rendered_user_message: list[dict] | None` — serialize/deserialize for free; old sessions get `None`.
- `AskOracle.step()` records both onto the `OracleResponse` it creates, only when the flag is on.
- Web monitor (`monitor.js`): shows the two fields in the `OracleResponse` detail panel. The curses TUI already shows them via its generic field formatter.
- `CLAUDE.md`: documents the env var.

## Testing
- New unit tests: the `Environment` flag / env-var parsing; `OracleResponse` round-trip + back-compat (old dict → `None`); `AskOracle.step()` capture on/off.
- Extended the `TestSystemPromptReachesModel` e2e test: with capture on, the `OracleResponse` records the rendered system body (pre-#42 it would have recorded the literal name).
- `uv run pytest -q` green; pre-commit green except the pre-existing mypy/openai internal error; `mypy` on the changed source files clean.
- Manually verified the rendered prompts appear in `hugin monitor`'s `OracleResponse` detail with `HUGIN_CAPTURE_RENDERED_PROMPTS=1`.

## Out of scope (see tasks/open/018-persist-rendered-prompt/)
Full-conversation-context capture; per-`Config` toggle; UI replay/diff.
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** data fields (Task 2), env-var flag threaded through `Environment` + `load` (Task 1), capture in `AskOracle.step()` only when enabled (Task 3), web monitor surfacing (Task 5), TUI — covered by its existing generic formatter, noted in Task 5 (no code change), `CLAUDE.md` doc (Task 6), serialization round-trip + back-compat tests (Task 2), capture on/off tests (Task 3), e2e regression test (Task 4). All spec "Success criteria" map to tasks.
- **Out-of-scope items** from the spec (full-context capture, `Config` toggle, UI replay/diff) are not implemented — intentional.
- **Type consistency:** field names `rendered_system_prompt` (str|None) and `rendered_user_message` (list[dict]|None) are used identically in `OracleResponse`, `AskOracle.step()`, the tests, and `monitor.js`. The flag is `Environment.capture_rendered_prompts` (bool) everywhere; the env var is `HUGIN_CAPTURE_RENDERED_PROMPTS` everywhere.
- **No placeholders:** every code step has the full code; commands have expected output.

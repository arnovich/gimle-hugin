"""Integration tests for artifacts example."""

import shutil
import tempfile
from unittest.mock import patch

import pytest

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.storage.local import LocalStorage


@pytest.fixture(autouse=True)
def _mock_llm_for_artifacts_example():
    """Prevent live LLM calls in the artifacts example tests.

    These tests validate the artifact/tool plumbing and storage integration.
    They should run offline and deterministically.
    """
    state = {"last_query": ""}

    def _last_user_text(messages):
        for m in reversed(messages):
            if m.get("role") != "user":
                continue
            content = m.get("content")
            if (
                isinstance(content, list)
                and content
                and isinstance(content[0], dict)
                and content[0].get("type") == "text"
            ):
                return str(content[0].get("text") or "")
        return ""

    def _last_tool_result(messages):
        """Return (tool_name, lines_dict) for the last tool_result user message."""
        for m in reversed(messages):
            if m.get("role") != "user":
                continue
            content = m.get("content")
            if not (
                isinstance(content, list)
                and content
                and isinstance(content[0], dict)
                and content[0].get("type") == "tool_result"
            ):
                continue
            tool_name = content[0].get("name")
            lines = content[0].get("content") or []
            kv = {}
            for item in lines:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text = str(item.get("text") or "")
                if ": " in text:
                    k, v = text.split(": ", 1)
                    kv[k.strip()] = v.strip()
            return tool_name, kv
        return None, {}

    def _extract_after(label, text):
        # Very small helper for lines like "Topic: X" / "Query: Y"
        marker = f"{label}:"
        for line in text.splitlines():
            if line.strip().startswith(marker):
                return line.split(":", 1)[1].strip()
        return ""

    def fake_chat_completion(system_prompt, messages, tools, llm_model):
        last_user = _last_user_text(messages)
        last_tool, kv = _last_tool_result(messages)

        # Drive most of the flow off the last tool result, since after a tool call
        # the "user" message is a tool_result (not plain text).
        if last_tool == "query_artifacts":
            query = kv.get("query") or state.get("last_query") or ""
            found = (kv.get("found") or "").lower() == "true"
            results_text = kv.get("results", "")
            if found and "artifact_id" in results_text:
                import re

                m = re.search(r"artifact_id'?:\s*'([^']+)'", results_text)
                if m:
                    return {
                        "role": "assistant",
                        "content": {"artifact_id": m.group(1)},
                        "tool_call": "get_artifact_content",
                        "tool_call_id": "get_1",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "extra_content": None,
                    }

            insight = (
                f"# Research: {query or 'Topic'}\n\n"
                f"Key points about {query or 'the topic'}.\n"
            )
            return {
                "role": "assistant",
                "content": {"insight": insight, "format": "markdown"},
                "tool_call": "save_insight",
                "tool_call_id": "save_1",
                "input_tokens": 1,
                "output_tokens": 1,
                "extra_content": None,
            }

        if last_tool == "get_artifact_content":
            artifact_id = kv.get("artifact_id") or ""
            insight = (
                "# Updated Research\n\n" f"Built on artifact {artifact_id}.\n"
            )
            return {
                "role": "assistant",
                "content": {"insight": insight, "format": "markdown"},
                "tool_call": "save_insight",
                "tool_call_id": "save_2",
                "input_tokens": 1,
                "output_tokens": 1,
                "extra_content": None,
            }

        if last_tool == "save_insight":
            return {
                "role": "assistant",
                "content": "Finished with a summary.",
                "tool_call": None,
                "tool_call_id": None,
                "input_tokens": 1,
                "output_tokens": 1,
                "extra_content": None,
            }

        # research_topic workflow:
        if (
            "Research the following topic and save your findings as artifacts"
            in last_user
        ):
            topic = (
                _extract_after("Topic", last_user) or "Artificial Intelligence"
            )
            state["last_query"] = topic
            return {
                "role": "assistant",
                "content": {"query": topic, "limit": 5},
                "tool_call": "query_artifacts",
                "tool_call_id": "query_1",
                "input_tokens": 1,
                "output_tokens": 1,
                "extra_content": None,
            }

        # continue_research workflow:
        if "Continue our research based on previous findings." in last_user:
            query = _extract_after("Query", last_user) or "AI safety"
            state["last_query"] = query
            return {
                "role": "assistant",
                "content": {"query": query, "limit": 5},
                "tool_call": "query_artifacts",
                "tool_call_id": "query_2",
                "input_tokens": 1,
                "output_tokens": 1,
                "extra_content": None,
            }

        # Default: end the branch (no tool call).
        return {
            "role": "assistant",
            "content": "Done.",
            "tool_call": None,
            "tool_call_id": None,
            "input_tokens": 1,
            "output_tokens": 1,
            "extra_content": None,
        }

    with patch(
        "gimle.hugin.llm.completion.chat_completion",
        side_effect=fake_chat_completion,
    ):
        yield


class TestArtifactsExample:
    """Test artifacts example demonstrates all three tools."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for test."""
        temp_dir = tempfile.mkdtemp()
        storage = LocalStorage(base_path=temp_dir)
        yield storage
        shutil.rmtree(temp_dir)

    def test_research_topic_saves_artifact(self, temp_storage):
        """Test that research_topic task saves an artifact."""
        env = Environment.load("examples/artifacts", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("research_assistant")
        task = env.task_registry.get("research_topic")
        agent = session.create_agent_from_task(config, task)

        for _ in range(20):
            if not agent.step():
                break
        # Persist artifacts created during the run (Storage saves artifacts when
        # interactions are persisted via save_session/save_agent).
        temp_storage.save_session(session)

        artifacts = temp_storage.list_artifacts()
        assert len(artifacts) > 0, "No artifacts were saved"

    def test_continue_research_queries_artifacts(self, temp_storage):
        """Test that continue_research queries and retrieves artifacts."""
        env = Environment.load("examples/artifacts", storage=temp_storage)
        session1 = Session(environment=env)

        config = env.config_registry.get("research_assistant")
        task1 = env.task_registry.get("research_topic")
        agent1 = session1.create_agent_from_task(config, task1)

        for _ in range(20):
            if not agent1.step():
                break
        temp_storage.save_session(session1)

        artifacts_after_first = temp_storage.list_artifacts()
        assert len(artifacts_after_first) > 0

        env2 = Environment.load("examples/artifacts", storage=temp_storage)
        session2 = Session(environment=env2)

        task2 = env2.task_registry.get("continue_research")
        agent2 = session2.create_agent_from_task(config, task2)

        for _ in range(20):
            if not agent2.step():
                break
        temp_storage.save_session(session2)

        artifacts_after_second = temp_storage.list_artifacts()
        assert len(artifacts_after_second) > len(artifacts_after_first)

    def test_query_engine_finds_artifacts(self, temp_storage):
        """Test query engine can find saved artifacts."""
        env = Environment.load("examples/artifacts", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("research_assistant")
        task = env.task_registry.get("research_topic")
        agent = session.create_agent_from_task(config, task)

        for _ in range(20):
            if not agent.step():
                break
        temp_storage.save_session(session)

        query_engine = env.query_engine
        results = query_engine.query("Artificial Intelligence", limit=5)

        assert len(results) > 0, "Query should find saved artifacts"
        assert results[0].artifact_type == "Text"

    def test_artifact_content_retrieval(self, temp_storage):
        """Test full artifact content can be retrieved."""
        env = Environment.load("examples/artifacts", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("research_assistant")
        task = env.task_registry.get("research_topic")
        agent = session.create_agent_from_task(config, task)

        for _ in range(20):
            if not agent.step():
                break
        temp_storage.save_session(session)

        artifacts = temp_storage.list_artifacts()
        assert len(artifacts) > 0

        artifact_id = artifacts[0]

        query_engine = env.query_engine
        content = query_engine.get_artifact_content(artifact_id)

        assert content is not None
        assert len(content) > 0
        assert isinstance(content, str)

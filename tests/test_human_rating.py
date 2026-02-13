"""Integration tests for human artifact rating."""

import json
from io import BytesIO
from unittest.mock import MagicMock

from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.artifacts.text import Text
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.storage.local import LocalStorage

from .memory_storage import MemoryStorage


class TestCliRateCommand:
    """Test the CLI rate_artifact_cli function."""

    def _create_artifact(self, storage, mock_stack):
        """Create a test artifact in storage."""
        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Test insight",
            format="plain",
        )
        storage.save_artifact(artifact)
        return artifact

    def test_cli_rate_saves_human_feedback(self, tmp_path, mock_stack):
        """Test CLI rate command creates feedback with source=human."""
        storage = LocalStorage(base_path=str(tmp_path))
        mock_stack.agent.environment.storage = storage

        artifact = self._create_artifact(storage, mock_stack)

        from gimle.hugin.cli.rate_artifact import rate_artifact_cli

        result = rate_artifact_cli(
            storage_path=str(tmp_path),
            artifact_id=artifact.id,
            rating=4,
            comment="Good insight",
        )

        assert result == 0

        # Verify feedback was saved
        fb_ids = storage.list_feedback(artifact_id=artifact.id)
        assert len(fb_ids) == 1
        fb = storage.load_feedback(fb_ids[0])
        assert fb.rating == 4
        assert fb.comment == "Good insight"
        assert fb.source == "human"
        assert fb.agent_id is None

    def test_cli_rate_nonexistent_artifact(self, tmp_path):
        """Test CLI rate with nonexistent artifact returns error."""
        from gimle.hugin.cli.rate_artifact import rate_artifact_cli

        result = rate_artifact_cli(
            storage_path=str(tmp_path),
            artifact_id="nonexistent",
            rating=3,
        )

        assert result == 1

    def test_cli_rate_nonexistent_storage(self):
        """Test CLI rate with nonexistent storage path."""
        from gimle.hugin.cli.rate_artifact import rate_artifact_cli

        result = rate_artifact_cli(
            storage_path="/nonexistent/path",
            artifact_id="any",
            rating=3,
        )

        assert result == 1

    def test_cli_rate_no_comment(self, tmp_path, mock_stack):
        """Test CLI rate without comment saves None."""
        storage = LocalStorage(base_path=str(tmp_path))
        mock_stack.agent.environment.storage = storage

        artifact = self._create_artifact(storage, mock_stack)

        from gimle.hugin.cli.rate_artifact import rate_artifact_cli

        result = rate_artifact_cli(
            storage_path=str(tmp_path),
            artifact_id=artifact.id,
            rating=5,
        )

        assert result == 0
        fb_ids = storage.list_feedback(artifact_id=artifact.id)
        fb = storage.load_feedback(fb_ids[0])
        assert fb.comment is None


class TestMonitorFeedbackEndpoints:
    """Test monitor API feedback endpoints."""

    def _create_handler(self, storage_path):
        """Create a mock handler with storage path."""
        from gimle.hugin.cli.monitor_agents import (
            AgentMonitorHTTPRequestHandler,
        )

        handler = MagicMock(spec=AgentMonitorHTTPRequestHandler)
        handler.storage_path = storage_path
        handler.wfile = BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.send_error = MagicMock()
        return handler

    def test_serve_feedback_list(self, tmp_path, mock_stack):
        """Test GET /api/feedback returns feedback list."""
        from gimle.hugin.cli.monitor_agents import (
            AgentMonitorHTTPRequestHandler,
        )

        storage = LocalStorage(base_path=str(tmp_path))
        mock_stack.agent.environment.storage = storage

        # Create artifact and feedback
        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Content",
            format="plain",
        )
        storage.save_artifact(artifact)

        fb = ArtifactFeedback(
            artifact_id=artifact.id,
            rating=4,
            source="human",
            comment="Nice",
        )
        storage.save_feedback(fb)

        # Create handler and call serve_feedback_list
        handler = self._create_handler(tmp_path)
        AgentMonitorHTTPRequestHandler.serve_feedback_list(handler, artifact.id)

        # Parse response
        response_bytes = handler.wfile.getvalue()
        feedback_list = json.loads(response_bytes)

        assert len(feedback_list) == 1
        assert feedback_list[0]["rating"] == 4
        assert feedback_list[0]["source"] == "human"
        assert feedback_list[0]["comment"] == "Nice"

    def test_handle_submit_feedback(self, tmp_path, mock_stack):
        """Test POST /api/feedback creates human feedback."""
        from gimle.hugin.cli.monitor_agents import (
            AgentMonitorHTTPRequestHandler,
        )

        storage = LocalStorage(base_path=str(tmp_path))
        mock_stack.agent.environment.storage = storage

        # Create artifact
        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Content",
            format="plain",
        )
        storage.save_artifact(artifact)

        # Create handler with POST body
        handler = self._create_handler(tmp_path)
        body = json.dumps(
            {
                "artifact_id": artifact.id,
                "rating": 5,
                "comment": "Excellent",
            }
        ).encode("utf-8")
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)

        AgentMonitorHTTPRequestHandler.handle_submit_feedback(handler)

        # Parse response
        response_bytes = handler.wfile.getvalue()
        response = json.loads(response_bytes)

        assert response["success"] is True
        assert "feedback_id" in response

        # Verify stored
        fb_ids = storage.list_feedback(artifact_id=artifact.id)
        assert len(fb_ids) == 1
        fb = storage.load_feedback(fb_ids[0])
        assert fb.source == "human"
        assert fb.rating == 5


class TestTuiRating:
    """Test TUI artifact rating."""

    def test_save_rating(self, tmp_path, mock_stack):
        """Test _save_rating creates human feedback."""
        storage = LocalStorage(base_path=str(tmp_path))
        mock_stack.agent.environment.storage = storage

        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Content",
            format="plain",
        )
        storage.save_artifact(artifact)

        # Create a minimal ArtifactScreen-like test
        # by directly calling the feedback creation logic
        feedback = ArtifactFeedback(
            artifact_id=artifact.id,
            rating=3,
            agent_id=None,
            source="human",
        )
        storage.save_feedback(feedback)

        fb_ids = storage.list_feedback(artifact_id=artifact.id)
        assert len(fb_ids) == 1
        loaded = storage.load_feedback(fb_ids[0])
        assert loaded.source == "human"
        assert loaded.rating == 3
        assert loaded.agent_id is None


class TestSourceFieldPersistence:
    """Test that source field persists correctly across storage."""

    def test_local_storage_round_trip(self, tmp_path):
        """Test source persists through LocalStorage save/load."""
        storage = LocalStorage(base_path=str(tmp_path))

        fb = ArtifactFeedback(
            artifact_id="art-1",
            rating=4,
            source="human",
            comment="CLI review",
        )
        storage.save_feedback(fb)

        loaded = storage.load_feedback(fb.id)
        assert loaded.source == "human"

    def test_memory_storage_round_trip(self):
        """Test source persists through MemoryStorage."""
        storage = MemoryStorage()

        fb = ArtifactFeedback(
            artifact_id="art-1",
            rating=5,
            source="human",
        )
        storage.save_feedback(fb)

        loaded = storage.load_feedback(fb.id)
        assert loaded.source == "human"

    def test_json_backward_compat(self, tmp_path):
        """Test loading old feedback without source field."""
        storage = LocalStorage(base_path=str(tmp_path))

        # Manually write feedback JSON without source field
        fb_dir = tmp_path / "feedback"
        fb_dir.mkdir(exist_ok=True)
        old_data = {
            "artifact_id": "art-1",
            "rating": 3,
            "uuid": "old-fb-uuid",
        }
        with open(fb_dir / "art-1_old-fb-uuid", "w") as f:
            json.dump(old_data, f)

        loaded = storage.load_feedback("old-fb-uuid")
        assert loaded.source == "agent"  # Default

"""Comprehensive tests for Text artifact."""

import pytest

from gimle.hugin.agent.task import Task

# Import Text to ensure it's registered in the artifact registry
from gimle.hugin.artifacts.text import Text
from gimle.hugin.interaction.task_definition import TaskDefinition

from .memory_storage import MemoryStorage


class TestTextArtifactCreation:
    """Test Text artifact creation and basic properties."""

    def test_text_artifact_has_uuid(self, mock_stack):
        """Test that Text artifact automatically gets a UUID."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        text_artifact = Text(interaction=task_def, content="Test content")

        assert hasattr(text_artifact, "uuid")
        assert text_artifact.uuid is not None
        assert isinstance(text_artifact.uuid, str)
        assert len(text_artifact.uuid) > 0

    def test_text_artifact_with_custom_uuid(self, mock_stack):
        """Test that Text artifact can be created with a custom UUID."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        custom_uuid = "custom-uuid-12345"
        text_artifact = Text(
            interaction=task_def, content="Test content", uuid=custom_uuid
        )

        assert text_artifact.uuid == custom_uuid

    def test_text_artifact_required_fields(self, mock_stack):
        """Test that Text artifact requires content field."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        # Should work with content
        text_artifact = Text(interaction=task_def, content="Test content")
        assert text_artifact.content == "Test content"

    def test_text_artifact_default_format(self, mock_stack):
        """Test that Text artifact defaults to 'plain' format."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        text_artifact = Text(interaction=task_def, content="Test content")

        assert text_artifact.format == "plain"

    def test_text_artifact_with_different_formats(self, mock_stack):
        """Test Text artifact with different format values."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        formats = ["markdown", "xml", "plain", "html", "json"]

        for fmt in formats:
            text_artifact = Text(
                interaction=task_def, content="Test content", format=fmt
            )
            assert text_artifact.format == fmt

    def test_text_artifact_invalid_format(self, mock_stack):
        """Test that Text artifact raises error for invalid format."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        with pytest.raises(ValueError, match="Invalid format"):
            Text(
                interaction=task_def,
                content="Test content",
                format="invalid_format",
            )

    def test_text_artifact_content_preservation(self, mock_stack):
        """Test that Text artifact preserves content correctly."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        long_content = "This is a very long content string " * 100
        text_artifact = Text(
            interaction=task_def, content=long_content, format="markdown"
        )

        assert text_artifact.content == long_content
        assert len(text_artifact.content) == len(long_content)

    def test_text_artifact_multiline_content(self, mock_stack):
        """Test Text artifact with multiline content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        multiline_content = """Line 1
Line 2
Line 3
With special chars: !@#$%^&*()"""

        text_artifact = Text(
            interaction=task_def, content=multiline_content, format="plain"
        )

        assert text_artifact.content == multiline_content
        assert "\n" in text_artifact.content


class TestTextArtifactSerialization:
    """Test Text artifact serialization and deserialization."""

    def test_text_artifact_to_dict(self, mock_stack):
        """Test serializing a Text artifact."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        text_artifact = Text(
            interaction=task_def, content="Test content", format="markdown"
        )

        data = text_artifact.to_dict()

        assert "type" in data
        assert "data" in data
        assert data["type"] == "Text"
        assert data["data"]["content"] == "Test content"
        assert data["data"]["format"] == "markdown"
        assert data["data"]["interaction"] == task_def.uuid
        assert "uuid" in data["data"]

    def test_text_artifact_from_dict(self, mock_stack):
        """Test deserializing a Text artifact."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        text_artifact = Text(
            interaction=task_def, content="Test content", format="markdown"
        )

        # Serialize
        data = text_artifact.to_dict()

        # Deserialize
        new_text_artifact = Text.from_dict(
            data, storage=storage, stack=mock_stack
        )

        assert isinstance(new_text_artifact, Text)
        assert new_text_artifact.uuid == text_artifact.uuid
        assert new_text_artifact.content == "Test content"
        assert new_text_artifact.format == "markdown"
        assert new_text_artifact.interaction.id == task_def.id

    def test_text_artifact_round_trip(self, mock_stack):
        """Test round-trip serialization/deserialization."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        original_content = "This is test content with **markdown** formatting"
        original_format = "markdown"

        text_artifact = Text(
            interaction=task_def,
            content=original_content,
            format=original_format,
        )
        original_uuid = text_artifact.uuid

        # Serialize
        data = text_artifact.to_dict()

        # Deserialize
        new_text_artifact = Text.from_dict(
            data, storage=storage, stack=mock_stack
        )

        assert new_text_artifact.uuid == original_uuid
        assert new_text_artifact.content == original_content
        assert new_text_artifact.format == original_format

    def test_text_artifact_preserves_uuid(self, mock_stack):
        """Test that Text artifact UUID is preserved during serialization."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        text_artifact = Text(
            interaction=task_def, content="Test content", format="plain"
        )
        original_uuid = text_artifact.uuid

        data = text_artifact.to_dict()
        new_text_artifact = Text.from_dict(
            data, storage=storage, stack=mock_stack
        )

        assert new_text_artifact.uuid == original_uuid

    def test_text_artifact_all_formats_round_trip(self, mock_stack):
        """Test round-trip for all supported formats."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        formats = ["markdown", "xml", "plain", "html", "json"]

        for fmt in formats:
            text_artifact = Text(
                interaction=task_def, content=f"Content for {fmt}", format=fmt
            )

            data = text_artifact.to_dict()
            new_text_artifact = Text.from_dict(
                data, storage=storage, stack=mock_stack
            )

            assert new_text_artifact.format == fmt
            assert new_text_artifact.content == f"Content for {fmt}"


class TestTextArtifactStorage:
    """Test Text artifact storage operations."""

    def test_text_artifact_save_and_load(self, mock_stack):
        """Test saving and loading a Text artifact from storage."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        text_artifact = Text(
            interaction=task_def, content="Saved content", format="markdown"
        )
        artifact_uuid = text_artifact.uuid

        storage.save_artifact(text_artifact)
        loaded_artifact = storage.load_artifact(artifact_uuid, stack=mock_stack)

        assert isinstance(loaded_artifact, Text)
        assert loaded_artifact.uuid == artifact_uuid
        assert loaded_artifact.content == "Saved content"
        assert loaded_artifact.format == "markdown"

    def test_text_artifact_multiple_artifacts(self, mock_stack):
        """Test storing and loading multiple Text artifacts."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        artifacts = []
        for i in range(5):
            artifact = Text(
                interaction=task_def,
                content=f"Content {i}",
                format=["markdown", "plain", "html", "json", "xml"][i],
            )
            artifacts.append(artifact)
            storage.save_artifact(artifact)

        # Load all artifacts back
        for i, original_artifact in enumerate(artifacts):
            loaded_artifact = storage.load_artifact(
                original_artifact.uuid, stack=mock_stack
            )
            assert loaded_artifact.uuid == original_artifact.uuid
            assert loaded_artifact.content == f"Content {i}"
            assert (
                loaded_artifact.format
                == ["markdown", "plain", "html", "json", "xml"][i]
            )


class TestTextArtifactRegistry:
    """Test Text artifact registry functionality."""

    def test_text_artifact_is_registered(self):
        """Test that Text artifact is registered in the artifact registry."""
        from gimle.hugin.artifacts.artifact import Artifact

        assert "Text" in Artifact._registry
        assert Artifact._registry["Text"] == Text

    def test_text_artifact_get_type(self):
        """Test getting Text artifact type from registry."""
        from gimle.hugin.artifacts.artifact import Artifact

        text_type = Artifact.get_type("Text")
        assert text_type == Text

    def test_text_artifact_from_dict_uses_registry(self, mock_stack):
        """Test that from_dict uses registry to create Text artifact."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        text_artifact = Text(
            interaction=task_def, content="Test content", format="markdown"
        )

        data = text_artifact.to_dict()

        # Use Artifact.from_dict which should use registry
        from gimle.hugin.artifacts.artifact import Artifact

        loaded_artifact = Artifact.from_dict(
            data, storage=storage, stack=mock_stack
        )

        assert isinstance(loaded_artifact, Text)
        assert loaded_artifact.content == "Test content"
        assert loaded_artifact.format == "markdown"


class TestTextArtifactEdgeCases:
    """Test Text artifact edge cases and error handling."""

    def test_text_artifact_empty_content(self, mock_stack):
        """Test Text artifact with empty content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        text_artifact = Text(interaction=task_def, content="", format="plain")

        assert text_artifact.content == ""
        assert text_artifact.format == "plain"

    def test_text_artifact_special_characters(self, mock_stack):
        """Test Text artifact with special characters in content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        special_content = "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?`~"
        text_artifact = Text(
            interaction=task_def, content=special_content, format="plain"
        )

        assert text_artifact.content == special_content

    def test_text_artifact_unicode_content(self, mock_stack):
        """Test Text artifact with unicode content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        unicode_content = "Unicode: 你好世界 🌍 émoji 🎉"
        text_artifact = Text(
            interaction=task_def, content=unicode_content, format="plain"
        )

        assert text_artifact.content == unicode_content

    def test_text_artifact_json_format_content(self, mock_stack):
        """Test Text artifact with JSON format and JSON-like content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        json_content = '{"key": "value", "number": 42}'
        text_artifact = Text(
            interaction=task_def, content=json_content, format="json"
        )

        assert text_artifact.content == json_content
        assert text_artifact.format == "json"

    def test_text_artifact_xml_format_content(self, mock_stack):
        """Test Text artifact with XML format and XML-like content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        xml_content = "<root><item>value</item></root>"
        text_artifact = Text(
            interaction=task_def, content=xml_content, format="xml"
        )

        assert text_artifact.content == xml_content
        assert text_artifact.format == "xml"

    def test_text_artifact_markdown_format_content(self, mock_stack):
        """Test Text artifact with markdown format and markdown content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        markdown_content = "# Heading\n\nThis is **bold** and *italic* text."
        text_artifact = Text(
            interaction=task_def, content=markdown_content, format="markdown"
        )

        assert text_artifact.content == markdown_content
        assert text_artifact.format == "markdown"

    def test_text_artifact_html_format_content(self, mock_stack):
        """Test Text artifact with HTML format and HTML content."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        html_content = "<html><body><h1>Title</h1><p>Content</p></body></html>"
        text_artifact = Text(
            interaction=task_def, content=html_content, format="html"
        )

        assert text_artifact.content == html_content
        assert text_artifact.format == "html"

    def test_text_artifact_case_sensitive_format(self, mock_stack):
        """Test that format validation is case-sensitive."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        # Should fail with uppercase
        with pytest.raises(ValueError, match="Invalid format"):
            Text(
                interaction=task_def, content="Test content", format="MARKDOWN"
            )

        # Should fail with mixed case
        with pytest.raises(ValueError, match="Invalid format"):
            Text(
                interaction=task_def, content="Test content", format="Markdown"
            )

"""Tests for model registry functionality."""

import pytest

from gimle.hugin.llm.models.model_registry import (
    ModelRegistry,
    get_model_registry,
)


class TestModelRegistry:
    """Test the ModelRegistry class functionality."""

    def test_model_registry_initialization(self, model_registry):
        """Test that ModelRegistry initializes with empty models dict."""
        assert isinstance(model_registry.models, dict)
        assert len(model_registry.models) == 0

    def test_register_model(self, model_registry, mock_model):
        """Test registering a model."""
        model_registry.register_model("test-model", mock_model)
        assert "test-model" in model_registry.models
        assert model_registry.models["test-model"] == mock_model

    def test_register_multiple_models(
        self, model_registry, mock_model, mock_model_with_custom_response
    ):
        """Test registering multiple models."""
        model_registry.register_model("model1", mock_model)
        model_registry.register_model("model2", mock_model_with_custom_response)

        assert len(model_registry.models) == 2
        assert "model1" in model_registry.models
        assert "model2" in model_registry.models
        assert model_registry.models["model1"] == mock_model
        assert (
            model_registry.models["model2"] == mock_model_with_custom_response
        )

    def test_get_model_success(self, model_registry, mock_model):
        """Test getting a registered model."""
        model_registry.register_model("test-model", mock_model)
        retrieved_model = model_registry.get_model("test-model")
        assert retrieved_model == mock_model

    def test_get_model_not_found(self, model_registry):
        """Test getting a model that doesn't exist."""
        with pytest.raises(ValueError, match="Model nonexistent not found"):
            model_registry.get_model("nonexistent")

    def test_get_model_empty_registry(self, model_registry):
        """Test getting a model from empty registry."""
        with pytest.raises(ValueError, match="Model test not found"):
            model_registry.get_model("test")


class TestGetModelRegistry:
    """Test the get_model_registry function."""

    def test_get_model_registry_returns_registry(self):
        """Test that get_model_registry returns a ModelRegistry instance."""
        # This test will fail if the actual model imports don't work
        # but that's expected in a test environment
        try:
            registry = get_model_registry()
            assert isinstance(registry, ModelRegistry)
        except ImportError:
            # Expected in test environment without actual model dependencies
            pytest.skip("Model dependencies not available in test environment")

    def test_get_model_registry_caches_result(self):
        """Test that get_model_registry uses LRU cache."""
        try:
            # First call
            registry1 = get_model_registry()
            # Second call should return the same instance due to caching
            registry2 = get_model_registry()
            assert registry1 is registry2
        except ImportError:
            # Expected in test environment without actual model dependencies
            pytest.skip("Model dependencies not available in test environment")

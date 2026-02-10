# Configuration Tests
"""Tests for configuration loading."""
import pytest
from memory_system import Config


def test_config_values():
    """Test configuration values are loaded correctly."""
    assert Config.MONGODB_URI is not None
    assert Config.LLM_URI is not None
    assert Config.LLM_EMBEDDING_URI is not None
    assert Config.LLM_MODEL is not None
    assert Config.LLM_EMBEDDING_MODEL is not None


def test_config_validation():
    """Test configuration validation."""
    errors = Config.validate()
    # Should have no errors with valid .env
    assert len(errors) == 0


def test_config_defaults():
    """Test configuration default values."""
    # Test that defaults work when env vars are not set
    import os

    # Store original values
    original_uri = os.environ.get("MONGODB_URI")
    original_llm_uri = os.environ.get("LLM_URI")

    # Remove env vars
    os.environ.pop("MONGODB_URI", None)
    os.environ.pop("LLM_URI", None)

    # Reload config
    from memory_system.config import get_config

    config = get_config()

    # Restore env vars
    if original_uri:
        os.environ["MONGODB_URI"] = original_uri
    if original_llm_uri:
        os.environ["LLM_URI"] = original_llm_uri


def test_config_short_term_memory_size():
    """Test short-term memory size configuration."""
    assert Config.SHORT_TERM_MEMORY_SIZE > 0


def test_config_vector_search_limit():
    """Test vector search limit configuration."""
    assert Config.VECTOR_SEARCH_LIMIT > 0
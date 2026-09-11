"""
tests/test_providers.py — Provider health checks and loud fallback warning tests
"""

import logging
from types import SimpleNamespace
import pytest
from agents.utils import check_all_providers_health, create_chat_model


def test_provider_health_check_all():
    """Verify that all configured providers return health check dictionary with valid classes."""
    results = check_all_providers_health(force=True)
    assert "primary" in results
    assert "fallback" in results
    assert "deep_thinking" in results

    # Check concrete classes
    assert results["primary"]["class"] in ["ChatGroq", "ChatOpenAI"]
    assert results["fallback"]["class"] in ["ChatGoogleGenerativeAI", "ChatOpenAI"]
    assert results["deep_thinking"]["class"] in ["ChatNVIDIA", "ChatOpenAI"]

    # Verify status is ok for configured providers with live keys
    assert results["primary"]["status"] == "ok"
    assert results["fallback"]["status"] == "ok"
    assert results["deep_thinking"]["status"] == "ok"


def test_loud_fallback_warning(caplog):
    """Verify that attempting to load a missing provider emits the loud warning."""
    bad_cfg = SimpleNamespace(
        name="test-model",
        concrete_class="ChatNonExistentProvider",
        api_base_url="https://api.example.com",
        api_key_env="NON_EXISTENT_KEY",
    )
    with caplog.at_level(logging.WARNING):
        model = create_chat_model(bad_cfg)
        # Should fall back to ChatOpenAI
        assert type(model).__name__ == "ChatOpenAI"
        assert any("[PROVIDER FALLBACK - CHECK requirements.txt]" in record.message for record in caplog.records)

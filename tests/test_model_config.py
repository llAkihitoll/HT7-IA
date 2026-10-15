"""El .env de ejemplo deja AGENT_MODEL vacío para usar el predeterminado."""

import pytest

from shared.model_config import NVIDIA_DEFAULT_MODEL, build_run_config


@pytest.mark.parametrize("configured, expected", [
    ("", NVIDIA_DEFAULT_MODEL),
    ("   ", NVIDIA_DEFAULT_MODEL),
    ("custom/model", "custom/model"),
])
def test_nvidia_model_default(monkeypatch, configured, expected):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("AGENT_MODEL", configured)
    assert build_run_config().model == expected

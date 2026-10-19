"""Each public handoff fixture crosses a fresh Loki environment boundary."""
import os

import pytest


@pytest.fixture(autouse=True)
def fresh_handoff_environment(monkeypatch):
    # Ambient activation must not make stale HERMES-only fixtures accidentally
    # bypass the public selector binding exercised by the actual scripts.
    for key in tuple(os.environ):
        if key.startswith("LOKI_") or key == "__LOKI_ENV_BOUND":
            monkeypatch.delenv(key, raising=False)

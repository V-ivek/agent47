import os
from uuid import uuid4

import pytest


@pytest.fixture
def base_url():
    return os.environ.get("PUNK_RECORDS_URL", "http://localhost:8000")


@pytest.fixture
def auth_headers():
    token = os.environ.get("PUNK_RECORDS_API_TOKEN", "test-token-123")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_event():
    return {
        "event_id": str(uuid4()),
        "schema_version": 1,
        "ts": "2026-02-07T22:00:00Z",
        "workspace_id": "ws-integration",
        "satellite_id": "sat-test",
        "trace_id": str(uuid4()),
        "type": "task.created",
        "severity": "low",
        "confidence": 0.9,
        "payload": {"title": "Integration test event"},
    }

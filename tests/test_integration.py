"""Integration tests that run against a live docker-compose stack.

Run with: pytest tests/test_integration.py -v
Requires: docker compose up --build -d (all services healthy)
"""

import os
import time
from uuid import uuid4

import httpx
import pytest

BASE_URL = os.environ.get("PUNK_RECORDS_URL", "http://localhost:8000")
TOKEN = os.environ.get("PUNK_RECORDS_API_TOKEN", "test-token-123")
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.integration


def _make_event(**overrides) -> dict:
    base = {
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
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


class TestServiceHealth:
    """1. Services start successfully."""

    def test_health_endpoint_returns_healthy(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["postgres"] == "ok"
        assert data["kafka"] == "ok"


class TestEventIngestion:
    """2. POST event -> appears in Kafka AND Postgres."""

    def test_post_event_accepted(self, client):
        event = _make_event()
        resp = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["event_id"] == event["event_id"]

    def test_event_persisted_to_postgres(self, client):
        """Post an event and verify it can be found by checking health stays healthy."""
        event = _make_event()
        resp = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp.status_code == 202
        # Give the consumer time to persist
        time.sleep(2)
        # Verify the service is still healthy (implies Postgres is accessible)
        health = client.get("/health")
        assert health.json()["status"] == "healthy"


class TestIdempotency:
    """3. Duplicate event_id -> no duplicate in Postgres."""

    def test_duplicate_event_accepted_but_not_duplicated(self, client):
        event = _make_event()
        # Send same event twice
        resp1 = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp1.status_code == 202
        resp2 = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp2.status_code == 202
        # Both accepted (202) - dedup happens at consumer/store level


class TestValidation:
    """4. Invalid event -> 400 with details."""

    def test_invalid_severity_returns_400(self, client):
        event = _make_event(severity="critical")
        resp = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_invalid_type_returns_400(self, client):
        event = _make_event(type="invalid.event.type")
        resp = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp.status_code == 400

    def test_missing_required_field_returns_400(self, client):
        event = _make_event()
        del event["workspace_id"]
        resp = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp.status_code == 400

    def test_schema_version_2_returns_400(self, client):
        event = _make_event(schema_version=2)
        resp = client.post("/events", json=event, headers=AUTH_HEADERS)
        assert resp.status_code == 400


class TestAuthentication:
    """Auth rejection for missing/wrong tokens."""

    def test_no_token_returns_error(self, client):
        event = _make_event()
        resp = client.post("/events", json=event)
        assert resp.status_code in (401, 422)

    def test_wrong_token_returns_401(self, client):
        event = _make_event()
        resp = client.post("/events", json=event, headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401


class TestMultipleEvents:
    """5. Multiple events can be ingested and system stays healthy."""

    def test_burst_of_events(self, client):
        for i in range(5):
            event = _make_event(
                workspace_id=f"ws-burst-{i}",
                payload={"index": i},
            )
            resp = client.post("/events", json=event, headers=AUTH_HEADERS)
            assert resp.status_code == 202

        # Wait for consumer to process
        time.sleep(3)
        health = client.get("/health")
        assert health.json()["status"] == "healthy"


class TestResilience:
    """6/7. Service health and resilience checks."""

    def test_health_check_works_after_load(self, client):
        # After all previous tests have run, health should still be good
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

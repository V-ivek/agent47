"""Unit tests for API endpoints using mocked dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from punk_records.api.events import router as events_router
from punk_records.api.health import router as health_router
from punk_records.config import Settings


def _create_test_app() -> FastAPI:
    """Create a test app with mocked state (no lifespan, no real services)."""
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(status_code=400, content={"detail": exc.errors()})

    app.include_router(events_router)
    app.include_router(health_router)

    app.state.settings = Settings(punk_records_api_token="test-token-123")
    app.state.producer = MagicMock()
    app.state.producer.send_event = AsyncMock()
    app.state.producer.check_health = AsyncMock(return_value=True)
    app.state.database = MagicMock()
    app.state.database.check_health = AsyncMock(return_value=True)

    return app


def _valid_event_body() -> dict:
    return {
        "event_id": str(uuid4()),
        "schema_version": 1,
        "ts": "2026-02-07T22:00:00Z",
        "workspace_id": "ws-test",
        "satellite_id": "sat-test",
        "trace_id": str(uuid4()),
        "type": "task.created",
        "severity": "low",
        "confidence": 0.9,
        "payload": {"title": "Hello Clawderpunk"},
    }


@pytest.fixture
def app():
    return _create_test_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestPostEvents:
    async def test_valid_event_returns_202(self, client):
        resp = await client.post(
            "/events",
            json=_valid_event_body(),
            headers={"Authorization": "Bearer test-token-123"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "event_id" in data

    async def test_missing_token_returns_error(self, client):
        resp = await client.post("/events", json=_valid_event_body())
        assert resp.status_code in (400, 422)  # 400 due to our 422→400 handler

    async def test_wrong_token_returns_401(self, client):
        resp = await client.post(
            "/events",
            json=_valid_event_body(),
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    async def test_invalid_event_returns_400(self, client):
        body = _valid_event_body()
        body["severity"] = "critical"  # invalid
        resp = await client.post(
            "/events",
            json=body,
            headers={"Authorization": "Bearer test-token-123"},
        )
        assert resp.status_code == 400

    async def test_missing_required_field_returns_400(self, client):
        body = _valid_event_body()
        del body["workspace_id"]
        resp = await client.post(
            "/events",
            json=body,
            headers={"Authorization": "Bearer test-token-123"},
        )
        assert resp.status_code == 400

    async def test_producer_called_with_event(self, app, client):
        body = _valid_event_body()
        await client.post(
            "/events",
            json=body,
            headers={"Authorization": "Bearer test-token-123"},
        )
        app.state.producer.send_event.assert_called_once()


class TestHealthEndpoint:
    async def test_health_returns_healthy(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["postgres"] == "ok"
        assert data["kafka"] == "ok"

    async def test_health_returns_unhealthy_when_pg_down(self, app, client):
        app.state.database.check_health = AsyncMock(return_value=False)
        resp = await client.get("/health")
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["postgres"] == "error"

    async def test_health_returns_unhealthy_when_kafka_down(self, app, client):
        app.state.producer.check_health = AsyncMock(return_value=False)
        resp = await client.get("/health")
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["kafka"] == "error"

    async def test_health_requires_no_auth(self, client):
        # Health should work without any auth header
        resp = await client.get("/health")
        assert resp.status_code == 200


class TestGetEvents:
    @pytest.fixture
    def mock_event_store(self):
        store = MagicMock()
        store.query_events = AsyncMock(return_value=[])
        store.count_events = AsyncMock(return_value=0)
        return store

    async def test_get_events_requires_auth(self, client):
        resp = await client.get("/events", params={"workspace_id": "ws-1"})
        assert resp.status_code in (400, 422)

    async def test_get_events_wrong_token_returns_401(self, client):
        resp = await client.get(
            "/events",
            params={"workspace_id": "ws-1"},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    async def test_get_events_requires_workspace_id(self, client):
        resp = await client.get(
            "/events",
            headers={"Authorization": "Bearer test-token-123"},
        )
        assert resp.status_code == 400

    async def test_get_events_basic(self, client, mock_event_store):
        sample_events = [
            {"event_id": str(uuid4()), "workspace_id": "ws-1", "type": "task.created"},
        ]
        mock_event_store.query_events = AsyncMock(return_value=sample_events)
        mock_event_store.count_events = AsyncMock(return_value=1)

        with patch(
            "punk_records.api.events.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/events",
                params={"workspace_id": "ws-1"},
                headers={"Authorization": "Bearer test-token-123"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == sample_events
        assert data["total"] == 1
        assert data["limit"] == 50
        assert data["offset"] == 0

    async def test_get_events_with_filters(self, client, mock_event_store):
        with patch(
            "punk_records.api.events.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/events",
                params={
                    "workspace_id": "ws-1",
                    "type": "task.created",
                    "after": "2026-01-01T00:00:00Z",
                    "before": "2026-12-31T23:59:59Z",
                },
                headers={"Authorization": "Bearer test-token-123"},
            )

        assert resp.status_code == 200
        mock_event_store.query_events.assert_called_once()
        call_args = mock_event_store.query_events.call_args
        assert call_args[0][0] == "ws-1"
        assert call_args[0][1] == "task.created"
        # after and before are datetime objects
        assert call_args[0][2] is not None
        assert call_args[0][3] is not None

    async def test_get_events_pagination(self, client, mock_event_store):
        mock_event_store.count_events = AsyncMock(return_value=100)

        with patch(
            "punk_records.api.events.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/events",
                params={
                    "workspace_id": "ws-1",
                    "limit": 10,
                    "offset": 20,
                },
                headers={"Authorization": "Bearer test-token-123"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 100
        assert data["limit"] == 10
        assert data["offset"] == 20
        call_args = mock_event_store.query_events.call_args
        assert call_args[0][4] == 10  # limit
        assert call_args[0][5] == 20  # offset

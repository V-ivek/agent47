"""Unit tests for Context Pack API v0."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from punk_records.api.context_packs import router as context_packs_router
from punk_records.config import Settings

AUTH = {"Authorization": "Bearer test-token-123"}


def _create_test_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(status_code=400, content={"detail": exc.errors()})

    app.include_router(context_packs_router)

    app.state.settings = Settings(punk_records_api_token="test-token-123")
    app.state.database = MagicMock()
    app.state.memory_store = MagicMock()
    app.state.memory_store.get_entries = AsyncMock(return_value=[])
    return app


@pytest.fixture
def app():
    return _create_test_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestContextPackV0:
    async def test_requires_auth(self, client):
        resp = await client.get("/context-packs/ws-test")
        assert resp.status_code == 401

    async def test_returns_v0_shape(self, app, client):
        app.state.memory_store.get_entries = AsyncMock(
            return_value=[
                {
                    "entry_id": str(uuid4()),
                    "workspace_id": "ws-test",
                    "bucket": "workspace",
                    "key": "architecture.stella",
                    "value": {"idea": "satellite coordination"},
                    "status": "promoted",
                    "confidence": 0.9,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            ]
        )

        mock_event_store = MagicMock()

        async def _query_events(workspace_id, **kwargs):
            if kwargs.get("type") == "decision.recorded":
                return [{"event_id": str(uuid4()), "type": "decision.recorded"}]
            if kwargs.get("type") == "task.created":
                return [{"event_id": str(uuid4()), "type": "task.created"}]
            if kwargs.get("type") == "risk.detected":
                return [{"event_id": str(uuid4()), "type": "risk.detected", "severity": "high"}]
            return []

        mock_event_store.query_events = AsyncMock(side_effect=_query_events)

        with patch("punk_records.api.context_packs.EventStore", return_value=mock_event_store):
            resp = await client.get("/context-packs/ws-test", headers=AUTH)

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "v0"
        assert data["workspace_id"] == "ws-test"
        assert "generated_at" in data
        assert "sections" in data
        assert "counts" in data
        assert data["counts"]["memory"] == 1
        assert data["counts"]["decisions"] == 1
        assert data["counts"]["tasks"] == 1
        assert data["counts"]["risks"] == 1

    async def test_query_ranking_filters_memory(self, app, client):
        app.state.memory_store.get_entries = AsyncMock(
            return_value=[
                {
                    "entry_id": str(uuid4()),
                    "workspace_id": "ws-test",
                    "bucket": "workspace",
                    "key": "kafka.routing",
                    "value": {"topic": "tasks.queue.llm"},
                    "status": "promoted",
                },
                {
                    "entry_id": str(uuid4()),
                    "workspace_id": "ws-test",
                    "bucket": "workspace",
                    "key": "random.note",
                    "value": {"text": "unrelated"},
                    "status": "promoted",
                },
            ]
        )

        mock_event_store = MagicMock()
        mock_event_store.query_events = AsyncMock(return_value=[])

        with patch("punk_records.api.context_packs.EventStore", return_value=mock_event_store):
            resp = await client.get(
                "/context-packs/ws-test",
                params={"q": "kafka llm"},
                headers=AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sections"]["memory"]) == 1
        assert data["sections"]["memory"][0]["title"] == "kafka.routing"
        assert data["sections"]["memory"][0]["relevance"]["score"] == 1.0

    async def test_since_is_forwarded_to_event_queries(self, app, client):
        app.state.memory_store.get_entries = AsyncMock(return_value=[])
        mock_event_store = MagicMock()
        mock_event_store.query_events = AsyncMock(return_value=[])

        since_str = "2026-02-01T00:00:00+00:00"

        with patch("punk_records.api.context_packs.EventStore", return_value=mock_event_store):
            resp = await client.get(
                "/context-packs/ws-test",
                params={"since": since_str},
                headers=AUTH,
            )

        assert resp.status_code == 200
        expected_dt = datetime.fromisoformat(since_str)
        assert mock_event_store.query_events.call_count == 3
        for call in mock_event_store.query_events.call_args_list:
            assert call.kwargs["after"] == expected_dt

    async def test_default_since_is_7_days(self, app, client):
        app.state.memory_store.get_entries = AsyncMock(return_value=[])
        mock_event_store = MagicMock()
        mock_event_store.query_events = AsyncMock(return_value=[])

        before = datetime.now(timezone.utc) - timedelta(days=7)

        with patch("punk_records.api.context_packs.EventStore", return_value=mock_event_store):
            resp = await client.get("/context-packs/ws-test", headers=AUTH)

        after = datetime.now(timezone.utc) - timedelta(days=7)

        assert resp.status_code == 200
        for call in mock_event_store.query_events.call_args_list:
            since_dt = call.kwargs["after"]
            assert before <= since_dt <= after

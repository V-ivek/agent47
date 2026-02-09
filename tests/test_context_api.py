"""Unit tests for context pack API endpoint."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from punk_records.api.context import router as context_router
from punk_records.api.events import router as events_router
from punk_records.api.health import router as health_router
from punk_records.config import Settings


def _create_test_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=400, content={"detail": exc.errors()}
        )

    app.include_router(context_router)
    app.include_router(events_router)
    app.include_router(health_router)

    app.state.settings = Settings(
        punk_records_api_token="test-token-123"
    )
    app.state.producer = MagicMock()
    app.state.producer.send_event = AsyncMock()
    app.state.producer.check_health = AsyncMock(return_value=True)
    app.state.database = MagicMock()
    app.state.database.check_health = AsyncMock(return_value=True)
    app.state.memory_store = MagicMock()
    app.state.memory_store.get_entries = AsyncMock(return_value=[])

    return app


AUTH = {"Authorization": "Bearer test-token-123"}


@pytest.fixture
def app():
    return _create_test_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c


class TestGetContext:
    @pytest.fixture
    def mock_event_store(self):
        store = MagicMock()
        store.query_events = AsyncMock(return_value=[])
        return store

    async def test_requires_auth(self, client):
        resp = await client.get("/context/ws-test")
        assert resp.status_code in (400, 422)

    async def test_wrong_token_returns_401(self, client):
        resp = await client.get(
            "/context/ws-test",
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    async def test_returns_context_pack(self, app, client, mock_event_store):
        memory_entries = [
            {
                "entry_id": str(uuid4()),
                "workspace_id": "ws-test",
                "bucket": "workspace",
                "key": "fact.one",
                "status": "promoted",
            },
        ]
        decision_events = [
            {"event_id": str(uuid4()), "type": "decision.recorded"},
        ]
        task_events = [
            {"event_id": str(uuid4()), "type": "task.created"},
        ]
        risk_events = [
            {"event_id": str(uuid4()), "type": "risk.detected", "severity": "high"},
        ]

        app.state.memory_store.get_entries = AsyncMock(
            return_value=memory_entries
        )

        async def _query_events(workspace_id, **kwargs):
            event_type = kwargs.get("type")
            if event_type == "decision.recorded":
                return decision_events
            elif event_type == "task.created":
                return task_events
            elif event_type == "risk.detected":
                return risk_events
            return []

        mock_event_store.query_events = AsyncMock(side_effect=_query_events)

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                headers=AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == "ws-test"
        assert "timestamp" in data
        assert len(data["sections"]["memory"]) == 1
        assert data["sections"]["memory"][0]["title"] == "fact.one"
        assert data["sections"]["memory"][0]["workspace_id"] == "ws-test"
        assert data["sections"]["decisions"] == decision_events
        assert data["sections"]["tasks"] == task_events
        assert data["sections"]["risks"] == risk_events

    async def test_empty_workspace_returns_empty_sections(
        self, app, client, mock_event_store
    ):
        app.state.memory_store.get_entries = AsyncMock(return_value=[])
        mock_event_store.query_events = AsyncMock(return_value=[])

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-empty",
                headers=AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == "ws-empty"
        assert data["sections"]["memory"] == []
        assert data["sections"]["decisions"] == []
        assert data["sections"]["tasks"] == []
        assert data["sections"]["risks"] == []

    async def test_limit_param_passed_to_queries(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                params={"limit": 25},
                headers=AUTH,
            )

        assert resp.status_code == 200
        # query_events is called 3 times (decisions, tasks, risks)
        assert mock_event_store.query_events.call_count == 3
        for call in mock_event_store.query_events.call_args_list:
            assert call.kwargs["limit"] == 25

    async def test_since_param_parsed_correctly(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])
        since_str = "2026-01-15T10:30:00+00:00"

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                params={"since": since_str},
                headers=AUTH,
            )

        assert resp.status_code == 200
        expected_dt = datetime.fromisoformat(since_str)
        for call in mock_event_store.query_events.call_args_list:
            assert call.kwargs["after"] == expected_dt

    async def test_default_since_is_7_days(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])

        before = datetime.now(timezone.utc) - timedelta(days=7)

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                headers=AUTH,
            )

        after = datetime.now(timezone.utc) - timedelta(days=7)

        assert resp.status_code == 200
        assert mock_event_store.query_events.call_count == 3
        for call in mock_event_store.query_events.call_args_list:
            since_dt = call.kwargs["after"]
            # The computed default should be between our before/after brackets
            assert before <= since_dt <= after

    async def test_memory_section_returns_promoted_entries(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                headers=AUTH,
            )

        assert resp.status_code == 200
        call_args = app.state.memory_store.get_entries.call_args
        assert call_args[0][0] == "ws-test"
        from punk_records.models.memory import MemoryStatus
        assert call_args.kwargs["status"] == MemoryStatus.PROMOTED

    async def test_decisions_section_queries_correct_type(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                headers=AUTH,
            )

        assert resp.status_code == 200
        # First call to query_events is for decisions
        decisions_call = mock_event_store.query_events.call_args_list[0]
        assert decisions_call[0][0] == "ws-test"
        assert decisions_call.kwargs["type"] == "decision.recorded"

    async def test_risks_section_queries_high_severity(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                headers=AUTH,
            )

        assert resp.status_code == 200
        # Third call to query_events is for risks
        risks_call = mock_event_store.query_events.call_args_list[2]
        assert risks_call[0][0] == "ws-test"
        assert risks_call.kwargs["type"] == "risk.detected"
        assert risks_call.kwargs["severity"] == "high"

    async def test_counts_reflect_section_lengths(
        self, app, client, mock_event_store
    ):
        memory_entries = [
            {"entry_id": str(uuid4()), "key": "a"},
            {"entry_id": str(uuid4()), "key": "b"},
            {"entry_id": str(uuid4()), "key": "c"},
        ]
        decision_events = [
            {"event_id": str(uuid4()), "type": "decision.recorded"},
            {"event_id": str(uuid4()), "type": "decision.recorded"},
        ]
        task_events = [
            {"event_id": str(uuid4()), "type": "task.created"},
        ]
        risk_events = []

        app.state.memory_store.get_entries = AsyncMock(
            return_value=memory_entries
        )

        async def _query_events(workspace_id, **kwargs):
            event_type = kwargs.get("type")
            if event_type == "decision.recorded":
                return decision_events
            elif event_type == "task.created":
                return task_events
            elif event_type == "risk.detected":
                return risk_events
            return []

        mock_event_store.query_events = AsyncMock(side_effect=_query_events)

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                headers=AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sections"]["memory"]) == 3
        assert len(data["sections"]["decisions"]) == 2
        assert len(data["sections"]["tasks"]) == 1
        assert len(data["sections"]["risks"]) == 0

    async def test_tasks_section_queries_correct_type(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                headers=AUTH,
            )

        assert resp.status_code == 200
        # Second call to query_events is for tasks
        tasks_call = mock_event_store.query_events.call_args_list[1]
        assert tasks_call[0][0] == "ws-test"
        assert tasks_call.kwargs["type"] == "task.created"

    async def test_since_naive_datetime_gets_utc(
        self, app, client, mock_event_store
    ):
        mock_event_store.query_events = AsyncMock(return_value=[])
        # Naive datetime (no timezone info)
        since_str = "2026-01-15T10:30:00"

        with patch(
            "punk_records.api.context.EventStore",
            return_value=mock_event_store,
        ):
            resp = await client.get(
                "/context/ws-test",
                params={"since": since_str},
                headers=AUTH,
            )

        assert resp.status_code == 200
        expected_dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        for call in mock_event_store.query_events.call_args_list:
            assert call.kwargs["after"] == expected_dt

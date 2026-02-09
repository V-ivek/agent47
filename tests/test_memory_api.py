"""Unit tests for memory API endpoints."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from punk_records.api.events import router as events_router
from punk_records.api.health import router as health_router
from punk_records.api.memory import router as memory_router
from punk_records.config import Settings


def _create_test_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=400, content={"detail": exc.errors()}
        )

    app.include_router(events_router)
    app.include_router(health_router)
    app.include_router(memory_router)

    app.state.settings = Settings(
        punk_records_api_token="test-token-123"
    )
    app.state.producer = MagicMock()
    app.state.producer.send_event = AsyncMock()
    app.state.producer.check_health = AsyncMock(return_value=True)
    app.state.database = MagicMock()
    app.state.database.check_health = AsyncMock(return_value=True)
    app.state.memory_store = MagicMock()
    app.state.memory_store.get_entries = AsyncMock(
        return_value=[]
    )
    app.state.projection_engine = MagicMock()
    app.state.projection_engine.replay = AsyncMock(
        return_value={
            "entries_deleted": 0,
            "events_replayed": 0,
            "entries_created": 0,
        }
    )

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


class TestGetMemory:
    async def test_requires_auth(self, client):
        resp = await client.get("/memory/ws-test")
        assert resp.status_code in (400, 422)

    async def test_wrong_token_returns_401(self, client):
        resp = await client.get(
            "/memory/ws-test",
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    async def test_returns_entries(self, app, client):
        entries = [
            {
                "entry_id": str(uuid4()),
                "workspace_id": "ws-test",
                "bucket": "workspace",
                "key": "fact.one",
                "status": "promoted",
            },
        ]
        app.state.memory_store.get_entries = AsyncMock(
            return_value=entries
        )

        resp = await client.get("/memory/ws-test", headers=AUTH)

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["workspace_id"] == "ws-test"

    async def test_bucket_filter(self, app, client):
        resp = await client.get(
            "/memory/ws-test",
            params={"bucket": "global"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        call_kwargs = (
            app.state.memory_store.get_entries.call_args
        )
        assert call_kwargs.kwargs["bucket"].value == "global"

    async def test_status_filter(self, app, client):
        resp = await client.get(
            "/memory/ws-test",
            params={"status": "candidate"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        call_kwargs = (
            app.state.memory_store.get_entries.call_args
        )
        assert call_kwargs.kwargs["status"].value == "candidate"

    async def test_invalid_bucket_returns_400(self, client):
        resp = await client.get(
            "/memory/ws-test",
            params={"bucket": "invalid"},
            headers=AUTH,
        )
        assert resp.status_code == 400
        assert "Invalid bucket" in resp.json()["detail"]

    async def test_invalid_status_returns_400(self, client):
        resp = await client.get(
            "/memory/ws-test",
            params={"status": "deleted"},
            headers=AUTH,
        )
        assert resp.status_code == 400
        assert "Invalid status" in resp.json()["detail"]

    async def test_include_expired(self, app, client):
        resp = await client.get(
            "/memory/ws-test",
            params={"include_expired": "true"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        call_kwargs = (
            app.state.memory_store.get_entries.call_args
        )
        assert call_kwargs.kwargs["include_expired"] is True

    async def test_default_excludes_expired(self, app, client):
        resp = await client.get(
            "/memory/ws-test", headers=AUTH
        )
        assert resp.status_code == 200
        call_kwargs = (
            app.state.memory_store.get_entries.call_args
        )
        assert call_kwargs.kwargs["include_expired"] is False


class TestReplay:
    async def test_requires_auth(self, client):
        resp = await client.post("/replay/ws-test")
        assert resp.status_code in (400, 422)

    async def test_wrong_token_returns_401(self, client):
        resp = await client.post(
            "/replay/ws-test",
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    async def test_replay_returns_summary(self, app, client):
        app.state.projection_engine.replay = AsyncMock(
            return_value={
                "entries_deleted": 5,
                "events_replayed": 20,
                "entries_created": 3,
            }
        )

        resp = await client.post(
            "/replay/ws-test", headers=AUTH
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_deleted"] == 5
        assert data["events_replayed"] == 20
        assert data["entries_created"] == 3
        app.state.projection_engine.replay.assert_called_once_with(
            "ws-test"
        )

    async def test_replay_empty_workspace(self, client):
        resp = await client.post(
            "/replay/ws-empty", headers=AUTH
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_deleted"] == 0
        assert data["events_replayed"] == 0

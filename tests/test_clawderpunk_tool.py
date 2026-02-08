"""Unit tests for clawderpunk_tool package (config, client, tool)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from clawderpunk_tool.client import PunkRecordsClient
from clawderpunk_tool.config import ToolConfig
from clawderpunk_tool.tool import ClawderpunkTool

# ---------------------------------------------------------------------------
# ToolConfig
# ---------------------------------------------------------------------------


class TestToolConfig:
    def test_loads_from_kwargs(self):
        cfg = ToolConfig(
            url="http://localhost:4701",
            token="tok",
            workspace_id="ws-1",
        )
        assert cfg.url == "http://localhost:4701"
        assert cfg.token == "tok"
        assert cfg.workspace_id == "ws-1"
        assert cfg.satellite_id == "agent-zero"  # default
        assert cfg.timeout == 10  # default

    def test_custom_defaults(self):
        cfg = ToolConfig(
            url="http://x",
            token="t",
            workspace_id="ws",
            satellite_id="custom-sat",
            timeout=30,
        )
        assert cfg.satellite_id == "custom-sat"
        assert cfg.timeout == 30

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("CLAWDERPUNK_URL", "http://env-url")
        monkeypatch.setenv("CLAWDERPUNK_TOKEN", "env-tok")
        monkeypatch.setenv("CLAWDERPUNK_WORKSPACE_ID", "env-ws")
        monkeypatch.setenv("CLAWDERPUNK_SATELLITE_ID", "env-sat")
        monkeypatch.setenv("CLAWDERPUNK_TIMEOUT", "20")
        cfg = ToolConfig()
        assert cfg.url == "http://env-url"
        assert cfg.token == "env-tok"
        assert cfg.workspace_id == "env-ws"
        assert cfg.satellite_id == "env-sat"
        assert cfg.timeout == 20

    def test_missing_required_raises(self):
        with pytest.raises(Exception):
            ToolConfig()  # no url, token, workspace_id


# ---------------------------------------------------------------------------
# Helpers for PunkRecordsClient tests
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> ToolConfig:
    defaults = {
        "url": "http://localhost:4701",
        "token": "test-token-123",
        "workspace_id": "ws-test",
    }
    defaults.update(overrides)
    return ToolConfig(**defaults)


def _mock_response(status_code: int = 202, json_data: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


# ---------------------------------------------------------------------------
# PunkRecordsClient
# ---------------------------------------------------------------------------


class TestPunkRecordsClient:
    @pytest.mark.asyncio
    async def test_context_manager_opens_and_closes(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        async with client as c:
            assert c._client is not None
            assert isinstance(c._client, httpx.AsyncClient)
        assert client._client is None

    @pytest.mark.asyncio
    async def test_post_event_success(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.post.return_value = _mock_response(202, {"status": "accepted"})

        result = await client.post_event({"type": "test"})
        assert result["ok"] is True
        assert result["status"] == 202
        assert result["data"] == {"status": "accepted"}
        client._client.post.assert_called_once_with("/events", json={"type": "test"})

    @pytest.mark.asyncio
    async def test_post_event_server_error(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.post.return_value = _mock_response(500, {"detail": "error"})

        result = await client.post_event({"type": "test"})
        assert result["ok"] is False
        assert result["status"] == 500

    @pytest.mark.asyncio
    async def test_post_event_timeout(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.post.side_effect = httpx.TimeoutException("timeout")

        result = await client.post_event({"type": "test"})
        assert result == {"ok": False, "error": "timeout"}

    @pytest.mark.asyncio
    async def test_post_event_connection_error(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.post.side_effect = httpx.ConnectError("refused")

        result = await client.post_event({"type": "test"})
        assert result == {"ok": False, "error": "connection_failed"}

    @pytest.mark.asyncio
    async def test_get_context_success(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get.return_value = _mock_response(
            200, {"promoted_memory": [], "decisions": []}
        )

        result = await client.get_context("ws-test", limit=5)
        assert result["ok"] is True
        assert result["status"] == 200
        client._client.get.assert_called_once_with(
            "/context/ws-test", params={"limit": 5}
        )

    @pytest.mark.asyncio
    async def test_get_context_with_since(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get.return_value = _mock_response(200, {})

        await client.get_context("ws-test", limit=10, since="2026-01-01T00:00:00")
        client._client.get.assert_called_once_with(
            "/context/ws-test",
            params={"limit": 10, "since": "2026-01-01T00:00:00"},
        )

    @pytest.mark.asyncio
    async def test_get_context_timeout(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get.side_effect = httpx.TimeoutException("timeout")

        result = await client.get_context("ws-test")
        assert result == {"ok": False, "error": "timeout"}

    @pytest.mark.asyncio
    async def test_health_success(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get.return_value = _mock_response(
            200, {"kafka": "ok", "postgres": "ok"}
        )

        result = await client.health()
        assert result["ok"] is True
        assert result["data"]["kafka"] == "ok"
        client._client.get.assert_called_once_with("/health")

    @pytest.mark.asyncio
    async def test_health_unreachable(self):
        cfg = _make_config()
        client = PunkRecordsClient(cfg)
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get.side_effect = httpx.ConnectError("down")

        result = await client.health()
        assert result == {"ok": False, "error": "unreachable"}

    @pytest.mark.asyncio
    async def test_auth_header_set(self):
        cfg = _make_config(token="my-secret")
        client = PunkRecordsClient(cfg)
        async with client as c:
            assert c._client.headers["Authorization"] == "Bearer my-secret"


# ---------------------------------------------------------------------------
# ClawderpunkTool
# ---------------------------------------------------------------------------


class TestClawderpunkTool:
    def _make_tool(self) -> ClawderpunkTool:
        cfg = _make_config()
        return ClawderpunkTool(config=cfg)

    @pytest.mark.asyncio
    async def test_context_manager(self):
        tool = self._make_tool()
        async with tool as t:
            assert t._client is not None
        assert tool._client is None

    @pytest.mark.asyncio
    async def test_build_envelope(self):
        tool = self._make_tool()
        envelope = tool._build_envelope(
            "test.event", {"key": "val"}, severity="high", confidence=0.9
        )
        assert envelope["type"] == "test.event"
        assert envelope["payload"] == {"key": "val"}
        assert envelope["severity"] == "high"
        assert envelope["confidence"] == 0.9
        assert envelope["workspace_id"] == "ws-test"
        assert envelope["satellite_id"] == "agent-zero"
        assert envelope["schema_version"] == 1
        assert "event_id" in envelope
        assert "ts" in envelope
        assert "trace_id" in envelope

    @pytest.mark.asyncio
    async def test_build_envelope_custom_trace_id(self):
        tool = self._make_tool()
        envelope = tool._build_envelope("x", {}, trace_id="my-trace")
        assert envelope["trace_id"] == "my-trace"

    @pytest.mark.asyncio
    async def test_emit_event(self):
        tool = self._make_tool()
        tool._client = AsyncMock(spec=PunkRecordsClient)
        tool._client.post_event.return_value = {"ok": True, "status": 202}

        result = await tool.emit_event("test.event", {"k": "v"}, severity="medium")
        assert result["ok"] is True
        call_args = tool._client.post_event.call_args[0][0]
        assert call_args["type"] == "test.event"
        assert call_args["severity"] == "medium"

    @pytest.mark.asyncio
    async def test_get_context(self):
        tool = self._make_tool()
        tool._client = AsyncMock(spec=PunkRecordsClient)
        tool._client.get_context.return_value = {"ok": True, "data": {"promoted_memory": []}}

        result = await tool.get_context(limit=5, since_days=3)
        assert result["ok"] is True
        tool._client.get_context.assert_called_once()
        call_args = tool._client.get_context.call_args
        assert call_args[0][0] == "ws-test"  # workspace_id
        assert call_args[1]["limit"] == 5
        assert call_args[1]["since"] is not None  # computed from since_days

    @pytest.mark.asyncio
    async def test_get_context_no_since(self):
        tool = self._make_tool()
        tool._client = AsyncMock(spec=PunkRecordsClient)
        tool._client.get_context.return_value = {"ok": True, "data": {}}

        await tool.get_context(since_days=0)
        call_args = tool._client.get_context.call_args
        assert call_args[1]["since"] is None

    @pytest.mark.asyncio
    async def test_record_decision(self):
        tool = self._make_tool()
        tool._client = AsyncMock(spec=PunkRecordsClient)
        tool._client.post_event.return_value = {"ok": True, "status": 202}

        result = await tool.record_decision(
            "Use Kafka", "Better for streaming", confidence=0.85
        )
        assert result["ok"] is True
        envelope = tool._client.post_event.call_args[0][0]
        assert envelope["type"] == "decision.recorded"
        assert envelope["severity"] == "medium"
        assert envelope["confidence"] == 0.85
        assert envelope["payload"]["decision"] == "Use Kafka"
        assert envelope["payload"]["rationale"] == "Better for streaming"

    @pytest.mark.asyncio
    async def test_create_task(self):
        tool = self._make_tool()
        tool._client = AsyncMock(spec=PunkRecordsClient)
        tool._client.post_event.return_value = {"ok": True, "status": 202}

        result = await tool.create_task("Fix bug", "Null pointer in parser", priority="high")
        assert result["ok"] is True
        envelope = tool._client.post_event.call_args[0][0]
        assert envelope["type"] == "task.created"
        assert envelope["severity"] == "low"
        assert envelope["confidence"] == 0.0
        assert envelope["payload"]["title"] == "Fix bug"
        assert envelope["payload"]["description"] == "Null pointer in parser"
        assert envelope["payload"]["priority"] == "high"

    @pytest.mark.asyncio
    async def test_emit_event_surfaces_client_error(self):
        tool = self._make_tool()
        tool._client = AsyncMock(spec=PunkRecordsClient)
        tool._client.post_event.return_value = {"ok": False, "error": "timeout"}

        result = await tool.emit_event("test", {})
        assert result["ok"] is False
        assert result["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_default_config_from_env(self, monkeypatch):
        monkeypatch.setenv("CLAWDERPUNK_URL", "http://from-env")
        monkeypatch.setenv("CLAWDERPUNK_TOKEN", "env-tok")
        monkeypatch.setenv("CLAWDERPUNK_WORKSPACE_ID", "env-ws")

        tool = ClawderpunkTool()  # no config passed — loads from env
        assert tool._config.url == "http://from-env"
        assert tool._config.workspace_id == "env-ws"

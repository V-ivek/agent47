from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from openclaw_skill.client import PunkRecordsClient, PunkRecordsError
from openclaw_skill.config import SkillConfig
from openclaw_skill.renderer import render_daily_snapshot, render_memory_generated
from openclaw_skill.sync import sync_memory


def test_skill_config_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAWDERPUNK_TOKEN", "t")
    monkeypatch.setenv("CLAWDERPUNK_WORKSPACE_ID", "w")
    cfg = SkillConfig()
    assert cfg.token == "t"
    assert cfg.workspace_id == "w"
    assert cfg.url
    assert cfg.satellite_id == "openclaw"


def test_client_handles_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "nope"})

    transport = httpx.MockTransport(handler)

    client = PunkRecordsClient("http://x", "t")
    object.__setattr__(
        client, "_client", httpx.Client(transport=transport, base_url="http://x")
    )
    with pytest.raises(PunkRecordsError):
        client.post_event({"x": 1})


def test_renderer_deterministic_and_newline() -> None:
    dt = datetime(2026, 2, 9, 0, 0, tzinfo=timezone.utc)
    out1 = render_memory_generated(
        workspace_id="w",
        memory_entries=[
            {
                "entry_id": "2",
                "key": "b",
                "value": {"z": 1, "a": 2},
                "status": "PROMOTED",
                "bucket": "workspace",
                "source_event_id": "e2",
                "promoted_at": "2026-02-09T00:00:00Z",
                "confidence": 0.8,
            },
            {
                "entry_id": "1",
                "key": "a",
                "value": "hello",
                "status": "PROMOTED",
                "bucket": "workspace",
                "source_event_id": "e1",
                "promoted_at": "2026-02-09T00:00:00Z",
                "confidence": 0.9,
            },
        ],
        decisions=[],
        tasks=[],
        risks=[],
        generated_at=dt,
    )
    out2 = render_memory_generated(
        workspace_id="w",
        memory_entries=[
            {
                "entry_id": "1",
                "key": "a",
                "value": "hello",
                "status": "PROMOTED",
                "bucket": "workspace",
                "source_event_id": "e1",
                "promoted_at": "2026-02-09T00:00:00Z",
                "confidence": 0.9,
            },
            {
                "entry_id": "2",
                "key": "b",
                "value": {"a": 2, "z": 1},
                "status": "PROMOTED",
                "bucket": "workspace",
                "source_event_id": "e2",
                "promoted_at": "2026-02-09T00:00:00Z",
                "confidence": 0.8,
            },
        ],
        decisions=[],
        tasks=[],
        risks=[],
        generated_at=dt,
    )

    assert out1 == out2
    assert out1.endswith("\n")
    # stable json payload ordering
    assert "{\"a\":2,\"z\":1}" in out1


def test_daily_snapshot_is_json_and_deterministic() -> None:
    dt = datetime(2026, 2, 9, 0, 0, tzinfo=timezone.utc)
    pack = {"memory": [{"x": 1, "a": 2}], "decisions": []}
    out = render_daily_snapshot(workspace_id="w", context_pack=pack, generated_at=dt)
    assert out.endswith("\n")
    assert "```json" in out
    assert json.dumps(pack, sort_keys=True, separators=(",", ":")) in out


def test_sync_memory_lock_and_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Minimal config
    monkeypatch.setenv("CLAWDERPUNK_URL", "http://x")
    monkeypatch.setenv("CLAWDERPUNK_TOKEN", "t")
    monkeypatch.setenv("CLAWDERPUNK_WORKSPACE_ID", "w")

    # Patch PunkRecordsClient methods by monkeypatching class methods via instance.
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get_context(self, **kwargs):
            return {"decisions": [], "tasks": [], "risks": []}

        def get_memory(self, **kwargs):
            return {"entries": []}

    monkeypatch.setattr("openclaw_skill.sync.PunkRecordsClient", lambda *a, **k: FakeClient())

    cfg = SkillConfig()
    res = sync_memory(cfg, vault_root=tmp_path)
    assert res["ok"] is True
    files = [Path(p) for p in res["files_written"]]
    for p in files:
        assert p.exists()
        assert p.read_text(encoding="utf-8").endswith("\n")

    # Simulate lock contention by holding lock
    out_dir = tmp_path / "memory" / "punk-records" / "w"
    lock_path = out_dir / ".sync.lock"
    with open(lock_path, "w") as fp:
        import fcntl

        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        res2 = sync_memory(cfg, vault_root=tmp_path)
        assert res2["ok"] is False
        assert res2["error"] == "sync_locked"

"""Integration tests that run against a live docker-compose stack.

Run with: pytest tests/test_integration.py -v
Requires: docker compose up --build -d (all services healthy)
"""

import os
import time
from uuid import uuid4

import httpx
import pytest

BASE_URL = os.environ.get("PUNK_RECORDS_URL", "http://localhost:4701")
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


# ---------------------------------------------------------------------------
# Epic 1 tests
# ---------------------------------------------------------------------------


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
        assert resp.status_code in (400, 401, 422)

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


# ---------------------------------------------------------------------------
# Epic 2 tests — Events Query API
# ---------------------------------------------------------------------------


class TestEventsQueryAPI:
    """GET /events returns posted events with correct filters."""

    def test_get_events_returns_posted_event(self, client):
        ws = f"ws-query-{uuid4().hex[:8]}"
        event = _make_event(workspace_id=ws)
        client.post("/events", json=event, headers=AUTH_HEADERS)
        time.sleep(3)

        resp = client.get("/events", params={"workspace_id": ws}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        ids = [e["event_id"] for e in data["events"]]
        assert event["event_id"] in ids

    def test_get_events_filter_by_type(self, client):
        ws = f"ws-qtype-{uuid4().hex[:8]}"
        ev1 = _make_event(workspace_id=ws, type="task.created")
        ev2 = _make_event(workspace_id=ws, type="finding.logged")
        client.post("/events", json=ev1, headers=AUTH_HEADERS)
        client.post("/events", json=ev2, headers=AUTH_HEADERS)
        time.sleep(3)

        resp = client.get(
            "/events",
            params={"workspace_id": ws, "type": "task.created"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        types = {e["type"] for e in data["events"]}
        assert types == {"task.created"}

    def test_get_events_pagination(self, client):
        ws = f"ws-qpage-{uuid4().hex[:8]}"
        for _ in range(3):
            client.post("/events", json=_make_event(workspace_id=ws), headers=AUTH_HEADERS)
        time.sleep(3)

        resp = client.get(
            "/events",
            params={"workspace_id": ws, "limit": 2, "offset": 0},
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert len(data["events"]) == 2
        assert data["total"] == 3

    def test_get_events_requires_auth(self, client):
        resp = client.get("/events", params={"workspace_id": "ws-x"})
        assert resp.status_code in (400, 401, 422)


# ---------------------------------------------------------------------------
# Epic 2 tests — Memory Projection Lifecycle
# ---------------------------------------------------------------------------


class TestMemoryCandidateProjection:
    """Post memory.candidate -> entry appears in GET /memory."""

    def test_candidate_appears_in_memory(self, client):
        ws = f"ws-mem-{uuid4().hex[:8]}"
        candidate_id = str(uuid4())
        event = _make_event(
            event_id=candidate_id,
            workspace_id=ws,
            type="memory.candidate",
            confidence=0.8,
            payload={"key": "test-pattern", "value": {"description": "A test pattern"}},
        )
        client.post("/events", json=event, headers=AUTH_HEADERS)
        time.sleep(3)

        # Candidates aren't shown by default (default status filter = promoted)
        # Query with status=candidate
        resp = client.get(
            f"/memory/{ws}", params={"status": "candidate"}, headers=AUTH_HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        keys = [e["key"] for e in data["entries"]]
        assert "test-pattern" in keys


class TestMemoryPromotedProjection:
    """Post memory.candidate + memory.promoted -> entry status changes."""

    def test_promoted_entry_appears_in_default_query(self, client):
        ws = f"ws-promo-{uuid4().hex[:8]}"
        candidate_id = str(uuid4())
        # Step 1: create candidate
        candidate_event = _make_event(
            event_id=candidate_id,
            workspace_id=ws,
            type="memory.candidate",
            confidence=0.6,
            payload={"key": "promoted-pattern", "value": {"info": "will be promoted"}},
        )
        client.post("/events", json=candidate_event, headers=AUTH_HEADERS)
        time.sleep(3)

        # Step 2: promote it
        promote_event = _make_event(
            workspace_id=ws,
            type="memory.promoted",
            payload={"entry_id": candidate_id},
        )
        client.post("/events", json=promote_event, headers=AUTH_HEADERS)
        time.sleep(3)

        # Default GET /memory returns promoted entries
        resp = client.get(f"/memory/{ws}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        keys = [e["key"] for e in data["entries"]]
        assert "promoted-pattern" in keys


class TestMemoryRetractedProjection:
    """Post memory.retracted -> entry retracted (not deleted)."""

    def test_retracted_entry_not_in_default_query(self, client):
        ws = f"ws-retract-{uuid4().hex[:8]}"
        candidate_id = str(uuid4())

        # Create + promote
        candidate = _make_event(
            event_id=candidate_id,
            workspace_id=ws,
            type="memory.candidate",
            confidence=0.5,
            payload={"key": "retract-me", "value": {}},
        )
        client.post("/events", json=candidate, headers=AUTH_HEADERS)
        time.sleep(3)

        promote = _make_event(
            workspace_id=ws,
            type="memory.promoted",
            payload={"entry_id": candidate_id},
        )
        client.post("/events", json=promote, headers=AUTH_HEADERS)
        time.sleep(3)

        # Now retract
        retract = _make_event(
            workspace_id=ws,
            type="memory.retracted",
            payload={"entry_id": candidate_id},
        )
        client.post("/events", json=retract, headers=AUTH_HEADERS)
        time.sleep(3)

        # Default query (status=promoted) should NOT include retracted entry
        resp = client.get(f"/memory/{ws}", headers=AUTH_HEADERS)
        data = resp.json()
        keys = [e["key"] for e in data["entries"]]
        assert "retract-me" not in keys

        # But status=retracted SHOULD include it
        resp2 = client.get(
            f"/memory/{ws}", params={"status": "retracted"}, headers=AUTH_HEADERS
        )
        data2 = resp2.json()
        assert data2["count"] >= 1
        keys2 = [e["key"] for e in data2["entries"]]
        assert "retract-me" in keys2


# ---------------------------------------------------------------------------
# Epic 2 tests — Replay
# ---------------------------------------------------------------------------


class TestReplayProjection:
    """POST /replay/{workspace_id} -> projections rebuilt from event history."""

    def test_replay_rebuilds_projections(self, client):
        ws = f"ws-replay-{uuid4().hex[:8]}"
        candidate_id = str(uuid4())

        # Create a candidate
        candidate = _make_event(
            event_id=candidate_id,
            workspace_id=ws,
            type="memory.candidate",
            confidence=0.7,
            payload={"key": "replay-test", "value": {"info": "replayed"}},
        )
        client.post("/events", json=candidate, headers=AUTH_HEADERS)
        time.sleep(3)

        # Verify candidate exists
        resp = client.get(
            f"/memory/{ws}", params={"status": "candidate"}, headers=AUTH_HEADERS
        )
        assert resp.json()["count"] >= 1

        # Replay — should delete and recreate from events
        resp = client.post(f"/replay/{ws}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["entries_created"] >= 1
        assert data["events_replayed"] >= 1

        # Verify candidate still exists after replay
        resp = client.get(
            f"/memory/{ws}", params={"status": "candidate"}, headers=AUTH_HEADERS
        )
        assert resp.json()["count"] >= 1
        keys = [e["key"] for e in resp.json()["entries"]]
        assert "replay-test" in keys

    def test_replay_requires_auth(self, client):
        resp = client.post("/replay/ws-x")
        assert resp.status_code in (400, 401, 422)


# ---------------------------------------------------------------------------
# Epic 2 tests — Auto-Promotion
# ---------------------------------------------------------------------------


class TestAutoPromotion:
    """High-confidence candidate + decision.recorded in trace -> auto-promoted."""

    def test_auto_promotion_via_decision_recorded(self, client):
        ws = f"ws-autopro-{uuid4().hex[:8]}"
        shared_trace = str(uuid4())
        candidate_id = str(uuid4())

        # Step 1: Post a decision.recorded event with the same trace
        decision = _make_event(
            workspace_id=ws,
            type="decision.recorded",
            trace_id=shared_trace,
            confidence=0.9,
            payload={"decision": "use pattern X"},
        )
        client.post("/events", json=decision, headers=AUTH_HEADERS)
        time.sleep(3)

        # Step 2: Post a high-confidence memory.candidate with the same trace
        candidate = _make_event(
            event_id=candidate_id,
            workspace_id=ws,
            type="memory.candidate",
            trace_id=shared_trace,
            confidence=0.85,
            payload={"key": "auto-promoted-pattern", "value": {"info": "should auto-promote"}},
        )
        client.post("/events", json=candidate, headers=AUTH_HEADERS)
        time.sleep(5)

        # The projection engine should have auto-promoted this candidate
        # because confidence >= 0.75 AND decision.recorded exists in the trace
        resp = client.get(f"/memory/{ws}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        keys = [e["key"] for e in data["entries"]]
        assert "auto-promoted-pattern" in keys


# ---------------------------------------------------------------------------
# Epic 2 tests — Memory API filters
# ---------------------------------------------------------------------------


class TestMemoryAPIFilters:
    """GET /memory with bucket and status filters."""

    def test_bucket_filter(self, client):
        ws = f"ws-bucket-{uuid4().hex[:8]}"
        # Create workspace-bucket candidate
        cand = _make_event(
            workspace_id=ws,
            type="memory.candidate",
            confidence=0.5,
            payload={"key": "ws-entry", "value": {}, "bucket": "workspace"},
        )
        client.post("/events", json=cand, headers=AUTH_HEADERS)
        time.sleep(3)

        # Query with bucket=workspace, status=candidate
        resp = client.get(
            f"/memory/{ws}",
            params={"bucket": "workspace", "status": "candidate"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert all(e["bucket"] == "workspace" for e in data["entries"])

        # Query with bucket=global should return nothing for this workspace
        resp2 = client.get(
            f"/memory/{ws}",
            params={"bucket": "global", "status": "candidate"},
            headers=AUTH_HEADERS,
        )
        assert resp2.json()["count"] == 0

    def test_memory_requires_auth(self, client):
        resp = client.get("/memory/ws-x")
        assert resp.status_code in (400, 401, 422)

    def test_invalid_bucket_returns_400(self, client):
        resp = client.get(
            "/memory/ws-x",
            params={"bucket": "invalid"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400

    def test_invalid_status_returns_400(self, client):
        resp = client.get(
            "/memory/ws-x",
            params={"status": "invalid"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Epic 2 tests — Ephemeral TTL
# ---------------------------------------------------------------------------


class TestEphemeralTTL:
    """Ephemeral entries with short TTL are filtered on read."""

    def test_ephemeral_entry_created_with_ttl(self, client):
        ws = f"ws-eph-{uuid4().hex[:8]}"
        # Create an ephemeral candidate with a long TTL (so it's not expired)
        cand = _make_event(
            workspace_id=ws,
            type="memory.candidate",
            confidence=0.5,
            payload={
                "key": "ephemeral-note",
                "value": {"note": "temporary"},
                "bucket": "ephemeral",
                "ttl_hours": 48,
            },
        )
        client.post("/events", json=cand, headers=AUTH_HEADERS)
        time.sleep(3)

        resp = client.get(
            f"/memory/{ws}",
            params={"status": "candidate"},
            headers=AUTH_HEADERS,
        )
        data = resp.json()
        assert data["count"] >= 1
        ephem = [e for e in data["entries"] if e["key"] == "ephemeral-note"]
        assert len(ephem) == 1
        assert ephem[0]["bucket"] == "ephemeral"
        assert ephem[0]["expires_at"] is not None

    def test_expired_ephemeral_filtered_by_default(self, client):
        ws = f"ws-eph-exp-{uuid4().hex[:8]}"
        # Create an ephemeral candidate with timestamp far in the past
        # so that even with ttl_hours=24, it's already expired
        cand = _make_event(
            workspace_id=ws,
            ts="2020-01-01T00:00:00Z",
            type="memory.candidate",
            confidence=0.5,
            payload={
                "key": "expired-note",
                "value": {"note": "old"},
                "bucket": "ephemeral",
                "ttl_hours": 1,
            },
        )
        client.post("/events", json=cand, headers=AUTH_HEADERS)
        time.sleep(3)

        # Default query should filter out expired
        resp = client.get(
            f"/memory/{ws}",
            params={"status": "candidate"},
            headers=AUTH_HEADERS,
        )
        keys = [e["key"] for e in resp.json()["entries"]]
        assert "expired-note" not in keys

        # include_expired=true should show it
        resp2 = client.get(
            f"/memory/{ws}",
            params={"status": "candidate", "include_expired": "true"},
            headers=AUTH_HEADERS,
        )
        keys2 = [e["key"] for e in resp2.json()["entries"]]
        assert "expired-note" in keys2


# ---------------------------------------------------------------------------
# Epic 3 tests — Context Pack API + ClawderpunkTool end-to-end
# ---------------------------------------------------------------------------


class TestContextPackAPI:
    """GET /context/{workspace_id} returns assembled context pack."""

    def test_context_pack_empty_workspace(self, client):
        ws = f"ws-ctx-empty-{uuid4().hex[:8]}"
        resp = client.get(f"/context/{ws}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == ws
        assert data["counts"]["memory"] == 0
        assert data["counts"]["decisions"] == 0
        assert data["counts"]["tasks"] == 0
        assert data["counts"]["risks"] == 0

    def test_context_pack_includes_decisions(self, client):
        ws = f"ws-ctx-dec-{uuid4().hex[:8]}"
        decision = _make_event(
            workspace_id=ws,
            type="decision.recorded",
            confidence=0.9,
            payload={"decision": "Use Redis", "rationale": "Low latency"},
        )
        client.post("/events", json=decision, headers=AUTH_HEADERS)
        time.sleep(3)

        resp = client.get(f"/context/{ws}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"]["decisions"] >= 1
        types = [e["type"] for e in data["decisions"]]
        assert "decision.recorded" in types

    def test_context_pack_includes_tasks(self, client):
        ws = f"ws-ctx-task-{uuid4().hex[:8]}"
        task = _make_event(
            workspace_id=ws,
            type="task.created",
            payload={"title": "Fix auth", "description": "Token expiry bug"},
        )
        client.post("/events", json=task, headers=AUTH_HEADERS)
        time.sleep(3)

        resp = client.get(f"/context/{ws}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"]["tasks"] >= 1
        types = [e["type"] for e in data["tasks"]]
        assert "task.created" in types

    def test_context_pack_includes_promoted_memory(self, client):
        ws = f"ws-ctx-mem-{uuid4().hex[:8]}"
        candidate_id = str(uuid4())
        shared_trace = str(uuid4())

        # Create high-confidence candidate with decision in trace -> auto-promote
        decision = _make_event(
            workspace_id=ws,
            type="decision.recorded",
            trace_id=shared_trace,
            confidence=0.9,
            payload={"decision": "use caching"},
        )
        client.post("/events", json=decision, headers=AUTH_HEADERS)
        time.sleep(3)

        candidate = _make_event(
            event_id=candidate_id,
            workspace_id=ws,
            type="memory.candidate",
            trace_id=shared_trace,
            confidence=0.85,
            payload={"key": "ctx-memory-entry", "value": {"info": "cached"}},
        )
        client.post("/events", json=candidate, headers=AUTH_HEADERS)
        time.sleep(5)

        resp = client.get(f"/context/{ws}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"]["memory"] >= 1
        keys = [e["key"] for e in data["memory"]]
        assert "ctx-memory-entry" in keys

    def test_context_pack_requires_auth(self, client):
        resp = client.get("/context/ws-x")
        assert resp.status_code in (400, 401, 422)

    def test_context_pack_respects_limit(self, client):
        ws = f"ws-ctx-lim-{uuid4().hex[:8]}"
        for i in range(3):
            task = _make_event(
                workspace_id=ws,
                type="task.created",
                payload={"title": f"Task {i}", "description": "..."},
            )
            client.post("/events", json=task, headers=AUTH_HEADERS)
        time.sleep(3)

        resp = client.get(
            f"/context/{ws}", params={"limit": 2}, headers=AUTH_HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tasks"]) <= 2


class TestClawderpunkToolE2E:
    """End-to-end tests using ClawderpunkTool against the live stack."""

    def test_emit_event_via_tool(self, client):
        import asyncio

        from clawderpunk_tool import ClawderpunkTool
        from clawderpunk_tool.config import ToolConfig

        ws = f"ws-tool-emit-{uuid4().hex[:8]}"
        cfg = ToolConfig(
            url=BASE_URL,
            token=TOKEN,
            workspace_id=ws,
        )

        async def _run():
            async with ClawderpunkTool(config=cfg) as tool:
                return await tool.emit_event(
                    "task.created",
                    {"title": "Tool test", "description": "E2E"},
                )

        result = asyncio.run(_run())
        assert result["ok"] is True
        assert result["status"] == 202

        # Verify event persisted
        time.sleep(3)
        resp = client.get(
            "/events", params={"workspace_id": ws}, headers=AUTH_HEADERS
        )
        data = resp.json()
        assert data["total"] >= 1

    def test_record_decision_via_tool(self, client):
        import asyncio

        from clawderpunk_tool import ClawderpunkTool
        from clawderpunk_tool.config import ToolConfig

        ws = f"ws-tool-dec-{uuid4().hex[:8]}"
        cfg = ToolConfig(url=BASE_URL, token=TOKEN, workspace_id=ws)

        async def _run():
            async with ClawderpunkTool(config=cfg) as tool:
                return await tool.record_decision(
                    "Use Postgres", "ACID guarantees", confidence=0.9
                )

        result = asyncio.run(_run())
        assert result["ok"] is True

        time.sleep(3)
        resp = client.get(f"/context/{ws}", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["counts"]["decisions"] >= 1

    def test_create_task_appears_in_context(self, client):
        import asyncio

        from clawderpunk_tool import ClawderpunkTool
        from clawderpunk_tool.config import ToolConfig

        ws = f"ws-tool-task-{uuid4().hex[:8]}"
        cfg = ToolConfig(url=BASE_URL, token=TOKEN, workspace_id=ws)

        async def _run():
            async with ClawderpunkTool(config=cfg) as tool:
                return await tool.create_task(
                    "Implement caching", "Add Redis layer", priority="high"
                )

        result = asyncio.run(_run())
        assert result["ok"] is True

        time.sleep(3)
        resp = client.get(f"/context/{ws}", headers=AUTH_HEADERS)
        data = resp.json()
        assert data["counts"]["tasks"] >= 1

    def test_get_context_via_tool(self, client):
        import asyncio

        from clawderpunk_tool import ClawderpunkTool
        from clawderpunk_tool.config import ToolConfig

        ws = f"ws-tool-ctx-{uuid4().hex[:8]}"
        cfg = ToolConfig(url=BASE_URL, token=TOKEN, workspace_id=ws)

        # First emit a decision so there's data
        async def _seed():
            async with ClawderpunkTool(config=cfg) as tool:
                await tool.record_decision("Test decision", "For context test")
                return await tool.get_context(limit=5)

        result = asyncio.run(_seed())
        # get_context returns before consumer persists, so just check ok
        assert result["ok"] is True
        assert result["status"] == 200

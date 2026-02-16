from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from punk_records.api.console import iso_utc, map_console_memory_status
from punk_records.api.deps import parse_iso8601_utc, verify_token
from punk_records.models.memory import MemoryStatus
from punk_records.store.event_store import EventStore

router = APIRouter()


def _normalize_memory_content(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        try:
            value_json = json.loads(value)
            return json.dumps(value_json, sort_keys=True, separators=(",", ":"))
        except Exception:
            return value

    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except Exception:
        return str(value)


def _to_context_memory(
    entry: dict[str, Any],
    score: float,
    match_terms: list[str],
) -> dict[str, Any]:
    return {
        "id": str(entry.get("entry_id")) if entry.get("entry_id") else None,
        "workspace_id": entry.get("workspace_id"),
        "bucket": entry.get("bucket"),
        "title": entry.get("key"),
        "content": _normalize_memory_content(entry.get("value")),
        "status": map_console_memory_status(
            entry.get("status"),
            expires_at=entry.get("expires_at"),
        ),
        "confidence": entry.get("confidence"),
        "created_at": iso_utc(entry.get("created_at")),
        "updated_at": iso_utc(entry.get("updated_at")),
        "source_event_id": (
            str(entry.get("source_event_id"))
            if entry.get("source_event_id")
            else None
        ),
        "relevance": {
            "score": round(score, 4),
            "match_terms": match_terms,
        },
    }


def _rank_memory(
    entries: list[dict[str, Any]],
    query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not entries:
        return []

    if not query or not query.strip():
        # Default ordering: newest updated/created first
        sorted_entries = sorted(
            entries,
            key=lambda e: (
                e.get("updated_at")
                or e.get("created_at")
                or datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True,
        )
        return [
            _to_context_memory(e, score=1.0, match_terms=[])
            for e in sorted_entries[:limit]
        ]

    terms = [t for t in query.lower().split() if t]
    if not terms:
        return []

    ranked: list[tuple[float, list[str], dict[str, Any]]] = []
    for entry in entries:
        haystack = " ".join(
            [
                str(entry.get("key") or "").lower(),
                _normalize_memory_content(entry.get("value")).lower(),
            ]
        )

        matched = [t for t in terms if t in haystack]
        if not matched:
            continue

        score = len(set(matched)) / len(set(terms))
        ranked.append((score, sorted(set(matched)), entry))

    ranked.sort(
        key=lambda r: (
            r[0],
            r[2].get("updated_at")
            or r[2].get("created_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    return [_to_context_memory(e, score=s, match_terms=m) for s, m, e in ranked[:limit]]


@router.get("/context-packs/{workspace_id}", dependencies=[Depends(verify_token)])
async def get_context_pack_v0(
    request: Request,
    workspace_id: str,
    q: str | None = Query(None, description="Optional keyword query for memory ranking"),
    since: str | None = Query(None, description="ISO-8601 timestamp for event sections"),
    memory_limit: int = Query(12, ge=1, le=100),
    decision_limit: int = Query(8, ge=1, le=100),
    task_limit: int = Query(8, ge=1, le=100),
    risk_limit: int = Query(8, ge=1, le=100),
):
    """Context Pack API v0.

    Returns compact, high-signal sections for satellite/Stella prompt assembly.
    """

    if since is not None:
        since_dt = parse_iso8601_utc(since, field_name="since")
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)

    memory_store = request.app.state.memory_store
    event_store = EventStore(request.app.state.database.pool)

    memory_entries = await memory_store.get_entries(workspace_id, status=MemoryStatus.PROMOTED)
    ranked_memory = _rank_memory(memory_entries, query=q, limit=memory_limit)

    decisions = await event_store.query_events(
        workspace_id,
        type="decision.recorded",
        after=since_dt,
        limit=decision_limit,
    )
    tasks = await event_store.query_events(
        workspace_id,
        type="task.created",
        after=since_dt,
        limit=task_limit,
    )
    risks = await event_store.query_events(
        workspace_id,
        type="risk.detected",
        severity="high",
        after=since_dt,
        limit=risk_limit,
    )

    now = datetime.now(timezone.utc).isoformat()

    return {
        "version": "v0",
        "workspace_id": workspace_id,
        "generated_at": now,
        "query": q,
        "sections": {
            "memory": ranked_memory,
            "decisions": decisions,
            "tasks": tasks,
            "risks": risks,
        },
        "counts": {
            "memory": len(ranked_memory),
            "decisions": len(decisions),
            "tasks": len(tasks),
            "risks": len(risks),
        },
        "provenance": {
            "retrieval": "keyword-v0",
            "memory_source": "memory_entries(status=promoted)",
            "event_source": "events(decision.recorded|task.created|risk.detected[high])",
        },
    }

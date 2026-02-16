from __future__ import annotations

import fcntl
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openclaw_skill.client import PunkRecordsClient, PunkRecordsError
from openclaw_skill.config import SkillConfig
from openclaw_skill.renderer import render_daily_snapshot, render_memory_generated


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    files_written: list[str]
    error: str | None = None


_GENERATED_AT_PATTERN = re.compile(r"^- generated_at:\s*`([^`]+)`\s*$", re.MULTILINE)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _parse_generated_at(markdown: str) -> datetime | None:
    match = _GENERATED_AT_PATTERN.search(markdown)
    if match is None:
        return None

    raw = match.group(1).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _write_if_changed(
    path: Path,
    *,
    generated_at: datetime,
    renderer: Callable[[datetime], str],
) -> bool:
    new_content = renderer(generated_at)

    if not path.exists():
        _atomic_write(path, new_content)
        return True

    existing_content = path.read_text(encoding="utf-8")
    if existing_content == new_content:
        return False

    existing_generated_at = _parse_generated_at(existing_content)
    if existing_generated_at is not None:
        preserved_content = renderer(existing_generated_at)
        if preserved_content == existing_content:
            # Semantic content is unchanged; preserve prior generated_at and avoid churn.
            return False

    _atomic_write(path, new_content)
    return True


def sync_memory(config: SkillConfig, *, vault_root: Path | None = None) -> dict[str, Any]:
    vault_root = vault_root or config.vault_root
    if vault_root is None:
        return {"ok": False, "error": "missing_vault_root"}

    workspace_id = config.workspace_id
    out_dir = Path(vault_root) / "memory" / "punk-records" / workspace_id
    daily_dir = out_dir / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    daily_dir.mkdir(parents=True, exist_ok=True)

    lock_path = out_dir / ".sync.lock"
    files_written: list[str] = []
    files_unchanged: list[str] = []

    with lock_path.open("w") as lock_fp:
        try:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"ok": False, "error": "sync_locked"}

        generated_at = datetime.now(timezone.utc)

        try:
            with PunkRecordsClient(
                base_url=config.url, token=config.token, timeout_seconds=config.timeout_seconds
            ) as client:
                context_pack = client.get_context(
                    workspace_id=workspace_id, limit=10, since=None
                )
                memory = client.get_memory(
                    workspace_id=workspace_id, status=None, bucket=None, include_expired=False
                )
        except PunkRecordsError as e:
            return {"ok": False, "error": "punk_records_error", "detail": str(e)}

        # Backends differ: memory endpoint returns {entries:[...]} in this repo.
        memory_entries = memory.get("entries") if isinstance(memory, dict) else None
        if not isinstance(memory_entries, list):
            # fall back to treating memory itself as list
            memory_entries = memory if isinstance(memory, list) else []

        # Context pack shape: current backend returns {memory,decisions,tasks,risks,...}
        decisions = context_pack.get("decisions", []) if isinstance(context_pack, dict) else []
        tasks = context_pack.get("tasks", []) if isinstance(context_pack, dict) else []
        risks = context_pack.get("risks", []) if isinstance(context_pack, dict) else []

        mem_path = out_dir / "MEMORY.generated.md"
        daily_path = daily_dir / f"{generated_at.date().isoformat()}.md"

        mem_written = _write_if_changed(
            mem_path,
            generated_at=generated_at,
            renderer=lambda ts: render_memory_generated(
                workspace_id=workspace_id,
                memory_entries=memory_entries,
                decisions=decisions,
                tasks=tasks,
                risks=risks,
                generated_at=ts,
            ),
        )
        if mem_written:
            files_written.append(str(mem_path))
        else:
            files_unchanged.append(str(mem_path))

        daily_written = _write_if_changed(
            daily_path,
            generated_at=generated_at,
            renderer=lambda ts: render_daily_snapshot(
                workspace_id=workspace_id,
                context_pack=context_pack,
                generated_at=ts,
            ),
        )
        if daily_written:
            files_written.append(str(daily_path))
        else:
            files_unchanged.append(str(daily_path))

        return {
            "ok": True,
            "files_written": files_written,
            "files_unchanged": files_unchanged,
        }

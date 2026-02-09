from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from openclaw_skill.client import PunkRecordsClient, PunkRecordsError
from openclaw_skill.config import SkillConfig
from openclaw_skill.sync import sync_memory


def _print(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")


def _parse_json(s: str) -> Any:
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid json: {e}")


def cmd_emit(args: argparse.Namespace) -> int:
    cfg = SkillConfig()  # from env
    payload = _parse_json(args.payload)

    event = {
        "event_id": str(uuid.uuid4()),
        "schema_version": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "workspace_id": cfg.workspace_id,
        "satellite_id": cfg.satellite_id,
        "trace_id": args.trace_id or str(uuid.uuid4()),
        "type": args.type,
        "severity": args.severity,
        "confidence": float(args.confidence),
        "payload": payload,
    }

    try:
        with PunkRecordsClient(cfg.url, cfg.token, cfg.timeout_seconds) as client:
            res = client.post_event(event)
        _print({"ok": True, "result": res, "event_id": event["event_id"]})
        return 0
    except PunkRecordsError as e:
        _print({"ok": False, "error": "punk_records_error", "detail": str(e)})
        return 1


def cmd_context(args: argparse.Namespace) -> int:
    cfg = SkillConfig()
    try:
        with PunkRecordsClient(cfg.url, cfg.token, cfg.timeout_seconds) as client:
            res = client.get_context(
                workspace_id=cfg.workspace_id,
                limit=int(args.limit),
                since=args.since,
            )
        _print({"ok": True, "context": res})
        return 0
    except PunkRecordsError as e:
        _print({"ok": False, "error": "punk_records_error", "detail": str(e)})
        return 1


def cmd_sync_memory(args: argparse.Namespace) -> int:
    cfg = SkillConfig()
    res = sync_memory(cfg, vault_root=args.vault_root)
    _print(res)
    return 0 if res.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clawderpunk")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_emit = sub.add_parser("emit", help="Emit an event into Punk Records")
    p_emit.add_argument("--type", required=True)
    p_emit.add_argument("--payload", required=True, help="JSON payload")
    p_emit.add_argument("--severity", default="low", choices=["low", "medium", "high"])
    p_emit.add_argument("--confidence", default="0.0")
    p_emit.add_argument("--trace-id", default=None)
    p_emit.set_defaults(fn=cmd_emit)

    p_ctx = sub.add_parser("context", help="Fetch a context pack")
    p_ctx.add_argument("--limit", default=10)
    p_ctx.add_argument("--since", default=None, help="ISO timestamp")
    p_ctx.set_defaults(fn=cmd_context)

    p_sync = sub.add_parser("sync-memory", help="Sync generated memory markdown")
    p_sync.add_argument("--vault-root", required=True)
    p_sync.set_defaults(fn=cmd_sync_memory)

    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())

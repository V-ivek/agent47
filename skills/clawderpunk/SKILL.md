---
name: clawderpunk
description: Emit events to Punk Records, fetch Context Packs, and sync governed memory into generated markdown.
metadata:
  openclaw:
    emoji: "📚"
    requires:
      bins: ["clawderpunk"]
      env:
        - CLAWDERPUNK_URL
        - CLAWDERPUNK_TOKEN
        - CLAWDERPUNK_WORKSPACE_ID
    notes:
      - "agent47 is the Stella; satellites emit events; Punk Records stores cumulative knowledge."
---

# Clawderpunk (Punk Records) Skill

Use this skill when you need to:
- **emit** structured events from this agent into Punk Records
- **fetch** a Context Pack for a workspace
- **sync** governed memory projections into local *generated* markdown (never overwriting human files)

## Commands

### `clawderpunk emit`
Emit an event into Punk Records (append-only log).

Examples:

```bash
clawderpunk emit --type decision.recorded --severity medium --confidence 0.9 --payload '{"title":"Decision","body":"We will..."}'
```

### `clawderpunk context`
Fetch a Context Pack for the current workspace.

```bash
clawderpunk context --limit 10 --since 2026-02-01T00:00:00+00:00
```

### `clawderpunk sync-memory`
Sync **generated** memory files to a dedicated directory (single-writer, deterministic output).

- Output directory:
  `(<vault_root>)/memory/punk-records/<workspace_id>/...`
- Never touches:
  - `<vault_root>/MEMORY.md`
  - `<vault_root>/memory/YYYY-MM-DD.md`

```bash
clawderpunk sync-memory --vault-root /path/to/obsidian-vault
```

## Required environment

- `CLAWDERPUNK_URL` — Punk Records base URL (e.g. `https://agent47.cloud/api/punk-records`)
- `CLAWDERPUNK_TOKEN` — bearer token
- `CLAWDERPUNK_WORKSPACE_ID` — workspace id

Optional:
- `CLAWDERPUNK_SATELLITE_ID` — defaults to `openclaw`

## Output format

All commands print **JSON** to stdout.
- Exit code `0` on success
- Exit code `1` on error

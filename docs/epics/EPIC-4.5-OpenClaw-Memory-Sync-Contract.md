# Epic 4.5 — OpenClaw Memory Sync Contract (Generated Memory)

## Goal
Make Punk Records ↔ OpenClaw memory **safe, deterministic, and multi-machine compatible**.

This epic defines the **contract** for how curated memory is materialized into markdown files that
OpenClaw can read—without corrupting human-curated notes or allowing multiple machines to race.

---

## Core Principles

1. **Sync Authority (Single Writer):**
   For any given `(workspace_id, vault_root)`, exactly **one** process is allowed to write generated
   memory files.

2. **Generated ≠ Curated:**
   Generated memory must never overwrite human-authored memory by default. Generated output goes to
   a dedicated directory and can be embedded/linked from curated notes.

3. **Deterministic Output:**
   Same inputs → byte-identical markdown (stable ordering, stable formatting).

4. **Provenance First:**
   Every emitted memory line must include provenance identifiers so we can audit and retract.

---

## Definitions

- **Punk Records:** canonical event+projection service.
- **OpenClaw Vault Root:** filesystem directory containing OpenClaw memory files (e.g. OpenClaw
  workspace root).
- **workspace_id:** logical workspace identifier in Clawderpunk.
- **Sync Authority:** the *only* runner allowed to write the generated markdown for a given
  workspace.

---

## Workspace Mapping (OpenClaw → Clawderpunk)

### Default mapping (recommended)
- `workspace_id = <openclaw sessionKey>` (or a stable hash of it if length/character constraints
  apply).

### Override
- Allow explicit override via env var:
  - `CLAWDERPUNK_WORKSPACE_ID`

**Rule:** Never silently mix multiple OpenClaw sessions into one workspace unless explicitly
configured.

---

## Interfaces (Inputs)

### Required Punk Records endpoints

1. **Context pack** (primary input)
   - `GET /context/{workspace_id}`
   - Returns a compact pack including (at minimum):
     - promoted memory entries
     - recent decisions
     - active tasks
     - high-severity risks

2. **(Optional) Memory list**
   - `GET /memory/{workspace_id}?status=promoted`
   - Used for richer metadata/provenance if context packs are too compact.

### Auth
- Bearer token only (MVP): `Authorization: Bearer <CLAWDERPUNK_TOKEN>`

---

## Output Files (Generated Memory)

All generated files live under:

```
<VaultRoot>/memory/punk-records/<workspace_id>/
```

### Required files

1. **Curated generated memory** (safe to overwrite)

```
<VaultRoot>/memory/punk-records/<workspace_id>/MEMORY.generated.md
```

2. **Daily snapshot** (safe to overwrite for a given day)

```
<VaultRoot>/memory/punk-records/<workspace_id>/daily/YYYY-MM-DD.md
```

### Optional convenience file
A small human-friendly index:

```
<VaultRoot>/memory/punk-records/<workspace_id>/README.md
```

---

## NEVER Overwrite Rules

By default, sync **must not** overwrite:
- `<VaultRoot>/MEMORY.md`
- `<VaultRoot>/memory/YYYY-MM-DD.md`

### If you must integrate with OpenClaw-native files
Only update a fenced owned block:

```md
<!-- BEGIN PUNK_RECORDS GENERATED (workspace_id: …) -->
… generated content …
<!-- END PUNK_RECORDS GENERATED -->
```

Anything outside that block is human-owned and must remain untouched.

---

## Deterministic Markdown Spec

### Ordering
To guarantee idempotency, render entries in stable order:

1. Section order (fixed):
   1) Header
   2) Promoted Memory
   3) Decisions
   4) Active Tasks
   5) Risks
   6) Footer (generation metadata)

2. Within each section:
   - primary sort: `key` (ascending)
   - secondary sort: `promoted_at` (ascending)
   - tiebreaker: `entry_id` (ascending)

If an item lacks `key`, use `entry_id` as primary.

### Rendering rules
- Use LF newlines.
- No trailing whitespace.
- Always end file with a single newline.
- JSON payloads are rendered using **stable JSON**:
  - sorted keys
  - no random whitespace

### Provenance (required per memory entry)
Each memory bullet must include:
- `entry_id`
- `source_event_id` (or the event_id that created it)
- `promoted_at` (or first-seen timestamp)
- `confidence`

Example memory line:

```md
- **shipping.address_format**: "UAE: villa + street"  
  - id: `<entry_id>` | source: `<event_id>` | promoted: `2026-02-08T12:00:00Z` | conf: 0.83
```

### Retractions
- Retracted entries must not appear in the Promoted Memory section.
- Optionally include a “Retracted (last 7d)” section if needed for audit, but default is omit.

### Ephemeral memory
- Ephemeral/TTL-bound entries are **never** written to `MEMORY.generated.md`.
- They may appear in daily snapshots if you explicitly choose to include them.

---

## Templates

### MEMORY.generated.md template

```md
# Punk Records Memory (Generated)

- workspace_id: `<workspace_id>`
- generated_at: `<ISO-8601 UTC>`
- source: Punk Records context pack

## Promoted Memory
- (none)

## Decisions (recent)
- (none)

## Active Tasks
- (none)

## Risks (high/medium)
- (none)

---

> This file is generated. Do not hand-edit.
```

### daily/YYYY-MM-DD.md template

```md
# YYYY-MM-DD — Punk Records Daily Snapshot (Generated)

- workspace_id: `<workspace_id>`
- generated_at: `<ISO-8601 UTC>`

## Events (summary)
- (optional)

## New Promotions
- (none)

## Decisions
- (none)

## Tasks
- (none)

## Risks
- (none)
```

---

## Concurrency + Atomicity

### File lock
Sync Authority must acquire a lock file:

```
<VaultRoot>/memory/punk-records/<workspace_id>/.sync.lock
```

Use an OS-level advisory lock (e.g., `fcntl`) so concurrent syncs don’t interleave.

### Atomic writes
Write to temp, then rename:
- `MEMORY.generated.md.tmp` → `MEMORY.generated.md`
- `daily/YYYY-MM-DD.md.tmp` → `daily/YYYY-MM-DD.md`

---

## Acceptance Criteria

1. Running `sync-memory` twice with unchanged inputs produces **no diff**.
2. Sync never overwrites human-authored memory files by default.
3. Provenance is present on every generated memory entry.
4. Multiple machines can read the generated files safely.
5. If two sync processes start, one blocks/fails cleanly via lock.

---

## Open Decisions

1. Should OpenClaw read generated memory automatically, or only via explicit `get_context` calls?
2. Should daily snapshots include non-promoted/ephemeral items for debugging, or keep them clean?
3. Do we want a "curation" workflow where OpenClaw can propose edits back to Punk Records?

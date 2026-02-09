# Replit Prompt — Clawderpunk UI Console (Punk Records)

Use this prompt in Replit AI (or any coding agent) to generate an MVP UI that works with the *current* Punk Records API, while being extensible through Epic 5.

---

## Prompt

You are building **Clawderpunk Console** — a web UI for the **Punk Records** service (FastAPI backend).

Clawderpunk’s model:
- **agent47 is the “Stella”** (central coordinating mind).
- Multiple **satellite agents** do work and emit events.
- Punk Records stores the cumulative knowledge and serves it back as Context Packs.

### 1) Goal
Create a clean, fast UI that helps the Stella (agent47) and operators **see the system**:
- health status (Kafka + Postgres)
- event log browsing + filters (satellite outputs)
- memory projection browsing (what became durable knowledge)
- context pack preview (what the Stella injects into prompts)
- replay a workspace (rebuild projections)

The UI must be designed to **scale conceptually** as Clawderpunk grows through Epic 5:
- Epic 3: Agent Zero integration (adapters)
- Epic 4: OpenClaw integration
- Epic 4.5: memory sync contract
- Epic 5: observability + scale/hardening

### 2) Backend (already exists)
Punk Records runs at `http://localhost:4701` in dev (see docker-compose.yml). The API requires a bearer token for most endpoints.

**Existing endpoints** (current code):
- `GET /health` (no auth)
- `POST /events` (auth) — emit event (accepts `EventEnvelope`)
- `GET /events?workspace_id=...&type=...&after=...&before=...&limit=...&offset=...` (auth)
- `GET /memory/{workspace_id}?bucket=...&status=...&include_expired=...` (auth)
- `POST /replay/{workspace_id}` (auth)
- `GET /context/{workspace_id}?limit=...&since=...` (auth)

Auth header format:
`Authorization: Bearer <PUNK_RECORDS_API_TOKEN>`

### 3) Tech choices (UI)
Build a **TypeScript** web app.

Preferred stack:
- Next.js (App Router) + React + Tailwind
- No server-side secrets required: store token in localStorage (explicitly show warning that this is dev-only)
- Use `fetch()` with a single API client wrapper
- Use a small component library if needed (shadcn/ui is fine) but keep dependencies minimal

If Next.js is too heavy for Replit, use Vite + React + Tailwind, but keep routing.

### 4) UI requirements
Create a left-nav console with these pages:

**A) Overview (/)**
- Health card: Postgres OK? Kafka OK? overall status
- Quick links to workspaces recently queried (store locally)

**B) Events (/events)**
- Workspace selector (text input)
- Filters: type, after, before
- Pagination (limit + offset)
- Table showing: ts, type, severity, workspace_id, satellite_id, trace_id, event_id
- Expand row → pretty-print payload JSON + copy buttons

**C) Memory (/memory)**
- Workspace selector
- Filters: bucket, status, include_expired
- Table: created_at/updated_at, status, bucket, confidence, title/summary (if present), source_event_id

**D) Context Pack (/context)**
- Workspace selector
- Inputs: limit, since
- Render pack sections: Memory / Decisions / Tasks / Risks

**E) Replay (/replay)**
- Workspace selector
- Button “Replay workspace”
- Show progress + result JSON
- Warn that replay reprocesses events and may be expensive

**F) Emit Event (/emit)**
- A form to submit a basic `EventEnvelope` for testing
- Provide presets for common event types (decision.recorded, memory.candidate, task.created)
- Validate required fields client-side

### 5) Extensibility requirements
Design the code so we can extend later:
- `src/lib/api/` contains an API client module with typed methods.
- `src/lib/models/` contains TypeScript types mirroring the backend models (EventEnvelope, MemoryEntry, ContextPack).
- Feature flags / placeholders for upcoming epic pages:
  - “Satellites” page (Epic 5)
  - “Adapters” page (Epic 3/4)
  - “Observability” page (Epic 5)

Do **not** implement those pages fully; provide scaffold routes + placeholder copy.

### 6) Developer experience
- Add a `.env.example` for `NEXT_PUBLIC_PUNK_RECORDS_URL` (default `http://localhost:4701`) and no token in env.
- Implement a settings panel (top-right) where the user can set:
  - API base URL
  - API token
  Persist both in localStorage.

### 7) UX + visual style
- Dark mode first.
- A crisp, “systems console” look.
- Use clear typography and spacing.
- Use minimal but high-signal color (green/red for health).

### 8) Output
Provide:
- Full runnable codebase
- A short `README.md` for the UI project with:
  - how to run
  - what endpoints it uses
  - screenshots placeholders

### 9) Important constraints
- No backend changes in this task.
- Don’t assume CORS is configured; include instructions for running UI and backend in same environment or via reverse proxy.
- Keep it safe: token is dev-only in local storage; warn users.

---

## Acceptance checklist
- [ ] Can set API URL + token, persists across refresh
- [ ] Overview shows /health status
- [ ] Events page queries and paginates /events
- [ ] Memory page queries /memory/{workspace_id}
- [ ] Context page renders /context/{workspace_id}
- [ ] Replay triggers /replay/{workspace_id}
- [ ] Emit sends POST /events
- [ ] Extensible scaffolding exists for Epics 3–5

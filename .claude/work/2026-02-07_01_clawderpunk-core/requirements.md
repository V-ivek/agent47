# Requirements – Epic 1: Event Backbone & Punk Records Core

**Source**: ROADMAP Phase 1 + EPIC-1-Core-Backbone.md + Tech Spec (sections 3-6, 11-12)

---

## Functional Requirements

### FR-1: Event Backbone (Redpanda/Kafka)
- Single Kafka topic: `clawderpunk.events.v1`
- Partition key: `workspace_id` (ordering guarantee per workspace)
- At-least-once delivery semantics
- Redpanda for local dev (Kafka API compatible)

### FR-2: Event Envelope Schema
All events must conform to this envelope:
- `event_id` (UUID) — unique, used for dedup
- `schema_version` (int) — starts at 1
- `ts` (ISO-8601 UTC)
- `workspace_id` (string)
- `satellite_id` (string)
- `trace_id` (UUID)
- `type` (string, `namespace.action` format)
- `severity` (`low` | `medium` | `high`)
- `confidence` (float, 0.0–1.0)
- `payload` (object, type-specific)

### FR-3: Event Validation
- Strict schema validation on ingestion
- Reject malformed events with clear error
- Secrets redaction before persistence

### FR-4: Punk Records Core Service
- Kafka consumer: consumes from `clawderpunk.events.v1`
- Kafka producer: can emit events
- Persist validated events to Postgres `events` table
- Idempotent writes: deduplicate by `event_id` (INSERT ON CONFLICT DO NOTHING)
- HTTP API: `POST /events` — accept events from external producers
- HTTP API: `GET /health` — health check

### FR-5: Postgres Event Store
- Table `events` with columns per spec (section 6.2)
- Indexes: `(workspace_id, ts)`, `(workspace_id, type, ts)`, `(trace_id)`

### FR-6: Docker Compose Dev Environment
- Services: redpanda, postgres, clawderpunk-records
- Single `docker compose up` to run everything

---

## Non-Functional Requirements

### NFR-1: Restart Safety
- System can restart without data loss
- Kafka consumer resumes from committed offset

### NFR-2: Multi-Machine Safe
- Events emitted from multiple machines must all arrive
- No shared filesystem writes

### NFR-3: Basic Observability
- Health check endpoint
- Structured logging (JSON)
- Validation failure logging

---

## Acceptance Criteria

1. `docker compose up` starts Redpanda + Postgres + Punk Records
2. POST to `/events` with a valid event → event appears in Kafka topic AND Postgres
3. POST duplicate `event_id` → no duplicate in Postgres (idempotent)
4. POST invalid event → 400 error with validation details
5. Punk Records Kafka consumer persists events produced directly to Kafka
6. Service restart → no events lost, consumer resumes
7. Health check returns service status

---

## Out of Scope (Epic 1)

- Projections / read models (Epic 2)
- Memory governance (Epic 2)
- Context Pack API (Epic 2+)
- Agent Zero / OpenClaw integrations (Epics 3-4)
- Replay CLI (Epic 2)
- Satellites

---

## Risks & Open Decisions

| # | Item | Impact | Notes |
|---|------|--------|-------|
| 1 | ~~Language choice~~ | RESOLVED | **Python FastAPI** — aligns with Agent Zero, Pydantic, aiokafka |
| 2 | Redpanda version / config for dev | LOW | Standard docker image should suffice |
| 3 | ~~Auth for /events~~ | RESOLVED | **Basic bearer token** via env var from Epic 1 |

---

## MVP Event Types (reference, all epics)

- `proposal.created`, `decision.recorded`, `risk.detected`, `finding.logged`
- `task.created`, `task.updated`
- `memory.candidate`, `memory.promoted`, `memory.retracted`

Epic 1 needs to validate all these types but only the event flow + persistence matters here.

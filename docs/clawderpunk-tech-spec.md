
# Clawderpunk – Technical Specification
**Version:** 1.0  
**Status:** Draft (Locked for MVP)  
**Last updated:** 2026-02-08

---

## 1. Overview

**Clawderpunk** is a distributed cognitive system inspired by *Vegapunk’s satellites* in *One Piece*.
It provides a **shared, replayable event log + governed memory layer** that multiple AI agent runtimes
can safely connect to, including **Agent Zero** and **OpenClaw**.

The system is built around an immutable event stream (Kafka API via Redpanda for development) and a
central service called **Punk Records**, which acts as the *single source of truth*.

---

## 2. Goals & Non‑Goals

### 2.1 Goals
- Single, append‑only **event log** as source of truth
- **Replayable** state and memory projections
- **Multi‑machine safe** (no shared filesystem writes by agents)
- **Governed memory** (curated, auditable long‑term knowledge)
- First‑class integration with:
  - Agent Zero
  - OpenClaw

### 2.2 Non‑Goals (MVP)
- Rich UI (API + CLI first)
- Full semantic/vector search (keyword + deterministic retrieval initially)
- Automatic sandboxing of third‑party tools (policy + review instead)

---

## 3. High‑Level Architecture

### 3.1 Core Components

1. **Event Backbone**
   - Redpanda (Kafka API compatible) for development
   - Kafka or Redpanda for production

2. **Punk Records (Core Service)**
   - Kafka consumer/producer
   - Event store (Postgres)
   - Projection engine
   - Context Pack API

3. **Satellites**
   - Independent workers (audit, reason, narrate, memory, observe, etc.)
   - Stateless; communicate only via events

4. **Adapters**
   - Agent Zero Tool Adapter
   - OpenClaw Skill/Plugin Adapter

---

## 4. Event Backbone Design

### 4.1 Topics

| Topic | Purpose |
|-----|--------|
| `clawderpunk.events.v1` | Primary immutable event log |

### 4.2 Partitioning
- Partition key: `workspace_id`
- Guarantees ordering within a workspace

### 4.3 Delivery Semantics
- At‑least‑once consumption
- Idempotent writes (dedupe by `event_id`)

---

## 5. Event Model

### 5.1 Envelope Schema

```json
{
  "event_id": "uuid",
  "schema_version": 1,
  "ts": "ISO-8601 UTC",
  "workspace_id": "string",
  "satellite_id": "string",
  "trace_id": "uuid",
  "type": "namespace.action",
  "severity": "low|medium|high",
  "confidence": 0.0,
  "payload": {}
}
```

### 5.2 Required Event Types (MVP)

- `proposal.created`
- `decision.recorded`
- `risk.detected`
- `finding.logged`
- `task.created`
- `task.updated`
- `memory.candidate`
- `memory.promoted`
- `memory.retracted`

---

## 6. Punk Records Service

### 6.1 Responsibilities
- Consume and validate events
- Persist events to Postgres
- Build deterministic projections
- Serve context packs via HTTP API

### 6.2 Event Store Schema

**Table:** `events`

| Column | Type |
|-----|-----|
| event_id | UUID (PK) |
| ts | TIMESTAMP |
| workspace_id | TEXT |
| satellite_id | TEXT |
| trace_id | UUID |
| type | TEXT |
| severity | TEXT |
| confidence | FLOAT |
| payload_json | JSONB |

Indexes:
- `(workspace_id, ts)`
- `(workspace_id, type, ts)`
- `(trace_id)`

---

## 7. Memory Model & Governance

### 7.1 Memory Buckets
- `global`
- `workspace`
- `ephemeral` (TTL‑bound)

### 7.2 Promotion Rules
A `memory.candidate` becomes `memory.promoted` if:
- confidence ≥ 0.75 **AND**
- referenced by ≥ 2 events in 7 days **OR**
- derived from `decision.recorded`

### 7.3 Retraction
- Performed via `memory.retracted`
- Old entries preserved for audit

---

## 8. Context Pack API

### 8.1 Purpose
Provide agents with a **compact, high‑signal context** to inject into prompts.

### 8.2 Contents
- Top relevant memory entries
- Recent decisions
- Active tasks
- High‑severity risks

---

## 9. Agent Zero Integration

### 9.1 Approach
- Custom Python tool: `clawderpunk_tool`
- Runs inside Agent Zero container
- Communicates with Punk Records via HTTP

### 9.2 Tool Surface (MVP)
- `emit_event(...)`
- `get_context(...)`
- `record_decision(...)`
- `create_task(...)`

### 9.3 Workspace Mapping
- Agent Zero project → `workspace_id`

---

## 10. OpenClaw Integration

### 10.1 Approach
- OpenClaw plugin with skills:
  - `clawderpunk_emit_event`
  - `clawderpunk_get_context`
  - `clawderpunk_sync_memory` (optional)

### 10.2 Memory Projection
- Punk Records is the **only writer**
- Writes to:
  - `memory/YYYY-MM-DD.md`
  - `MEMORY.md`
- Prevents multi‑machine corruption

---

## 11. Security

- Strict schema validation
- Allowlisted endpoints only
- Secrets redaction before emitting events
- Token‑based auth between adapters and Punk Records

---

## 12. Deployment (Dev)

**Docker Compose Services**
- redpanda
- postgres
- clawderpunk-records
- optional satellites

---

## 13. Observability

### Metrics
- Kafka consumer lag
- Events/sec
- Projection latency
- Validation failures

### Logs
- Invalid events
- Projection errors
- Replay operations

---

## 14. MVP Milestones

1. Event backbone + Punk Records core
2. Memory governance + projections
3. Agent Zero tool integration
4. OpenClaw plugin integration
5. Replay CLI

---

## 15. Open Decisions (Post‑Review)
- Punk Records language: Python FastAPI vs Node/NestJS
- Markdown projection in MVP or Phase 2
- Derived events topic in MVP

---

**End of Document**

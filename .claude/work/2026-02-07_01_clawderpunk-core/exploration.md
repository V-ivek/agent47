# Exploration – Epic 1: Event Backbone & Punk Records Core

---

## Codebase State

**Greenfield project** — no existing application code. Only:
- `docs/clawderpunk-tech-spec.md` — full tech spec
- `docs/epics/` — ROADMAP + Epic definitions
- `.mcp.json` — MCP server config (Serena + Context7)

---

## Architecture Analysis

### Component Map (Epic 1 scope)

```
┌─────────────────┐      ┌──────────────────────────┐
│   HTTP Client    │──POST──▶  Punk Records (API)    │
│ (agents, CLI)    │      │  ┌─────────────────────┐ │
└─────────────────┘      │  │ Event Validator      │ │
                          │  └─────────┬───────────┘ │
                          │            │ valid        │
                          │  ┌─────────▼───────────┐ │
                          │  │ Kafka Producer       │──────▶ Redpanda
                          │  └─────────────────────┘ │      (clawderpunk.events.v1)
                          │                          │           │
                          │  ┌─────────────────────┐ │           │
                          │  │ Kafka Consumer       │◀───────────┘
                          │  └─────────┬───────────┘ │
                          │            │              │
                          │  ┌─────────▼───────────┐ │
                          │  │ Event Store (PG)     │ │
                          │  │ idempotent upsert    │ │
                          │  └─────────────────────┘ │
                          └──────────────────────────┘
```

### Flow
1. Client POSTs event to `/events` API
2. Punk Records validates schema
3. Valid event → produce to Kafka topic
4. Kafka consumer picks it up → persist to Postgres (dedupe by event_id)
5. Direct Kafka producers (satellites, other services) follow same consumer path

### Why produce-then-consume?
- Single source of truth is the Kafka log
- All events (HTTP + direct Kafka) flow through the same consumer pipeline
- Enables future replay from Kafka offsets

---

## Technology Decisions (Resolved)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Language/Framework** | Python FastAPI | Aligns with Agent Zero, Pydantic for validation, aiokafka proven |
| **Auth in Epic 1** | Basic bearer token | Static token via env var, low effort, prevents open access |

### Stack
- **Web**: FastAPI + uvicorn
- **Kafka**: aiokafka (async producer/consumer)
- **Postgres**: asyncpg (raw queries, no ORM for MVP)
- **Validation**: Pydantic v2
- **Config**: pydantic-settings (env-based)
- **Auth**: Static bearer token from `PUNK_RECORDS_API_TOKEN` env var

---

## Proposed Project Structure

```
clawderpunk/
├── docker-compose.yml
├── pyproject.toml
├── src/
│   └── punk_records/
│       ├── __init__.py
│       ├── main.py              # FastAPI app entry
│       ├── config.py            # Settings (env-based)
│       ├── models/
│       │   └── events.py        # Pydantic event envelope + types
│       ├── api/
│       │   ├── __init__.py
│       │   ├── events.py        # POST /events
│       │   └── health.py        # GET /health
│       ├── kafka/
│       │   ├── __init__.py
│       │   ├── producer.py      # Kafka producer wrapper
│       │   └── consumer.py      # Kafka consumer + persist loop
│       └── store/
│           ├── __init__.py
│           ├── database.py      # asyncpg connection pool
│           └── event_store.py   # Idempotent event persistence
├── migrations/
│   └── 001_create_events.sql
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_api.py
│   └── test_consumer.py
├── Dockerfile
└── docs/
    └── (existing docs)
```

---

## Key Implementation Notes

1. **Pydantic models** enforce the envelope schema at API boundary
2. **aiokafka** for async producer/consumer within the same FastAPI process
3. **asyncpg** for high-performance Postgres access
4. **INSERT ON CONFLICT (event_id) DO NOTHING** for idempotent writes
5. **Consumer runs as background task** in FastAPI lifespan
6. **Alembic** or raw SQL migrations for schema management (raw SQL simpler for MVP)
7. **Redpanda** docker image (`redpandadata/redpanda`) — drop-in Kafka replacement
8. **pydantic-settings** for env-based config (KAFKA_BROKERS, DATABASE_URL, etc.)

---

## Complexity Assessment

**Medium complexity** — well-defined scope, but multiple moving parts:
- Docker Compose orchestration (3 services + health dependencies)
- Kafka producer/consumer lifecycle management
- Async patterns throughout
- Integration testing requires all services running

**Estimate**: ~8-10 implementation tasks

**Recommendation**: Use `/plan` for detailed task breakdown — this is complex enough to warrant a proper ordered plan with dependencies.

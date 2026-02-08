
# Epic 1 – Event Backbone & Punk Records Core

## Goal
Establish Clawderpunk’s immutable source of truth using Kafka (Redpanda for dev) and a reliable Punk Records core service.

## Scope
- Redpanda/Kafka setup
- Punk Records service skeleton
- Event ingestion, validation, persistence
- Idempotent event handling

## Deliverables
- Kafka topic: `clawderpunk.events.v1`
- Punk Records `/events` API
- Postgres-backed event store
- Health checks & basic metrics

## Success Criteria
- Events can be emitted from multiple machines
- Events are persisted exactly-once logically (dedup by event_id)
- System can restart without data loss

## Out of Scope
- Projections
- Agent integrations


# Epic 4 – OpenClaw Integration

## Goal
Integrate Clawderpunk with OpenClaw while preserving OpenClaw’s native memory model.

## Scope
- OpenClaw plugin & skills
- Emit events from OpenClaw conversations
- Fetch context packs
- Optional projection back into OpenClaw memory files

## Deliverables
- OpenClaw skills:
  - clawderpunk_emit_event
  - clawderpunk_get_context
- Safe, single-writer memory projection

## Success Criteria
- OpenClaw sessions contribute to Punk Records
- Curated memory appears in OpenClaw MEMORY.md
- No memory corruption across machines

## Out of Scope
- Third-party skill marketplace distribution


# Epic 3 – Agent Zero Integration

## Goal
Enable Agent Zero to use Clawderpunk as its external memory and event substrate.

## Scope
- Custom Agent Zero tool (`clawderpunk_tool`)
- Event emission from Agent Zero runs
- Context pack retrieval

## Deliverables
- Python tool under Agent Zero `/tools`
- Workspace ↔ Agent Zero project mapping
- Authenticated HTTP calls to Punk Records

## Success Criteria
- Agent Zero can log decisions, findings, tasks
- Context packs influence Agent Zero reasoning
- Multiple Agent Zero instances work concurrently

## Out of Scope
- UI integration in Agent Zero dashboard

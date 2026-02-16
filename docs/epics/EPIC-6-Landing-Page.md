# Epic 6 — Landing Page / Home Page + Flashy README

## Goal
Make Punk Records feel like a real open-source product:
- A strong GitHub presence (flashy README)
- A public landing/home page that explains the vision and links to the live Console + API

## Scope
### 1) GitHub README (product-grade)
- Hero section: 1-liner pitch + “why” + core promises
- Visuals:
  - Architecture mermaid diagram
  - Console screenshots/GIFs (assets committed to repo)
- Quickstart (copy/paste)
- Links:
  - Console UI: https://punk-records-console.replit.app/
  - API base: https://agent47.cloud/api/punk-records
- Roadmap: Epics checklist
- Contributing section (optional in Epic 6 or follow-up)

### 2) Landing page options
Pick one implementation path:
- **A) MkDocs + GitHub Pages** (fastest, consistent with docs)
- **B) Static site (Astro/Next) + Vercel/Netlify** (flashiest)
- **C) Nginx-served static HTML** (simple, manual)

Deliverables should be compatible with later Epics (3–5) and highlight Stella/satellites model.

## Deliverables
- New/updated README.md
- `docs/index.md` updated to function as a home page
- `/docs/assets/` (or `/assets/`) with images used by both README + docs
- If deploying:
  - GitHub Pages config or deploy workflow (depending on option)

## Success Criteria
- New visitors understand in <60 seconds:
  - what Punk Records is
  - why it exists (event backbone + governed memory)
  - how to run it + where to see it
- Console UI and API links are prominent
- Repo looks “alive” and credible (visuals, quickstart, roadmap)

## Out of Scope
- Full marketing site with pricing, auth flows, etc.
- Enterprise multi-tenant UI

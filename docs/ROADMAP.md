# Roadmap

## Current State (v0.1 — April 2026)

### Shared Infrastructure
- [x] Transport abstraction (stdio + SSE)
- [x] OAuth 2.0 with consent page
- [x] Security: path sandboxing, audit logging, read-only mode
- [x] Generic CLI subprocess runner
- [x] Monorepo structure with editable install

### Servers
- [x] **GitHub** (40 tools) — repos, branches, PRs, issues, workflows, releases, gists
- [x] **Freelance Job Search** (7 tools) — 8 platforms, skill matching, notifications

---

## Short-Term (v0.2 — Next 2-4 weeks)

### Freelance Server Improvements
- [ ] Persistent job history (SQLite or JSON file)
- [ ] Application tracking (applied, interviewing, rejected, accepted)
- [ ] Proposal/cover letter generation tool (uses Claude to draft based on job + profile)
- [ ] Custom scraper resilience (retry logic, proxy rotation for Arc.dev/Dice)
- [ ] LinkedIn adapter via Proxycurl or browser automation
- [ ] Rate trend analysis (track $/hr over time for skills)
- [ ] Scheduled search via GitHub Actions (already has workflow, needs monorepo path fix)

### New Servers
- [ ] **Slack MCP** — channels, messages, search, DMs (via Slack CLI or API)
- [ ] **Calendar MCP** — Google Calendar / Outlook integration
- [ ] **Notes/Obsidian MCP** — read/write markdown notes, search knowledge base

### Infrastructure
- [ ] `mcp-shared` CLI tool: `mcp-new <name>` to scaffold a new server
- [ ] Shared test harness: test any server's tools programmatically
- [ ] Docker support: Dockerfile per server for cloud deployment
- [ ] Rate limiting middleware for SSE transport

---

## Medium-Term (v0.3 — 1-3 months)

### Freelance Ecosystem
- [ ] **Connector Hub**: Bidirectional integrations between freelance platforms
  - Auto-apply to Upwork jobs matching criteria
  - Sync proposals across platforms
  - Track responses and conversion rates
- [ ] **Portfolio MCP**: Manage portfolio site content, case studies, testimonials
- [ ] **Invoice MCP**: Time tracking, invoice generation, payment tracking
- [ ] **Client CRM MCP**: Track leads, communications, project history

### New Servers
- [ ] **AWS MCP** — S3, Lambda, EC2 management (via AWS CLI)
- [ ] **Docker MCP** — container management, logs, deployment
- [ ] **Database MCP** — query, migrate, backup (PostgreSQL, MongoDB)
- [ ] **Email MCP** — Gmail/Outlook read, compose, search

### Infrastructure
- [ ] Azure deployment (using $100 credit)
  - Container Apps for SSE servers
  - Azure Key Vault for secrets
  - Application Insights for monitoring
- [ ] Persistent OAuth storage (Redis or SQLite, replacing in-memory)
- [ ] Multi-server launcher: single command to start multiple servers
- [ ] Health check dashboard: status of all running servers

---

## Long-Term (v1.0 — 3-6 months)

### Platform
- [ ] Public MCP server registry (like npm for MCP servers)
- [ ] Composable server chains (output of one server feeds into another)
- [ ] WebSocket transport for real-time bidirectional tools
- [ ] Multi-user support with proper OAuth (not just password consent)

### Freelance Vision
- [ ] Full freelancing lifecycle in Claude:
  1. Search jobs → 2. Match & rank → 3. Generate proposal → 4. Apply → 5. Track → 6. Invoice → 7. Get paid
- [ ] ML-based job matching (learn from accept/reject patterns)
- [ ] Market rate intelligence (aggregate rate data across platforms)

---

## Decision Log

| Date | Decision | Reasoning |
|------|----------|-----------|
| 2026-04-03 | Monorepo over separate repos | Single-owner project, shared code changes need instant propagation |
| 2026-04-03 | `pip install -e` over plugin loading | Simplest mechanism, standard Python packaging |
| 2026-04-03 | In-memory OAuth over database | Personal use, restart = re-auth is acceptable |
| 2026-04-03 | SSE over Streamable HTTP | Claude.ai uses SSE transport (confirmed via ngrok logs) |
| 2026-04-03 | Password consent over full OAuth UI | Personal use, security-by-obscurity (tunnel URL) + password is sufficient |

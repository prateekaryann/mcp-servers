# Freelance Job Search MCP Server

Searches **8 freelance job platforms** concurrently and matches jobs against your skill profile.

## Platforms

| Platform | Method | Status |
|----------|--------|--------|
| RemoteOK | JSON API | Active |
| We Work Remotely | RSS | Active |
| Upwork | RSS | Active |
| Freelancer.com | Public API | Active |
| Indeed | RSS | Active |
| Arc.dev | Web scraper | Fragile |
| Dice.com | HTML parser | Fragile |
| LinkedIn | Limited API | Needs auth |

## Prerequisites

- Python 3.10+
- `pip install -e ./shared` (from monorepo root)
- `pip install httpx pydantic defusedxml python-dotenv anyio`

## Quick Start

```bash
cd servers/freelance
python server.py
```

## Tools (7)

| Tool | Description |
|------|-------------|
| `search_jobs` | Search across all platforms with filters |
| `rank_jobs_by_match` | Score cached jobs against your profile |
| `quick_search` | Search + rank in one call |
| `get_job_details` | Full details for a specific job |
| `update_profile` | Update skills/domains/rate |
| `get_profile` | View current profile |
| `get_stats` | Platform stats and cache info |

## Configuration

Edit `config.py` to set your skills, domains, and preferred rate.

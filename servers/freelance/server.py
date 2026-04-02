#!/usr/bin/env python3
"""
Freelance Job Search MCP Server

Searches 8+ freelance job platforms and matches jobs against your skill profile.

Platforms: RemoteOK, We Work Remotely, Upwork, Freelancer.com, Indeed, Arc.dev, Dice, LinkedIn

Usage:
    python server.py
"""

import asyncio
import json
import logging
from typing import List, Optional
from datetime import datetime

from mcp_shared import create_server, run_server, log_tool_call

from models import (
    Job,
    JobSearchParams,
    Platform,
    JobType,
    ExperienceLevel,
    UserProfile,
    MatchResult,
)
from adapters import JobAggregator, ADAPTERS
from matching import SkillMatcher
from config import DEFAULT_PROFILE, DEFAULT_SEARCH_KEYWORDS

# Create server (transport configured via MCP_TRANSPORT env var)
mcp = create_server("freelance-jobs")

# Global state
_aggregator: Optional[JobAggregator] = None
_profile: UserProfile = DEFAULT_PROFILE
_cached_jobs: List[Job] = []
_last_search_time: Optional[datetime] = None
logger = logging.getLogger("freelance-jobs")


def get_aggregator() -> JobAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = JobAggregator()
    return _aggregator


# =============================================================================
# TOOLS
# =============================================================================

@mcp.tool(description="""
Search for freelance jobs across multiple platforms.

Searches RemoteOK, We Work Remotely, Upwork, Freelancer, Indeed, Arc.dev, Dice
for jobs matching your criteria.

Args:
    keywords: Keywords to search for (e.g., ["FastAPI", "Python", "AWS"])
    skills: Skills to match (e.g., ["React", "TypeScript"])
    platforms: Platforms to search (default: all). Options: remoteok, weworkremotely, upwork, freelancer, indeed, arcdev, dice, linkedin
    min_rate: Minimum hourly rate in USD
    max_results: Maximum number of results (default: 30)
    posted_within_hours: Only jobs posted within this many hours (default: 168 = 1 week)
""")
async def search_jobs(
    keywords: List[str] = None,
    skills: List[str] = None,
    platforms: List[str] = None,
    min_rate: float = None,
    max_results: int = 30,
    posted_within_hours: int = 168,
) -> str:
    """Search for freelance jobs"""
    global _cached_jobs, _last_search_time
    log_tool_call("search_jobs", keywords=str(keywords), platforms=str(platforms), max_results=max_results)

    if not keywords and not skills:
        keywords = DEFAULT_SEARCH_KEYWORDS[:5]
        skills = _profile.primary_skills[:5]

    platform_enums = []
    if platforms:
        for p in platforms:
            try:
                platform_enums.append(Platform(p.lower()))
            except ValueError:
                logger.warning(f"Unknown platform: {p}")
    else:
        platform_enums = list(ADAPTERS.keys())

    params = JobSearchParams(
        keywords=keywords or [],
        skills=skills or [],
        platforms=platform_enums,
        min_rate=min_rate,
        max_results=max_results,
        posted_within_hours=posted_within_hours,
        remote_only=True,
    )

    aggregator = get_aggregator()
    jobs = await aggregator.search(params)

    _cached_jobs = jobs
    _last_search_time = datetime.utcnow()

    if not jobs:
        return json.dumps({"status": "success", "message": "No jobs found", "total": 0, "jobs": []}, indent=2)

    job_dicts = []
    for job in jobs[:max_results]:
        job_dicts.append({
            "id": job.id,
            "platform": job.platform,
            "title": job.title,
            "company": job.company,
            "url": str(job.url),
            "skills": job.skills[:10],
            "job_type": job.job_type,
            "rate": f"${job.rate_min}-{job.rate_max}" if job.rate_min else "Not specified",
            "posted": job.posted_at.isoformat() if job.posted_at else "Unknown",
            "description_preview": job.description[:300] + "..." if len(job.description) > 300 else job.description,
        })

    return json.dumps({
        "status": "success",
        "total": len(jobs),
        "platforms_searched": [p.value for p in platform_enums],
        "jobs": job_dicts
    }, indent=2)


@mcp.tool(description="""
Score and rank jobs against your skill profile.
Takes cached search results and scores based on skill matches, domain expertise, and rate.
""")
async def rank_jobs_by_match(top_n: int = 10) -> str:
    """Score and rank jobs against profile"""
    log_tool_call("rank_jobs_by_match", top_n=top_n)

    if not _cached_jobs:
        return json.dumps({"status": "error", "message": "No cached jobs. Run search_jobs first."})

    matcher = SkillMatcher(_profile)
    results = matcher.rank_jobs(_cached_jobs)

    ranked = []
    for result in results[:top_n]:
        ranked.append({
            "rank": len(ranked) + 1,
            "score": result.overall_score,
            "title": result.job.title,
            "company": result.job.company,
            "platform": result.job.platform,
            "url": str(result.job.url),
            "matched_skills": result.matched_primary_skills + result.matched_secondary_skills,
            "matched_domains": result.matched_domains,
            "missing_skills": result.missing_skills,
            "recommendation": result.recommendation,
            "rate": f"${result.job.rate_min}-{result.job.rate_max}" if result.job.rate_min else "Not specified",
        })

    return json.dumps({
        "status": "success",
        "profile_name": _profile.name,
        "total_scored": len(results),
        "ranked_jobs": ranked
    }, indent=2)


@mcp.tool(description="Get detailed information about a specific job by ID.")
async def get_job_details(job_id: str) -> str:
    """Get details for a specific job"""
    log_tool_call("get_job_details", job_id=job_id)

    for job in _cached_jobs:
        if job.id == job_id:
            return json.dumps({
                "status": "success",
                "job": {
                    "id": job.id, "platform": job.platform, "title": job.title,
                    "company": job.company, "url": str(job.url), "description": job.description,
                    "skills": job.skills, "job_type": job.job_type,
                    "rate_min": job.rate_min, "rate_max": job.rate_max, "currency": job.currency,
                    "location": job.location, "is_remote": job.is_remote,
                    "posted_at": job.posted_at.isoformat() if job.posted_at else None,
                }
            }, indent=2)

    return json.dumps({"status": "error", "message": f"Job {job_id} not found in cache. Run search_jobs first."})


@mcp.tool(description="Update your skill profile for better job matching.")
async def update_profile(
    primary_skills: List[str] = None,
    secondary_skills: List[str] = None,
    domains: List[str] = None,
    min_rate: float = None,
) -> str:
    """Update the user profile"""
    global _profile
    log_tool_call("update_profile", primary_skills=str(primary_skills), domains=str(domains), min_rate=min_rate)

    updates = {}
    if primary_skills is not None:
        _profile.primary_skills = primary_skills
        updates["primary_skills"] = primary_skills
    if secondary_skills is not None:
        _profile.secondary_skills = secondary_skills
        updates["secondary_skills"] = secondary_skills
    if domains is not None:
        _profile.domains = domains
        updates["domains"] = domains
    if min_rate is not None:
        _profile.preferred_rate_min = min_rate
        updates["preferred_rate_min"] = min_rate

    return json.dumps({"status": "success", "message": "Profile updated", "updates": updates}, indent=2)


@mcp.tool(description="Get current skill profile used for job matching")
async def get_profile() -> str:
    """Get the current profile"""
    log_tool_call("get_profile")
    return json.dumps({
        "name": _profile.name,
        "primary_skills": _profile.primary_skills,
        "secondary_skills": _profile.secondary_skills,
        "domains": _profile.domains,
        "preferred_rate_min": _profile.preferred_rate_min,
        "experience_years": _profile.experience_years,
        "excluded_keywords": _profile.excluded_keywords,
    }, indent=2)


@mcp.tool(description="Get statistics about available platforms and last search.")
async def get_stats() -> str:
    """Get server statistics"""
    log_tool_call("get_stats")
    return json.dumps({
        "available_platforms": [p.value for p in ADAPTERS.keys()],
        "cached_jobs": len(_cached_jobs),
        "last_search": _last_search_time.isoformat() if _last_search_time else None,
        "profile_loaded": _profile.name,
    }, indent=2)


@mcp.tool(description="Quick search + rank in one call. Uses your default profile skills.")
async def quick_search(max_results: int = 15) -> str:
    """Quick search with default profile"""
    log_tool_call("quick_search", max_results=max_results)
    await search_jobs(
        keywords=DEFAULT_SEARCH_KEYWORDS[:3],
        skills=_profile.primary_skills[:5],
        max_results=50,
        posted_within_hours=168,
    )
    return await rank_jobs_by_match(top_n=max_results)


# =============================================================================
# RUN SERVER
# =============================================================================

if __name__ == "__main__":
    run_server(mcp)

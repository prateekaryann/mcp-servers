#!/usr/bin/env python3
"""
Scheduled Job Search Runner

Run this script via cron or GitHub Actions to periodically
search for new jobs and send notifications.

Usage:
    python run_scheduled.py
    
Environment Variables:
    TELEGRAM_BOT_TOKEN - Telegram bot token
    TELEGRAM_CHAT_ID - Telegram chat ID
    DISCORD_WEBHOOK_URL - Discord webhook URL (optional)
    
Cron Example (every 6 hours):
    0 */6 * * * cd /path/to/freelance-job-mcp && python run_scheduled.py

GitHub Actions Example:
    name: Job Search
    on:
      schedule:
        - cron: '0 */6 * * *'
      workflow_dispatch:
    jobs:
      search:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with:
              python-version: '3.11'
          - run: pip install -r requirements.txt
          - run: python run_scheduled.py
            env:
              TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
              TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
"""

import asyncio
import json
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

from models import Job, JobSearchParams, Platform
from adapters import JobAggregator, ADAPTERS
from matching import SkillMatcher
from notifications import TelegramNotifier, DiscordNotifier, notify_all
from config import DEFAULT_PROFILE, DEFAULT_SEARCH_KEYWORDS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("scheduled-search")

# File to track seen jobs
SEEN_JOBS_FILE = Path(__file__).parent / ".seen_jobs.json"


def load_seen_jobs() -> Set[str]:
    """Load set of previously seen job IDs"""
    if SEEN_JOBS_FILE.exists():
        try:
            with open(SEEN_JOBS_FILE) as f:
                data = json.load(f)
                # Clean old entries (older than 7 days)
                cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
                return {
                    job_id for job_id, timestamp in data.items()
                    if timestamp > cutoff
                }
        except Exception as e:
            logger.warning(f"Failed to load seen jobs: {e}")
    return set()


def save_seen_jobs(seen: Set[str], new_jobs: List[Job]):
    """Save updated set of seen job IDs"""
    try:
        # Load existing
        existing = {}
        if SEEN_JOBS_FILE.exists():
            with open(SEEN_JOBS_FILE) as f:
                existing = json.load(f)
        
        # Add new jobs
        now = datetime.utcnow().isoformat()
        for job in new_jobs:
            existing[job.id] = now
        
        # Keep only recent entries
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
        existing = {k: v for k, v in existing.items() if v > cutoff}
        
        with open(SEEN_JOBS_FILE, "w") as f:
            json.dump(existing, f)
            
    except Exception as e:
        logger.warning(f"Failed to save seen jobs: {e}")


async def run_search() -> tuple[List[Job], List[Job]]:
    """
    Run job search and identify new jobs
    
    Returns:
        Tuple of (all_jobs, new_jobs)
    """
    logger.info("Starting scheduled job search...")
    
    # Load previously seen jobs
    seen_ids = load_seen_jobs()
    logger.info(f"Loaded {len(seen_ids)} previously seen job IDs")
    
    # Build search params
    params = JobSearchParams(
        keywords=DEFAULT_SEARCH_KEYWORDS[:5],
        skills=DEFAULT_PROFILE.primary_skills[:8],
        platforms=list(ADAPTERS.keys()),
        min_rate=DEFAULT_PROFILE.preferred_rate_min,
        max_results=100,
        posted_within_hours=48,  # Last 2 days
        remote_only=True,
    )
    
    # Search
    aggregator = JobAggregator()
    all_jobs = await aggregator.search(params)
    await aggregator.close()
    
    logger.info(f"Found {len(all_jobs)} total jobs")
    
    # Filter to new jobs only
    new_jobs = [job for job in all_jobs if job.id not in seen_ids]
    logger.info(f"Found {len(new_jobs)} new jobs")
    
    # Save updated seen jobs
    save_seen_jobs(seen_ids, all_jobs)
    
    return all_jobs, new_jobs


async def score_and_notify(all_jobs: List[Job], new_jobs: List[Job]):
    """Score jobs and send notifications"""
    
    if not new_jobs:
        logger.info("No new jobs to notify about")
        return
    
    # Score new jobs
    matcher = SkillMatcher(DEFAULT_PROFILE)
    results = matcher.rank_jobs(new_jobs)
    
    # Filter to good matches only (score >= 50)
    good_matches = [r for r in results if r.overall_score >= 50]
    
    if not good_matches:
        logger.info("No jobs above score threshold")
        return
    
    logger.info(f"Found {len(good_matches)} jobs above threshold")
    
    # Send notifications
    telegram = TelegramNotifier()
    
    if telegram.is_configured:
        # Send top matches
        await telegram.notify_top_matches(
            good_matches[:5],
            title=f"🎯 {len(good_matches)} New Job Matches!"
        )
        
        # If many good matches, also send a summary
        if len(good_matches) > 5:
            platforms = list(set(r.job.platform for r in good_matches))
            await telegram.notify_daily_summary(
                total_searched=len(all_jobs),
                new_jobs=len(new_jobs),
                top_match_score=good_matches[0].overall_score if good_matches else 0,
                platforms=platforms,
            )
        
        await telegram.close()
        logger.info("Sent Telegram notifications")
    else:
        logger.warning("Telegram not configured, skipping notifications")
        # Print to console instead
        print("\n" + "="*60)
        print(f"TOP JOB MATCHES ({len(good_matches)} found)")
        print("="*60)
        
        for i, match in enumerate(good_matches[:10], 1):
            job = match.job
            print(f"\n{i}. [{match.overall_score:.0f}%] {job.title}")
            print(f"   Company: {job.company}")
            print(f"   Platform: {job.platform}")
            print(f"   Skills: {', '.join(match.matched_primary_skills[:5])}")
            print(f"   URL: {job.url}")
        
        print("\n" + "="*60)


async def main():
    """Main entry point"""
    try:
        all_jobs, new_jobs = await run_search()
        await score_and_notify(all_jobs, new_jobs)
        logger.info("Scheduled search completed successfully")
        
    except Exception as e:
        logger.error(f"Scheduled search failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

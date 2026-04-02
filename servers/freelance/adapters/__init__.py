"""
Platform Adapters for Freelance Job Search
"""

from typing import List, Dict, Type
import asyncio
import logging

from models import Job, JobSearchParams, Platform

from .base import BaseAdapter, TECH_SKILLS
from .remoteok import RemoteOKAdapter
from .weworkremotely import WeWorkRemotelyAdapter
from .freelancer import FreelancerAdapter
from .upwork import UpworkAdapter
from .linkedin import LinkedInAdapter
from .indeed import IndeedAdapter
from .arcdev import ArcDevAdapter

logger = logging.getLogger(__name__)

# Registry of all available adapters
ADAPTERS: Dict[Platform, Type[BaseAdapter]] = {
    Platform.REMOTEOK: RemoteOKAdapter,
    Platform.WEWORKREMOTELY: WeWorkRemotelyAdapter,
    Platform.FREELANCER: FreelancerAdapter,
    Platform.UPWORK: UpworkAdapter,
    Platform.LINKEDIN: LinkedInAdapter,
    Platform.INDEED: IndeedAdapter,
    Platform.ARC_DEV: ArcDevAdapter,
}


class JobAggregator:
    """
    Aggregates job results from multiple platforms
    """
    
    def __init__(self, platforms: List[Platform] = None):
        """
        Initialize the aggregator
        
        Args:
            platforms: List of platforms to search. If None, uses all available.
        """
        if platforms is None:
            platforms = list(ADAPTERS.keys())
        
        self.adapters: Dict[Platform, BaseAdapter] = {}
        
        for platform in platforms:
            if platform in ADAPTERS:
                self.adapters[platform] = ADAPTERS[platform]()
            else:
                logger.warning(f"Unknown platform: {platform}")
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search all platforms concurrently and aggregate results
        
        Returns:
            List of jobs sorted by posted date (most recent first)
        """
        # Filter to only requested platforms
        active_adapters = {
            p: a for p, a in self.adapters.items()
            if p in params.platforms
        }
        
        if not active_adapters:
            logger.warning("No active adapters for requested platforms")
            return []
        
        # Search all platforms concurrently
        tasks = []
        for platform, adapter in active_adapters.items():
            task = asyncio.create_task(
                self._search_platform(adapter, params),
                name=f"search_{platform.value}"
            )
            tasks.append((platform, task))
        
        # Gather results
        all_jobs = []
        for platform, task in tasks:
            try:
                jobs = await task
                all_jobs.extend(jobs)
                logger.info(f"[{platform.value}] Returned {len(jobs)} jobs")
            except Exception as e:
                logger.error(f"[{platform.value}] Failed: {e}")
        
        # Deduplicate by title + company (some jobs cross-posted)
        seen = set()
        unique_jobs = []
        for job in all_jobs:
            key = f"{job.title.lower()}_{job.company.lower() if job.company else ''}"
            if key not in seen:
                seen.add(key)
                unique_jobs.append(job)
        
        # Sort by posted date (most recent first)
        unique_jobs.sort(
            key=lambda j: j.posted_at or datetime.min,
            reverse=True
        )
        
        # Limit results
        return unique_jobs[:params.max_results]
    
    async def _search_platform(self, adapter: BaseAdapter, params: JobSearchParams) -> List[Job]:
        """Search a single platform with error handling"""
        try:
            return await adapter.search(params)
        except Exception as e:
            logger.error(f"[{adapter.platform}] Search error: {e}")
            return []
    
    async def close(self):
        """Close all adapter connections"""
        for adapter in self.adapters.values():
            try:
                await adapter.close()
            except Exception as e:
                logger.debug(f"Error closing adapter: {e}")


# Need this import for datetime.min
from datetime import datetime

__all__ = [
    "BaseAdapter",
    "TECH_SKILLS",
    "RemoteOKAdapter",
    "WeWorkRemotelyAdapter",
    "FreelancerAdapter",
    "UpworkAdapter",
    "LinkedInAdapter",
    "IndeedAdapter",
    "ArcDevAdapter",
    "ADAPTERS",
    "JobAggregator",
]

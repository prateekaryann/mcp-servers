"""
RemoteOK Adapter - Uses their public JSON API
https://remoteok.com/api
"""

from typing import List, Optional
from datetime import datetime
import logging

from models import Job, JobSearchParams, Platform, JobType
from .base import BaseAdapter, TECH_SKILLS

logger = logging.getLogger(__name__)


class RemoteOKAdapter(BaseAdapter):
    """Adapter for RemoteOK.com - Has a free public JSON API"""
    
    platform = Platform.REMOTEOK
    base_url = "https://remoteok.com"
    rate_limit_delay = 2.0  # Be respectful
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search RemoteOK jobs via their JSON API
        
        API endpoint: https://remoteok.com/api
        Returns JSON array of jobs
        """
        jobs = []
        
        try:
            # RemoteOK's API is simple - just returns all recent jobs
            response = await self._get(f"{self.base_url}/api")
            data = response.json()
            
            # First element is a legal notice, skip it
            job_listings = data[1:] if len(data) > 1 else []
            
            for listing in job_listings:
                try:
                    job = self._parse_job(listing)
                    
                    # Apply filters
                    if not self._matches_filters(job, params):
                        continue
                    
                    jobs.append(job)
                    
                    if len(jobs) >= params.max_results:
                        break
                        
                except Exception as e:
                    logger.warning(f"Failed to parse RemoteOK job: {e}")
                    continue
            
            logger.info(f"[RemoteOK] Found {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"[RemoteOK] Search failed: {e}")
        
        return jobs
    
    def _parse_job(self, data: dict) -> Job:
        """Parse RemoteOK job listing into unified Job model"""
        
        # Parse posted date
        posted_at = None
        if data.get("date"):
            try:
                posted_at = datetime.fromisoformat(data["date"].replace("Z", "+00:00"))
            except:
                pass
        
        # Extract skills from tags and description
        tags = data.get("tags", []) or []
        description = data.get("description", "") or ""
        extracted_skills = self._extract_skills(description, TECH_SKILLS)
        all_skills = list(set(tags + extracted_skills))
        
        # Parse salary/rate
        salary_min = data.get("salary_min")
        salary_max = data.get("salary_max")
        
        # Determine job type
        job_type = JobType.FULL_TIME  # RemoteOK is mostly full-time
        position = (data.get("position") or "").lower()
        if "contract" in position or "freelance" in position:
            job_type = JobType.CONTRACT
        elif "part-time" in position or "part time" in position:
            job_type = JobType.PART_TIME
        
        return Job(
            id=f"remoteok_{data.get('id', data.get('slug', 'unknown'))}",
            platform=Platform.REMOTEOK,
            url=data.get("url", f"{self.base_url}/remote-jobs/{data.get('slug', '')}"),
            title=data.get("position", "Unknown Position"),
            company=data.get("company", "Unknown Company"),
            description=description[:5000],  # Truncate long descriptions
            skills=all_skills,
            job_type=job_type,
            rate_min=float(salary_min) / 2080 if salary_min else None,  # Convert annual to hourly
            rate_max=float(salary_max) / 2080 if salary_max else None,
            currency="USD",
            is_remote=True,
            location=data.get("location", "Remote"),
            posted_at=posted_at,
        )
    
    def _matches_filters(self, job: Job, params: JobSearchParams) -> bool:
        """Check if job matches search parameters"""
        
        # Keyword matching
        if params.keywords:
            text = f"{job.title} {job.description} {' '.join(job.skills)}".lower()
            if not any(kw.lower() in text for kw in params.keywords):
                return False
        
        # Skill matching
        if params.skills:
            job_skills_lower = [s.lower() for s in job.skills]
            if not any(s.lower() in job_skills_lower for s in params.skills):
                return False
        
        # Rate filtering
        if params.min_rate and job.rate_max and job.rate_max < params.min_rate:
            return False
        
        # Posted date filtering
        if params.posted_within_hours and job.posted_at:
            hours_ago = (datetime.utcnow() - job.posted_at).total_seconds() / 3600
            if hours_ago > params.posted_within_hours:
                return False
        
        return True
    
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """Get details for a specific job"""
        # RemoteOK doesn't have individual job API, return None
        # Jobs are returned with full details in search
        return None

"""
Freelancer.com Adapter - Uses their public API
https://developers.freelancer.com/

Note: Some endpoints require OAuth, but job search is public
"""

from typing import List, Optional
from datetime import datetime
import logging

from models import Job, JobSearchParams, Platform, JobType
from .base import BaseAdapter, TECH_SKILLS

logger = logging.getLogger(__name__)


class FreelancerAdapter(BaseAdapter):
    """Adapter for Freelancer.com - Uses their public API"""
    
    platform = Platform.FREELANCER
    base_url = "https://www.freelancer.com/api"
    rate_limit_delay = 1.0
    
    # Skill ID mappings for common tech skills
    SKILL_IDS = {
        "python": 13,
        "javascript": 17,
        "react": 813,
        "nodejs": 507,
        "aws": 579,
        "docker": 903,
        "kubernetes": 1173,
        "typescript": 1113,
        "fastapi": 1847,  # May need verification
        "django": 22,
        "flask": 507,
        "postgresql": 97,
        "mongodb": 365,
        "machine learning": 671,
        "data science": 1059,
    }
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search Freelancer.com via their API
        
        API Docs: https://developers.freelancer.com/docs/projects/project-search
        """
        jobs = []
        
        try:
            # Build query parameters
            query_params = {
                "limit": min(params.max_results, 100),
                "offset": 0,
                "project_types[]": ["fixed", "hourly"],
                "full_description": "true",
                "job_details": "true",
                "user_details": "true",
                "compact": "false",
            }
            
            # Add keyword query
            if params.keywords:
                query_params["query"] = " ".join(params.keywords)
            elif params.skills:
                query_params["query"] = " ".join(params.skills[:5])
            
            # Add skill IDs if we can map them
            skill_ids = []
            for skill in params.skills:
                skill_lower = skill.lower()
                if skill_lower in self.SKILL_IDS:
                    skill_ids.append(self.SKILL_IDS[skill_lower])
            
            if skill_ids:
                query_params["jobs[]"] = skill_ids[:10]  # Max 10 skills
            
            # Min budget filter
            if params.min_rate:
                query_params["min_avg_hourly_rate"] = int(params.min_rate)
            
            response = await self._get(
                f"{self.base_url}/projects/0.1/projects/active",
                params=query_params
            )
            
            data = response.json()
            
            if data.get("status") == "success" and data.get("result", {}).get("projects"):
                for project in data["result"]["projects"]:
                    try:
                        job = self._parse_project(project)
                        
                        if self._matches_filters(job, params):
                            jobs.append(job)
                            
                    except Exception as e:
                        logger.debug(f"Failed to parse Freelancer project: {e}")
                        continue
            
            logger.info(f"[Freelancer] Found {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"[Freelancer] Search failed: {e}")
        
        return jobs[:params.max_results]
    
    def _parse_project(self, data: dict) -> Job:
        """Parse Freelancer project into Job model"""
        
        # Parse dates
        posted_at = None
        if data.get("time_submitted"):
            try:
                posted_at = datetime.fromtimestamp(data["time_submitted"])
            except:
                pass
        
        # Get budget info
        budget = data.get("budget", {})
        rate_min = budget.get("minimum")
        rate_max = budget.get("maximum")
        
        # Determine job type
        job_type = JobType.FIXED
        if data.get("type") == "hourly" or data.get("hourly_project_info"):
            job_type = JobType.HOURLY
            # For hourly, use hourly rates
            hourly_info = data.get("hourly_project_info", {})
            if hourly_info:
                rate_min = hourly_info.get("commitment", {}).get("minimum")
                rate_max = hourly_info.get("commitment", {}).get("maximum")
        
        # Extract skills from job IDs
        skills = []
        for job in data.get("jobs", []):
            if isinstance(job, dict):
                skill_name = job.get("name", "")
                if skill_name:
                    skills.append(skill_name)
        
        # Also extract from description
        description = data.get("description", "") or data.get("preview_description", "")
        extracted_skills = self._extract_skills(description, TECH_SKILLS)
        skills = list(set(skills + extracted_skills))
        
        # Currency
        currency = data.get("currency", {}).get("code", "USD")
        
        # Build URL
        seo_url = data.get("seo_url", f"project/{data.get('id')}")
        url = f"https://www.freelancer.com/projects/{seo_url}"
        
        return Job(
            id=f"freelancer_{data.get('id')}",
            platform=Platform.FREELANCER,
            url=url,
            title=data.get("title", "Unknown Project"),
            company=data.get("owner", {}).get("username", "Unknown"),
            description=description[:5000],
            skills=skills,
            job_type=job_type,
            rate_min=float(rate_min) if rate_min else None,
            rate_max=float(rate_max) if rate_max else None,
            currency=currency,
            is_remote=True,
            location="Remote",
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
            text_lower = job.description.lower() + " " + job.title.lower()
            
            # Check both skill list and description
            has_skill = any(
                s.lower() in job_skills_lower or s.lower() in text_lower 
                for s in params.skills
            )
            if not has_skill:
                return False
        
        # Rate filtering (for fixed, rate is total; for hourly, it's per hour)
        if params.min_rate and job.rate_max:
            # For fixed projects, don't filter by hourly rate
            if job.job_type == JobType.HOURLY and job.rate_max < params.min_rate:
                return False
        
        # Posted date filtering
        if params.posted_within_hours and job.posted_at:
            hours_ago = (datetime.utcnow() - job.posted_at).total_seconds() / 3600
            if hours_ago > params.posted_within_hours:
                return False
        
        return True
    
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """Get detailed project information"""
        
        # Extract numeric ID
        project_id = job_id.replace("freelancer_", "")
        
        try:
            response = await self._get(
                f"{self.base_url}/projects/0.1/projects/{project_id}",
                params={"full_description": "true"}
            )
            
            data = response.json()
            if data.get("status") == "success" and data.get("result"):
                return self._parse_project(data["result"])
                
        except Exception as e:
            logger.error(f"[Freelancer] Failed to get project {project_id}: {e}")
        
        return None

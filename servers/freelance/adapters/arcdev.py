"""
Arc.dev Adapter

Arc.dev is a premium platform for remote developers.
They don't have a public API, so this uses web scraping techniques.
"""

from typing import List, Optional
from datetime import datetime
import re
import json
import logging

from models import Job, JobSearchParams, Platform, JobType
from .base import BaseAdapter, TECH_SKILLS

logger = logging.getLogger(__name__)


class ArcDevAdapter(BaseAdapter):
    """Adapter for Arc.dev - Premium remote developer jobs"""
    
    platform = Platform.ARC_DEV
    base_url = "https://arc.dev"
    rate_limit_delay = 3.0
    
    # Arc.dev job search endpoints
    SEARCH_ENDPOINTS = {
        "all": "/remote-jobs",
        "python": "/remote-jobs/python",
        "react": "/remote-jobs/reactjs", 
        "nodejs": "/remote-jobs/nodejs",
        "fastapi": "/remote-jobs/fastapi",
        "aws": "/remote-jobs/aws",
        "devops": "/remote-jobs/devops",
        "fullstack": "/remote-jobs/full-stack",
    }
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search Arc.dev jobs
        
        Arc.dev doesn't have a public API, so we try to:
        1. Fetch category pages based on skills
        2. Parse embedded JSON data
        """
        jobs = []
        
        # Determine which endpoints to fetch based on skills
        endpoints_to_fetch = set()
        
        skill_map = {
            "python": "python",
            "fastapi": "fastapi",
            "react": "react",
            "nodejs": "nodejs",
            "node.js": "nodejs",
            "aws": "aws",
            "devops": "devops",
        }
        
        for skill in (params.skills + params.keywords):
            skill_lower = skill.lower()
            if skill_lower in skill_map:
                endpoints_to_fetch.add(skill_map[skill_lower])
        
        # Default to all if no specific skills
        if not endpoints_to_fetch:
            endpoints_to_fetch.add("all")
        
        for endpoint_key in endpoints_to_fetch:
            try:
                endpoint = self.SEARCH_ENDPOINTS.get(endpoint_key, self.SEARCH_ENDPOINTS["all"])
                url = f"{self.base_url}{endpoint}"
                
                response = await self._get(url, headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                
                parsed = self._parse_page(response.text)
                
                for job in parsed:
                    if self._matches_filters(job, params) and job.id not in [j.id for j in jobs]:
                        jobs.append(job)
                        
                        if len(jobs) >= params.max_results:
                            break
                
            except Exception as e:
                logger.warning(f"[Arc.dev] Failed to fetch {endpoint_key}: {e}")
        
        logger.info(f"[Arc.dev] Found {len(jobs)} matching jobs")
        return jobs[:params.max_results]
    
    def _parse_page(self, html_content: str) -> List[Job]:
        """Parse Arc.dev page for job listings"""
        jobs = []
        
        # Arc.dev embeds job data as JSON in script tags
        # Try to find Next.js/React data
        json_pattern = re.compile(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>([^<]+)</script>',
            re.IGNORECASE
        )
        
        match = json_pattern.search(html_content)
        if match:
            try:
                data = json.loads(match.group(1))
                # Navigate to jobs data (structure may vary)
                jobs_data = self._extract_jobs_from_nextdata(data)
                
                for job_data in jobs_data:
                    job = self._parse_job_data(job_data)
                    if job:
                        jobs.append(job)
                        
            except json.JSONDecodeError:
                logger.debug("[Arc.dev] Failed to parse Next.js data")
        
        # Fallback: Basic HTML parsing
        if not jobs:
            jobs = self._parse_html_fallback(html_content)
        
        return jobs
    
    def _extract_jobs_from_nextdata(self, data: dict) -> List[dict]:
        """Extract job listings from Next.js page data"""
        jobs = []
        
        try:
            # Try common Next.js data paths
            props = data.get("props", {})
            page_props = props.get("pageProps", {})
            
            # Look for jobs array
            for key in ["jobs", "listings", "data", "results"]:
                if key in page_props:
                    potential_jobs = page_props[key]
                    if isinstance(potential_jobs, list):
                        jobs.extend(potential_jobs)
                        break
            
            # Also check nested structures
            if not jobs and "initialState" in page_props:
                state = page_props["initialState"]
                if isinstance(state, dict):
                    for key, value in state.items():
                        if isinstance(value, list) and len(value) > 0:
                            if isinstance(value[0], dict) and "title" in value[0]:
                                jobs.extend(value)
                                break
                                
        except Exception as e:
            logger.debug(f"[Arc.dev] Error extracting jobs: {e}")
        
        return jobs
    
    def _parse_job_data(self, data: dict) -> Optional[Job]:
        """Parse a single job from JSON data"""
        
        try:
            job_id = data.get("id") or data.get("slug") or "unknown"
            title = data.get("title") or data.get("name", "")
            company = data.get("company", {})
            if isinstance(company, dict):
                company_name = company.get("name", "Unknown")
            else:
                company_name = str(company) if company else "Unknown"
            
            description = data.get("description", "") or data.get("summary", "")
            
            # Skills
            skills = data.get("skills", []) or data.get("tags", [])
            if isinstance(skills, list):
                skills = [s.get("name", s) if isinstance(s, dict) else str(s) for s in skills]
            else:
                skills = []
            
            # URL
            slug = data.get("slug") or job_id
            url = data.get("url") or f"{self.base_url}/remote-jobs/{slug}"
            
            # Rate
            salary = data.get("salary", {}) or {}
            rate_min = salary.get("min") or data.get("salaryMin")
            rate_max = salary.get("max") or data.get("salaryMax")
            
            # Convert annual to hourly if needed
            if rate_min and rate_min > 1000:
                rate_min = rate_min / 2080
            if rate_max and rate_max > 1000:
                rate_max = rate_max / 2080
            
            # Posted date
            posted_at = None
            date_str = data.get("postedAt") or data.get("createdAt") or data.get("publishedAt")
            if date_str:
                try:
                    posted_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except:
                    pass
            
            return Job(
                id=f"arcdev_{job_id}",
                platform=Platform.ARC_DEV,
                url=url,
                title=title,
                company=company_name,
                description=description[:5000],
                skills=skills,
                job_type=JobType.FULL_TIME,
                rate_min=float(rate_min) if rate_min else None,
                rate_max=float(rate_max) if rate_max else None,
                currency="USD",
                is_remote=True,
                location=data.get("location", "Remote"),
                posted_at=posted_at,
            )
            
        except Exception as e:
            logger.debug(f"[Arc.dev] Failed to parse job: {e}")
            return None
    
    def _parse_html_fallback(self, html_content: str) -> List[Job]:
        """Fallback HTML parsing when JSON isn't available"""
        jobs = []
        
        # Basic pattern matching for job cards
        # This is fragile and may need updates as the site changes
        job_pattern = re.compile(
            r'href="(/remote-jobs/[^"]+)"[^>]*>.*?'
            r'class="[^"]*job-title[^"]*"[^>]*>([^<]+)<',
            re.DOTALL | re.IGNORECASE
        )
        
        for match in job_pattern.finditer(html_content):
            url_path, title = match.groups()
            
            job = Job(
                id=f"arcdev_{url_path.split('/')[-1]}",
                platform=Platform.ARC_DEV,
                url=f"{self.base_url}{url_path}",
                title=title.strip(),
                company="Unknown",
                description="",
                skills=[],
                is_remote=True,
                location="Remote",
            )
            jobs.append(job)
        
        return jobs
    
    def _matches_filters(self, job: Job, params: JobSearchParams) -> bool:
        """Check if job matches filters"""
        
        if params.keywords:
            text = f"{job.title} {job.description} {' '.join(job.skills)}".lower()
            if not any(kw.lower() in text for kw in params.keywords):
                return False
        
        if params.skills:
            job_skills_lower = [s.lower() for s in job.skills]
            text_lower = f"{job.title} {job.description}".lower()
            
            has_skill = any(
                s.lower() in job_skills_lower or s.lower() in text_lower 
                for s in params.skills
            )
            if not has_skill:
                return False
        
        return True
    
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """Get detailed job info"""
        return None

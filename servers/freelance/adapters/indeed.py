"""
Indeed Adapter - Uses RSS feeds

Indeed has RSS feeds for job searches that can be accessed publicly.
Format: https://www.indeed.com/rss?q=keyword&l=location
"""

from typing import List, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
import re
import html
import logging
import urllib.parse

from models import Job, JobSearchParams, Platform, JobType
from .base import BaseAdapter, TECH_SKILLS

logger = logging.getLogger(__name__)


class IndeedAdapter(BaseAdapter):
    """Adapter for Indeed.com - Uses RSS feeds"""
    
    platform = Platform.INDEED
    base_url = "https://www.indeed.com"
    rate_limit_delay = 2.0
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search Indeed via RSS feed
        
        RSS URL format: https://www.indeed.com/rss?q=keyword&l=remote&sort=date
        """
        jobs = []
        
        try:
            # Build search query
            query_parts = []
            if params.keywords:
                query_parts.extend(params.keywords)
            if params.skills:
                query_parts.extend(params.skills[:3])
            
            query = " ".join(query_parts) if query_parts else "software developer"
            
            # Build RSS URL
            rss_params = {
                "q": query,
                "l": "remote",  # Location filter for remote
                "sort": "date",  # Sort by date
                "fromage": str(params.posted_within_hours // 24) if params.posted_within_hours else "7",
            }
            
            # Add remote filter
            if params.remote_only:
                rss_params["remotejob"] = "1"
            
            rss_url = f"{self.base_url}/rss?" + urllib.parse.urlencode(rss_params)
            
            response = await self._get(rss_url)
            parsed_jobs = self._parse_rss(response.text)
            
            for job in parsed_jobs:
                if self._matches_filters(job, params):
                    jobs.append(job)
                    
                    if len(jobs) >= params.max_results:
                        break
            
            logger.info(f"[Indeed] Found {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"[Indeed] Search failed: {e}")
        
        return jobs
    
    def _parse_rss(self, xml_content: str) -> List[Job]:
        """Parse Indeed RSS feed into Job objects"""
        jobs = []
        
        try:
            root = ET.fromstring(xml_content)
            
            for item in root.findall(".//item"):
                try:
                    job = self._parse_item(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Failed to parse Indeed RSS item: {e}")
                    continue
                    
        except ET.ParseError as e:
            logger.error(f"Failed to parse Indeed RSS XML: {e}")
        
        return jobs
    
    def _parse_item(self, item: ET.Element) -> Optional[Job]:
        """Parse a single RSS item into a Job"""
        
        title_elem = item.find("title")
        link_elem = item.find("link")
        description_elem = item.find("description")
        pubdate_elem = item.find("pubDate")
        source_elem = item.find("source")
        
        if not title_elem or not link_elem:
            return None
        
        title = title_elem.text or ""
        url = link_elem.text or ""
        raw_description = description_elem.text or "" if description_elem else ""
        
        # Clean description
        description = html.unescape(raw_description)
        description = re.sub(r'<[^>]+>', ' ', description)
        description = re.sub(r'\s+', ' ', description).strip()
        
        # Parse company from source or title
        company = "Unknown"
        if source_elem is not None and source_elem.text:
            company = source_elem.text.strip()
        
        # Parse date
        posted_at = None
        if pubdate_elem is not None and pubdate_elem.text:
            try:
                from email.utils import parsedate_to_datetime
                posted_at = parsedate_to_datetime(pubdate_elem.text)
            except:
                pass
        
        # Extract skills
        full_text = f"{title} {description}"
        skills = self._extract_skills(full_text, TECH_SKILLS)
        
        # Determine job type
        job_type = JobType.FULL_TIME
        text_lower = full_text.lower()
        if "contract" in text_lower or "freelance" in text_lower:
            job_type = JobType.CONTRACT
        elif "part-time" in text_lower or "part time" in text_lower:
            job_type = JobType.PART_TIME
        
        # Extract rate from description
        rate_min, rate_max = self._parse_rate(description)
        
        # Generate unique ID from URL
        job_id = re.search(r'jk=([a-zA-Z0-9]+)', url)
        job_id = job_id.group(1) if job_id else str(hash(url))[:12]
        
        return Job(
            id=f"indeed_{job_id}",
            platform=Platform.INDEED,
            url=url,
            title=title,
            company=company,
            description=description[:5000],
            skills=skills,
            job_type=job_type,
            rate_min=rate_min,
            rate_max=rate_max,
            currency="USD",
            is_remote="remote" in full_text.lower(),
            location="Remote" if "remote" in full_text.lower() else "Various",
            posted_at=posted_at,
        )
    
    def _matches_filters(self, job: Job, params: JobSearchParams) -> bool:
        """Check if job matches search parameters"""
        
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
        
        if params.remote_only and not job.is_remote:
            return False
        
        if params.posted_within_hours and job.posted_at:
            hours_ago = (datetime.utcnow() - job.posted_at.replace(tzinfo=None)).total_seconds() / 3600
            if hours_ago > params.posted_within_hours:
                return False
        
        return True
    
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """Indeed doesn't provide public job details API"""
        return None

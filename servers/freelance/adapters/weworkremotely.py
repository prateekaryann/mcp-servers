"""
We Work Remotely Adapter - Uses RSS feeds
https://weworkremotely.com/
"""

from typing import List, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
import re
import html
import logging

from models import Job, JobSearchParams, Platform, JobType
from .base import BaseAdapter, TECH_SKILLS

logger = logging.getLogger(__name__)


class WeWorkRemotelyAdapter(BaseAdapter):
    """Adapter for WeWorkRemotely.com - Uses RSS feeds"""
    
    platform = Platform.WEWORKREMOTELY
    base_url = "https://weworkremotely.com"
    rate_limit_delay = 1.5
    
    # RSS feed URLs by category
    RSS_FEEDS = {
        "programming": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "devops": "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "design": "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "all": "https://weworkremotely.com/remote-jobs.rss",
    }
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """Search WeWorkRemotely via RSS feeds"""
        jobs = []
        
        # Determine which feeds to fetch based on keywords
        feeds_to_fetch = ["programming", "devops"]  # Default for tech jobs
        
        # Add all feed if searching broadly
        if not params.keywords and not params.skills:
            feeds_to_fetch = ["all"]
        
        for feed_name in feeds_to_fetch:
            try:
                feed_url = self.RSS_FEEDS.get(feed_name, self.RSS_FEEDS["all"])
                response = await self._get(feed_url)
                
                parsed_jobs = self._parse_rss(response.text)
                
                for job in parsed_jobs:
                    if self._matches_filters(job, params):
                        jobs.append(job)
                        
                        if len(jobs) >= params.max_results:
                            break
                
            except Exception as e:
                logger.warning(f"[WWR] Failed to fetch {feed_name} feed: {e}")
        
        # Deduplicate by job ID
        seen_ids = set()
        unique_jobs = []
        for job in jobs:
            if job.id not in seen_ids:
                seen_ids.add(job.id)
                unique_jobs.append(job)
        
        logger.info(f"[WWR] Found {len(unique_jobs)} matching jobs")
        return unique_jobs[:params.max_results]
    
    def _parse_rss(self, xml_content: str) -> List[Job]:
        """Parse RSS XML into Job objects"""
        jobs = []
        
        try:
            root = ET.fromstring(xml_content)
            
            for item in root.findall(".//item"):
                try:
                    job = self._parse_item(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Failed to parse RSS item: {e}")
                    continue
                    
        except ET.ParseError as e:
            logger.error(f"Failed to parse RSS XML: {e}")
        
        return jobs
    
    def _parse_item(self, item: ET.Element) -> Optional[Job]:
        """Parse a single RSS item into a Job"""
        
        title_elem = item.find("title")
        link_elem = item.find("link")
        description_elem = item.find("description")
        pubdate_elem = item.find("pubDate")
        
        if not title_elem or not link_elem:
            return None
        
        title = title_elem.text or ""
        url = link_elem.text or ""
        description = html.unescape(description_elem.text or "") if description_elem else ""
        
        # Remove HTML tags from description
        description = re.sub(r'<[^>]+>', ' ', description)
        description = re.sub(r'\s+', ' ', description).strip()
        
        # Parse company from title (format: "Company: Job Title")
        company = "Unknown"
        job_title = title
        if ":" in title:
            parts = title.split(":", 1)
            company = parts[0].strip()
            job_title = parts[1].strip() if len(parts) > 1 else title
        
        # Parse date
        posted_at = None
        if pubdate_elem is not None and pubdate_elem.text:
            try:
                # Format: "Mon, 01 Jan 2024 00:00:00 +0000"
                from email.utils import parsedate_to_datetime
                posted_at = parsedate_to_datetime(pubdate_elem.text)
            except:
                pass
        
        # Extract job ID from URL
        job_id = url.split("/")[-1] if url else "unknown"
        
        # Extract skills from description and title
        full_text = f"{title} {description}"
        skills = self._extract_skills(full_text, TECH_SKILLS)
        
        # Determine job type
        job_type = JobType.FULL_TIME
        text_lower = full_text.lower()
        if "contract" in text_lower or "freelance" in text_lower:
            job_type = JobType.CONTRACT
        elif "part-time" in text_lower or "part time" in text_lower:
            job_type = JobType.PART_TIME
        
        # Try to extract rate from description
        rate_min, rate_max = self._parse_rate(description)
        
        return Job(
            id=f"wwr_{job_id}",
            platform=Platform.WEWORKREMOTELY,
            url=url,
            title=job_title,
            company=company,
            description=description[:5000],
            skills=skills,
            job_type=job_type,
            rate_min=rate_min,
            rate_max=rate_max,
            currency="USD",
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
            if not any(s.lower() in job_skills_lower for s in params.skills):
                return False
        
        # Posted date filtering
        if params.posted_within_hours and job.posted_at:
            hours_ago = (datetime.utcnow() - job.posted_at.replace(tzinfo=None)).total_seconds() / 3600
            if hours_ago > params.posted_within_hours:
                return False
        
        return True
    
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """WWR doesn't provide individual job API"""
        return None

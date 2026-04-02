"""
Upwork Adapter - Uses RSS feeds (API requires OAuth approval)
https://www.upwork.com/ab/feed/jobs/rss

Note: Upwork's official API requires OAuth approval process.
This adapter uses their public RSS feeds as an alternative.
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


class UpworkAdapter(BaseAdapter):
    """Adapter for Upwork.com - Uses RSS feeds"""
    
    platform = Platform.UPWORK
    base_url = "https://www.upwork.com"
    rate_limit_delay = 2.0  # Be respectful
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search Upwork via RSS feed
        
        RSS URL format: https://www.upwork.com/ab/feed/jobs/rss?q=keyword&sort=recency
        """
        jobs = []
        
        try:
            # Build search query
            query_parts = []
            
            if params.keywords:
                query_parts.extend(params.keywords)
            if params.skills:
                query_parts.extend(params.skills[:5])  # Limit skills in query
            
            query = " ".join(query_parts) if query_parts else "python developer"
            
            # Build RSS URL
            rss_params = {
                "q": query,
                "sort": "recency",
            }
            
            # Add budget filter if specified
            if params.min_rate:
                # Upwork uses budget ranges
                rss_params["budget"] = f"{int(params.min_rate)}-"
            
            rss_url = f"{self.base_url}/ab/feed/jobs/rss?" + urllib.parse.urlencode(rss_params)
            
            response = await self._get(rss_url)
            parsed_jobs = self._parse_rss(response.text)
            
            for job in parsed_jobs:
                if self._matches_filters(job, params):
                    jobs.append(job)
                    
                    if len(jobs) >= params.max_results:
                        break
            
            logger.info(f"[Upwork] Found {len(jobs)} matching jobs")
            
        except Exception as e:
            logger.error(f"[Upwork] Search failed: {e}")
        
        return jobs
    
    def _parse_rss(self, xml_content: str) -> List[Job]:
        """Parse Upwork RSS feed into Job objects"""
        jobs = []
        
        try:
            root = ET.fromstring(xml_content)
            
            for item in root.findall(".//item"):
                try:
                    job = self._parse_item(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.debug(f"Failed to parse Upwork RSS item: {e}")
                    continue
                    
        except ET.ParseError as e:
            logger.error(f"Failed to parse Upwork RSS XML: {e}")
        
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
        raw_description = description_elem.text or "" if description_elem else ""
        
        # Unescape and clean HTML
        description = html.unescape(raw_description)
        description = re.sub(r'<[^>]+>', ' ', description)
        description = re.sub(r'\s+', ' ', description).strip()
        
        # Parse Upwork-specific metadata from description
        # Format often includes: "Budget: $X - Posted: Date - Skills: ..."
        budget_match = re.search(r'Budget[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(?:-\s*\$?([\d,]+(?:\.\d+)?))?', description, re.I)
        hourly_match = re.search(r'Hourly[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(?:-\s*\$?([\d,]+(?:\.\d+)?))?', description, re.I)
        
        rate_min, rate_max = None, None
        job_type = JobType.FIXED
        
        if hourly_match:
            job_type = JobType.HOURLY
            rate_min = float(hourly_match.group(1).replace(",", "")) if hourly_match.group(1) else None
            rate_max = float(hourly_match.group(2).replace(",", "")) if hourly_match.group(2) else rate_min
        elif budget_match:
            job_type = JobType.FIXED
            rate_min = float(budget_match.group(1).replace(",", "")) if budget_match.group(1) else None
            rate_max = float(budget_match.group(2).replace(",", "")) if budget_match.group(2) else rate_min
        
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
        
        # Also try to extract skills from "Skills:" section in description
        skills_match = re.search(r'Skills?[:\s]+([^.]+?)(?:\.|$)', description, re.I)
        if skills_match:
            skill_text = skills_match.group(1)
            additional_skills = [s.strip() for s in skill_text.split(",") if s.strip()]
            skills = list(set(skills + additional_skills))
        
        # Extract job ID from URL
        job_id = "unknown"
        id_match = re.search(r'~([a-zA-Z0-9]+)', url)
        if id_match:
            job_id = id_match.group(1)
        
        return Job(
            id=f"upwork_{job_id}",
            platform=Platform.UPWORK,
            url=url,
            title=title,
            company="Client on Upwork",  # Upwork doesn't expose client names in RSS
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
            text_lower = f"{job.title} {job.description}".lower()
            
            has_skill = any(
                s.lower() in job_skills_lower or s.lower() in text_lower 
                for s in params.skills
            )
            if not has_skill:
                return False
        
        # Rate filtering (for hourly jobs)
        if params.min_rate and job.job_type == JobType.HOURLY:
            if job.rate_max and job.rate_max < params.min_rate:
                return False
        
        # Posted date filtering
        if params.posted_within_hours and job.posted_at:
            hours_ago = (datetime.utcnow() - job.posted_at.replace(tzinfo=None)).total_seconds() / 3600
            if hours_ago > params.posted_within_hours:
                return False
        
        return True
    
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """Upwork doesn't provide public job details API"""
        return None

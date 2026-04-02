"""
Dice.com Adapter

Dice is a tech-focused job board. They have RSS feeds available.
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


class DiceAdapter(BaseAdapter):
    """Adapter for Dice.com - Tech-focused job board"""
    
    platform = Platform.DICE
    base_url = "https://www.dice.com"
    rate_limit_delay = 2.0
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search Dice via RSS feed
        
        Dice RSS: https://www.dice.com/jobs/rss?q=keyword&location=Remote
        """
        jobs = []
        
        try:
            # Build search query
            query_parts = []
            if params.keywords:
                query_parts.extend(params.keywords)
            if params.skills:
                query_parts.extend(params.skills[:5])
            
            query = " ".join(query_parts) if query_parts else "python developer"
            
            # Dice job search API endpoint (JSON)
            # Note: Dice's public API is limited, using search page scraping as fallback
            search_url = f"{self.base_url}/jobs"
            search_params = {
                "q": query,
                "location": "Remote",
                "latitude": "",
                "longitude": "",
                "countryCode": "US",
                "locationPrecision": "",
                "radius": "",
                "radiusUnit": "mi",
                "page": "1",
                "pageSize": str(min(params.max_results, 50)),
                "filters.postedDate": "SEVEN",  # Last 7 days
                "filters.workplaceTypes": "Remote",
                "language": "en",
            }
            
            # Try to fetch search results
            try:
                response = await self._get(
                    f"{self.base_url}/jobs/q-{urllib.parse.quote(query)}-jobs",
                    params={"filters.workplaceTypes": "Remote"}
                )
                
                # Parse HTML for job listings
                jobs = self._parse_search_html(response.text, params)
                
            except Exception as e:
                logger.warning(f"[Dice] Search page fetch failed: {e}")
                # Fallback: try RSS if available
                jobs = await self._search_rss(params)
            
            logger.info(f"[Dice] Found {len(jobs)} jobs")
            
        except Exception as e:
            logger.error(f"[Dice] Search failed: {e}")
        
        return jobs[:params.max_results]
    
    async def _search_rss(self, params: JobSearchParams) -> List[Job]:
        """Fallback RSS search"""
        jobs = []
        
        try:
            query = " ".join(params.keywords + params.skills[:3]) if params.keywords or params.skills else "developer"
            rss_url = f"{self.base_url}/rss/jobs/q-{urllib.parse.quote(query)}-jobs"
            
            response = await self._get(rss_url)
            
            root = ET.fromstring(response.text)
            for item in root.findall(".//item"):
                job = self._parse_rss_item(item)
                if job and self._matches_filters(job, params):
                    jobs.append(job)
                    
        except Exception as e:
            logger.debug(f"[Dice] RSS fallback failed: {e}")
        
        return jobs
    
    def _parse_search_html(self, html_content: str, params: JobSearchParams) -> List[Job]:
        """Parse Dice search results HTML"""
        jobs = []
        
        # Look for job card patterns in HTML
        # Dice uses data attributes for job info
        job_pattern = re.compile(
            r'data-id="([^"]+)".*?'
            r'<a[^>]*href="(/job-detail/[^"]+)"[^>]*>([^<]+)</a>.*?'
            r'data-cy="card-company"[^>]*>([^<]+)<',
            re.DOTALL | re.IGNORECASE
        )
        
        for match in job_pattern.finditer(html_content):
            job_id, url_path, title, company = match.groups()
            
            job = Job(
                id=f"dice_{job_id}",
                platform=Platform.DICE,
                url=f"{self.base_url}{url_path}",
                title=html.unescape(title.strip()),
                company=html.unescape(company.strip()),
                description="",  # Would need individual page fetch
                skills=self._extract_skills(title, TECH_SKILLS),
                is_remote=True,
                location="Remote",
            )
            
            if self._matches_filters(job, params):
                jobs.append(job)
        
        return jobs
    
    def _parse_rss_item(self, item: ET.Element) -> Optional[Job]:
        """Parse RSS item into Job"""
        
        title_elem = item.find("title")
        link_elem = item.find("link")
        description_elem = item.find("description")
        pubdate_elem = item.find("pubDate")
        
        if not title_elem or not link_elem:
            return None
        
        title = title_elem.text or ""
        url = link_elem.text or ""
        description = html.unescape(description_elem.text or "") if description_elem else ""
        description = re.sub(r'<[^>]+>', ' ', description).strip()
        
        # Parse company from title (format often: "Title - Company")
        company = "Unknown"
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            if len(parts) == 2:
                title, company = parts[0].strip(), parts[1].strip()
        
        # Parse date
        posted_at = None
        if pubdate_elem is not None and pubdate_elem.text:
            try:
                from email.utils import parsedate_to_datetime
                posted_at = parsedate_to_datetime(pubdate_elem.text)
            except:
                pass
        
        # Extract skills
        skills = self._extract_skills(f"{title} {description}", TECH_SKILLS)
        
        # Generate ID
        job_id = re.search(r'/([a-zA-Z0-9-]+)(?:\?|$)', url)
        job_id = job_id.group(1) if job_id else str(hash(url))[:12]
        
        return Job(
            id=f"dice_{job_id}",
            platform=Platform.DICE,
            url=url,
            title=title,
            company=company,
            description=description[:5000],
            skills=skills,
            is_remote=True,
            location="Remote",
            posted_at=posted_at,
        )
    
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
        """Get job details from Dice"""
        return None

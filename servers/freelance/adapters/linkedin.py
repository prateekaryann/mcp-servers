"""
LinkedIn Jobs Adapter

LinkedIn doesn't provide a public API for job search.
This adapter uses alternative approaches:
1. LinkedIn's RSS feed (limited)
2. Google Jobs RSS for LinkedIn listings
3. Direct search URL scraping (requires more sophisticated handling)

For production, consider using LinkedIn's official Marketing API (requires approval)
or a service like Proxycurl.
"""

from typing import List, Optional
from datetime import datetime
import re
import html
import logging
import urllib.parse

from models import Job, JobSearchParams, Platform, JobType
from .base import BaseAdapter, TECH_SKILLS

logger = logging.getLogger(__name__)


class LinkedInAdapter(BaseAdapter):
    """
    Adapter for LinkedIn Jobs
    
    Note: This uses a workaround since LinkedIn doesn't have a public jobs API.
    For production use, consider:
    - LinkedIn Marketing API (requires approval)
    - Proxycurl or similar services
    - Manual scraping with proper rate limiting and headers
    """
    
    platform = Platform.LINKEDIN
    base_url = "https://www.linkedin.com"
    rate_limit_delay = 3.0  # Be very respectful with LinkedIn
    
    async def search(self, params: JobSearchParams) -> List[Job]:
        """
        Search LinkedIn Jobs
        
        This uses LinkedIn's job search URL and attempts to parse results.
        Note: May require additional headers/cookies for reliable access.
        """
        jobs = []
        
        try:
            # Build LinkedIn job search URL
            keywords = " ".join(params.keywords + params.skills[:3]) if params.keywords or params.skills else "software developer"
            
            search_params = {
                "keywords": keywords,
                "f_WT": "2",  # Remote filter
                "sortBy": "DD",  # Sort by date
            }
            
            search_url = f"{self.base_url}/jobs/search?" + urllib.parse.urlencode(search_params)
            
            # Try to fetch (may be blocked without proper auth)
            try:
                response = await self._get(
                    search_url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                )
                
                # Parse job listings from HTML
                jobs = self._parse_search_results(response.text, params)
                
            except Exception as e:
                logger.warning(f"[LinkedIn] Direct search failed (expected): {e}")
                # Fall back to alternative method
                jobs = await self._search_via_google(params)
            
            logger.info(f"[LinkedIn] Found {len(jobs)} jobs")
            
        except Exception as e:
            logger.error(f"[LinkedIn] Search failed: {e}")
        
        return jobs[:params.max_results]
    
    def _parse_search_results(self, html_content: str, params: JobSearchParams) -> List[Job]:
        """Parse LinkedIn search results HTML"""
        jobs = []
        
        # LinkedIn's HTML structure changes frequently
        # This is a basic pattern - may need updates
        
        # Look for job card patterns
        job_pattern = re.compile(
            r'data-job-id="(\d+)".*?'
            r'class="[^"]*job-card[^"]*".*?'
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?'
            r'company[^>]*>([^<]+)<',
            re.DOTALL | re.IGNORECASE
        )
        
        for match in job_pattern.finditer(html_content):
            job_id, url, title, company = match.groups()
            
            job = Job(
                id=f"linkedin_{job_id}",
                platform=Platform.LINKEDIN,
                url=f"https://www.linkedin.com{url}" if url.startswith("/") else url,
                title=html.unescape(title.strip()),
                company=html.unescape(company.strip()),
                description="",  # Would need to fetch individual job pages
                skills=self._extract_skills(title, TECH_SKILLS),
                is_remote=True,
                location="Remote",
            )
            
            if self._matches_filters(job, params):
                jobs.append(job)
        
        return jobs
    
    async def _search_via_google(self, params: JobSearchParams) -> List[Job]:
        """
        Alternative: Search for LinkedIn jobs via Google
        
        This is a fallback when direct LinkedIn access fails.
        Uses Google's site: search operator.
        """
        # This would require Google Custom Search API or similar
        # For now, return empty list and log a message
        
        logger.info("[LinkedIn] Direct API access required for reliable results")
        logger.info("[LinkedIn] Consider setting up LinkedIn Marketing API or Proxycurl")
        
        return []
    
    def _matches_filters(self, job: Job, params: JobSearchParams) -> bool:
        """Check if job matches search parameters"""
        
        if params.keywords:
            text = f"{job.title} {job.company}".lower()
            if not any(kw.lower() in text for kw in params.keywords):
                return False
        
        return True
    
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """Get LinkedIn job details (requires auth)"""
        return None


class LinkedInConfig:
    """
    Configuration for LinkedIn API access
    
    To use LinkedIn's official API:
    1. Create a LinkedIn App at https://www.linkedin.com/developers/
    2. Request access to Marketing API
    3. Set these credentials as environment variables
    """
    
    CLIENT_ID: str = ""  # Set via env: LINKEDIN_CLIENT_ID
    CLIENT_SECRET: str = ""  # Set via env: LINKEDIN_CLIENT_SECRET
    ACCESS_TOKEN: str = ""  # Set via env: LINKEDIN_ACCESS_TOKEN
    
    # Alternative: Use Proxycurl
    PROXYCURL_API_KEY: str = ""  # Set via env: PROXYCURL_API_KEY

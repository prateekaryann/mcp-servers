"""
Base adapter for job platforms
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
import httpx
import asyncio
import logging

from models import Job, JobSearchParams, Platform

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """Base class for all platform adapters"""
    
    platform: Platform
    base_url: str
    rate_limit_delay: float = 1.0  # seconds between requests
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "FreelanceJobMCP/1.0 (Job Search Aggregator)"
            }
        )
        self._last_request_time: Optional[datetime] = None
    
    async def _rate_limit(self):
        """Enforce rate limiting between requests"""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            if elapsed < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = datetime.utcnow()
    
    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """Make a rate-limited GET request"""
        await self._rate_limit()
        logger.debug(f"[{self.platform}] GET {url}")
        response = await self.client.get(url, **kwargs)
        response.raise_for_status()
        return response
    
    async def _post(self, url: str, **kwargs) -> httpx.Response:
        """Make a rate-limited POST request"""
        await self._rate_limit()
        logger.debug(f"[{self.platform}] POST {url}")
        response = await self.client.post(url, **kwargs)
        response.raise_for_status()
        return response
    
    @abstractmethod
    async def search(self, params: JobSearchParams) -> List[Job]:
        """Search for jobs on this platform"""
        pass
    
    @abstractmethod
    async def get_job_details(self, job_id: str) -> Optional[Job]:
        """Get detailed information about a specific job"""
        pass
    
    def _extract_skills(self, text: str, known_skills: List[str]) -> List[str]:
        """Extract skills from job description text"""
        text_lower = text.lower()
        found_skills = []
        
        for skill in known_skills:
            # Check for exact match or common variations
            skill_lower = skill.lower()
            if skill_lower in text_lower:
                found_skills.append(skill)
            # Check for variations like "React.js" -> "React"
            elif skill_lower.replace(".", "").replace("js", "") in text_lower:
                found_skills.append(skill)
        
        return list(set(found_skills))
    
    def _parse_rate(self, rate_str: str) -> tuple[Optional[float], Optional[float]]:
        """Parse rate string like '$50-100/hr' into (min, max)"""
        import re
        
        if not rate_str:
            return None, None
        
        # Remove currency symbols and clean up
        rate_str = rate_str.replace("$", "").replace(",", "").strip()
        
        # Try to find range pattern
        range_match = re.search(r'(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)', rate_str)
        if range_match:
            return float(range_match.group(1)), float(range_match.group(2))
        
        # Try single number
        single_match = re.search(r'(\d+(?:\.\d+)?)', rate_str)
        if single_match:
            rate = float(single_match.group(1))
            return rate, rate
        
        return None, None
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Common tech skills for extraction
TECH_SKILLS = [
    # Languages
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Golang", "Rust", "C++", "C#",
    "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R", "MATLAB", "SQL", "Bash", "Shell",
    
    # Python frameworks
    "FastAPI", "Django", "Flask", "Celery", "SQLAlchemy", "Pydantic", "asyncio",
    
    # JavaScript frameworks
    "React", "React.js", "ReactJS", "Next.js", "NextJS", "Vue", "Vue.js", "Angular",
    "Node.js", "NodeJS", "Express", "NestJS", "Svelte", "Remix",
    
    # Frontend
    "HTML", "CSS", "Tailwind", "TailwindCSS", "Bootstrap", "Sass", "SCSS",
    "Webpack", "Vite", "TypeScript", "Redux", "Zustand", "MobX",
    
    # Cloud & DevOps
    "AWS", "Amazon Web Services", "Azure", "GCP", "Google Cloud",
    "Docker", "Kubernetes", "K8s", "EKS", "ECS", "Lambda", "EC2", "S3", "RDS",
    "Terraform", "Ansible", "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI",
    "Helm", "ArgoCD", "Prometheus", "Grafana", "DataDog",
    
    # Databases
    "PostgreSQL", "Postgres", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "DynamoDB", "Cassandra", "Neo4j", "SQLite", "Oracle", "SQL Server",
    
    # AI/ML
    "Machine Learning", "ML", "Deep Learning", "NLP", "LLM", "GPT", "OpenAI",
    "TensorFlow", "PyTorch", "Keras", "scikit-learn", "Pandas", "NumPy",
    "Hugging Face", "LangChain", "RAG", "Bedrock", "SageMaker", "Claude",
    
    # Healthcare/Clinical (domain-specific)
    "FDA", "ICH", "GCP", "Clinical Trial", "CTMS", "EDC", "TMF", "CSR", "DSUR",
    "21 CFR", "HIPAA", "HL7", "FHIR", "ICD-10", "CDISC", "SDTM", "ADaM",
    
    # Other
    "REST", "GraphQL", "gRPC", "WebSocket", "API", "Microservices",
    "CI/CD", "DevOps", "Agile", "Scrum", "Git", "Linux", "Unix",
]

"""
Unified Job Model for Multi-Platform Freelance Job Search
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl
from enum import Enum


class JobType(str, Enum):
    HOURLY = "hourly"
    FIXED = "fixed"
    FULL_TIME = "full_time"
    CONTRACT = "contract"
    PART_TIME = "part_time"


class ExperienceLevel(str, Enum):
    ENTRY = "entry"
    INTERMEDIATE = "intermediate"
    SENIOR = "senior"
    EXPERT = "expert"


class Platform(str, Enum):
    UPWORK = "upwork"
    FREELANCER = "freelancer"
    LINKEDIN = "linkedin"
    REMOTEOK = "remoteok"
    WEWORKREMOTELY = "weworkremotely"
    ARC_DEV = "arc_dev"
    TOPTAL = "toptal"
    INDEED = "indeed"
    DICE = "dice"
    GLASSDOOR = "glassdoor"
    WELLFOUND = "wellfound"
    FLEXJOBS = "flexjobs"
    GITHUB_JOBS = "github_jobs"
    STACKOVERFLOW = "stackoverflow"
    TURING = "turing"
    GUN_IO = "gun_io"


class Job(BaseModel):
    """Unified job model across all platforms"""
    
    # Core identifiers
    id: str = Field(..., description="Unique job ID (platform-specific)")
    platform: Platform = Field(..., description="Source platform")
    url: HttpUrl = Field(..., description="Direct link to job posting")
    
    # Job details
    title: str = Field(..., description="Job title")
    company: Optional[str] = Field(None, description="Company name")
    description: str = Field(..., description="Job description")
    
    # Skills & requirements
    skills: List[str] = Field(default_factory=list, description="Required skills")
    experience_level: Optional[ExperienceLevel] = Field(None, description="Experience level")
    
    # Compensation
    job_type: Optional[JobType] = Field(None, description="Type of engagement")
    rate_min: Optional[float] = Field(None, description="Minimum rate (hourly or fixed)")
    rate_max: Optional[float] = Field(None, description="Maximum rate")
    currency: str = Field(default="USD", description="Currency code")
    
    # Location
    is_remote: bool = Field(default=True, description="Remote position")
    location: Optional[str] = Field(None, description="Location if not fully remote")
    timezone: Optional[str] = Field(None, description="Preferred timezone")
    
    # Metadata
    posted_at: Optional[datetime] = Field(None, description="When job was posted")
    scraped_at: datetime = Field(default_factory=datetime.utcnow, description="When we fetched it")
    
    # Matching (computed)
    match_score: Optional[float] = Field(None, description="Match score 0-100")
    matched_skills: List[str] = Field(default_factory=list, description="Skills that matched")
    missing_skills: List[str] = Field(default_factory=list, description="Skills required but not in profile")
    
    class Config:
        use_enum_values = True


class JobSearchParams(BaseModel):
    """Parameters for searching jobs"""
    
    keywords: List[str] = Field(
        default_factory=list,
        description="Keywords to search for"
    )
    skills: List[str] = Field(
        default_factory=list,
        description="Skills to match"
    )
    platforms: List[Platform] = Field(
        default_factory=lambda: list(Platform),
        description="Platforms to search"
    )
    min_rate: Optional[float] = Field(None, description="Minimum hourly rate")
    max_rate: Optional[float] = Field(None, description="Maximum hourly rate")
    job_types: List[JobType] = Field(
        default_factory=list,
        description="Types of jobs to include"
    )
    experience_levels: List[ExperienceLevel] = Field(
        default_factory=list,
        description="Experience levels to include"
    )
    posted_within_hours: int = Field(
        default=168,  # 1 week
        description="Only jobs posted within this many hours"
    )
    remote_only: bool = Field(default=True, description="Only remote jobs")
    max_results: int = Field(default=50, description="Maximum results to return")
    
    class Config:
        use_enum_values = True


class UserProfile(BaseModel):
    """User's skill profile for matching"""
    
    name: str = Field(..., description="User's name")
    
    # Primary skills (high proficiency)
    primary_skills: List[str] = Field(
        default_factory=list,
        description="Skills you're expert in"
    )
    
    # Secondary skills (comfortable with)
    secondary_skills: List[str] = Field(
        default_factory=list,
        description="Skills you're comfortable with"
    )
    
    # Domain expertise
    domains: List[str] = Field(
        default_factory=list,
        description="Domain expertise (e.g., 'healthcare', 'fintech')"
    )
    
    # Preferences
    preferred_rate_min: Optional[float] = Field(None, description="Minimum hourly rate")
    preferred_job_types: List[JobType] = Field(
        default_factory=list,
        description="Preferred job types"
    )
    experience_years: int = Field(default=5, description="Years of experience")
    
    # Exclusions
    excluded_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords to exclude from search"
    )
    
    class Config:
        use_enum_values = True


class MatchResult(BaseModel):
    """Result of matching a job against user profile"""
    
    job: Job
    overall_score: float = Field(..., description="Overall match score 0-100")
    skill_score: float = Field(..., description="Skill match score")
    domain_score: float = Field(..., description="Domain match score")
    rate_score: float = Field(..., description="Rate match score")
    matched_primary_skills: List[str] = Field(default_factory=list)
    matched_secondary_skills: List[str] = Field(default_factory=list)
    matched_domains: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    recommendation: str = Field(..., description="Brief recommendation")

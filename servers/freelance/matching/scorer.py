"""
Skill Matching Engine

Scores jobs against a user profile to find the best matches.
"""

from typing import List, Tuple, Set
from dataclasses import dataclass
import re
import logging

from models import Job, UserProfile, MatchResult

logger = logging.getLogger(__name__)


# Skill aliases - maps variations to canonical names
SKILL_ALIASES = {
    # Python ecosystem
    "python3": "python",
    "python 3": "python",
    "py": "python",
    
    # JavaScript ecosystem
    "js": "javascript",
    "es6": "javascript",
    "ecmascript": "javascript",
    "react.js": "react",
    "reactjs": "react",
    "react js": "react",
    "next.js": "nextjs",
    "next js": "nextjs",
    "node.js": "nodejs",
    "node js": "nodejs",
    "node": "nodejs",
    "vue.js": "vue",
    "vuejs": "vue",
    "vue js": "vue",
    "angular.js": "angular",
    "angularjs": "angular",
    
    # Cloud
    "amazon web services": "aws",
    "amazon aws": "aws",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "microsoft azure": "azure",
    
    # Containers/Orchestration
    "k8s": "kubernetes",
    "kube": "kubernetes",
    
    # Databases
    "postgres": "postgresql",
    "pg": "postgresql",
    "mongo": "mongodb",
    "elastic": "elasticsearch",
    "es": "elasticsearch",
    
    # AI/ML
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "llm": "large language models",
    "gpt": "large language models",
    "genai": "generative ai",
    "gen ai": "generative ai",
    
    # Healthcare/Clinical
    "fda compliance": "fda",
    "ich guidelines": "ich",
    "good clinical practice": "gcp",
    "clinical trial management": "ctms",
    "trial master file": "tmf",
    "clinical study report": "csr",
    
    # Frameworks
    "fast api": "fastapi",
    "fast-api": "fastapi",
}


def normalize_skill(skill: str) -> str:
    """Normalize a skill name to its canonical form"""
    skill_lower = skill.lower().strip()
    return SKILL_ALIASES.get(skill_lower, skill_lower)


def extract_skills_from_text(text: str, known_skills: List[str]) -> Set[str]:
    """Extract known skills from text"""
    text_lower = text.lower()
    found = set()
    
    for skill in known_skills:
        skill_normalized = normalize_skill(skill)
        
        # Check for exact match
        if skill_normalized in text_lower:
            found.add(skill)
        
        # Check original form too
        if skill.lower() in text_lower:
            found.add(skill)
    
    return found


class SkillMatcher:
    """
    Matches jobs against user profiles and scores them
    """
    
    # Weights for different scoring components
    WEIGHTS = {
        "primary_skill": 15.0,    # Points per matched primary skill
        "secondary_skill": 8.0,   # Points per matched secondary skill
        "domain": 10.0,           # Points per matched domain
        "rate_match": 10.0,       # Points for rate in range
        "recency": 5.0,           # Points for recent posting
    }
    
    # Maximum points possible
    MAX_SCORE = 100.0
    
    def __init__(self, profile: UserProfile):
        """
        Initialize matcher with a user profile
        
        Args:
            profile: The user's skill profile
        """
        self.profile = profile
        
        # Normalize all skills for matching
        self.primary_skills_normalized = {
            normalize_skill(s) for s in profile.primary_skills
        }
        self.secondary_skills_normalized = {
            normalize_skill(s) for s in profile.secondary_skills
        }
        self.domains_normalized = {
            d.lower() for d in profile.domains
        }
        
        # Combined skill set for extraction
        self.all_skills = list(set(
            profile.primary_skills + 
            profile.secondary_skills +
            list(self.primary_skills_normalized) +
            list(self.secondary_skills_normalized)
        ))
    
    def score_job(self, job: Job) -> MatchResult:
        """
        Score a single job against the user profile
        
        Returns:
            MatchResult with scores and matched skills
        """
        # Extract skills from job
        job_text = f"{job.title} {job.description} {' '.join(job.skills)}"
        job_skills = extract_skills_from_text(job_text, self.all_skills)
        job_skills_normalized = {normalize_skill(s) for s in job_skills}
        
        # Also include explicit job skills
        for skill in job.skills:
            job_skills_normalized.add(normalize_skill(skill))
        
        # Match primary skills
        matched_primary = self.primary_skills_normalized & job_skills_normalized
        matched_primary_original = [
            s for s in self.profile.primary_skills
            if normalize_skill(s) in matched_primary
        ]
        
        # Match secondary skills
        matched_secondary = self.secondary_skills_normalized & job_skills_normalized
        matched_secondary_original = [
            s for s in self.profile.secondary_skills
            if normalize_skill(s) in matched_secondary
        ]
        
        # Match domains
        job_text_lower = job_text.lower()
        matched_domains = [
            d for d in self.profile.domains
            if d.lower() in job_text_lower
        ]
        
        # Find missing skills (required but not in profile)
        all_user_skills = self.primary_skills_normalized | self.secondary_skills_normalized
        missing_skills = [
            s for s in job.skills
            if normalize_skill(s) not in all_user_skills
        ][:5]  # Limit to top 5
        
        # Calculate scores
        skill_score = self._calculate_skill_score(
            len(matched_primary), 
            len(matched_secondary),
            len(self.profile.primary_skills),
            len(self.profile.secondary_skills)
        )
        
        domain_score = self._calculate_domain_score(
            len(matched_domains),
            len(self.profile.domains)
        )
        
        rate_score = self._calculate_rate_score(job)
        
        # Overall score (weighted)
        overall_score = min(
            skill_score * 0.6 + domain_score * 0.25 + rate_score * 0.15,
            100.0
        )
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            overall_score,
            matched_primary_original,
            matched_domains,
            missing_skills
        )
        
        # Update job with match info
        job.match_score = overall_score
        job.matched_skills = matched_primary_original + matched_secondary_original
        job.missing_skills = missing_skills
        
        return MatchResult(
            job=job,
            overall_score=round(overall_score, 1),
            skill_score=round(skill_score, 1),
            domain_score=round(domain_score, 1),
            rate_score=round(rate_score, 1),
            matched_primary_skills=matched_primary_original,
            matched_secondary_skills=matched_secondary_original,
            matched_domains=matched_domains,
            missing_skills=missing_skills,
            recommendation=recommendation,
        )
    
    def _calculate_skill_score(
        self, 
        primary_matches: int, 
        secondary_matches: int,
        total_primary: int,
        total_secondary: int
    ) -> float:
        """Calculate skill match score (0-100)"""
        
        if total_primary == 0 and total_secondary == 0:
            return 50.0  # Neutral score if no skills defined
        
        # Calculate match percentages
        primary_pct = (primary_matches / total_primary * 100) if total_primary > 0 else 0
        secondary_pct = (secondary_matches / total_secondary * 100) if total_secondary > 0 else 0
        
        # Primary skills weighted more heavily
        if total_primary > 0 and total_secondary > 0:
            score = primary_pct * 0.7 + secondary_pct * 0.3
        elif total_primary > 0:
            score = primary_pct
        else:
            score = secondary_pct
        
        # Bonus for multiple matches
        total_matches = primary_matches + secondary_matches
        if total_matches >= 5:
            score = min(score + 10, 100)
        elif total_matches >= 3:
            score = min(score + 5, 100)
        
        return score
    
    def _calculate_domain_score(self, matches: int, total: int) -> float:
        """Calculate domain match score (0-100)"""
        
        if total == 0:
            return 50.0  # Neutral
        
        return (matches / total) * 100
    
    def _calculate_rate_score(self, job: Job) -> float:
        """Calculate rate match score (0-100)"""
        
        if not self.profile.preferred_rate_min:
            return 50.0  # Neutral if no preference
        
        if not job.rate_max and not job.rate_min:
            return 50.0  # Unknown rate
        
        job_rate = job.rate_max or job.rate_min
        
        if job_rate >= self.profile.preferred_rate_min:
            # Meets or exceeds preferred rate
            return 100.0
        elif job_rate >= self.profile.preferred_rate_min * 0.8:
            # Within 20% of preferred rate
            return 75.0
        elif job_rate >= self.profile.preferred_rate_min * 0.6:
            # Within 40%
            return 50.0
        else:
            return 25.0
    
    def _generate_recommendation(
        self,
        score: float,
        matched_primary: List[str],
        matched_domains: List[str],
        missing_skills: List[str]
    ) -> str:
        """Generate a brief recommendation"""
        
        if score >= 85:
            return f"🔥 Excellent match! Your {', '.join(matched_primary[:2])} skills align perfectly."
        elif score >= 70:
            return f"✅ Strong match. Good fit for your {', '.join(matched_primary[:2])} expertise."
        elif score >= 55:
            if missing_skills:
                return f"⚠️ Decent match, but may need: {', '.join(missing_skills[:2])}"
            return "⚠️ Moderate match. Review requirements carefully."
        elif score >= 40:
            return f"📝 Partial match. Missing: {', '.join(missing_skills[:3])}"
        else:
            return "❌ Low match. Skills don't align well with this role."
    
    def rank_jobs(self, jobs: List[Job]) -> List[MatchResult]:
        """
        Score and rank a list of jobs
        
        Returns:
            List of MatchResults sorted by score (highest first)
        """
        results = [self.score_job(job) for job in jobs]
        results.sort(key=lambda r: r.overall_score, reverse=True)
        return results

"""
User Profile Configuration

Edit this file to customize your skill profile and preferences.
"""

from models import UserProfile, JobType

# Your skill profile for job matching
DEFAULT_PROFILE = UserProfile(
    name="Prateek",
    
    # Primary Skills - Your core expertise (highest proficiency)
    primary_skills=[
        # Backend
        "Python",
        "FastAPI",
        "Django",
        "REST API",
        
        # Frontend
        "React",
        "TypeScript",
        "Vite",
        "JavaScript",
        
        # Cloud & DevOps
        "AWS",
        "Docker",
        "Kubernetes",
        "EKS",
        "Lambda",
        "GitHub Actions",
        "CI/CD",
        
        # AI/LLM
        "Bedrock",
        "LangChain",
        "LLM",
        "GenAI",
    ],
    
    # Secondary Skills - Comfortable working with
    secondary_skills=[
        # Databases
        "PostgreSQL",
        "MongoDB",
        "Redis",
        "RDS",
        "S3",
        
        # Additional tools
        "Helm",
        "ECR",
        "Terraform",
        "Celery",
        "SQLAlchemy",
        "Pydantic",
        
        # Frontend additional
        "TailwindCSS",
        "Tailwind",
        "Next.js",
        "HTML",
        "CSS",
        
        # Other
        "Git",
        "Linux",
        "Bash",
        "Microservices",
        "GraphQL",
    ],
    
    # Domain Expertise - Industry/vertical knowledge
    domains=[
        "Healthcare",
        "Life Sciences",
        "Clinical Trial",
        "Pharma",
        "FDA",
        "ICH",
        "Regulatory",
        "CTMS",
        "TMF",
        "CSR",
        "DSUR",
        "21 CFR",
        "Compliance",
        "Fintech",
    ],
    
    # Minimum acceptable hourly rate (USD)
    preferred_rate_min=50.0,
    
    # Preferred job types
    preferred_job_types=[
        JobType.CONTRACT,
        JobType.HOURLY,
        JobType.FIXED,
    ],
    
    # Years of experience
    experience_years=6,
    
    # Keywords to exclude from search results
    excluded_keywords=[
        "unpaid",
        "internship",
        "junior",
        "entry level",
        "wordpress only",
        "shopify only",
    ],
)


# Search defaults
DEFAULT_SEARCH_KEYWORDS = [
    "FastAPI",
    "Python Backend",
    "React TypeScript",
    "AWS",
    "Full Stack",
    "Clinical Trial",
    "Healthcare Software",
    "GenAI",
    "LLM",
]

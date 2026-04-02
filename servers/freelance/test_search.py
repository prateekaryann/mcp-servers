#!/usr/bin/env python3
"""
Quick test script to verify the MCP server works correctly.

Usage:
    python test_search.py
"""

import asyncio
import json
import sys

# Add parent to path for imports
sys.path.insert(0, ".")

async def test_search():
    """Test basic search functionality"""
    print("🔍 Testing Freelance Job Search MCP Server...")
    print("=" * 60)
    
    # Test imports
    print("\n1. Testing imports...")
    try:
        from models import Job, JobSearchParams, Platform, UserProfile
        from adapters import JobAggregator, ADAPTERS
        from matching import SkillMatcher
        from config import DEFAULT_PROFILE
        print("   ✅ All imports successful")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return False
    
    # Test available platforms
    print("\n2. Available platforms:")
    for platform in ADAPTERS.keys():
        print(f"   • {platform.value}")
    
    # Test profile
    print(f"\n3. Profile loaded: {DEFAULT_PROFILE.name}")
    print(f"   Primary skills: {len(DEFAULT_PROFILE.primary_skills)}")
    print(f"   Secondary skills: {len(DEFAULT_PROFILE.secondary_skills)}")
    print(f"   Domains: {len(DEFAULT_PROFILE.domains)}")
    
    # Test search on one platform (RemoteOK - most reliable)
    print("\n4. Testing search on RemoteOK...")
    try:
        params = JobSearchParams(
            keywords=["Python"],
            skills=["FastAPI"],
            platforms=[Platform.REMOTEOK],
            max_results=5,
            posted_within_hours=168,
        )
        
        aggregator = JobAggregator([Platform.REMOTEOK])
        jobs = await aggregator.search(params)
        await aggregator.close()
        
        print(f"   ✅ Found {len(jobs)} jobs")
        
        if jobs:
            print("\n   Sample job:")
            job = jobs[0]
            print(f"   • Title: {job.title}")
            print(f"   • Company: {job.company}")
            print(f"   • Skills: {', '.join(job.skills[:5])}")
            print(f"   • URL: {job.url}")
    
    except Exception as e:
        print(f"   ❌ Search error: {e}")
        return False
    
    # Test skill matching
    print("\n5. Testing skill matcher...")
    try:
        if jobs:
            matcher = SkillMatcher(DEFAULT_PROFILE)
            result = matcher.score_job(jobs[0])
            print(f"   ✅ Match score: {result.overall_score}%")
            print(f"   Matched skills: {', '.join(result.matched_primary_skills[:3])}")
            print(f"   Recommendation: {result.recommendation}")
    except Exception as e:
        print(f"   ❌ Matching error: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All tests passed! The MCP server is ready to use.")
    print("\nNext steps:")
    print("1. Configure Claude Desktop with the MCP server")
    print("2. Set up Telegram notifications (optional)")
    print("3. Deploy scheduled search via GitHub Actions (optional)")
    
    return True


async def test_all_platforms():
    """Test all platforms (takes longer)"""
    from adapters import ADAPTERS, JobAggregator
    from models import JobSearchParams, Platform
    
    print("\n🌐 Testing all platforms...")
    print("=" * 60)
    
    params = JobSearchParams(
        keywords=["Python", "Developer"],
        skills=["React"],
        max_results=3,
        posted_within_hours=168,
    )
    
    results = {}
    
    for platform in ADAPTERS.keys():
        print(f"\n• Testing {platform.value}...", end=" ")
        try:
            aggregator = JobAggregator([platform])
            jobs = await aggregator.search(params)
            await aggregator.close()
            results[platform.value] = len(jobs)
            print(f"✅ {len(jobs)} jobs")
        except Exception as e:
            results[platform.value] = f"Error: {e}"
            print(f"❌ {e}")
    
    print("\n" + "=" * 60)
    print("Summary:")
    for platform, result in results.items():
        status = "✅" if isinstance(result, int) and result > 0 else "⚠️" if isinstance(result, int) else "❌"
        print(f"  {status} {platform}: {result}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test the job search MCP server")
    parser.add_argument("--all", action="store_true", help="Test all platforms")
    args = parser.parse_args()
    
    if args.all:
        asyncio.run(test_all_platforms())
    else:
        asyncio.run(test_search())

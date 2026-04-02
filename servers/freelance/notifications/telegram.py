"""
Telegram Notification Module

Sends alerts to Telegram when new matching jobs are found.

Setup:
1. Create a Telegram bot via @BotFather
2. Get your chat ID by messaging the bot and checking /getUpdates
3. Set environment variables:
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
"""

import os
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
import httpx

from models import Job, MatchResult

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends job alerts to Telegram
    """
    
    def __init__(
        self,
        bot_token: str = None,
        chat_id: str = None,
    ):
        """
        Initialize Telegram notifier
        
        Args:
            bot_token: Telegram bot token (or set TELEGRAM_BOT_TOKEN env var)
            chat_id: Telegram chat ID (or set TELEGRAM_CHAT_ID env var)
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured")
        
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        self.client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured"""
        return bool(self.bot_token and self.chat_id)
    
    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message to Telegram
        
        Args:
            text: Message text (supports HTML formatting)
            parse_mode: "HTML" or "Markdown"
            
        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            logger.warning("Telegram not configured, skipping notification")
            return False
        
        try:
            response = await self.client.post(
                f"{self.api_base}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                }
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def notify_new_jobs(self, jobs: List[Job], title: str = "🔔 New Job Alerts") -> bool:
        """
        Send notification about new jobs
        
        Args:
            jobs: List of new jobs to notify about
            title: Notification title
        """
        if not jobs:
            return True
        
        # Build message
        lines = [f"<b>{title}</b>", f"Found {len(jobs)} new matching jobs:", ""]
        
        for i, job in enumerate(jobs[:10], 1):  # Limit to 10 jobs per message
            rate_str = f"${job.rate_min:.0f}-{job.rate_max:.0f}/hr" if job.rate_min else "Rate TBD"
            skills_str = ", ".join(job.skills[:5]) if job.skills else "N/A"
            
            lines.extend([
                f"<b>{i}. {self._escape_html(job.title)}</b>",
                f"🏢 {self._escape_html(job.company or 'Unknown')}",
                f"💰 {rate_str}",
                f"🔧 {skills_str}",
                f"🔗 <a href=\"{job.url}\">Apply</a>",
                "",
            ])
        
        if len(jobs) > 10:
            lines.append(f"... and {len(jobs) - 10} more jobs")
        
        message = "\n".join(lines)
        return await self.send_message(message)
    
    async def notify_top_matches(
        self, 
        matches: List[MatchResult], 
        title: str = "🎯 Top Job Matches"
    ) -> bool:
        """
        Send notification about top matching jobs
        
        Args:
            matches: List of MatchResult objects
            title: Notification title
        """
        if not matches:
            return True
        
        lines = [f"<b>{title}</b>", ""]
        
        for i, match in enumerate(matches[:5], 1):  # Top 5 matches
            job = match.job
            score_emoji = "🔥" if match.overall_score >= 80 else "✅" if match.overall_score >= 60 else "📝"
            
            lines.extend([
                f"{score_emoji} <b>#{i} Score: {match.overall_score:.0f}%</b>",
                f"<b>{self._escape_html(job.title)}</b>",
                f"🏢 {self._escape_html(job.company or 'Unknown')}",
                f"✓ Matched: {', '.join(match.matched_primary_skills[:3])}",
                f"🔗 <a href=\"{job.url}\">View Job</a>",
                "",
            ])
        
        message = "\n".join(lines)
        return await self.send_message(message)
    
    async def notify_daily_summary(
        self,
        total_searched: int,
        new_jobs: int,
        top_match_score: float,
        platforms: List[str],
    ) -> bool:
        """
        Send daily summary notification
        """
        lines = [
            "📊 <b>Daily Job Search Summary</b>",
            "",
            f"🔍 Platforms searched: {', '.join(platforms)}",
            f"📋 Total jobs found: {total_searched}",
            f"🆕 New since yesterday: {new_jobs}",
            f"🎯 Top match score: {top_match_score:.0f}%",
            "",
            f"<i>Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</i>",
        ]
        
        message = "\n".join(lines)
        return await self.send_message(message)
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters"""
        if not text:
            return ""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class DiscordNotifier:
    """
    Sends job alerts to Discord via webhook
    
    Setup:
    1. Create a webhook in your Discord server
    2. Set DISCORD_WEBHOOK_URL environment variable
    """
    
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.client = httpx.AsyncClient(timeout=30.0)
    
    @property
    def is_configured(self) -> bool:
        return bool(self.webhook_url)
    
    async def send_message(self, content: str, embeds: List[dict] = None) -> bool:
        """Send a message to Discord"""
        if not self.is_configured:
            return False
        
        try:
            payload = {"content": content}
            if embeds:
                payload["embeds"] = embeds
            
            response = await self.client.post(self.webhook_url, json=payload)
            return response.status_code in (200, 204)
            
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False
    
    async def notify_new_jobs(self, jobs: List[Job]) -> bool:
        """Send job notifications to Discord"""
        if not jobs:
            return True
        
        embeds = []
        for job in jobs[:10]:
            embed = {
                "title": job.title[:256],
                "url": str(job.url),
                "color": 0x00ff00,  # Green
                "fields": [
                    {"name": "Company", "value": job.company or "Unknown", "inline": True},
                    {"name": "Platform", "value": job.platform, "inline": True},
                    {"name": "Rate", "value": f"${job.rate_min}-{job.rate_max}/hr" if job.rate_min else "TBD", "inline": True},
                    {"name": "Skills", "value": ", ".join(job.skills[:5]) or "N/A", "inline": False},
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }
            embeds.append(embed)
        
        return await self.send_message(f"🔔 Found {len(jobs)} new jobs!", embeds=embeds[:10])
    
    async def close(self):
        await self.client.aclose()


class EmailNotifier:
    """
    Sends job alerts via email (SMTP)
    
    Set environment variables:
    - SMTP_HOST
    - SMTP_PORT
    - SMTP_USER
    - SMTP_PASSWORD
    - EMAIL_FROM
    - EMAIL_TO
    """
    
    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER")
        self.password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("EMAIL_FROM")
        self.to_email = os.getenv("EMAIL_TO")
    
    @property
    def is_configured(self) -> bool:
        return all([self.user, self.password, self.from_email, self.to_email])
    
    async def send_email(self, subject: str, body: str) -> bool:
        """Send an email (requires aiosmtplib)"""
        if not self.is_configured:
            return False
        
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = self.to_email
            
            msg.attach(MIMEText(body, "html"))
            
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=True,
            )
            return True
            
        except ImportError:
            logger.warning("aiosmtplib not installed, email notifications unavailable")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


# Convenience function
async def notify_all(
    jobs: List[Job] = None,
    matches: List[MatchResult] = None,
    telegram: bool = True,
    discord: bool = False,
    email: bool = False,
) -> dict:
    """
    Send notifications to all configured channels
    
    Returns:
        Dict with status for each channel
    """
    results = {}
    
    if telegram:
        notifier = TelegramNotifier()
        if notifier.is_configured:
            if matches:
                results["telegram"] = await notifier.notify_top_matches(matches)
            elif jobs:
                results["telegram"] = await notifier.notify_new_jobs(jobs)
            await notifier.close()
    
    if discord:
        notifier = DiscordNotifier()
        if notifier.is_configured:
            if jobs:
                results["discord"] = await notifier.notify_new_jobs(jobs)
            await notifier.close()
    
    return results

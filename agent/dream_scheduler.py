# Dream Scheduler
"""Dream scheduler for timezone-aware scheduled events."""
import asyncio
import crontab
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path


class DreamScheduler:
    """Scheduler for agent dream mode with timezone awareness."""

    def __init__(self, agent):
        self.agent = agent
        self.logger = agent.logger if agent else None
        self.cron_jobs: Dict[str, Dict[str, Any]] = {}
        self.running = False
        self._check_interval = 60  # Check every minute

    async def start(self):
        """Start the dream scheduler."""
        self.running = True
        if self.logger:
            self.logger.log_stage("dream_scheduler_start", {})
        await self._schedule_default_dream()
        await self._run_scheduler_loop()

    async def stop(self):
        """Stop the dream scheduler."""
        self.running = False
        if self.logger:
            self.logger.log_stage("dream_scheduler_stop", {})

    async def _schedule_default_dream(self):
        """Schedule default dream at 2 AM user's local time."""
        timezone_str = await self.agent.get_timezone()
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo("America/New_York")

        # Calculate next 2 AM in user's timezone
        now = datetime.now(tz)
        next_dream = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if now.hour >= 2:
            next_dream += timedelta(days=1)

        self.cron_jobs["default_dream"] = {
            "cron": f"0 2 * * *",  # 2 AM daily
            "timezone": timezone_str,
            "next_run": next_dream,
            "callback": "run_dream_cycle",
        }

    async def _run_scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                await self._check_jobs()
                await asyncio.sleep(self._check_interval)
            except Exception as e:
                if self.logger:
                    self.logger.log_stage("scheduler_error", {"error": str(e)})
                await asyncio.sleep(self._check_interval)

    async def _check_jobs(self):
        """Check and execute due jobs."""
        now = datetime.now(timezone.utc)
        timezone_str = await self.agent.get_timezone()

        try:
            tz = ZoneInfo(timezone_str)
            local_now = now.astimezone(tz)
        except Exception:
            local_now = now

        for job_name, job in self.cron_jobs.items():
            if job.get("next_run") and local_now >= job["next_run"]:
                await self._execute_job(job_name, job)
                await self._schedule_next_run(job)

    async def _schedule_next_run(self, job: Dict[str, Any]):
        """Schedule the next run for a cron job."""
        cron_expr = job.get("cron", "0 2 * * *")

        try:
            tz_name = job.get("timezone", "America/New_York")
            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)

            # Simple cron parsing for common patterns
            parts = cron_expr.split()
            if len(parts) >= 2:
                minute, hour = int(parts[0]), int(parts[1])
                next_run = now.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if now.hour * 60 + now.minute >= hour * 60 + minute:
                    next_run += timedelta(days=1)
                job["next_run"] = next_run.astimezone(timezone.utc)
        except Exception as e:
            if self.logger:
                self.logger.log_stage("cron_parse_error", {"error": str(e)})

    async def _execute_job(self, job_name: str, job: Dict[str, Any]):
        """Execute a scheduled job."""
        callback = job.get("callback", "run_dream_cycle")

        if self.logger:
            self.logger.log_stage("execute_job", {"job": job_name, "callback": callback})

        if callback == "run_dream_cycle":
            await self._run_dream_job()

    async def _run_dream_job(self):
        """Execute dream cycle for scheduled job."""
        from agent.automated_manager import AutomatedMemoryManager

        if self.logger:
            self.logger.log_stage("dream_job_start", {})

        manager = AutomatedMemoryManager(self.agent)
        result = await manager.run_dream_cycle()

        if self.logger:
            self.logger.log_stage("dream_job_complete", {"result": result})

    async def add_cron_job(self, name: str, cron_expr: str, timezone_str: str = None):
        """Add a cron job."""
        timezone_str = timezone_str or await self.agent.get_timezone()

        self.cron_jobs[name] = {
            "cron": cron_expr,
            "timezone": timezone_str,
            "next_run": None,
            "callback": "run_dream_cycle",
        }

        # Calculate initial next run
        await self._schedule_next_run(self.cron_jobs[name])

    async def remove_job(self, name: str) -> bool:
        """Remove a cron job."""
        if name in self.cron_jobs:
            del self.cron_jobs[name]
            return True
        return False

    async def list_jobs(self) -> List[Dict[str, Any]]:
        """List all scheduled jobs."""
        await self._schedule_default_dream()  # Ensure default exists
        return [
            {
                "name": name,
                "cron": job.get("cron"),
                "timezone": job.get("timezone"),
                "next_run": job.get("next_run"),
            }
            for name, job in self.cron_jobs.items()
        ]

    async def trigger_now(self, job_name: str) -> Dict[str, Any]:
        """Trigger a job immediately."""
        if job_name not in self.cron_jobs:
            return {"success": False, "error": f"Job '{job_name}' not found"}

        job = self.cron_jobs[job_name]
        await self._execute_job(job_name, job)
        return {"success": True, "job": job_name}


async def run_dream_cycle(agent) -> Dict[str, Any]:
    """Run a dream cycle."""
    from agent.automated_manager import AutomatedMemoryManager

    manager = AutomatedMemoryManager(agent)
    return await manager.run_dream_cycle()
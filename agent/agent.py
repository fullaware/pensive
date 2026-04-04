# Agent Base Class
"""Base agent class with shared memory access and timezone awareness."""
import asyncio
import importlib.util
import sys
import os
import json
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timezone, timedelta
from pathlib import Path

from memory_system import (
    ShortTermMemory,
    EpisodicMemory,
    SemanticMemory,
    QueryRouter,
    SystemPromptsManager,
    Bootstrapper,
    Config,
    MongoDB,
    db,
    COLLECTION_EPISODIC,
    COLLECTION_FACTS,
)
from utils import LLMClient, EmbeddingClient
from time_management import TaskManager, ReminderManager, TimeTracker


class AgentLogger:
    """Logger for agent operations with timing and metrics."""

    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.stages: List[Dict] = []
        self.start_time: float = 0

    def start(self):
        """Start timing."""
        self.start_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0

    def log_stage(self, stage: str, details: Optional[Dict] = None):
        """Log a stage with timing."""
        elapsed = asyncio.get_event_loop().time() - self.start_time if asyncio.get_event_loop().is_running() else 0
        self.stages.append({
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "details": details or {}
        })
        print(f"[{self.agent_id}:{stage}] elapsed={elapsed:.3f}s | {details}")


class AgentPreferences:
    """User preferences for an agent session."""

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.collection = db.get_collection("user_preferences")
        self._preferences: Dict[str, Any] = {
            "timezone": "America/New_York",
            "communication_style": "short",  # "short" or "long"
            "use_emojis": False,
            "notifications_enabled": True,
            "active_skills": [],
        }
        self._loaded = False

    async def load(self) -> Dict[str, Any]:
        """Load preferences from MongoDB."""
        if self._loaded:
            return self._preferences

        doc = await self.collection.find_one({"user_id": self.user_id})
        if doc:
            self._preferences.update({
                "timezone": doc.get("timezone", "America/New_York"),
                "communication_style": doc.get("communication_style", "short"),
                "use_emojis": doc.get("use_emojis", False),
                "notifications_enabled": doc.get("notifications_enabled", True),
                "active_skills": doc.get("active_skills", []),
            })
        self._loaded = True
        return self._preferences

    async def update(self, key: str, value: Any) -> bool:
        """Update a preference."""
        self._preferences[key] = value
        await self.collection.update_one(
            {"user_id": self.user_id},
            {"$set": {key: value}},
            upsert=True
        )
        return True

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a preference value."""
        if not self._loaded:
            await self.load()
        return self._preferences.get(key, default)

    async def add_active_skill(self, skill_name: str) -> bool:
        """Add a skill to active skills list."""
        if skill_name not in self._preferences.get("active_skills", []):
            await self.update("active_skills", self._preferences.get("active_skills", []) + [skill_name])
            return True
        return False

    async def remove_active_skill(self, skill_name: str) -> bool:
        """Remove a skill from active skills list."""
        skills = self._preferences.get("active_skills", [])
        if skill_name in skills:
            await self.update("active_skills", [s for s in skills if s != skill_name])
            return True
        return False


class AgentSkill:
    """Represents a skill that can be executed by the agent."""

    def __init__(self, skill_path: Path):
        self.path = skill_path
        self.name = skill_path.stem
        self.module = None
        self._metadata: Dict[str, Any] = {}
        self._load_metadata()

    def _load_metadata(self):
        """Load skill metadata from file."""
        try:
            with open(self.path, 'r') as f:
                content = f.read()
                # Extract metadata from __skill_name__, __skill_description__, __skill_active__
                self._metadata = {
                    "name": self.name,
                    "description": "No description available",
                    "active": False,
                }
                # Try to find metadata comments
                for line in content.split('\n'):
                    if line.startswith('# __skill_name__'):
                        self._metadata["name"] = line.split('=', 1)[1].strip().strip('"\'')
                    elif line.startswith('# __skill_description__'):
                        self._metadata["description"] = line.split('=', 1)[1].strip().strip('"\'')
                    elif line.startswith('# __skill_active__'):
                        val = line.split('=', 1)[1].strip().lower()
                        self._metadata["active"] = val in ('true', '1', 'yes')
        except Exception as e:
            print(f"Error loading skill metadata: {e}")

    async def load_module(self) -> Optional[Any]:
        """Load the skill as a Python module."""
        if self.module:
            return self.module

        try:
            spec = importlib.util.spec_from_file_location(self.name, self.path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[self.name] = module
                spec.loader.exec_module(module)
                self.module = module
                return module
        except Exception as e:
            print(f"Error loading skill module: {e}")
        return None

    async def execute(self, *args, **kwargs) -> Optional[Any]:
        """Execute the skill's execute function."""
        module = await self.load_module()
        if module and hasattr(module, 'execute'):
            try:
                result = module.execute(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except Exception as e:
                print(f"Error executing skill {self.name}: {e}")
        return None

    def is_active(self) -> bool:
        """Check if skill is active."""
        return self._metadata.get("active", False)

    def activate(self):
        """Mark skill as active."""
        self._metadata["active"] = True

    def deactivate(self):
        """Mark skill as inactive."""
        self._metadata["active"] = False

    def get_metadata(self) -> Dict[str, Any]:
        """Get skill metadata."""
        return self._metadata


class BaseAgent:
    """Base agent class with shared memory access and timezone awareness."""

    def __init__(self, agent_id: str = "default", user_id: str = "default"):
        self.agent_id = agent_id
        self.user_id = user_id
        self.logger = AgentLogger(agent_id)
        self.preferences: Optional[AgentPreferences] = None
        self.skills: Dict[str, AgentSkill] = {}
        self._skills_loaded = False

        # Memory systems
        self.short_term = ShortTermMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.router = QueryRouter()
        self.system_prompts = SystemPromptsManager()
        self.llm = LLMClient()
        self.embedding_client = EmbeddingClient()
        self.tasks = TaskManager()
        self.reminders = ReminderManager()
        self.time_tracker = TimeTracker()

    async def initialize(self):
        """Initialize the agent."""
        self.preferences = AgentPreferences(self.user_id)
        await self.load_skills()

    async def close(self):
        """Close all clients and connections."""
        await self.episodic.close()
        await self.router.close()
        await self.llm.close()

    async def load_skills(self):
        """Load skills from the skills directory (system and built)."""
        skills_dir = Path(__file__).parent.parent / "skills"
        if not skills_dir.exists():
            return

        # Load system skills from /skills/system/
        system_dir = skills_dir / "system"
        if system_dir.exists():
            for skill_file in system_dir.glob("*.py"):
                skill = AgentSkill(skill_file)
                self.skills[skill.name] = skill

        # Load built skills from /skills/built/
        built_dir = skills_dir / "built"
        if built_dir.exists():
            for skill_file in built_dir.glob("*.py"):
                skill = AgentSkill(skill_file)
                self.skills[skill.name] = skill

        self._skills_loaded = True

    async def get_active_skills(self) -> List[AgentSkill]:
        """Get list of active skills."""
        await self.load_skills()
        return [s for s in self.skills.values() if s.is_active()]

    async def execute_skill(self, skill_name: str, *args, **kwargs) -> Optional[Any]:
        """Execute a skill by name."""
        if skill_name not in self.skills:
            return None
        return await self.skills[skill_name].execute(*args, **kwargs)

    async def build_skill(self, description: str) -> Dict[str, Any]:
        """Build a new skill using LLM from a natural language description."""
        self.logger.log_stage("skill_building", {"description": description[:100]})

        prompt = """Create a Python skill based on the user's description. The skill should:
1. Have a clear __skill_name__ (snake_case, descriptive)
2. Have a __skill_description__ explaining what it does
3. Be __skill_active__ = False (deactivated by default)
4. Import only: httpx, json, asyncio
5. Have an async execute() function that performs the task

Respond in this exact JSON format:
{
    "skill_name": "skill_name_here",
    "description": "What the skill does",
    "code": "full python code here"
}

Examples:
- For "search zen for queries": skill_name = "search_zen", code uses httpx to call the search API
- For "get current weather": skill_name = "get_weather", code makes API call to weather service

Description: {description}

Respond ONLY with valid JSON, no markdown, no explanations.
"""

        messages = [
            {"role": "system", "content": prompt.format(description=description)},
            {"role": "user", "content": "Create the skill now."},
        ]

        response = await self.llm.generate(messages, temperature=0.2, max_tokens=2000)
        
        if not response:
            return {"error": "LLM returned empty response"}

        # Parse JSON response
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "success": True,
                    "skill_name": result.get("skill_name", "unnamed_skill"),
                    "description": result.get("description", ""),
                    "code": result.get("code", ""),
                }
        except json.JSONDecodeError:
            return {"error": f"Failed to parse LLM response: {response}"}

        return {"error": "Failed to create skill"}

    async def save_skill(self, skill_name: str, description: str, code: str) -> Dict[str, Any]:
        """Save a skill to the skills directory."""
        skills_dir = Path(__file__).parent.parent / "skills" / "built"
        skills_dir.mkdir(exist_ok=True)

        skill_file = skills_dir / f"{skill_name}.py"
        
        # Write skill file with metadata
        skill_content = f"""# __skill_name__ = "{skill_name}"
# __skill_description__ = "{description}"
# __skill_active__ = False

{code}
"""
        try:
            with open(skill_file, 'w') as f:
                f.write(skill_content)
            return {"success": True, "path": str(skill_file)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def activate_skill(self, skill_name: str) -> Dict[str, Any]:
        """Activate a skill."""
        if skill_name not in self.skills:
            await self.load_skills()

        if skill_name not in self.skills:
            return {"success": False, "error": f"Skill '{skill_name}' not found"}

        skill = self.skills[skill_name]
        skill.activate()

        # Update metadata in file
        skill_file = Path(__file__).parent.parent / "skills" / "built" / f"{skill_name}.py"
        if skill_file.exists():
            with open(skill_file, 'r') as f:
                content = f.read()
            content = content.replace('__skill_active__ = False', '__skill_active__ = True')
            with open(skill_file, 'w') as f:
                f.write(content)

        if self.preferences:
            await self.preferences.add_active_skill(skill_name)

        return {"success": True, "skill_name": skill_name}

    async def deactivate_skill(self, skill_name: str) -> Dict[str, Any]:
        """Deactivate a skill."""
        if skill_name not in self.skills:
            return {"success": False, "error": f"Skill '{skill_name}' not found"}

        skill = self.skills[skill_name]
        skill.deactivate()

        # Update metadata in file
        skill_file = Path(__file__).parent.parent / "skills" / "built" / f"{skill_name}.py"
        if skill_file.exists():
            with open(skill_file, 'r') as f:
                content = f.read()
            content = content.replace('__skill_active__ = True', '__skill_active__ = False')
            with open(skill_file, 'w') as f:
                f.write(content)

        if self.preferences:
            await self.preferences.remove_active_skill(skill_name)

        return {"success": True, "skill_name": skill_name}

    async def list_skills(self) -> List[Dict[str, Any]]:
        """List all available skills with metadata."""
        await self.load_skills()
        return [skill.get_metadata() for skill in self.skills.values()]

    async def get_timezone(self) -> str:
        """Get agent's timezone."""
        if self.preferences:
            return await self.preferences.get("timezone", "America/New_York")
        return "America/New_York"

    async def get_current_time(self) -> str:
        """Get current time in agent's timezone."""
        tz_name = await self.get_timezone()
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
            now = datetime.now(timezone.utc).astimezone(tz)
            return now.strftime("%B %d, %Y at %I:%M %p %Z")
        except Exception:
            return datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

    async def process_query(self, user_query: str, session_id: str = None, commit_memories: bool = True) -> Dict:
        """Process a user query using all memory systems."""
        raise NotImplementedError("Subclasses must implement process_query")

    async def detect_intent(self, user_query: str) -> Dict:
        """Detect intent from user query."""
        return await self.router.determine_intent(user_query)
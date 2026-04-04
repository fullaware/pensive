# Skills Manager
"""Skills manager for registering, validating, and executing skills."""
import asyncio
import importlib.util
import sys
import os
import re
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timezone


class SkillsManager:
    """Manager for agent skills."""

    def __init__(self, agent):
        self.agent = agent
        self.logger = agent.logger if agent else None
        self.skills: Dict[str, "ManagedSkill"] = {}
        self.skills_dir = Path(__file__).parent.parent / "skills"
        self.built_dir = self.skills_dir / "built"

        # Ensure directories exist
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.built_dir.mkdir(parents=True, exist_ok=True)

    async def load_skills(self) -> Dict[str, "ManagedSkill"]:
        """Load all skills from the skills directory."""
        if self.logger:
            self.logger.log_stage("load_skills", {"skills_dir": str(self.skills_dir)})

        # Clear existing skills
        self.skills.clear()

        # Load system skills
        await self._load_system_skills()

        # Load built skills
        await self._load_built_skills()

        return self.skills

    async def _load_system_skills(self):
        """Load system skills from /skills/system/."""
        system_dir = self.skills_dir / "system"
        if not system_dir.exists():
            return

        for skill_file in system_dir.glob("*.py"):
            skill = ManagedSkill.from_file(skill_file)
            if skill:
                self.skills[skill.name] = skill

    async def _load_built_skills(self):
        """Load user-built skills from /skills/built/."""
        if not self.built_dir.exists():
            return

        for skill_file in self.built_dir.glob("*.py"):
            skill = ManagedSkill.from_file(skill_file)
            if skill:
                self.skills[skill.name] = skill

    async def get_skill(self, name: str) -> Optional["ManagedSkill"]:
        """Get a skill by name."""
        if name not in self.skills:
            await self.load_skills()
        return self.skills.get(name)

    async def activate_skill(self, name: str) -> Dict[str, Any]:
        """Activate a skill."""
        skill = await self.get_skill(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found"}

        skill.activate()
        await skill.update_active_status(True)

        if self.agent.preferences:
            await self.agent.preferences.add_active_skill(name)

        return {"success": True, "skill_name": name}

    async def deactivate_skill(self, name: str) -> Dict[str, Any]:
        """Deactivate a skill."""
        skill = await self.get_skill(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found"}

        skill.deactivate()
        await skill.update_active_status(False)

        if self.agent.preferences:
            await self.agent.preferences.remove_active_skill(name)

        return {"success": True, "skill_name": name}

    async def build_skill(self, description: str) -> Dict[str, Any]:
        """Build a new skill using LLM."""
        if self.logger:
            self.logger.log_stage("build_skill", {"description": description[:100]})

        # Build skill using agent
        result = await self.agent.build_skill(description)

        if not result.get("success"):
            return result

        # Save skill
        save_result = await self.agent.save_skill(
            result["skill_name"],
            result["description"],
            result["code"]
        )

        if not save_result.get("success"):
            return {"success": False, "error": save_result.get("error")}

        # Reload skills
        await self.load_skills()

        return {
            "success": True,
            "skill_name": result["skill_name"],
            "description": result["description"],
            "path": save_result.get("path"),
        }

    async def list_skills(self) -> List[Dict[str, Any]]:
        """List all skills with metadata."""
        await self.load_skills()
        return [skill.get_metadata() for skill in self.skills.values()]

    async def get_active_skills(self) -> List["ManagedSkill"]:
        """Get list of active skills."""
        await self.load_skills()
        return [s for s in self.skills.values() if s.is_active()]

    async def execute_skill(self, name: str, *args, **kwargs) -> Optional[Any]:
        """Execute a skill by name."""
        skill = await self.get_skill(name)
        if not skill:
            return None
        return await skill.execute(*args, **kwargs)


class ManagedSkill:
    """Represents a skill with management capabilities."""

    def __init__(self, name: str, path: Path, code: str, description: str = "", active: bool = False):
        self.name = name
        self.path = path
        self.code = code
        self.description = description
        self.active = active
        self.module = None
        self._execute_func = None

    @classmethod
    def from_file(cls, path: Path) -> Optional["ManagedSkill"]:
        """Create a ManagedSkill from a Python file."""
        try:
            with open(path, 'r') as f:
                content = f.read()

            # Extract metadata
            name = path.stem
            description = "No description available"
            active = False

            for line in content.split('\n'):
                if line.startswith('# __skill_name__'):
                    name = line.split('=', 1)[1].strip().strip('"\'')
                elif line.startswith('# __skill_description__'):
                    description = line.split('=', 1)[1].strip().strip('"\'')
                elif line.startswith('# __skill_active__'):
                    val = line.split('=', 1)[1].strip().lower()
                    active = val in ('true', '1', 'yes')

            return cls(
                name=name,
                path=path,
                code=content,
                description=description,
                active=active,
            )
        except Exception as e:
            print(f"Error loading skill from {path}: {e}")
            return None

    def activate(self):
        """Mark skill as active."""
        self.active = True

    def deactivate(self):
        """Mark skill as inactive."""
        self.active = False

    def is_active(self) -> bool:
        """Check if skill is active."""
        return self.active

    async def update_active_status(self, active: bool):
        """Update active status in the skill file."""
        if not self.path.exists():
            return

        with open(self.path, 'r') as f:
            content = f.read()

        content = content.replace(
            f'# __skill_active__ = {not active}',
            f'# __skill_active__ = {active}'
        )

        with open(self.path, 'w') as f:
            f.write(content)

        self.active = active

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

    def get_metadata(self) -> Dict[str, Any]:
        """Get skill metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "active": self.active,
            "path": str(self.path),
        }
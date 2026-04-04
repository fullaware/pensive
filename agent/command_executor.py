# Command Executor
"""Command executor for handling system commands."""
import asyncio
import json
import os
import subprocess
import tempfile
from typing import Dict, Optional, Any, List
from pathlib import Path
from datetime import datetime, timezone


class SafeExecutor:
    """Sandboxed Python executor with restricted imports."""

    ALLOWED_MODULES = {"httpx", "json", "re", "datetime", "asyncio", "time", "math"}
    MAX_EXECUTION_TIME = 30  # seconds

    def __init__(self, agent):
        self.agent = agent
        self.logger = agent.logger if agent else None

    async def execute_code(self, code: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute Python code in a sandboxed environment."""
        if self.logger:
            self.logger.log_stage("safe_execution", {"code_length": len(code)})

        # Create restricted globals
        restricted_globals = {
            "__builtins__": {
                "True": True,
                "False": False,
                "None": None,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "print": print,
                "len": len,
                "range": range,
                "abs": abs,
                "round": round,
            },
            "asyncio": asyncio,
            "datetime": datetime,
            "time": __import__("time"),
            "math": __import__("math"),
            "re": __import__("re"),
            "json": json,
        }

        # Add allowed httpx module
        try:
            restricted_globals["httpx"] = __import__("httpx")
        except ImportError:
            return {"success": False, "error": "httpx module not available"}

        # Add context variables
        if context:
            restricted_globals.update(context)

        # Execute in temporary file for better error handling
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # Execute the code
            exec_result = {}
            exec_globals = restricted_globals.copy()

            # Use exec with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: exec(compile(code, temp_file, 'exec'), exec_globals, exec_result)),
                timeout=self.MAX_EXECUTION_TIME
            )

            return {
                "success": True,
                "result": exec_result,
                "output": exec_globals.get("_output", ""),
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Execution timed out after {self.MAX_EXECUTION_TIME}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            os.unlink(temp_file)

    async def execute_function(self, module_name: str, function_name: str, *args, **kwargs) -> Dict[str, Any]:
        """Execute a specific function from a module."""
        if self.logger:
            self.logger.log_stage("function_execution", {
                "module": module_name,
                "function": function_name,
            })

        try:
            module = __import__(module_name, fromlist=[function_name])
            func = getattr(module, function_name)

            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            return {"success": True, "result": result}
        except ImportError as e:
            return {"success": False, "error": f"Module not found: {e}"}
        except AttributeError as e:
            return {"success": False, "error": f"Function not found: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class CommandExecutor:
    """Executor for system commands."""

    def __init__(self, agent):
        self.agent = agent
        self.safe_executor = SafeExecutor(agent)
        self.logger = agent.logger if agent else None

    async def execute_command(self, command: str, details: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a system command."""
        if self.logger:
            self.logger.log_stage("command_execution", {"command": command, "details": details})

        if command == "build_skill":
            return await self._execute_build_skill(details)
        elif command == "activate_skill":
            return await self._execute_activate_skill(details)
        elif command == "deactivate_skill":
            return await self._execute_deactivate_skill(details)
        elif command == "list_skills":
            return await self._execute_list_skills(details)
        elif command == "set_preference":
            return await self._execute_set_preference(details)
        elif command == "run_dream":
            return await self._execute_run_dream(details)
        else:
            return {"success": False, "error": f"Unknown command: {command}"}

    async def _execute_build_skill(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute build skill command."""
        description = details.get("skill_description", "")

        if not description:
            return {"success": False, "error": "No skill description provided"}

        # Build skill using LLM
        result = await self.agent.build_skill(description)

        if result.get("success"):
            # Save skill
            save_result = await self.agent.save_skill(
                result["skill_name"],
                result["description"],
                result["code"]
            )
            return {
                "success": True,
                "skill_name": result["skill_name"],
                "description": result["description"],
                "status": "created (deactivated)",
            }
        return result

    async def _execute_activate_skill(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute activate skill command."""
        skill_name = details.get("skill_name", "")

        if not skill_name:
            return {"success": False, "error": "No skill name provided"}

        result = await self.agent.activate_skill(skill_name)
        return result

    async def _execute_deactivate_skill(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute deactivate skill command."""
        skill_name = details.get("skill_name", "")

        if not skill_name:
            return {"success": False, "error": "No skill name provided"}

        result = await self.agent.deactivate_skill(skill_name)
        return result

    async def _execute_list_skills(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute list skills command."""
        skills = await self.agent.list_skills()

        # Filter and format
        active_skills = [s for s in skills if s.get("active", False)]
        inactive_skills = [s for s in skills if not s.get("active", False)]

        return {
            "success": True,
            "total": len(skills),
            "active": len(active_skills),
            "inactive": len(inactive_skills),
            "skills": skills,
        }

    async def _execute_set_preference(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute set preference command."""
        preference = details.get("preference", {})

        if not preference:
            return {"success": False, "error": "No preference provided"}

        results = []
        for key, value in preference.items():
            await self.agent.preferences.update(key, value)
            results.append({"key": key, "value": value, "success": True})

        return {"success": True, "updated": results}

    async def _execute_run_dream(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Execute dream command."""
        from agent.automated_manager import AutomatedMemoryManager

        manager = AutomatedMemoryManager(self.agent)
        result = await manager.run_dream_cycle()

        return {"success": True, "dream_result": result}

    async def execute_skill(self, skill_name: str, *args, **kwargs) -> Dict[str, Any]:
        """Execute a skill by name."""
        result = await self.agent.execute_skill(skill_name, *args, **kwargs)
        return {"success": True, "result": result} if result else {"success": False, "error": f"Skill '{skill_name}' not found or failed"}
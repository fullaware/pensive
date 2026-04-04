# Agent modules
"""Agent modules for the agentic platform."""
from agent.agent import (
    BaseAgent,
    AgentPreferences,
    AgentSkill,
    AgentLogger,
)
from agent.telegram_gateway import TelegramGateway, get_gateway
from agent.intent_router import IntentRouter, detect_intent
from agent.command_executor import CommandExecutor, SafeExecutor
from agent.skills_manager import SkillsManager, ManagedSkill
from agent.dream_scheduler import DreamScheduler, run_dream_cycle
from agent.orchestrator import AgenticOrchestrator, OrchestratorLogger

__all__ = [
    "BaseAgent",
    "AgentPreferences", 
    "AgentSkill",
    "AgentLogger",
    "TelegramGateway",
    "get_gateway",
    "IntentRouter",
    "detect_intent",
    "CommandExecutor",
    "SafeExecutor",
    "SkillsManager",
    "ManagedSkill",
    "DreamScheduler",
    "run_dream_cycle",
    "AgenticOrchestrator",
]

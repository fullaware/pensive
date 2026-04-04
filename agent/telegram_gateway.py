# Telegram Gateway
"""Telegram gateway using python-telegram-bot v22.7."""
import asyncio
import re
import json
import os
from typing import Dict, Optional, Any
from pathlib import Path

from telegram import Update, MessageEntity, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    JobQueue,
)

from agent import BaseAgent, AgentPreferences


class TelegramContext(ContextTypes.DEFAULT_TYPE):
    """Custom context type for Telegram bot."""
    
    def __init__(self, bot: "telegram.Bot"):
        super().__init__(bot)
        self.agent: Optional[BaseAgent] = None
        self.user_id: str = ""
        self.session_id: str = ""


class TelegramGateway:
    """Telegram gateway for the Pensive agentic platform."""

    def __init__(self, bot_token: str, update_method: str = "polling"):
        self.bot_token = bot_token
        self.update_method = update_method
        self.application: Optional[Application] = None
        self.agents: Dict[str, BaseAgent] = {}
        self.job_queue: Optional[JobQueue] = None

    async def start(self):
        """Start the Telegram gateway."""
        # Create application
        self.application = ApplicationBuilder() \
            .token(self.bot_token) \
            .build()

        # Add handlers
        self._add_handlers()

        # Start polling or webhook
        if self.update_method == "polling":
            # run_polling() returns a Future, we need to await it in a task
            self.polling_task = asyncio.create_task(self.application.run_polling())
        else:
            # Webhook setup - requires HTTPS
            # run_webhook() returns None and blocks, so we use start_polling for async
            asyncio.create_task(self.application.start_polling())

    def _add_handlers(self):
        """Add all message and command handlers."""
        # Start command
        self.application.add_handler(CommandHandler("start", self._handle_start))

        # Help command
        self.application.add_handler(CommandHandler("help", self._handle_help))

        # Skill commands
        self.application.add_handler(CommandHandler("skill", self._handle_skill))

        # Status command
        self.application.add_handler(CommandHandler("status", self._handle_status))

        # Dream command
        self.application.add_handler(CommandHandler("dream", self._handle_dream))

        # Message handler (natural language)
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message
        ))

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        user_id = str(user.id)
        
        # Create or get agent
        agent = await self._get_or_create_agent(user_id)
        
        # Load preferences
        await agent.preferences.load()
        
        # Get current time
        current_time = await agent.get_current_time()
        use_emojis = await agent.preferences.get("use_emojis", False)
        
        # Send welcome message
        emoji = "👋" if use_emojis else ""
        message = f"{emoji} Hello {user.first_name}! I'm Pensive, your agentic assistant.\n\n"
        message += f"Current time: {current_time}\n"
        message += f"Use /help to see available commands."
        
        await update.message.reply_text(message)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        use_emojis = await context.agent.preferences.get("use_emojis", False)
        emoji = "💡" if use_emojis else ""
        
        help_text = f"""{emoji} *Available Commands*

/start - Welcome message with user preferences
/help - Show this help message
/skill list - List all available skills
/skill build <description> - Build a new skill
/skill activate <name> - Activate a skill
/skill deactivate <name> - Deactivate a skill
/status - Show agent status and memory stats
/dream - Manually trigger dream mode

*Natural Language Commands:*
- "build skill that searches Zen" - Create a new skill
- "never use emojis" - Update communication preferences
- "what skills do you have?" - List available skills
- "activate skill search_zen" - Enable a skill
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def _handle_skill(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /skill command."""
        user_id = str(update.effective_user.id)
        agent = await self._get_or_create_agent(user_id)
        
        # Get skill subcommand
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /skill <list|build|activate|deactivate> [args]")
            return

        command = args[0].lower()
        
        if command == "list":
            skills = await agent.list_skills()
            use_emojis = await agent.preferences.get("use_emojis", False)
            emoji = "📋" if use_emojis else ""
            
            response = f"{emoji} *Available Skills*\n\n"
            for skill in skills:
                active = "✅" if skill.get("active", False) else "❌"
                response += f"{active} *{skill.get('name', 'unnamed')}*\n"
                response += f"  {skill.get('description', 'No description')}\n\n"
            
            await update.message.reply_text(response, parse_mode="Markdown")
            
        elif command == "build":
            if len(args) < 2:
                await update.message.reply_text("Usage: /skill build <skill description>")
                return
            
            description = " ".join(args[1:])
            await update.message.reply_text(f"Building skill: {description}")
            
            result = await agent.build_skill(description)
            
            if result.get("success"):
                save_result = await agent.save_skill(
                    result["skill_name"],
                    result["description"],
                    result["code"]
                )
                if save_result.get("success"):
                    await update.message.reply_text(
                        f"Skill '{result['skill_name']}' created!\n"
                        f"Description: {result['description']}\n"
                        f"Status: Deactivated (activate with /skill activate {result['skill_name']})"
                    )
                else:
                    await update.message.reply_text(f"Failed to save skill: {save_result.get('error')}")
            else:
                await update.message.reply_text(f"Failed to build skill: {result.get('error', 'Unknown error')}")
                
        elif command == "activate":
            if len(args) < 2:
                await update.message.reply_text("Usage: /skill activate <skill_name>")
                return
            
            skill_name = args[1]
            result = await agent.activate_skill(skill_name)
            
            if result.get("success"):
                await update.message.reply_text(f"✅ Skill '{skill_name}' activated!")
            else:
                await update.message.reply_text(f"Failed to activate: {result.get('error', 'Unknown error')}")
                
        elif command == "deactivate":
            if len(args) < 2:
                await update.message.reply_text("Usage: /skill deactivate <skill_name>")
                return
            
            skill_name = args[1]
            result = await agent.deactivate_skill(skill_name)
            
            if result.get("success"):
                await update.message.reply_text(f"❌ Skill '{skill_name}' deactivated!")
            else:
                await update.message.reply_text(f"Failed to deactivate: {result.get('error', 'Unknown error')}")
        else:
            await update.message.reply_text(f"Unknown skill command: {command}")

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        user_id = str(update.effective_user.id)
        agent = await self._get_or_create_agent(user_id)
        
        use_emojis = await agent.preferences.get("use_emojis", False)
        emoji = "📊" if use_emojis else ""
        
        # Get skill count
        await agent.load_skills()
        active_skills = [s for s in agent.skills.values() if s.is_active()]
        
        response = f"""{emoji} *Agent Status*

Active Skills: {len(active_skills)}/{len(agent.skills)}
Time: {await agent.get_current_time()}
Communication: {await agent.preferences.get('communication_style', 'short')}
Emojis: {'Enabled' if await agent.preferences.get('use_emojis', False) else 'Disabled'}
"""
        await update.message.reply_text(response, parse_mode="Markdown")

    async def _handle_dream(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /dream command."""
        user_id = str(update.effective_user.id)
        agent = await self._get_or_create_agent(user_id)
        
        use_emojis = await agent.preferences.get("use_emojis", False)
        emoji = "💤" if use_emojis else ""
        
        # Trigger dream mode
        await update.message.reply_text(f"{emoji} Triggering dream mode...")
        
        from agent.automated_manager import AutomatedMemoryManager
        manager = AutomatedMemoryManager(agent)
        result = await manager.run_dream_cycle()
        
        await update.message.reply_text(f"{emoji} Dream cycle complete!\n{json.dumps(result, indent=2)}")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle natural language messages."""
        user_id = str(update.effective_user.id)
        message_text = update.message.text
        
        # Get or create agent for this user
        agent = await self._get_or_create_agent(user_id)
        
        # Detect intent and process
        intent = await agent.detect_intent(message_text)
        
        if intent.get("intent") == "command":
            # Handle command
            command = intent.get("command")
            if command == "build_skill":
                # Extract skill description
                description = self._extract_skill_description(message_text)
                await update.message.reply_text(f"Building skill: {description}")
                
                result = await agent.build_skill(description)
                if result.get("success"):
                    save_result = await agent.save_skill(
                        result["skill_name"],
                        result["description"],
                        result["code"]
                    )
                    if save_result.get("success"):
                        await update.message.reply_text(
                            f"Skill '{result['skill_name']}' created and saved!"
                        )
                else:
                    await update.message.reply_text(f"Failed: {result.get('error')}")
                    
            elif command == "set_preference":
                # Extract preference
                preference = intent.get("preference", {})
                for key, value in preference.items():
                    await agent.preferences.update(key, value)
                await update.message.reply_text("Preferences updated!")
                
            elif command == "list_skills":
                skills = await agent.list_skills()
                use_emojis = await agent.preferences.get("use_emojis", False)
                emoji = "📋" if use_emojis else ""
                
                response = f"{emoji} Available Skills:\n\n"
                for skill in skills:
                    active = "ACTIVE" if skill.get("active", False) else "INACTIVE"
                    response += f"- {skill.get('name', 'unnamed')}: {skill.get('description', 'No description')} [{active}]\n"
                
                await update.message.reply_text(response)
                
            elif command == "activate_skill":
                skill_name = intent.get("skill_name")
                if skill_name:
                    result = await agent.activate_skill(skill_name)
                    if result.get("success"):
                        await update.message.reply_text(f"Activated skill: {skill_name}")
                    else:
                        await update.message.reply_text(f"Failed: {result.get('error')}")
                else:
                    # List skills to help user
                    skills = await agent.list_skills()
                    response = "Available skills:\n"
                    for skill in skills:
                        response += f"- {skill.get('name', 'unnamed')}: {skill.get('description', 'No description')}\n"
                    await update.message.reply_text(response)
                    
            else:
                # Generic command response
                await update.message.reply_text(f"Executing command: {command}")
        else:
            # Regular query - process through agent
            response = await agent.process_query(message_text, session_id=user_id)
            await update.message.reply_text(response.get("response", "I received your message."))

    def _extract_skill_description(self, message: str) -> str:
        """Extract skill description from natural language."""
        # Patterns to match skill descriptions
        patterns = [
            r"build skill (that|for|to)?\s*(.+?)(?:\s*$)",
            r"create skill (that|for|to)?\s*(.+?)(?:\s*$)",
            r"make a skill (that|for|to)?\s*(.+?)(?:\s*$)",
            r"skill (.+?)(?:\s*$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                description = match.group(2).strip()
                if description:
                    return description
        
        return message

    async def _get_or_create_agent(self, user_id: str) -> BaseAgent:
        """Get existing agent or create new one."""
        if user_id not in self.agents:
            self.agents[user_id] = BaseAgent(agent_id="telegram", user_id=user_id)
            await self.agents[user_id].initialize()
        return self.agents[user_id]

    async def stop(self):
        """Stop the Telegram gateway."""
        if self.application:
            await self.application.stop()
        for agent in self.agents.values():
            await agent.close()


# Global gateway instance
_gateway: Optional[TelegramGateway] = None


async def get_gateway() -> TelegramGateway:
    """Get or create the global gateway instance."""
    global _gateway
    if _gateway is None:
        from memory_system.config import Config
        token = Config.TELEGRAM_BOT_TOKEN
        method = Config.TELEGRAM_UPDATE_METHOD
        _gateway = TelegramGateway(token, method)
    return _gateway
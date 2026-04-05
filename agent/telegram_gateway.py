# Telegram Gateway
"""Telegram gateway using python-telegram-bot v22.7."""
import asyncio
import re
import json
import os
import logging
from typing import Dict, Optional, Any, List
from pathlib import Path

from telegram import Update, MessageEntity, BotCommand, Bot
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

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

from agent import BaseAgent, AgentPreferences
from memory_system.config import Config
from memory_system.schema import COLLECTION_UNAUTHORIZED_ACCESS, UnauthorizedAccessSchema
from memory_system.mongodb import MongoDB


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
        self._running: bool = False
        self._polling_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the Telegram gateway."""
        logger.info("Starting Telegram gateway...")
        
        # Create application
        self.application = ApplicationBuilder() \
            .token(self.bot_token) \
            .build()
        logger.info("Application created")

        # Initialize application
        await self.application.initialize()
        logger.info("Application initialized")

        # Add handlers
        self._add_handlers()
        logger.info("Handlers added")

        # Start the application (required for update processing/dispatching)
        await self.application.start()
        logger.info("Application started")

        # Start polling using async updater
        self._running = True
        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        logger.info("Polling started")

    async def stop(self):
        """Stop the Telegram gateway."""
        self._running = False
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
        for agent in self.agents.values():
            await agent.close()

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
        logger.info(f"/start command received from user {update.effective_user.id}")
        user = update.effective_user
        user_id = str(user.id)
        
        # Check if user is authorized
        if not await self.is_user_authorized(user_id, user.username, update):
            logger.info(f"User {user_id} not authorized")
            return
        
        try:
            # Create or get agent
            agent = await self._get_or_create_agent(user_id)
            
            # Load preferences
            await agent.preferences.load()
            
            # Get current time
            current_time = await agent.get_current_time()
            use_emojis = await agent.preferences.get("use_emojis", False)
            
            # Send welcome message (no Markdown to avoid parse errors)
            emoji = "👋 " if use_emojis else ""
            message = (
                f"{emoji}Hello {user.first_name}! I'm Pensive, your agentic assistant.\n\n"
                f"Your user ID: {user_id}\n"
                f"Current time: {current_time}\n"
                f"Use /help to see available commands."
            )
            
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in /start handler: {e}", exc_info=True)
            # Always reply with user ID even if agent creation fails
            error_msg = str(e)[:200].replace("`", "'").replace("*", "").replace("_", " ")
            await update.message.reply_text(
                f"Hello {user.first_name}!\n\n"
                f"Your user ID: {user_id}\n\n"
                f"⚠️ Agent initialization error: {error_msg}"
            )

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        # Get agent from context
        agent = await self._get_or_create_agent(str(update.effective_user.id))
        
        use_emojis = await agent.preferences.get("use_emojis", False)
        emoji = "💡" if use_emojis else ""
        
        help_text = (
            f"{emoji} Available Commands\n\n"
            f"/start - Welcome message with user preferences\n"
            f"/help - Show this help message\n"
            f"/skill list - List all available skills\n"
            f"/skill build [description] - Build a new skill\n"
            f"/skill activate [name] - Activate a skill\n"
            f"/skill deactivate [name] - Deactivate a skill\n"
            f"/status - Show agent status and memory stats\n"
            f"/dream - Manually trigger dream mode\n\n"
            f"Natural Language Commands:\n"
            f'- "build skill that searches Zen" - Create a new skill\n'
            f'- "never use emojis" - Update communication preferences\n'
            f'- "what skills do you have?" - List available skills\n'
            f'- "activate skill search_zen" - Enable a skill'
        )
        await update.message.reply_text(help_text)

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
            
            response = f"{emoji} Available Skills\n\n"
            for skill in skills:
                active = "✅" if skill.get("active", False) else "❌"
                response += f"{active} {skill.get('name', 'unnamed')}\n"
                response += f"  {skill.get('description', 'No description')}\n\n"
            
            await update.message.reply_text(response)
            
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
        
        response = (
            f"{emoji} Agent Status\n\n"
            f"Active Skills: {len(active_skills)}/{len(agent.skills)}\n"
            f"Time: {await agent.get_current_time()}\n"
            f"Communication: {await agent.preferences.get('communication_style', 'short')}\n"
            f"Emojis: {'Enabled' if await agent.preferences.get('use_emojis', False) else 'Disabled'}"
        )
        await update.message.reply_text(response)

    async def _handle_dream(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /dream command."""
        user_id = str(update.effective_user.id)
        agent = await self._get_or_create_agent(user_id)
        
        use_emojis = await agent.preferences.get("use_emojis", False)
        emoji = "💤" if use_emojis else ""
        
        # Trigger dream mode
        await update.message.reply_text(f"{emoji} Triggering dream mode...")
        
        from memory_system.automated_manager import AutomatedMemoryManager
        manager = AutomatedMemoryManager()
        result = await manager.run_dream_cycle()
        
        await update.message.reply_text(f"{emoji} Dream cycle complete!\n{json.dumps(result, indent=2)}")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle natural language messages by forwarding to Pensive API."""
        user_id = str(update.effective_user.id)
        message_text = update.message.text
        
        # Check authorization
        if not await self.is_user_authorized(user_id, update.effective_user.username, update):
            return
        
        logger.info(f"Message from user {user_id}: {message_text[:100]}")
        
        try:
            # Forward query to Pensive API
            import httpx
            
            api_url = os.getenv("PENSIVE_API_URL", "http://pensive-api:8000")
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{api_url}/api/v1/query",
                    json={
                        "query": message_text,
                        "session_id": user_id,
                    },
                )
                
                if response.status_code == 200:
                    result = response.json()
                    answer = result.get("answer", "I received your message but couldn't generate a response.")
                    
                    # Telegram has a 4096 character limit per message
                    if len(answer) > 4000:
                        # Split into chunks
                        chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
                        for chunk in chunks:
                            await update.message.reply_text(chunk)
                    else:
                        await update.message.reply_text(answer)
                else:
                    error_detail = response.text[:200] if response.text else "Unknown error"
                    logger.error(f"API error {response.status_code}: {error_detail}")
                    await update.message.reply_text(
                        f"Sorry, I encountered an error communicating with the backend (HTTP {response.status_code})."
                    )
                    
        except httpx.ConnectError:
            logger.error("Cannot connect to Pensive API")
            await update.message.reply_text(
                "Sorry, I can't reach the Pensive API right now. Please try again later."
            )
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            error_msg = str(e)[:200].replace("`", "'").replace("*", "").replace("_", " ")
            await update.message.reply_text(
                f"Sorry, an error occurred: {error_msg}"
            )

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

    async def is_user_authorized(self, user_id: str, username: Optional[str], update: Optional[Update] = None) -> bool:
        """Check if user is authorized to interact with the bot.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username (if available)
            update: Optional Update object for sending response
            
        Returns:
            True if user is authorized, False otherwise
        """
        allowed_ids = Config.TELEGRAM_ALLOWED_USER_IDS.strip()
        
        # If no allowed user IDs are set, allow all users
        if not allowed_ids:
            return True
        
        # Parse allowed user IDs from comma-separated list
        allowed_user_list = [x.strip() for x in allowed_ids.split(",")]
        
        # Check if user_id is in allowed list
        if user_id in allowed_user_list:
            return True
        
        # User is not authorized
        # Send unauthorized response if update is provided
        if update:
            await update.message.reply_text(user_id)
        
        # Log unauthorized access
        await self.log_unauthorized_access(user_id, username)
        
        # If bot owner is configured, send notification
        await self.notify_bot_owner_of_unauthorized_access(user_id, username)
        
        return False
    
    async def log_unauthorized_access(self, user_id: str, username: Optional[str], message_text: Optional[str] = None) -> None:
        """Log unauthorized access attempt to MongoDB.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username (if available)
            message_text: Content of the message (if available)
        """
        try:
            await MongoDB.connect()
            unauthorized_record = UnauthorizedAccessSchema.create(
                user_id=int(user_id),
                username=username,
                message_text=message_text
            )
            collection = MongoDB.get_collection(COLLECTION_UNAUTHORIZED_ACCESS)
            collection.insert_one(unauthorized_record)  # insert_one returns InsertOneResult in motor
        except Exception as e:
            pass  # Log silently to avoid disrupting the bot
    
    async def notify_bot_owner_of_unauthorized_access(self, user_id: str, username: Optional[str]) -> None:
        """Send notification to bot owner about unauthorized access.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username (if available)
        """
        bot_owner_id = Config.TELEGRAM_BOT_OWNER_ID.strip()
        if not bot_owner_id:
            return
        
        try:
            from telegram import Bot
            bot = Bot(Config.TELEGRAM_BOT_TOKEN)
            message = f"⚠️ Unauthorized Access Attempt\n\nUser ID: {user_id}\nUsername: {username or 'N/A'}\nTime: {self._get_current_time_formatted()}"
            await bot.send_message(chat_id=int(bot_owner_id), text=message)
        except Exception as e:
            pass  # Log silently to avoid disrupting the bot
    
    def _get_current_time_formatted(self) -> str:
        """Get current time formatted for display."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    async def _get_or_create_agent(self, user_id: str) -> BaseAgent:
        """Get existing agent or create new one."""
        if user_id not in self.agents:
            self.agents[user_id] = BaseAgent(agent_id="telegram", user_id=user_id)
            await self.agents[user_id].initialize()
        return self.agents[user_id]

    async def wait_for_stop(self):
        """Wait for the polling task to complete."""
        if self._polling_task:
            await self._polling_task

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
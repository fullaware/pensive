# Start Telegram Gateway
"""
Start the Telegram gateway for the Pensive agentic platform.

Based on the echobot example from python-telegram-bot:
https://docs.python-telegram-bot.org/en/stable/examples.echobot.html

Uses application.run_polling() which handles the entire bot lifecycle:
initialize() -> start() -> polling -> stop() -> shutdown()
"""
import logging
import sys
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Reduce httpx noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    """Called after Application.initialize() - connect to MongoDB here."""
    from memory_system.mongodb import MongoDB
    logger.info("Connecting to MongoDB...")
    await MongoDB.connect()
    logger.info("MongoDB connected.")


async def post_shutdown(application) -> None:
    """Called after Application.shutdown() - disconnect from MongoDB here."""
    from memory_system.mongodb import MongoDB
    logger.info("Disconnecting from MongoDB...")
    await MongoDB.disconnect()
    logger.info("MongoDB disconnected.")


def main() -> None:
    """Start the bot using run_polling() - exactly like the echobot example."""
    from memory_system.config import Config

    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Check for bot token
    if not Config.TELEGRAM_BOT_TOKEN:
        print("Warning: TELEGRAM_BOT_TOKEN not set in environment")
        print("Telegram gateway will be disabled.")
        sys.exit(0)

    # Import the gateway handlers
    from agent.telegram_gateway import TelegramGateway

    # Create a gateway instance (for handler methods and state)
    gateway = TelegramGateway(
        bot_token=Config.TELEGRAM_BOT_TOKEN,
        update_method=Config.TELEGRAM_UPDATE_METHOD,
    )

    # Build the application with post_init/post_shutdown hooks
    # post_init runs after initialize() - perfect for MongoDB connection
    # post_shutdown runs after shutdown() - perfect for cleanup
    application = (
        ApplicationBuilder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Store reference so handlers can access gateway state
    gateway.application = application

    # Add handlers - same as echobot pattern
    application.add_handler(CommandHandler("start", gateway._handle_start))
    application.add_handler(CommandHandler("help", gateway._handle_help))
    application.add_handler(CommandHandler("skill", gateway._handle_skill))
    application.add_handler(CommandHandler("status", gateway._handle_status))
    application.add_handler(CommandHandler("dream", gateway._handle_dream))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, gateway._handle_message)
    )

    logger.info("Starting Telegram bot with run_polling()...")
    print(f"Bot token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"Starting bot with run_polling() (echobot pattern)...")

    # run_polling() is a BLOCKING call that handles the entire lifecycle:
    # initialize() -> post_init() -> start() -> polling -> stop() -> shutdown() -> post_shutdown()
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()

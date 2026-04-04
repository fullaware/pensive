# Start Telegram Gateway
"""Start the Telegram gateway for the Pensive agentic platform."""
import asyncio
import sys
from memory_system import Config, MongoDB
from agent import TelegramGateway


async def main():
    """Start the Telegram gateway."""
    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Check for bot token - skip Telegram if not configured
    if not Config.TELEGRAM_BOT_TOKEN:
        print("Warning: TELEGRAM_BOT_TOKEN not set in environment")
        print("Telegram gateway will be disabled. Set TELEGRAM_BOT_TOKEN in .env to enable.")
        print("Starting without Telegram gateway...")
        return

    # Connect to MongoDB
    print("Connecting to MongoDB...")
    await MongoDB.connect()

    try:
        # Create and start Telegram gateway
        print("Starting Telegram Gateway...")
        gateway = TelegramGateway(
            bot_token=Config.TELEGRAM_BOT_TOKEN,
            update_method=Config.TELEGRAM_UPDATE_METHOD
        )
        
        print(f"Telegram Gateway started!")
        print(f"Bot token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
        print(f"Update method: {Config.TELEGRAM_UPDATE_METHOD}")
        print("Press Ctrl+C to stop.")
        
        # Start the gateway
        await gateway.start()
        
        # Keep running - the polling task runs in the background
        # Wait indefinitely until stopped
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        print("\nStopping Telegram Gateway...")
        await gateway.stop()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await MongoDB.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
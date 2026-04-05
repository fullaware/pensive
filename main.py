# Main Entry Point
"""Main entry point for the agentic memory system CLI.

Note: Telegram gateway is handled by the separate pensive-telegram service
via start_telegram.py. It is NOT started from this file.
"""
import asyncio
import sys
import os
from memory_system import Config, MongoDB
from agent import AgenticOrchestrator


async def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the API server in the background."""
    import uvicorn
    
    config = uvicorn.Config(
        "api.routes:app",
        host=host,
        port=port,
        log_level="info",
        reload=False
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Run the main CLI loop or API server."""
    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Connect to MongoDB
    await MongoDB.connect()

    # Initialize orchestrator
    orchestrator = AgenticOrchestrator()

    # Initialize bootstrap prompt from MongoDB
    print("Loading bootstrap prompt from MongoDB...")
    await orchestrator.initialize_bootstrap()

    print("Agentic Memory System Ready!")
    print("Type 'quit' or 'exit' to stop.")
    print()

    # Determine mode: CLI or API server
    mode = os.environ.get("PENSEIVE_MODE", "cli").lower()
    
    if mode == "api":
        # Run as API server only (for Docker)
        print(f"Starting API server on http://0.0.0.0:8000")
        await run_api_server()
    else:
        # Run CLI loop
        while True:
            # Get user input
            try:
                user_input = input("You: ").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit"]:
                print("Goodbye!")
                break

            # Process query
            print("Processing...")
            result = await orchestrator.process_query(user_input)

            # Display response
            print(f"AI: {result['answer']}")
            if result.get("sources"):
                print(f"  (Sources: {', '.join(result['sources'])})")
            print()

    # Cleanup
    print("Stopping...")
    await orchestrator.close()
    await MongoDB.disconnect()
    print("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())

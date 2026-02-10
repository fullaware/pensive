# Main Entry Point
"""Main entry point for the agentic memory system CLI."""
import asyncio
import sys
from memory_system import Config, MongoDB
from agent import AgenticOrchestrator


async def main():
    """Run the main CLI loop."""
    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Connect to MongoDB
    await MongoDB.connect()

    try:
        # Create orchestrator
        orchestrator = AgenticOrchestrator()

        print("Agentic Memory System Ready!")
        print("Type 'quit' or 'exit' to stop.")
        print()

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

    finally:
        # Cleanup
        await orchestrator.close()
        await MongoDB.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
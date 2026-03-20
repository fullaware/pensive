#!/usr/bin/env python3
"""Launch script for automated memory management loop.

This script starts the background loop that:
- Organizes and tags memories
- Detects stale/outdated content
- Enforces system prompt version limits (max 5)
- Creates tasks for pending questions needing tools
- Runs compression on old episodic memories

Usage:
    python scripts/run_automated_manager.py
    python scripts/run_automated_manager.py --interval 6   # Run every 6 hours
    python scripts/run_automated_manager.py --one-time     # Run once and exit
"""
import asyncio
import sys
import os
import argparse

# Add the project root to Python path for imports
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)) + "/.."
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from memory_system import Config, MongoDB, AutomatedMemoryManager


async def run_loop(interval_hours: float = 24.0, one_time: bool = False):
    """Run the automated memory manager loop.

    Args:
        interval_hours: How often to run cleanup tasks
        one_time: If True, run once and exit instead of looping
    """
    # Validate configuration
    errors = Config.validate()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    # Connect to MongoDB
    print("Connecting to MongoDB...")
    await MongoDB.connect()
    print("Connected successfully!")

    # Create and start automated manager
    manager = AutomatedMemoryManager()

    try:
        if one_time:
            print("Running cleanup tasks once...")
            await manager.run_cleanup_tasks()
            print("Cleanup completed!")
        else:
            print(f"Starting automated memory management loop (interval: {interval_hours}h)")
            await manager.start(interval_hours)
    except KeyboardInterrupt:
        print("\nReceived shutdown signal...")
    finally:
        await manager.stop()
        await MongoDB.disconnect()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Automated Memory Management Loop"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=24.0,
        help="Hours between cleanup runs (default: 24)"
    )
    parser.add_argument(
        "--one-time",
        action="store_true",
        help="Run once and exit (default: False)"
    )

    args = parser.parse_args()

    asyncio.run(run_loop(
        interval_hours=args.interval,
        one_time=args.one_time
    ))


if __name__ == "__main__":
    main()
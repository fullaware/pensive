# Pensive Agent Development Guidelines

## Application Intent & Vision

Pensive is a self-hosted, agentic memory platform that runs 24/7 as an intelligent assistant. The core philosophy is:

1. **Always-On Agent**: The system should run continuously, maintaining context across sessions
2. **Shared Memory Space**: Multiple agents/users share a common memory pool with individual sessions
3. **Self-Improving Skills**: The LLM can build, manage, and optimize its own skills without user intervention
4. **Intelligent Memory Management**: Automatic organization, compression, and pruning of memories
5. **Time-Aware**: Agents have timezone awareness and handle scheduled events (like "dream" mode)

## Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Pensive Agentic Platform                 │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  API Server  │  │  Telegram    │  │   Automated      │   │
│  │  (Port 8000) │  │  Gateway     │  │   Manager        │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│         │                 │                  │                │
│         └─────────────────┴──────────────────┘                │
│                           │                                  │
│                   ┌───────▼───────┐                          │
│                   │  Query Router │                          │
│                   └───────┬───────┘                          │
│                           │                                  │
│    ┌──────────────────────┼──────────────────────┐          │
│    │                      │                      │          │
│ ┌──▼──┐               ┌──▼──┐               ┌──▼──┐        │
│ │Short│               │Epi- │               │Seman│        │
│ │Term │               │sodic│               │tic  │        │
│ │Mem  │               │Mem  │               │Mem  │        │
│ └─────┘               └─────┘               └─────┘        │
│    │                      │                      │          │
│    └──────────────────────┼──────────────────────┘          │
│                           │                                  │
│                  ┌────────▼────────┐                        │
│                  │  MongoDB (with   │                        │
│                  │   Vector Search)│                        │
│                  └─────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

## Development Philosophy

### 1. The LLM Should Self-Manage Its Memory

**Goal**: Reduce user intervention in memory management

**Key Behaviors**:
- The LLM should automatically detect when it's being asked the same question repeatedly
- It should create skills to answer common questions
- It should organize memories during "dream" mode (scheduled background processing)
- It should prune redundant/low-confidence memories

**Implementation Pattern**:
```python
# Example: Memory self-management skill
# __skill_name__ = "self_optimize_memory"
# __skill_description__ = "Analyze memories and optimize organization"
# __skill_active__ = False

async def execute():
    # Find repeated questions
    # Group similar memories
    # Create summaries for long memory chains
    # Suggest skill creation for frequently asked questions
    pass
```

### 2. Skills Are the Primary Interface

**Key Principles**:
- Skills are Python modules with metadata (`__skill_name__`, `__skill_description__`, `__skill_active__`)
- Skills execute in a sandboxed environment with restricted imports
- Skills are created deactivated by default (security by default)
- The LLM should activate/deactivate skills based on context

**Skill Directory Structure**:
```
skills/
├── system/          # Built-in system skills (never modified by LLM)
│   ├── get_weather.py
│   ├── run_command.py
│   └── ...
├── built/           # Skills created by LLM (can be modified)
│   └── [skill_name].py
└── references/      # Skill development documentation
    └── ...
```

### 3. Time-Aware Processing

**Requirements**:
- All agents should have timezone awareness
- Scheduled events (like dream mode) should run at appropriate local times
- The LLM should understand temporal context when processing queries

**Implementation**:
```python
# Agent has methods for time management
await agent.get_current_time()  # Returns formatted time in agent's timezone
await agent.get_timezone()      # Returns timezone string

# Dream scheduler uses cron syntax with timezone support
# Runs at 2 AM user's local time by default
```

### 4. Preference System

**Core Preferences**:
- `timezone`: Agent's timezone (affects scheduled events)
- `communication_style`: "short" or "long" (response length)
- `use_emojis`: Whether to include emojis (important for TTS)
- `active_skills`: List of enabled skills

**Preference Learning**:
- The LLM should learn user preferences from natural language commands
- "Never use emojis" → sets `use_emojis = False`
- "Use short responses" → sets `communication_style = "short"`
- Preferences are stored in MongoDB per user

## Development Checklist for New Features

### When Adding a New Agent Capability:

1. **Define the skill**:
   - [ ] Create skill in `skills/system/` or `skills/built/`
   - [ ] Add metadata comments (`__skill_name__`, `__skill_description__`, `__skill_active__`)
   - [ ] Implement async `execute()` function
   - [ ] Test with `await agent.execute_skill('skill_name', args)`

2. **Update intent detection**:
   - [ ] Add command pattern to `agent/intent_router.py`
   - [ ] Add natural language trigger examples
   - [ ] Add corresponding command handler in `agent/command_executor.py`

3. **Update documentation**:
   - [ ] Add skill to README.md features list
   - [ ] Document usage in AGENT.md if complex

4. **Test thoroughly**:
   - [ ] Test CLI mode (`python main.py`)
   - [ ] Test Telegram mode (if applicable)
   - [ ] Test API mode (`curl` or OpenWebUI)

### When Modifying Memory Systems:

1. **Backward compatibility**: Ensure changes don't break existing memories
2. **Migration scripts**: Create scripts in `scripts/` if schema changes
3. **Testing**: Run existing tests (`pytest`) to ensure nothing broke
4. **Vector indexes**: Update `scripts/recreate_index.py` if embedding dimensions change

## Common Tasks for the Next Agent

### 1. Optimize Memory Organization

**Current State**: Memories are stored but may not be optimally organized

**Task**:
- Analyze memory patterns in the database
- Create skills for automatic clustering/grouping
- Implement automatic summary generation for long memory chains
- Add "memory热度" (hotness) tracking for automatic archival decisions

### 2. Skill Creation Optimization

**Current State**: Skills are built manually or via natural language

**Task**:
- Add skill suggestion system (detects repeated questions)
- Create "skill template" system for common patterns
- Implement skill dependency management
- Add skill performance metrics (execution time, success rate)

### 3. Dream Mode Enhancement

**Current State**: Basic dream mode exists for memory organization

**Task**:
- Implement multi-level memory compression
- Add "memory pruning" for low-confidence memories
- Create "memory fusion" for related memories
- Add dream mode logging for debugging

### 4. Multi-Agent Support

**Current State**: Single agent with shared memory

**Task**:
- Implement agent routing based on user/session
- Create agent-specific preferences
- Add inter-agent communication skills
- Implement resource allocation between agents

## Technical Notes

### Code Style
- Use async/await throughout (async-first design)
- Follow Python type hints
- Use httpx for async HTTP requests
- Use MongoDB for all persistent storage

### Configuration
- All configuration via environment variables
- `.env` file for local development
- `env.example` as template
- Docker Compose for production

### Testing
- Run `pytest` before committing changes
- Test both CLI and API modes
- Check MongoDB connections are closed properly

### Deployment
- Docker Compose for easy deployment
- Health check endpoint at `/health`
- Logs to stdout/stderr for container orchestration

## Gotchas & Pitfalls

1. **MongoDB Connection Pooling**: Always use async connections, don't share clients across threads
2. **Embedding Dimensions**: Must match the embedding model output (check `EMBEDDING_DIMENSIONS`)
3. **Vector Indexes**: Need to be recreated if embedding dimensions change
4. **Skill Imports**: Skills run in sandbox - only allow safe imports (httpx, json, asyncio)
5. **Timezones**: Always store timestamps as UTC in MongoDB, convert to local time only for display
6. **Telegram Polling**: Use async polling mode, not blocking `run_polling()`

## Next Steps for the Next Agent

1. Read through this AGENT.md and the main README.md
2. Review the current codebase structure
3. Check the MongoDB database for current memory patterns
4. Identify 1-2 improvements that would add the most value
5. Implement with proper testing
6. Update AGENT.md with any new patterns or guidelines
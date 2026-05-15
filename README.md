# Pensive - Agentic Memory System

An AI agent system with multiple memory types (Short-Term, Episodic, Semantic) inspired by the [Rosston Agentic Memory System](https://www.rosston.dev/blog/groundhog-day).

## Background

This system is based on the concepts described in Rosston Ritter's article [Beyond the Chatbot: Escaping the "Groundhog Day" Loop with Agentic Memory](https://www.rosston.dev/blog/groundhog-day), which outlines a memory architecture for AI agents that includes:

- **Short-Term Memory**: Session history and conversation context (cached)
- **Long-Term Memory**: Stored in MongoDB with two components:
  - **Episodic Memory**: Past events with vector embeddings for similarity search
  - **Semantic Memory**: Facts and knowledge with structured data storage

The key insight from the article is that to move from forgetful chatbots to truly intelligent agents, we need an agent to "remember" across sessions. This is achieved through a **Consolidation Workflow** that moves critical context from short-term session history to long-term MongoDB storage.

## Features

### Agentic Platform Features

#### Self-Building Skills
- **Natural Language Skill Creation**: Users can say "build skill that searches the web" and the LLM generates the skill
- **Skill Activation**: Skills are created deactivated by default; users activate with "activate skill xyz"
- **Skill Management**: List, activate, deactivate skills via `/skill` commands or natural language
- **Safe Execution**: Skills run in a sandboxed environment with restricted imports and timeouts

#### Telegram Integration
- **Dedicated Telegram Service**: Runs as a separate Docker container (`pensive-telegram`) using the python-telegram-bot echobot pattern with `application.run_polling()`
- **API-Backed Conversations**: Natural language messages are forwarded to the Pensive API (`/api/v1/query`) via HTTP, enabling full LLM-powered conversations through Telegram
- **User Authorization**: Configurable `TELEGRAM_ALLOWED_USER_IDS` restricts bot access; unauthorized attempts are logged and the bot owner is notified
- **Multi-User Support**: Each Telegram user gets their own isolated agent session
- **Natural Language Commands**: "never use emojis" or "use short responses" updates preferences
- **Timezone Awareness**: Agent respects user's timezone for scheduled events
- **Commands**: `/start` (shows user ID), `/help`, `/skill`, `/status`, `/dream`
- **User Onboarding**: `/start` returns the user's numeric Telegram ID for adding to `TELEGRAM_ALLOWED_USER_IDS`

#### Dream Mode (Sleep Mode)
- **Scheduled Execution**: Runs automatically at 2 AM user's local timezone
- **Memory Organization**: Organizes and compresses memories during scheduled "dream" time
- **Pattern Detection**: Identifies repeated questions and suggests skill creation
- **Manual Trigger**: Users can trigger dream mode manually with `/dream`

### Core Memory Systems
- **Short-Term Memory**: Session history and conversation context
- **Episodic Memory**: Vector search against past events
- **Semantic Memory**: Facts and knowledge storage (MongoDB)
- **Query Router**: AI-powered query intention detection
- **System Prompts**: Dynamic prompt management with user preferences
- **REST API**: OpenAI-compatible API for integration with tools like OpenWebUI

### Advanced Memory Features

#### Multi-Level Abstraction
- **Episodic Layer**: Raw conversation/event logs with embeddings
- **Semantic Layer**: Individual facts with versioning
  
### Automated Memory Management

The system includes an automated background loop that continuously organizes and maintains memories:

- **Staleness Detection**: Automatically identifies and tags memories that have become outdated
- **Memory Tagging & Organization**: Automatic tagging based on content and temporal context
- **System Prompt Version Control**: Enforces a maximum of 5 versions, archiving older ones automatically

#### Running the Automated Manager

```bash
# Run automated memory management loop (runs every 24 hours by default)
python -m memory_system.automated_manager

# Run with custom interval
python -m memory_system.automated_manager --interval 6  # Run every 6 hours

# Run once and exit (for testing or cron jobs)
python -m memory_system.automated_manager --one-time

# Using Docker
docker-compose run pensive-api python -m memory_system.automated_manager
```

- **Temporal Context in Prompts**: LLM receives current date/time with explicit UTC reference
- **Test Command**: `/test` prefix allows memory verification without committing new memories

### Long-Term Memory Bootstrap (SYSTEM Prompt Persistence)

- **SYSTEM Prompt in MongoDB**: The SYSTEM prompt is persisted in MongoDB and loaded on startup
- **Auto-Consolidation**: After fact detection, the SYSTEM prompt is automatically updated with new information
- **Version Tracking**: Multiple versions of the SYSTEM prompt are stored for rollback capability
- **Fast Bootstrap**: The bootstrap prompt is loaded from MongoDB on startup, providing long-term memory context
- **Background Updates**: The SYSTEM prompt is updated in the background after significant events

## Features (AI Agent Perspective)

### Dynamic Memory Learning

- **Automatic Fact Extraction**: The system uses LLM to extract important information from user conversations without hardcoded fact types
- **Vector-Based Retrieval**: Facts are stored with embeddings and retrieved using semantic similarity search
- **Version Tracking**: Facts support versioning with archived history for tracking changes over time
- **No Manual Schema Updates**: New facts can be learned on-the-fly without code changes

## Architecture

```mermaid
flowchart TD
  userQuery[User Query] --> router[Query Router: Determine Intent]
  router --> shortTerm[Short-Term Memory]
  router --> episodic[Episodic Memory: Vector Search on MongoDB]
  router --> semantic[Semantic Memory: Vector Search on MongoDB]

  shortTerm --> shortTermRead[Read: Session Context]
  episodic --> episodicRead[Read: Similar Events]
  semantic --> semanticRead[Read: Facts & Knowledge]

  shortTermRead --> queryResults[Retrieved Memories from All Systems]
  episodicRead --> queryResults
  semanticRead --> queryResults

  queryResults --> systemPrompt[Build System Prompt with Retrieved Memories]
  systemPrompt --> llm[LLM Generation]
  llm --> response[Response Generated]

  response --> userReturn[Return Response to User]
  
  response --> commitEpisodic[Commit to Episodic Memory]
  commitEpisodic --> episodicEmbed[Generate Embedding]
  episodicEmbed --> mongoDb[(MongoDB)]
  
  response --> commitSemantic[Commit to Semantic Memory]
  commitSemantic --> semanticEmbed[Generate Embedding]
  semanticEmbed --> mongoDb

  style userReturn fill:#9ed6ac,stroke:#333, color:#000
  style mongoDb fill:#9ed6ac,stroke:#333, color:#000
  style commitEpisodic fill:#9ec8d6,stroke:#333, color:#000
  style commitSemantic fill:#9ec8d6,stroke:#333, color:#000
```

## Requirements

- Python 3.13+
- MongoDB with Vector Search capabilities
- Any OpenAI API-compatible endpoint (Ollama, LM Studio, llama.cpp, etc.)


## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt
```

## Configuration

Copy `env.example` to `.env` and update with your settings:

```bash
cp env.example .env
```

Edit `.env` with your configuration:

```env
# MongoDB Configuration
MONGODB_URI=mongodb://username:password@host.docker.internal:27017/?authSource=admin&directConnection=true
MONGODB_DB=agentic_memory

# LLM Configuration
LLM_URI=http://10.28.28.15:8080
LLM_EMBEDDING_URI=http://10.28.28.15:8080
LLM_MODEL=Qwen/Qwen3-Coder-Next-GGUF:Q4_K_M
LLM_EMBEDDING_MODEL=jsonMartin/voyage-4-nano-gguf
EMBEDDING_DIMENSIONS=1024

# Memory Configuration
SHORT_TERM_MEMORY_SIZE=10
EPISODIC_MEMORY_LIMIT=100
VECTOR_SEARCH_LIMIT=5

# Telegram Configuration
# Get your bot token from @BotFather on Telegram
# Leave empty to disable Telegram integration
TELEGRAM_BOT_TOKEN=
TELEGRAM_UPDATE_METHOD=polling         # polling or webhook
TELEGRAM_ALLOWED_USER_IDS=             # Comma-separated Telegram user IDs (empty = allow all)
TELEGRAM_BOT_OWNER_ID=                 # Bot owner's Telegram user ID (receives unauthorized access alerts)
```

## Usage

### Quick Start with Docker (Recommended for 24/7 Operation)

```bash
# Build and start the system (runs 24/7 with Telegram polling)
docker compose up -d --build

# View logs
docker compose logs -f pensive-api
docker compose logs -f pensive-telegram

# Stop the system
docker compose down

# Restart the system
docker compose restart
```

The API will be available at `http://localhost:8000`.

#### Docker Services

| Service | Description | Entry Point |
|---------|-------------|-------------|
| `pensive-api` | REST API server (FastAPI/Uvicorn on port 8000) | `python main.py` |
| `pensive-telegram` | Telegram bot gateway (polls Telegram, forwards to API) | `python -m services.start_telegram` |

**Important**: The Telegram bot runs as a **separate service** from the API. It forwards natural language messages to `http://pensive-api:8000/api/v1/query` via Docker's internal network. Only one instance of `pensive-telegram` should run at a time to avoid Telegram polling conflicts.

#### Telegram Bot Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) on Telegram
2. Set `TELEGRAM_BOT_TOKEN` in your `.env` file
3. Start the services: `docker compose up -d --build`
4. Send `/start` to your bot — it will reply with your numeric user ID
5. Add your user ID to `TELEGRAM_ALLOWED_USER_IDS` in `.env`
6. Optionally set `TELEGRAM_BOT_OWNER_ID` to receive unauthorized access alerts
7. Restart: `docker compose restart pensive-telegram`
8. Send any text message to chat with the LLM through Telegram

### CLI Mode

```bash
# Activate virtual environment
source venv/bin/activate

# Start the CLI interface
python main.py
```

### REST API Mode (Standalone)

Start the API server:

```bash
# Activate virtual environment
source venv/bin/activate

# Start the API server (with Telegram gateway if BOT_TOKEN is set)
uvicorn api.routes:app --host 0.0.0.0 --port 8000

# Or start just the Telegram gateway
python start_telegram.py
```

#### OpenAI-Compatible Endpoints

The API provides OpenAI-compatible endpoints:

- `GET /v1/models` - List available models
- `POST /v1/chat/completions` - Chat completions
- `POST /v1/embeddings` - Generate embeddings

#### Custom Endpoints

- `GET /health` - Health check
- `POST /api/v1/query` - Custom query
- `GET /api/v1/facts` - List facts
- `POST /api/v1/facts` - Create fact
- `GET /api/v1/facts/{key}` - Get fact
- `DELETE /api/v1/facts/{key}` - Delete fact
- `GET /api/v1/memories/episodic` - List episodic memories
- `POST /api/v1/memories/episodic` - Add episodic memory

#### Memory Management Endpoints

- `GET /api/v1/memory-management/schedule` - Get memory cleanup schedule
- `POST /api/v1/memory-management/schedule` - Update memory cleanup schedule
- `GET /api/v1/memory-management/status` - Get memory management status
- `GET /api/v1/memory-management/metrics` - Get memory management metrics
- `POST /api/v1/memory-management/run` - Run memory management tasks manually

#### Example API Usage

```bash
# Chat completions (OpenAI-compatible)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "pensive",
    "messages": [{"role": "user", "content": "What is my name?"}]
  }'

# Health check
curl http://localhost:8000/health

# Get memory cleanup schedule
curl -X GET http://localhost:8000/api/v1/memory-management/schedule

# Get memory management status
curl -X GET http://localhost:8000/api/v1/memory-management/status

# Get memory management metrics
curl -X GET http://localhost:8000/api/v1/memory-management/metrics

# Run memory management tasks manually
curl -X POST http://localhost:8000/api/v1/memory-management/run

# Update memory management schedule
curl -X POST http://localhost:8000/api/v1/memory-management/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "cron_expression": "0 2 * * *",
    "enabled": true,
    "tasks": ["system_prompt_versions", "stale_memories"]
  }'
```

#### OpenWebUI Integration

To use with OpenWebUI:

1. Start the Pensive API server
2. In OpenWebUI, go to Settings > Models
3. Add a new model with:
   - Model Name: `pensive`
   - API Base URL: `http://localhost:8000/v1`
   - API Key: (optional, leave empty if not using auth)

## Project Structure

This project follows 12-Factor App methodology with proper configuration management:

```
pensive/
├── config/                # Configuration (12-Factor: Store config in environment)
│   ├── default.json      # Default configuration (development)
│   └── production.json   # Production configuration (uses environment variables)
├── services/             # Shared services (replaces utils/)
│   ├── __init__.py
│   └── llm.py           # LLM and embedding client
├── timemgmt/             # Time management (replaces time_management/)
│   ├── __init__.py
│   ├── tasks.py         # Task management
│   ├── reminders.py     # Reminder system
│   └── time_tracking.py # Time tracking
├── memory_system/        # Core memory modules
│   ├── __init__.py
│   ├── config.py        # Configuration loader
│   ├── mongodb.py       # MongoDB connection with vector search
│   ├── schema.py        # Database schemas with version tracking
│   ├── short_term.py    # Short-term memory
│   ├── episodic.py      # Episodic memory with vector search
│   ├── semantic.py      # Semantic memory (facts with versioning)
│   ├── system_prompts.py # System prompt management
│   ├── router.py        # Query router with LLM intent detection
│   ├── temporal.py      # Temporal indexing and bucketing
│   ├── links.py         # Bidirectional memory linking
│   ├── decay.py         # Memory decay and expiration
│   ├── thematic.py      # Multi-level abstraction (thematic layer)
│   ├── compression.py   # Memory compression and archiving
│   ├── memory_metrics.py # Memory quality metrics tracking
│   └── automated_manager.py # Automated memory management loop
├── agent/                # Agent modules
│   ├── __init__.py
│   ├── agent.py         # Base agent class with timezone awareness
│   ├── telegram_gateway.py # Telegram bot gateway (python-telegram-bot v22)
│   ├── intent_router.py # Natural language intent detection
│   ├── command_executor.py # Command execution with safe executor
│   ├── skills_manager.py # Skills registration and management
│   ├── dream_scheduler.py # Timezone-aware dream mode scheduler
│   └── orchestrator.py  # Main orchestrator with LLM fact detection
├── api/                  # API layer (FastAPI routes)
│   ├── __init__.py
│   ├── models.py        # Pydantic models for request/response
│   └── routes.py        # FastAPI routes
├── skills/               # Agent skills
│   ├── system/          # System skills
│   └── built/           # User-built skills
├── tests/                # Test suite
│   ├── __init__.py
│   ├── conftest.py      # Test configuration and fixtures
│   ├── test_config.py   # Config tests
│   ├── test_router.py   # Router tests
│   ├── test_semantic_memory.py  # Semantic memory tests
│   └── test_short_term_memory.py  # Short-term memory tests
├── .env                  # Environment variables (never commit to git)
├── env.example           # Example environment configuration
├── requirements.txt      # Production dependencies
├── requirements-dev.txt  # Development dependencies
├── main.py              # CLI entry point
└── README.md            # This file
```

### 12-Factor Compliance

This project follows 12-Factor App methodology:

1. **Codebase**: Single codebase tracked in version control
2. **Dependencies**: Explicitly declared and isolated (requirements.txt)
3. **Config**: Configuration stored in environment variables (see `config/`)
4. **Backing Services**: MongoDB treated as a connected service
5. **Build, Release, Run**: Separated via Docker images
6. **Processes**: Stateless processes with sessions in MongoDB
7. **Port Binding**: API exposed via port 8000
8. **Concurrency**: Horizontal scaling via multiple instances
9. **Disposability**: Fast startup and graceful shutdown
10. **Dev/Prod Parity**: Same technology in dev and prod
11. **Logs**: Structured logging for audit and diagnostics
12. **Admin Processes**: One-off admin tasks via scripts

### Key Components

- **memory_system/**: Core memory modules with MongoDB integration
  - `schema.py`: Database schemas with version tracking for facts
  - `mongodb.py`: MongoDB connection with vector search support
  - `semantic.py`: Semantic memory with fact versioning and archiving
  - `episodic.py`: Episodic memory with vector similarity search
  - `router.py`: Query router with LLM intent detection

- **Advanced Memory Modules**
  - `temporal.py`: Temporal indexing with time-based bucketing
  - `links.py`: Bidirectional memory linking and graph traversal
  - `decay.py`: Memory decay, expiration dates, and archival
  - `thematic.py`: Multi-level abstraction (episodic → thematic → semantic)
  - `compression.py`: Memory compression and storage optimization
  - `memory_metrics.py`: Quality metrics tracking and analytics

- **automated_manager.py**: Automated background loop for memory maintenance
  - Staleness detection and tagging
  - System prompt version control
  - Low confidence archival
  - Memory compression scheduling

- **agent/**: Agent orchestration
  - `orchestrator.py`: Main orchestrator combining all memory systems
    - LLM-based fact detection for important information
    - Current date context in system prompts
    - Fact versioning with archived history

- **timemgmt/**: Task and time tracking
  - `tasks.py`: Task management
  - `reminders.py`: Reminder system
  - `time_tracking.py`: Time tracking

- **services/**: Shared services
  - `llm.py`: LLM and embedding client for Qwen/Qwen3-Coder-Next-GGUF model

- **tests/**: Comprehensive test suite
  - 28 tests covering all modules
  - Async fixture support for MongoDB integration tests
  - pytest-asyncio for async test support

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_config.py

# Run with verbose output
pytest -v
```

### Example Docker Logs Output

```log
pensive-api-1  | [intent_detection] elapsed=0.000s | {'query_length': 40}
pensive-api-1  | [LLM] elapsed=2.312s | tps=0.0 | tokens_in=0 | tokens_out=0
pensive-api-1  | [intent_complete] elapsed=2.313s | {'intent': 'task'}
pensive-api-1  | [memory_gathering] elapsed=2.313s | {'memory_systems': ['short_term', 'episodic', 'semantic']}
pensive-api-1  | [memory_complete] elapsed=2.445s | {'sources': ['semantic memory', 'short-term memory', 'episodic memory']}
pensive-api-1  | [prompt_building] elapsed=2.445s | {'memories_count': 3}
pensive-api-1  | [prompt_complete] elapsed=2.447s | {'prompt_length': 1059}
pensive-api-1  | [llm_generation] elapsed=2.447s | {'prompt_length': 1059}
pensive-api-1  | [LLM] elapsed=2.364s | tps=0.0 | tokens_in=0 | tokens_out=0
pensive-api-1  | [llm_complete] elapsed=4.812s | {'response_length': 240}
pensive-api-1  | [committing_episodic] elapsed=4.812s | {'event_count': 2}
pensive-api-1  | [fact_detection] elapsed=4.812s | {'query_length': 40}
pensive-api-1  | INFO:     172.19.0.1:65438 - "POST /v1/chat/completions HTTP/1.1" 200 OK
pensive-api-1  | [LLM] elapsed=0.806s | tps=0.0 | tokens_in=0 | tokens_out=0
```

## Vector Index Management

If you change the `EMBEDDING_DIMENSIONS` configuration, you need to recreate the vector indexes:

```bash
# Activate virtual environment
source venv/bin/activate

# Recreate vector indexes
python -m memory_system.mongodb recreate_indexes
```

This will delete existing vector indexes and create new ones with the correct dimensions.

## License

MIT
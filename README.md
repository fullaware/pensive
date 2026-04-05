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
- **Natural Language Skill Creation**: Users can say "build skill that searches Zen" and the LLM generates the skill
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
- **Time Management**: Tasks, reminders, and time tracking
- **Query Router**: AI-powered query intention detection
- **System Prompts**: Dynamic prompt management with user preferences
- **REST API**: OpenAI-compatible API for integration with tools like OpenWebUI

### Advanced Memory Features

#### Temporal Indexing
- **Time-Based Bucketing**: Events are bucketed into time windows (hour/day/week/month)
- **Efficient Range Queries**: Query memories by temporal context without scanning all embeddings
- **Time-Aware Retrieval**: All queries include temporal context relative to "now"

#### Memory Linking
- **Bidirectional Links**: Facts and episodic memories can reference each other
- **Graph Traversal**: Navigate relationships between memories using graph queries
- **Automatic Linking**: Events automatically link to recently created/updated facts

#### Memory Decay & Expiration
- **Confidence Decay**: Older memories automatically get lower confidence scores
- **Expiration Dates**: Optional expiration for ephemeral facts (e.g., current mood, weather)
- **Auto-Archival**: Low-confidence memories are archived instead of deleted

#### Multi-Level Abstraction
- **Episodic Layer**: Raw conversation/event logs with embeddings
- **Thematic Layer**: Grouped/clustered events (e.g., "all project discussions this month")
- **Semantic Layer**: Individual facts with versioning
- **Efficient Group Queries**: Answer "what have we discussed about X this month?" without re-embedding

#### Memory Auditing & Provenance
- **Source Tracking**: Track original source (conversation ID, external API, manual entry)
- **Confidence Explanations**: Store why a memory was created and its confidence level
- **Human Verification**: Track auto-extracted vs. user-confirmed memories

#### Conflict Resolution
- **Merge Strategies**: Latest-wins, majority-vote when multiple sources exist
- **Disputed Status**: Automatically flag facts with low confidence for human review
- **Version History**: Complete audit trail of fact changes

#### Memory Compression
- **Daily Summaries**: Long episodic memories are summarized into daily summaries
- **Cost Optimization**: Archive to cheaper storage after configurable retention period
- **Embedding-Only Storage**: Keep only embeddings for retrieval, move full content to object storage

#### Memory Quality Metrics
- **Retrieval Counts**: Track hot vs. cold memories by retrieval frequency
- **Success Rate**: Monitor if users find what they need in retrieved memories
- **Age Distribution**: Analyze memory age distribution for optimization

### Automated Memory Management

The system includes an automated background loop that continuously organizes and maintains memories:

- **Staleness Detection**: Automatically identifies and tags memories that have become outdated
- **Memory Tagging & Organization**: Automatic tagging based on content and temporal context
- **System Prompt Version Control**: Enforces a maximum of 5 versions, archiving older ones automatically
- **Low Confidence Archival**: Archives memories with low confidence scores that are also old
- **Memory Compression**: Compresses old episodic memories into daily summaries
- **Pending Task Monitoring**: Tracks tasks that have been pending for too long and creates reminders

#### Running the Automated Manager

```bash
# Run automated memory management loop (runs every 24 hours by default)
python scripts/run_automated_manager.py

# Run with custom interval
python scripts/run_automated_manager.py --interval 6  # Run every 6 hours

# Run once and exit (for testing or cron jobs)
python scripts/run_automated_manager.py --one-time

# Using Docker
docker-compose run pensive-api python scripts/run_automated_manager.py
```

#### Configuration Options

Add these to your `.env` file:

```env
# Automated Memory Management Configuration
MEMORY_CLEANUP_INTERVAL_HOURS=24       # Hours between cleanup runs
MAX_SYSTEM_PROMPT_VERSIONS=5           # Maximum system prompt versions to keep
STALENESS_DAYS_THRESHOLD=14            # Days before content is considered stale
AUTO_TAG_ENABLED=true                  # Enable automatic memory tagging
LOW_CONFIDENCE_THRESHOLD=0.3           # Confidence below this gets archived
AUTO_ARCHIVE_AGE_DAYS=90               # Age threshold for auto-archival

# Temporal Configuration
TEMPORAL_BUCKET_SIZE=day               # Time bucket size: hour, day, week, month

# Memory Linking
LINKING_ENABLED=true                   # Enable bidirectional memory linking

# Compression Settings
COMPRESSION_ENABLED=true               # Enable memory compression
COMPRESS_AFTER_DAYS=30                 # Compress episodic memories after this many days

# Quality Metrics
METRICS_ENABLED=true                   # Enable memory quality metrics collection
```

### Time-Aware Features

- **Time-Enhanced Recall**: All episodic memory queries include time context relative to "now"
- **UTC-First Timestamps**: All timestamps stored as ISODate in MongoDB (UTC timezone)
- **Relative Time Display**: Human-readable time context (e.g., "2 hours ago", "in 3 days")
- **Time Tracking Integration**: Active time tracking sessions with duration calculations
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

### Memory Quality Monitoring

The system tracks memory health and provides insights:

- **Hot Memories**: Frequently retrieved memories (likely high-value)
- **Cold Memories**: Rarely retrieved (candidates for compression/archival)
- **Confidence Distribution**: View confidence score distribution across all memories
- **Success Rate Analysis**: Track how often retrieved memories satisfy user queries

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

### Memory Architecture

```mermaid
flowchart TD
  rawEvent[Raw Event] --> episodic[Episodic Memory]
  
  episodic -->|Direct Query| vectorSearch1[Vector Search]
  episodic -->|Bucketing| temporalIndex[Temporal Index]
  
  thematic[Thematic Memory] <--> episodic
  thematic --> vectorSearch2[Vector Search]
  
  semantic[Semantic Memory] <--> thematic
  semantic --> vectorSearch3[Vector Search]
  
  temporalIndex --> timeRange[Time-Based Queries]
  
  vectorSearch1 --> queryResults
  vectorSearch2 --> queryResults
  vectorSearch3 --> queryResults
  
  link1[Memory Links] <--> episodic
  link2[Memory Links] <--> semantic
  
  decay1[Decay System] --> episodic
  decay2[Decay System] --> semantic
  
  compression1[Compression] --> episodic
  compression2[Compression] --> thematic
```

## Environment

This system is built and runs on the following hardware and software configuration:

### Hardware

| Component | Specification |
|-----------|---------------|
| **Machine** | 2025 Apple Mac Studio M3 Ultra |
| **CPU** | 28 cores (20 Performance + 8 Efficiency) |
| **GPU** | 60 GPU Cores @ 819.3 GB/s memory bandwidth |
| **RAM** | 96GB Unified Memory |

### Software Stack

| Component | Version/Details |
|-----------|-----------------|
| **Python** | 3.13 |
| **MongoDB** | 8.2.4 with Vector Search |
| **LLM Inference** | llama.cpp server (build 7990) |
| **LLM Model** | Qwen/Qwen3-Coder-Next-GGUF:Q4_K_M |
| **Embedding Model** | jsonMartin/voyage-4-nano-gguf |

### Performance Considerations

- The M3 Ultra's 96GB unified memory allows for efficient handling of large models and embeddings without swapping
- The 819.3 GB/s memory bandwidth enables fast data transfers between CPU, GPU, and neural engine
- Vector search in MongoDB leverages the high memory bandwidth for fast similarity searches
- llama.cpp's quantized models (Q4_K_M) provide a good balance between inference speed and model quality on Apple Silicon

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

# Temporal Indexing Configuration
TEMPORAL_BUCKET_SIZE=day               # hour, day, week, or month

# Memory Linking Configuration
LINKING_ENABLED=true                   # Enable bidirectional memory linking

# Automated Management Configuration
MEMORY_CLEANUP_INTERVAL_HOURS=24       # Hours between cleanup runs
MAX_SYSTEM_PROMPT_VERSIONS=5           # Maximum system prompt versions to keep

# Compression Configuration
COMPRESSION_ENABLED=true               # Enable memory compression
COMPRESS_AFTER_DAYS=30                 # Compress episodic memories after this many days

# Quality Metrics Configuration
METRICS_ENABLED=true                   # Enable memory quality metrics collection

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
| `pensive-telegram` | Telegram bot gateway (polls Telegram, forwards to API) | `python start_telegram.py` |

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
- `GET /api/v1/tasks` - List tasks
- `POST /api/v1/tasks` - Create task
- `GET /api/v1/tasks/{task_id}` - Get task
- `DELETE /api/v1/tasks/{task_id}` - Delete task
- `GET /api/v1/memories/episodic` - List episodic memories
- `POST /api/v1/memories/episodic` - Add episodic memory

#### Memory Management Endpoints

- `GET /api/v1/memory/schedule` - Get memory cleanup schedule
- `PUT /api/v1/memory/schedule` - Update memory cleanup schedule
- `POST /api/v1/memory/run-cleanup` - Run memory cleanup manually

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
curl -X GET http://localhost:8000/api/v1/memory/schedule

# Run memory cleanup manually
curl -X POST http://localhost:8000/api/v1/memory/run-cleanup
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

```
agents/
├── .env                    # Environment variables
├── .gitignore             # Git ignore rules
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development dependencies
├── main.py                # CLI entry point
├── README.md              # This file
├── MEMORY.md              # Memory system documentation
├── env.example            # Example environment configuration
├── memory_system/         # Core memory modules
│   ├── __init__.py
│   ├── config.py         # Configuration loader
│   ├── mongodb.py        # MongoDB connection with vector search
│   ├── schema.py         # Database schemas with version tracking
│   ├── short_term.py     # Short-term memory
│   ├── episodic.py       # Episodic memory with vector search
│   ├── semantic.py       # Semantic memory (facts with versioning)
│   ├── system_prompts.py # System prompt management
│   ├── router.py         # Query router with LLM intent detection
│   ├── temporal.py       # Temporal indexing and bucketing
│   ├── links.py          # Bidirectional memory linking
│   ├── decay.py          # Memory decay and expiration
│   ├── thematic.py       # Multi-level abstraction (thematic layer)
│   ├── compression.py    # Memory compression and archiving
│   ├── memory_metrics.py # Memory quality metrics tracking
│   └── automated_manager.py # Automated memory management loop
├── time_management/       # Task and time tracking
│   ├── __init__.py
│   ├── tasks.py          # Task management
│   ├── reminders.py      # Reminder system
│   └── time_tracking.py  # Time tracking
├── agent/                 # Agent modules
│   ├── __init__.py
│   ├── agent.py          # Base agent class with timezone awareness
│   ├── telegram_gateway.py  # Telegram bot gateway (python-telegram-bot v22)
│   ├── intent_router.py  # Natural language intent detection
│   ├── command_executor.py  # Command execution with safe executor
│   ├── skills_manager.py  # Skills registration and management
│   ├── dream_scheduler.py  # Timezone-aware dream mode scheduler
│   └── orchestrator.py   # Main orchestrator with LLM fact detection
├── utils/                 # Utility modules
│   ├── __init__.py
│   └── llm.py           # LLM and embedding client
└── tests/                 # Test suite
    ├── __init__.py
    ├── conftest.py      # Test configuration and fixtures
    ├── test_config.py   # Config tests
    ├── test_router.py   # Router tests
    ├── test_semantic_memory.py  # Semantic memory tests
    └── test_short_term_memory.py  # Short-term memory tests
```

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

- **time_management/**: Task and time tracking
  - `tasks.py`: Task management
  - `reminders.py`: Reminder system
  - `time_tracking.py`: Time tracking

- **utils/**: Utility modules
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
python scripts/recreate_index.py
```

This will delete existing vector indexes and create new ones with the correct dimensions.

## License

MIT
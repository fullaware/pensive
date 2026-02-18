# Pensive - Agentic Memory System

An AI agent system with multiple memory types (Short-Term, Episodic, Semantic) inspired by the Rosston Agentic Memory System.

## Features

- **Short-Term Memory**: Session history and conversation context
- **Episodic Memory**: Vector search against past events
- **Semantic Memory**: Facts and knowledge storage (MongoDB)
- **Time Management**: Tasks, reminders, and time tracking
- **Query Router**: AI-powered query intention detection
- **System Prompts**: Dynamic prompt management with user preferences
- **REST API**: OpenAI-compatible API for integration with tools like OpenWebUI
- **Dynamic Fact Detection**: LLM-based extraction of important information from conversations
- **Vector Search for Facts**: Semantic similarity-based fact retrieval using embeddings

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

# Embedding Model Configuration
# Set EMBEDDING_DIMENSIONS to match your embedding model output
# text-embedding-qwen3-embedding-8b returns 1024 dimensions
```

## Usage

### CLI Mode

```bash
python main.py
```

### REST API Mode

Start the API server:

```bash
# Activate virtual environment
source venv/bin/activate

# Start the API server
uvicorn api.routes:app --host 0.0.0.0 --port 8000
```

Or use Docker Compose:

```bash
docker-compose up -d
```

The API will be available at `http://localhost:8000`.

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
│   └── router.py         # Query router with LLM intent detection
├── time_management/       # Task and time tracking
│   ├── __init__.py
│   ├── tasks.py          # Task management
│   ├── reminders.py      # Reminder system
│   └── time_tracking.py  # Time tracking
├── agent/                 # Agent modules
│   ├── __init__.py
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
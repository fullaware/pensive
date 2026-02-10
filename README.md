# Pensive - Agentic Memory System

An AI agent system with multiple memory types (Short-Term, Episodic, Semantic) inspired by the Rosston Agentic Memory System.

## Features

- **Short-Term Memory**: Session history and conversation context
- **Episodic Memory**: Vector search against past events
- **Semantic Memory**: Facts and knowledge storage (MongoDB)
- **Time Management**: Tasks, reminders, and time tracking
- **Query Router**: AI-powered query intention detection
- **System Prompts**: Dynamic prompt management with user preferences
- **Pushover Notifications**: Alert system for important events

## Architecture

```mermaid
flowchart LR
  userQuery[User Query] --> aiIntention["AI: What is this user's intentions based on what we know, generate a new query to run against our various tools that would satisfy the request."]
  aiIntention --> toolQuery[Generated query to tools]

  subgraph tools [Memory tools]
    shortTermMemory[Short-Term Memory: Session History, recall from previous conversations]
    episodicRecall[Episodic Memory: Past events, summarize and save, recall via Vector Search]
    semanticRecall[Semantic Memory: Facts and knowledge, save and recall exact information e.g. USER lives in a house under a bridge]
  end

  toolQuery --> shortTermMemory
  toolQuery --> episodicRecall
  toolQuery --> semanticRecall

  shortTermMemory --> combinedResults[Combined results]
  episodicRecall --> combinedResults
  semanticRecall --> combinedResults

  combinedResults --> presentToUser[Present to user]

  presentToUser --> commitEpisodic[Commit summary to Episodic Memory]
  presentToUser --> commitSemantic[Commit summary to Semantic Memory]
```

## Requirements

- Python 3.13+
- MongoDB with Vector Search capabilities
- LLM API endpoint (e.g., Ollama, LM Studio)
- Embedding model endpoint

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
LLM_EMBEDDING_URI=http://10.28.28.15:1234/v1
LLM_MODEL=Qwen/Qwen3-Coder-Next-GGUF:Q4_K_M
LLM_EMBEDDING_MODEL=voyage-4-nano@f16

# Memory Configuration
SHORT_TERM_MEMORY_SIZE=10
EPISODIC_MEMORY_LIMIT=100
VECTOR_SEARCH_LIMIT=5

# Embedding Model Configuration (1024 dimensions for voyage-4-nano)

# Pushover Configuration
PUSHOVER_TOKEN=your_pushover_token
PUSHOVER_USER=your_pushover_user
```

## Usage

### CLI Mode

```bash
python main.py
```

### Programmatic Usage

```python
import asyncio
from agent import AgenticOrchestrator

async def main():
    orchestrator = AgenticOrchestrator()
    
    result = await orchestrator.process_query("What is my name?")
    print(result["answer"])
    
    await orchestrator.close()

asyncio.run(main())
```

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
│   ├── llm.py           # LLM and embedding client
│   └── pushover.py      # Pushover notifications
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
  - `pushover.py`: Pushover notification client

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

## License

MIT
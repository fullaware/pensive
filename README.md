# 🧠 Pensive - Family Assistant

A self-hosted AI assistant with persistent memory, designed for families. Features hierarchical memory management, multi-user support with role-based access control, and integrations with external services like weather and Google Calendar.

## ✨ Features

- **ChatGPT-like Interface**: Modern, responsive chat UI with streaming responses
- **Real-time Metrics**: Tokens/second display during response generation
- **Reasoning Model Support**: Collapsible thinking sections for models like DeepSeek, Claude
- **Persistent Memory**: Conversations stored in MongoDB with semantic search
- **Vector Search**: Embeddings for intelligent memory retrieval
- **Multi-User Support**: Family members have individual profiles with isolated memories
- **Role-Based Access Control**: Admins have full privileges, users have restricted access
- **Admin Dashboard**: User management, memory browser, usage metrics
- **Weather Integration**: Real-time weather lookups via Open-Meteo API
- **Google Calendar Integration**: Create, view, update, and delete calendar events
- **Web Search**: DuckDuckGo integration for research tasks
- **Research Agent**: Spawn sub-agents for deep research tasks

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Chat UI    │  │ Admin Dash  │  │  Login / Auth       │  │
│  │  (SSE)      │  │  Users      │  │                     │  │
│  │  Streaming  │  │  Memory     │  │                     │  │
│  │  TPS Badge  │  │  Metrics    │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/SSE
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────────┐   │
│  │ /auth   │  │ /chat   │  │ /memory │  │ /admin        │   │
│  │ Login   │  │ Message │  │ Search  │  │ Users         │   │
│  │ Session │  │ History │  │ Stats   │  │ Sessions      │   │
│  └─────────┘  └─────────┘  └─────────┘  └───────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Existing Python Modules                        │
│  agent_factory │ memory/ │ auth/ │ tools │ calendar        │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │       MongoDB           │
              │  • agent_memory         │
              │  • users                │
              │  • sessions             │
              │  • metrics              │
              └─────────────────────────┘
```

## 📋 Requirements

- Python 3.11+
- Node.js 18+ (for frontend)
- MongoDB 8.2+ (Community Edition with vector search support)
- LLM API access (OpenRouter, OpenAI, Ollama, or compatible endpoint)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/yourusername/pensive.git
cd pensive
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=chat_db

# LLM Configuration
LLM_MODEL=google/gemini-2.5-flash
LLM_URI=https://openrouter.ai/api/v1
LLM_API_KEY=your_api_key  # Optional for local providers like Ollama

# Embedding Model (for semantic search)
LLM_EMBEDDING_MODEL=qwen/qwen3-embedding-8b
VECTOR_DIMENSIONS=0  # 0 = use model's native size

# Authentication
SESSION_TIMEOUT_MINUTES=480
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=changeme

# Metrics
METRICS_RETENTION_DAYS=90

# Frontend URL (for CORS)
FRONTEND_ORIGINS=http://localhost:3000

# Google Calendar (optional)
GOOGLE_CALENDAR_CREDENTIALS_FILE=credentials.json
GOOGLE_CALENDAR_TOKEN_FILE=token.json
GOOGLE_CALENDAR_ID=primary
```

### 3. Start MongoDB

```bash
# Using Docker
docker run -d --name mongodb -p 27017:27017 mongodb/mongodb-community-server:latest

# Or install locally: https://www.mongodb.com/docs/manual/installation/
```

### 4. Run with Docker Compose (Recommended)

```bash
# Start both frontend and backend
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

- **Frontend**: `http://localhost:8080`
- **Backend API**: `http://localhost:8383`

### Alternative: Run Without Docker

**Backend:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## 👥 User Management

### Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full access, manage users, view all sessions, full calendar control |
| **User** | Basic chat, weather, create calendar events (no delete/update) |

### First Login

1. On first run, a default admin account is created:
   - Username: `admin` (or value of `DEFAULT_ADMIN_USERNAME`)
   - Password: `changeme` (or value of `DEFAULT_ADMIN_PASSWORD`)
2. **Change this password immediately** in the Admin Dashboard
3. Create additional family members in the Admin Dashboard

### Tool Permissions by Role

| Tool | Admin | User |
|------|-------|------|
| Weather | ✅ | ✅ |
| Search Conversations | ✅ | ✅ |
| Remember/Mark Important | ✅ | ✅ |
| Calendar - View | ✅ | ✅ |
| Calendar - Create | ✅ | ✅ |
| Calendar - Update | ✅ | ❌ |
| Calendar - Delete | ✅ | ❌ |
| Web Search | ✅ | ❌ |
| Research Agent | ✅ | ❌ |
| Summarize Memory | ✅ | ❌ |
| Purge Memory | ✅ | ❌ |
| Memory Stats | ✅ | ❌ |

## 📡 API Endpoints

### Authentication
```
POST   /api/auth/login      # Login, returns session cookie
POST   /api/auth/logout     # Logout
GET    /api/auth/me         # Get current user
POST   /api/auth/validate   # Validate session
```

### Chat
```
POST   /api/chat/message    # Send message (SSE streaming response)
GET    /api/chat/history    # Get paginated chat history
DELETE /api/chat/history    # Clear chat history
```

### Memory
```
POST   /api/memory/search   # Search memories
GET    /api/memory/stats    # Get memory statistics
POST   /api/memory/summarize  # Trigger summarization (admin)
DELETE /api/memory/purge    # Purge old memories (admin)
```

### Admin
```
GET    /api/admin/users     # List users
POST   /api/admin/users     # Create user
PATCH  /api/admin/users/:id # Update user
DELETE /api/admin/users/:id # Delete user
GET    /api/admin/sessions/:user_id  # Get user sessions
GET    /api/admin/stats     # System statistics
```

### Metrics
```
GET    /api/metrics/realtime  # Real-time metrics (TPS, active users)
GET    /api/metrics/history   # Historical metrics
```

## 📁 Project Structure

```
pensive/
├── api/                    # FastAPI backend
│   ├── main.py             # App entry point, CORS
│   ├── models.py           # Pydantic request/response schemas
│   ├── dependencies.py     # Auth middleware, DI
│   └── routes/
│       ├── auth.py         # Authentication routes
│       ├── chat.py         # Chat with SSE streaming
│       ├── memory.py       # Memory management
│       ├── admin.py        # User/session management
│       └── metrics.py      # Usage analytics
├── frontend/               # Next.js frontend
│   ├── src/
│   │   ├── app/            # Pages (chat, login, admin)
│   │   ├── components/     # React components
│   │   │   ├── chat/       # Chat UI components
│   │   │   └── ui/         # Base UI components
│   │   └── lib/            # API client, auth context
│   └── package.json
├── app/                    # Core Python modules
│   ├── agent_factory.py    # Agent creation
│   ├── auth/               # User management
│   ├── memory/             # Memory system
│   ├── tools.py            # Agent tools
│   └── ...
├── main.py                 # Entry point (runs FastAPI)
├── config.py               # Configuration
├── database.py             # MongoDB connection
└── requirements.txt        # Python dependencies
```

## 🔧 Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MONGODB_URI` | Yes | - | MongoDB connection string |
| `MONGODB_DB` | Yes | - | Database name |
| `LLM_MODEL` | Yes | - | LLM model identifier |
| `LLM_URI` | Yes | - | LLM API endpoint |
| `LLM_API_KEY` | No | - | LLM API key (optional for local providers) |
| `LLM_EMBEDDING_MODEL` | No | `qwen/qwen3-embedding-8b` | Embedding model |
| `VECTOR_DIMENSIONS` | No | `0` | Embedding dimensions (0 = native) |
| `SESSION_TIMEOUT_MINUTES` | No | `480` | Session timeout |
| `DEFAULT_ADMIN_USERNAME` | No | `admin` | Initial admin username |
| `DEFAULT_ADMIN_PASSWORD` | No | `changeme` | Initial admin password |
| `FRONTEND_ORIGINS` | No | `http://localhost:3000` | CORS allowed origins |

## 🔒 Security Notes

1. **Change default password** immediately after first login
2. **Add to `.gitignore`**:
   ```
   .env
   credentials.json
   token.json
   frontend/node_modules/
   ```
3. **Production deployment**: Run behind a reverse proxy (nginx) with HTTPS
4. **MongoDB**: Enable authentication in production

## 🐛 Troubleshooting

### API not connecting
- Ensure backend is running on port 8000
- Check CORS settings if frontend is on a different port
- Verify `FRONTEND_ORIGINS` includes your frontend URL

### LLM errors
- For local providers (Ollama), `LLM_API_KEY` is optional
- Verify `LLM_URI` and `LLM_MODEL` are correct

### Vector search not working
- Verify MongoDB 7.0+ is installed
- Check embeddings are being generated (check API logs)

## 📄 License

MIT License - See LICENSE file for details.

## 🤝 Contributing

Contributions welcome! Please read the contributing guidelines before submitting PRs.

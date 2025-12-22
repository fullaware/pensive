# 🧠 Pensive - Family Assistant

A self-hosted AI assistant with persistent memory, designed for families. Features hierarchical memory management, multi-user support with role-based access control, and integrations with external services like weather and Google Calendar.

## ✨ Features

- **Persistent Memory**: Conversations are stored in MongoDB with semantic search capabilities
- **Vector Search**: Uses embeddings for intelligent memory retrieval
- **Multi-User Support**: Family members have individual profiles with isolated memories
- **Role-Based Access Control**: Parents have full admin privileges, children have restricted access
- **Parental Oversight**: Parents can review children's chat history
- **Memory Management**: Automatic summarization, decay scoring, and importance tracking
- **Weather Integration**: Real-time weather lookups via Open-Meteo API
- **Google Calendar Integration**: Create, view, update, and delete calendar events
- **Web Search**: DuckDuckGo integration for research tasks
- **Research Agent**: Spawn sub-agents for deep research tasks

## 📋 Requirements

- Python 3.11+
- MongoDB 7.0+ (Community Edition with vector search support)
- LLM API access (OpenRouter, OpenAI, or compatible endpoint)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/yourusername/pensive.git
cd pensive
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=chat_db

# LLM Configuration (OpenRouter example)
LLM_MODEL=google/gemini-2.5-flash
LLM_URI=https://openrouter.ai/api/v1
LLM_API_KEY=your_openrouter_api_key

# Embedding Model (for semantic search)
LLM_EMBEDDING_MODEL=qwen/qwen3-embedding-8b
# Optional: Set specific dimensions (0 = use model's native size)
VECTOR_DIMENSIONS=0

# Authentication
SESSION_TIMEOUT_MINUTES=480
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=changeme

# Metrics
METRICS_RETENTION_DAYS=90

# Google Calendar (optional - see setup below)
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

### 4. Run the Application

```bash
python gradio_app.py
```

Navigate to `http://localhost:8080` in your browser.

The application uses Gradio for the web interface, providing a modern, responsive UI with built-in chat streaming support.

## 👥 User Management

### Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full admin access, can manage users, view all sessions, full calendar control |
| **User** | Basic chat, weather, create calendar events (no delete/update), no web search or research agents |

### First Login

1. On first run, a default parent account is created:
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

## 📅 Google Calendar Setup

### 1. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "Pensive Family Assistant")
3. Enable the **Google Calendar API**:
   - Navigate to "APIs & Services" → "Library"
   - Search for "Google Calendar API"
   - Click "Enable"

### 2. Create OAuth2 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - User Type: External (or Internal for Workspace)
   - App name: "Pensive"
   - Add your email as a test user
4. Application type: **Desktop app**
5. Name: "Pensive Desktop"
6. Download the JSON file

### 3. Configure Pensive

1. Rename the downloaded file to `credentials.json`
2. Place it in the project root directory
3. Update `.env`:
   ```env
   GOOGLE_CALENDAR_CREDENTIALS_FILE=credentials.json
   GOOGLE_CALENDAR_TOKEN_FILE=token.json
   GOOGLE_CALENDAR_ID=primary
   ```

### 4. First Authorization

1. The first time you use a calendar command, a browser window will open
2. Sign in with your Google account
3. Grant calendar permissions
4. A `token.json` file will be created (add to `.gitignore`)

### 5. Calendar Commands

Once configured, you can ask Pensive:
- "What's on my calendar this week?"
- "Create a dentist appointment for tomorrow at 2pm"
- "Move my meeting to 3pm"
- "Cancel the team lunch event"

**Note**: The `GOOGLE_CALENDAR_ID` can be:
- `primary` - Your main calendar
- A specific calendar ID (found in Google Calendar settings)

## 🗄️ MongoDB Setup

### Vector Search Index

Pensive uses MongoDB's native vector search. The application automatically creates the required index, but you can verify it:

```javascript
// In MongoDB shell
use chat_db
db.vector_embeddings.getIndexes()
```

The index should include:
- `embedding` field with vector search configuration
- `numDimensions: 4096` (or your configured dimension)
- `similarity: cosine`

### Collections

| Collection | Purpose |
|------------|---------|
| `chat_history` | Conversation messages and summaries |
| `vector_embeddings` | Semantic search embeddings |
| `users` | User accounts and permissions |
| `sessions` | Chat session logs for parental review |
| `metrics` | Performance and usage metrics |
| `agent_memory` | New unified memory system (STM/LTM) |

## 🔧 Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MONGODB_URI` | Yes | - | MongoDB connection string |
| `MONGODB_DB` | Yes | - | Database name |
| `LLM_MODEL` | Yes | - | LLM model identifier |
| `LLM_URI` | Yes | - | LLM API endpoint |
| `LLM_API_KEY` | Yes | - | LLM API key |
| `LLM_EMBEDDING_MODEL` | No | `qwen/qwen3-embedding-8b` | Embedding model for vector search |
| `VECTOR_DIMENSIONS` | No | `0` (native) | Embedding dimensions (0 = use model default) |
| `SESSION_TIMEOUT_MINUTES` | No | `480` | Session timeout (8 hours) |
| `DEFAULT_ADMIN_USERNAME` | No | `admin` | Initial admin username |
| `DEFAULT_ADMIN_PASSWORD` | No | `changeme` | Initial admin password |
| `METRICS_RETENTION_DAYS` | No | `90` | How long to keep metrics |
| `GOOGLE_CALENDAR_CREDENTIALS_FILE` | No | `credentials.json` | OAuth credentials file |
| `GOOGLE_CALENDAR_TOKEN_FILE` | No | `token.json` | OAuth token file |
| `GOOGLE_CALENDAR_ID` | No | `primary` | Target calendar ID |

## 📁 Project Structure

```
pensive/
├── gradio_app.py           # Gradio main application entry point
├── config.py               # Configuration and constants
├── database.py             # MongoDB connection and collections
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (not in git)
├── credentials.json        # Google OAuth credentials (not in git)
├── token.json              # Google OAuth token (not in git)
├── app/
│   ├── __init__.py
│   ├── agent_factory.py    # Agent creation and configuration
│   ├── calendar.py         # Google Calendar integration
│   ├── context.py          # Context retrieval helpers
│   ├── memory_extraction.py # Topic/entity extraction
│   ├── memory_management.py # Decay, summarization, maintenance
│   ├── metrics.py          # Usage metrics collection
│   ├── profile.py          # User profile management
│   ├── sessions.py         # Session logging
│   ├── tools.py            # Agent tool definitions
│   ├── vector_memory.py    # Vector search operations
│   ├── weather.py          # Weather API integration
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── manager.py      # User CRUD operations
│   │   ├── middleware.py   # Session authentication
│   │   ├── models.py       # User/Role models
│   │   ├── permissions.py  # Tool permission checks
│   │   └── relationships.py # Family relationships
│   └── memory/
│       ├── __init__.py
│       ├── coordinator.py  # STM/LTM coordination
│       ├── models.py       # Memory tier models
│       ├── retrieval.py    # Hybrid search
│       └── store.py        # Memory storage
```

## 🔒 Security Notes

1. **Change default password** immediately after first login
2. **Add to `.gitignore`**:
   ```
   .env
   credentials.json
   token.json
   *.sqlite
   ```
3. **OAuth tokens** contain sensitive access - protect `token.json`
4. **MongoDB** - consider enabling authentication in production
5. **Network** - run behind a reverse proxy (nginx) with HTTPS in production

## 🐛 Troubleshooting

### "Google Calendar is not configured"
- Ensure `credentials.json` exists in project root
- Install dependencies: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`

### Vector search not working
- Verify MongoDB 7.0+ is installed
- Check that the vector index was created: `db.vector_embeddings.getIndexes()`
- Ensure embeddings are being generated (check logs)

### Memory visualization empty
- The new `agent_memory` collection may not have data yet
- Start chatting to build up the memory system

### Permission denied errors
- Check user role in Admin Dashboard
- Verify tool permissions for the user's role

## 📄 License

MIT License - See LICENSE file for details.

## 🤝 Contributing

Contributions welcome! Please read the contributing guidelines before submitting PRs.

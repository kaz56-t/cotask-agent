# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CoTask Agent is an AutoGen Multi-Task Orchestrator that executes autonomous tasks in parallel using OpenAI/Claude APIs interchangeably. The system uses Docker Compose to manage three services: backend (FastAPI), frontend (Next.js), and runtime (Python execution environment).

## Development Commands

### Starting the Application
```bash
# Start all services with Docker Compose (recommended)
docker-compose up -d

# View logs
docker-compose logs -f
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop services
docker-compose down

# Stop and remove volumes (WARNING: deletes all data)
docker-compose down -v
rm -rf data/
```

### Backend Development
```bash
cd backend

# Install dependencies using uv
uv sync

# Run backend standalone (without Docker)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# The backend code is mounted in ./backend so changes auto-reload in Docker
```

### Frontend Development
```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm build

# Run linter
npm run lint

# The frontend code is mounted in ./frontend so changes auto-reload in Docker
```

### API Access
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Architecture

### Core Components

**Backend (FastAPI + LangGraph)**
- `main.py`: Main FastAPI application with all REST API endpoints
- `database.py`: SQLAlchemy models (Task, ChatSession, ChatMessage, TaskLog)
- `models.py`: Pydantic models for API request/response validation
- `executor.py`: RuntimeExecutor class for Docker-based code execution in isolated runtime container
- `complexity_analyzer.py`: AI-powered task classification (determines task type and complexity)

**Agent System** (`backend/agent/`)
- `router.py`: Routes tasks to appropriate agents based on task type
- `base.py`: Base agent utilities and LLM initialization
- `chat_agent.py`: Handles interactive chat for requirements definition
- `code_agent.py`: Architect+Executor pattern for code generation tasks
- `simple_code_agent.py`: Single-step code generation for simple tasks
- `text_agent.py`: Text generation/editing tasks (emails, reports, summaries)
- `search_agent.py`: Web search capabilities using DuckDuckGo

**Services** (`backend/services/`)
- `chat_service.py`: Chat message processing and session management
- `task_service.py`: Task execution orchestration, runs agents in background

**Prompts** (`backend/prompts/`)
- System prompts for each agent type defining their behavior and capabilities

**Frontend (Next.js 16 + React 19)**
- App Router structure in `frontend/app/`
- Components in `frontend/components/`
- API client and types in `frontend/lib/`

**Runtime Container**
- Isolated Python environment for executing generated code
- Mounted at `/workspace` in container
- Output artifacts saved to `/workspace/outputs/{task_id}`
- Artifacts copied back to host at `./backend/data/artifacts/`

### Task Workflow

1. **Task Creation**: User creates task via API → Task saved to database → Initial chat message triggers requirements definition
2. **Requirements Definition**: ChatAgent interacts with user to clarify requirements (can be skipped with test-execute endpoint)
3. **Task Classification**: When execution starts, `complexity_analyzer.py` classifies task type (code_generation, web_search, text_generation, scraping, rag, simple_text)
4. **Agent Routing**: `agent/router.py` routes task to appropriate specialized agent based on task type
5. **Execution**: Agent executes workflow (may involve multiple iterations)
6. **Code Execution**: For code_generation tasks, code runs in isolated runtime container via `executor.py`
7. **Artifacts**: Generated files saved to runtime container, then copied to host filesystem
8. **Logging**: All agent interactions logged to TaskLog table for debugging/monitoring

### Database Schema

**Tasks Table**
- Core fields: id, name, description, model_provider, model_name, status
- Timestamps: created_at, updated_at, started_at, completed_at
- Task metadata: task_type, complexity, estimated_iterations
- Relationships: One-to-one with ChatSession, one-to-many with TaskLog

**ChatSessions Table**
- Stores conversation context for requirements definition
- One-to-one relationship with Task

**ChatMessages Table**
- Individual messages in a chat session
- role: "user" or "assistant"

**TaskLogs Table**
- Detailed execution logs from agents
- role: "architect", "executor", "system", etc.

### Key Design Patterns

**Agent Router Pattern**: Tasks are dynamically routed to specialized agents (CodeAgent for code generation, SearchAgent for web search, TextAgent for simple text tasks, etc.)

**Architect+Executor Pattern**: CodeAgent splits into two roles - Architect plans the solution, Executor implements and iterates until success.

**Isolated Execution**: Code runs in a separate runtime container accessed via Docker API for security and resource isolation.

**Chat-Based Requirements**: Each task has an associated chat session for interactive requirements definition (can be bypassed for testing).

**Task Classification**: LLM-based analysis determines task type and complexity before routing to appropriate agent.

## Environment Configuration

Required environment variables in `.env`:
```bash
# LLM API Keys (at least one required)
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# Optional: Langfuse for LLM observability
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...

# Task configuration
MAX_CONCURRENT_TASKS=3

# Database
DATABASE_URL=sqlite:///./data/sqlite.db
```

## Important Notes

- Backend uses `uv` for Python dependency management (not pip)
- Frontend uses npm (not yarn or pnpm in docker setup)
- Backend mounts Docker socket (`/var/run/docker.sock`) to control runtime container
- SQLite database persisted in `./backend/data/cotask.db` (or path from DATABASE_URL)
- Artifacts generated by agents stored in `./backend/data/artifacts/{task_id}/`
- Runtime container name is `cotask-agent-runtime` (defined in executor.py)
- All three services must be running for full functionality
- Changes to backend/frontend code auto-reload when using Docker Compose

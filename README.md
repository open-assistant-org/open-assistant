<img src="open-assistant.svg" width="120" alt="Open Assistant">

# Open Assistant

A sophisticated multi-agent personal assistant system that integrates with your daily tools to manage emails, files, calendars, tasks, and notes through natural conversations.

## Installation

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/open-assistant-org/open-assistant/main/install.sh)
```

That's it. The script will check for Docker, pull the image, and guide you through configuring your LLM provider.

## Overview

This personal assistant bot provides a unified interface to interact with your productivity tools through a multi-agent architecture. Each agent specializes in specific tasks (email management, file access, calendar operations, etc.) while coordinating to provide seamless assistance.

**Design Philosophy**: Built for **single-user, self-hosted** deployments. Runs in a single Docker container for simplicity, security, and ease of maintenance. Not designed for multi-user or high-availability scenarios.

## Core Features

### Email Management
- **Gmail Integration**: Send, read, search emails; create drafts; list labels
- **Outlook Integration**: Send, read emails; create drafts; support for multiple folders

### File Storage Access
- **OneDrive**: List and search files from Microsoft OneDrive
- **Nextcloud**: List, read, search, download files; get file info; check existence

### Calendar Management
- **Google Calendar**: List calendars and events; create events with attendees, location, all-day support
- **Outlook Calendar**: List calendars and events; create events with online meeting support

### Note-taking & Knowledge Base
- **Notion Integration**: Create notes and pages; search content; query databases; append content; update pages

### Web Capabilities
- **Web Search**: Privacy-focused web search via Brave Search API
- **Web Browsing**: Automated browsing with Playwright - navigate, click, type, scroll, extract text
  - Vision-based page understanding using screenshots
  - Automatic text extraction for data analysis
  - Headless browser with configurable viewport

### Task Scheduling
- **Cron Jobs**: Recurring scheduled tasks with cron expressions
- **Future Tasks**: One-time scheduled tasks for reminders and delayed actions
- **Job Management**: Enable/disable, edit, run now, view execution history

### Communication Channels
- **WhatsApp**: Interact via WhatsApp using whatsapp-web.js bridge (QR code authentication)
- **Web UI**: Chat interface, settings management, conversation history, monitoring dashboard

### Conversation Management
- **History**: Full conversation persistence with search and date filtering
- **Memory**: Smart context management with automatic summarization
- **Features**: Pin conversations, auto-generate titles, conversation statistics

### Personalization
- **System Prompt**: Default base prompt with customizable instructions on top
- **Memory**: Text-based store for user context — name, preferences, people, places, relations; built automatically by nightly cron job
- **Soul**: Assistant personality and communication style; shaped automatically by nightly cron job from conversation feedback

### Monitoring & Observability
- **Health Checks**: Database, LLM API, disk space monitoring
- **Metrics**: Conversation stats, message counts, API usage
- **Audit Logging**: Track all tool executions, settings changes, authentication events
- **System Logs**: View and filter application logs

## Architecture

The system uses a **multi-agent architecture** powered by LLM tool calling:

**Flow**: LLM → Agents → Tools

- **Agents** (9 total): coordinator, research, communication, writer, file_handler, planner, navigator, system, browser
- **Tools**: 88+ callable tools mapped to service operations
- **Services/Integrations**: Enable tools by connecting Google, Outlook, Notion, Nextcloud, WhatsApp, Brave Search, and more

The coordinator agent orchestrates tasks by delegating to specialist agents, each with their own set of tools. Services (integrations) are enabled independently — each service you connect expands the toolset available to agents.

## Project Structure

```
open-assistant/
├── .github/              # CI/CD pipelines and GitHub workflows
│   └── workflows/        # GitHub Actions configurations
├── docs/                 # Project documentation
│   ├── architecture/     # System design and architecture docs
│   ├── integrations/     # Integration guides for each service
│   └── setup/            # Setup and configuration guides
├── src/                  # Source code
│   ├── agents/           # Agent definitions and registry
│   ├── api/              # API endpoints
│   ├── core/             # Core system components (database, tools, scheduler)
│   ├── integrations/     # Service integrations (Gmail, Outlook, etc.)
│   ├── models/           # Data models
│   ├── services/         # Business logic services
│   ├── ui/                # Web UI components
│   └── utils/             # Utility functions and helpers
├── config/               # Configuration files
├── .gitignore             # Git ignore rules
└── README.md              # This file
```

## Technology Stack

- **Language**: Python 3.11+
- **Agent System**: Data-driven multi-agent orchestration (9 agents with 88+ tools)
- **Browser Automation**: Playwright (Chromium)
- **APIs**:
  - Microsoft Graph API (Outlook, OneDrive)
  - Google APIs (Gmail, Calendar)
  - Notion API
  - Nextcloud WebDAV
  - Brave Search API
- **Communication**:
  - WhatsApp via whatsapp-web.js bridge (Node.js)
  - Web UI (FastAPI backend, vanilla JavaScript frontend)
- **Task Scheduling**: APScheduler for cron jobs and future tasks
- **Database**: SQLite (single-user deployment)

## Getting Started

### Prerequisites

- Docker (recommended) or Python 3.11+ with uv
- Node.js 16+ (for WhatsApp integration)
- API credentials for integrations (optional):
  - Google Workspace (Gmail, Calendar)
  - Microsoft 365 (Outlook, OneDrive)
  - Notion
  - Nextcloud instance

### Installation

#### Option 1: Docker (Recommended)

**Pull from GitHub Container Registry:**
```bash
# Pull the latest image
docker pull ghcr.io/open-assistant-org/open-assistant:latest

# Run the container (development/localhost)
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config:/app/config \
  -e ENCRYPTION_KEY="your-key-here" \
  -e APP_URL="http://localhost:8080" \
  --name open-assistant \
  ghcr.io/open-assistant-org/open-assistant:latest

# For production with custom domain, add APP_URL and CORS_ORIGINS:
# docker run -d \
#   -p 8080:8080 \
#   -v $(pwd)/data:/app/data \
#   -v $(pwd)/logs:/app/logs \
#   -e ENCRYPTION_KEY="your-key-here" \
#   -e APP_URL="https://assistant.yourdomain.com" \
#   -e CORS_ORIGINS="https://assistant.yourdomain.com" \
#   --name open-assistant \
#   ghcr.io/open-assistant-org/open-assistant:latest

# Check health
curl http://localhost:8080/health
```

**Or build locally:**
```bash
# Clone the repository
git clone https://github.com/open-assistant-org/open-assistant
cd open-assistant

# Copy and configure settings
cp .env.example .env
# Edit .env with your settings:
#   - Set ENCRYPTION_KEY (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#   - Set APP_URL (e.g., https://assistant.yourdomain.com for production, or http://localhost:8080 for local)
#   - Optional: Set CORS_ORIGINS if frontend is on different domain

# Build and run with docker-compose
docker-compose up -d

# Check logs
docker-compose logs -f

# Access the application at your APP_URL (default: http://localhost:8080)
```

#### Option 2: Local Development with uv

```bash
# Clone the repository
git clone https://github.com/open-assistant-org/open-assistant
cd open-assistant

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Setup configuration
cp .env.example .env
# Edit .env with your settings

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Add the key to .env as ENCRYPTION_KEY

# Install WhatsApp bridge dependencies (if using WhatsApp)
cd src/integrations/whatsapp/bridge
npm install
cd ../../../..

# Run the application (database initializes automatically on first start)
uv run python -m src.main

# In a separate terminal, run the WhatsApp bridge (if using WhatsApp)
cd src/integrations/whatsapp/bridge
npm start
```

### Via WhatsApp

1. Enable WhatsApp integration in the settings UI
2. Scan the QR code displayed in the settings to link your WhatsApp account
3. Send messages to the linked WhatsApp number to interact with your assistant
4. The assistant will respond to incoming messages automatically

### Via Web UI

Access the web interface at `http://localhost:8080` to:
- Manage service connections
- View conversation history
- Monitor task execution
- Configure settings

## Development

### Development Guidelines

**📋 Documentation-First Development**: ALL features must be documented before implementation.

**Quick Start**:
1. Read [`docs/setup/development.md`](docs/setup/development.md) - Development environment setup
2. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) - Contribution guidelines and workflow

**Workflow**: Documentation → User Approval → Implementation → Verification

**Tech Stack**:
- Backend: Python 3.11+, FastAPI, raw sqlite3 (DatabaseManager)
- Frontend: Vanilla JavaScript, HTML5, CSS3 (no build step)
- Database: SQLite (single-user deployment)
- All open-source, single Docker container deployment

### Versioning

This project uses tag-based versioning. Releases are tagged with semantic versioning (e.g., `v1.0.0`, `v1.1.0`).

### Documentation

Comprehensive documentation is available in the `docs/` directory:
- [Integration Guides](docs/integrations/)
- [Development Setup](docs/setup/development.md)

## Security

- All API credentials are stored securely using environment variables or encrypted configuration
- OAuth2 flows are used for all service integrations
- Tokens are refreshed automatically and stored securely
- See [Configuration Guide](docs/setup/configuration.md) for security best practices

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to report issues, suggest features, and submit pull requests.

## License

This project is licensed under the [BUSL-1.1 License](LICENSE).

## Support

For issues, questions, or contributions, please open an issue in the repository.

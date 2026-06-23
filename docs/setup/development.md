# Development Setup Guide

This guide covers setting up the development environment for Open Assistant.

## Prerequisites

- Python 3.11 or higher
- Git
- uv (recommended) or pip and venv
- SQLite3 (usually included with Python)

### Installing uv

uv is a fast Python package installer and resolver (10-100x faster than pip):

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify installation
uv --version
```

## Initial Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd open-assistant
```

### 2. Install Dependencies with uv

```bash
# Install production dependencies
uv sync

# Install with development dependencies
uv sync --extra dev
```

This creates a virtual environment in `.venv/` and installs all dependencies from `pyproject.toml`.

Dependencies include:
- FastAPI (web framework)
- uvicorn (ASGI server)
- SQLAlchemy (database ORM)
- APScheduler (task scheduling)
- google-api-python-client (Gmail, Calendar)
- msal (Microsoft Graph API)
- notion-client (Notion API)
- webdavclient3 (Nextcloud)
- python-dotenv (environment variables)
- pyyaml (config file parsing)
- cryptography (credential encryption)

### 3. Setup Configuration

```bash
# Copy example files
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# Edit .env with your settings
nano .env

# Edit config.yaml with your service configurations
nano config/config.yaml
```

### 4. Generate Encryption Key

```bash
# Generate a Fernet encryption key
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add the generated key to .env
echo "ENCRYPTION_KEY=<generated-key>" >> .env
```

### 5. Initialize Database

```bash
# Create data directory and initialize database
uv run python -m src.core.database init
```

This will create the database schema and initial tables.

## Project Structure

```
src/
├── __init__.py
├── main.py                    # Application entry point
├── agents/                    # Agent implementations
│   ├── __init__.py
│   ├── base_agent.py          # Base agent class
│   ├── orchestrator.py        # Main orchestrator agent
│   ├── email_agent.py
│   ├── calendar_agent.py
│   ├── file_agent.py
│   ├── task_agent.py
│   └── notion_agent.py
├── core/                      # Core system components
│   ├── __init__.py
│   ├── database.py            # Database models and session
│   ├── config.py              # Configuration loader
│   ├── encryption.py          # Credential encryption
│   └── message_queue.py       # Internal message queue
├── integrations/              # External service integrations
│   ├── __init__.py
│   ├── gmail/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   └── client.py
│   ├── outlook/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   └── client.py
│   ├── notion/
│   │   ├── __init__.py
│   │   └── client.py
│   └── nextcloud/
│       ├── __init__.py
│       └── client.py
├── api/                       # REST API
│   ├── __init__.py
│   ├── app.py                 # FastAPI application
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── conversations.py
│   │   ├── connections.py
│   │   ├── tasks.py
│   │   ├── cron_jobs.py
│   │   └── settings.py
│   └── websocket.py           # WebSocket handler
├── ui/                        # Web UI
│   ├── __init__.py
│   ├── app.py                 # UI backend
│   ├── static/                # Static files (JS, CSS)
│   └── templates/             # HTML templates
└── utils/                     # Utility functions
    ├── __init__.py
    ├── logger.py              # Logging setup
    ├── validators.py          # Input validation
    └── helpers.py             # Common helper functions
```

## Development Workflow

### Running the Application

**Start main service:**
```bash
uv run python -m src.main
```

**Start web UI (when implemented):**
```bash
uv run python -m src.ui.app
# or with auto-reload
uv run uvicorn src.api.app:app --reload --port 8080
```

### Code Style

Use consistent Python style:
- Follow PEP 8
- Use type hints
- Write docstrings for classes and functions
- Use meaningful variable names

Example:
```python
from typing import List, Optional

class EmailAgent:
    """Agent for handling email operations across Gmail and Outlook."""

    def read_emails(
        self,
        service: str,
        filter: str = "unread",
        limit: int = 10
    ) -> List[dict]:
        """
        Read emails from the specified service.

        Args:
            service: Email service ('gmail' or 'outlook')
            filter: Email filter (default: 'unread')
            limit: Maximum number of emails to return

        Returns:
            List of email dictionaries

        Raises:
            ValueError: If service is not supported
        """
        pass
```

### Logging

Use the built-in logger:

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)

logger.info("Processing email request")
logger.error("Failed to connect to Gmail", exc_info=True)
logger.debug(f"Email content: {email_data}")
```

### Database Migrations

For now, database changes are manual:

1. Update schema in `src/core/database.py`
2. Create migration SQL in `migrations/`
3. Apply manually or create migration script

Future: Consider using Alembic for automated migrations.

### Configuration Management

Configuration priority (highest to lowest):
1. Environment variables
2. `.env` file
3. `config/config.yaml`
4. Default values in code

Load config:
```python
from src.core.config import get_config

config = get_config()
gmail_enabled = config.gmail.enabled
```

## Debugging

### Debug Mode

Set log level to DEBUG in config:
```yaml
general:
  log_level: "DEBUG"
```

Or via environment:
```bash
export LOG_LEVEL=DEBUG
uv run python -m src.main
```

### Database Inspection

```bash
# Open SQLite database
sqlite3 data/assistant.db

# List tables
.tables

# Query conversations
SELECT * FROM conversations LIMIT 10;

# Schema
.schema conversations
```

### Testing Integrations

Each integration should have a test script:

```bash
# Test Gmail connection
uv run python -m src.integrations.gmail.test

# Test Outlook connection
uv run python -m src.integrations.outlook.test

# Test Notion connection
uv run python -m src.integrations.notion.test
```

## Common Development Tasks

### Adding a New Agent

1. Create agent file: `src/agents/new_agent.py`
2. Inherit from `BaseAgent`
3. Implement required methods
4. Register in orchestrator
5. Add integration tests

### Adding a New Service Integration

1. Create integration directory: `src/integrations/service_name/`
2. Implement auth flow
3. Implement client
4. Add configuration schema
5. Update documentation

### Adding API Endpoints

1. Create route file: `src/api/new_routes.py`
2. Define FastAPI routes
3. Add request/response models
4. Register in main app

## Environment Variables Reference

```bash
# Core
DATABASE_URL=sqlite:///data/assistant.db
ENCRYPTION_KEY=your-fernet-key
LOG_LEVEL=INFO
ENVIRONMENT=development

# Gmail
GMAIL_CREDENTIALS_PATH=config/credentials/gmail_credentials.json

# Outlook
OUTLOOK_CLIENT_ID=client-id
OUTLOOK_CLIENT_SECRET=client-secret
OUTLOOK_TENANT_ID=tenant-id

# Notion
NOTION_API_TOKEN=secret_token

# Nextcloud
NEXTCLOUD_SERVER_URL=https://cloud.example.com
NEXTCLOUD_USERNAME=username
NEXTCLOUD_PASSWORD=app-password

# WhatsApp
WACLI_PATH=/usr/local/bin/wacli
WHATSAPP_PHONE=+1234567890

# Web UI
WEB_UI_HOST=0.0.0.0
WEB_UI_PORT=8080
```

## Troubleshooting

### Import Errors

Ensure you're running from the project root:
```bash
python -m src.main  # Correct
python src/main.py  # May cause import issues
```

### Database Locked

SQLite can have locking issues with concurrent access:
- Use PostgreSQL for production
- Close connections properly
- Use connection pooling

### OAuth Flow Issues

For local OAuth flows:
- Ensure redirect URIs match configuration
- Check firewall isn't blocking callback
- Use `http://localhost:8080` not `http://127.0.0.1:8080`

## Next Steps

1. Implement core database models
2. Create base agent class
3. Implement orchestrator
4. Add first integration (Gmail recommended)
5. Build basic API endpoints
6. Create simple UI
7. Add WhatsApp integration

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [Python Best Practices](https://docs.python-guide.org/)
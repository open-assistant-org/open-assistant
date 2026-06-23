# Configuration Guide

This guide covers the configuration of Open Assistant and all its integrations.

## Overview: Database-First Configuration

Open Assistant uses a **database-first configuration approach**. All settings are stored in the database and can be managed through:
- **Settings API**: RESTful endpoints for programmatic access
- **Web UI**: User-friendly interface for managing settings (coming soon)
- **Migration Tool**: Automated migration from environment variables to database

### Configuration Precedence (Fallback Chain)

The system uses a three-tier fallback strategy for retrieving settings:

1. **Database** (Primary): Settings stored in the `settings` table
2. **Environment Variables** (Fallback): Values from `.env` file or system environment
3. **Defaults** (Last Resort): Default values defined in setting definitions

### Bootstrap vs. Managed Settings

#### Bootstrap Settings (ENV Only)
Critical settings that **cannot** be stored in the database for security and bootstrapping reasons:
- `DATABASE_URL`: Database connection string (e.g., `sqlite:///data/assistant.db`)
- `ENCRYPTION_KEY`: Key for encrypting sensitive credentials
- `APP_URL`: Base URL of your deployment (e.g., `https://assistant.yourdomain.com` or `http://localhost:8080`)
- `CORS_ORIGINS`: Comma-separated list of allowed CORS origins (optional, defaults to APP_URL + localhost)

These settings are always read from environment variables and cannot be changed via the Settings API.

#### Managed Settings (Database)
All other settings can be migrated to and managed from the database:
- Application settings (logging, environment)
- LLM configuration
- Integration settings (Gmail, Outlook, Notion, etc.)
- Web UI settings

## Initial Setup

### Step 1: Create Environment File

Create a `.env` file in the project root with bootstrap settings:

```bash
# Bootstrap Settings (Required - Cannot be stored in DB)
DATABASE_URL=sqlite:///data/assistant.db
# Or for PostgreSQL: postgresql://user:password@localhost/assistant_db

ENCRYPTION_KEY=your-32-character-encryption-key-here

# Deployment Configuration
# Set your domain/URL for production deployments
APP_URL=http://localhost:8080
# For production: APP_URL=https://assistant.yourdomain.com

# CORS Origins (optional - defaults to APP_URL + localhost ports)
# Only needed if frontend is on different domain than APP_URL
# CORS_ORIGINS=https://assistant.yourdomain.com,https://app.yourdomain.com
```

**Generate an encryption key:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 2: Initialize Database

The database is automatically initialized on first startup. The application will:
1. Create the database file (if using SQLite)
2. Run all migrations to create tables

Start the application:
```bash
python -m src.main
```

### Step 3: Configure Settings

You can configure settings using one of these methods:

#### Method A: Environment Variables (Legacy)

Add settings to your `.env` file:
```bash
# Application Settings
APP_ENVIRONMENT=development
LOG_LEVEL=INFO

# LLM Configuration
LLM_PROVIDER=openrouter
LLM_MODEL=anthropic/claude-sonnet-4.6
LLM_API_KEY=your-api-key-here

# Gmail Integration
GMAIL_ENABLED=true
GMAIL_CREDENTIALS_PATH=config/credentials/gmail_credentials.json

# Outlook Integration
OUTLOOK_ENABLED=true
OUTLOOK_CLIENT_ID=your-client-id
OUTLOOK_CLIENT_SECRET=your-client-secret
OUTLOOK_TENANT_ID=your-tenant-id

# Notion Integration
NOTION_ENABLED=true
NOTION_API_KEY=your-notion-api-key

# Nextcloud Integration
NEXTCLOUD_ENABLED=true
NEXTCLOUD_URL=https://your-nextcloud-instance.com
NEXTCLOUD_USERNAME=your-username
NEXTCLOUD_PASSWORD=your-app-password

# WhatsApp Integration
WHATSAPP_ENABLED=true
WHATSAPP_WACLI_PATH=/path/to/wacli
```

#### Method B: Settings API (Recommended)

Use the RESTful API to manage settings:

```bash
# Get all setting definitions
curl http://localhost:8000/api/settings/definitions

# Get settings by category
curl http://localhost:8000/api/settings/category/llm

# Get a specific setting
curl http://localhost:8000/api/settings/llm.provider

# Update a setting
curl -X PUT http://localhost:8000/api/settings/llm.provider \
  -H "Content-Type: application/json" \
  -d '{"value": "openrouter"}'

# Validate a setting without saving
curl -X POST http://localhost:8000/api/settings/validate/llm.temperature \
  -H "Content-Type: application/json" \
  -d '{"value": 0.7}'
```

#### Method C: Settings Web UI

The web-based Settings UI is available at `/settings` and provides tabs for:

- **Application**: General settings, logging, memory management, web UI configuration
- **LLM**: Language model provider, API key, model selection, connection testing
- **Prompts**: Personalization of the assistant experience:
  - **System Prompt** (default + custom instructions): Define the base behavior and add custom instructions
  - **Memory**: Text-based store for user context (name, preferences, people, places, relations)
  - **Soul**: Personality and communication style description, shaped by user feedback
- **Integrations**: Enable/disable services (Google, Outlook, Notion, Nextcloud, WhatsApp), manage credentials, test connections
- **Advanced**: Audit log viewer, reset all settings

## Configuration Categories

Settings are organized into the following categories:

### 1. Application Settings
- **Category**: `APPLICATION`
- **Keys**: `app.environment`, `app.name`, `app.version`
- **Description**: General application configuration

### 2. Logging Settings
- **Category**: `LOGGING`
- **Keys**: `logging.level`, `logging.format`, `logging.file_path`
- **Description**: Logging configuration

### 3. Memory Management
- **Category**: `MEMORY`
- **Keys**: `memory.max_context_length`, `memory.max_turns`, `memory.summarization_threshold`
- **Description**: Conversation memory and context management

### 4. Web UI Settings
- **Category**: `WEB_UI`
- **Keys**: `web_ui.host`, `web_ui.port`, `web_ui.reload`
- **Description**: Web server configuration
- **Note**: `CORS_ORIGINS` is currently an ENV variable, planned migration to DB

### 5. LLM Configuration
- **Category**: `LLM`
- **Keys**: `llm.provider`, `llm.model`, `llm.base_url`, `llm.api_key`, `llm.temperature`, `llm.max_tokens`, `llm.tool_output_max_chars`, `memory.max_tokens`, `llm.media_model`, `llm.worker_model`, `llm.writer_model`
- **Description**: Language model provider and settings
- **Max Context Tokens** (`memory.max_tokens`, ENV `MEMORY_MAX_TOKENS`, default `100000`): tokens of conversation history loaded each turn — distinct from `llm.max_tokens`, which caps the response. The default is sized for 200K-context models, leaving headroom for the system prompt, tool definitions, in-turn tool results, and the response. Lower it for smaller-window models.
- **Max Tool Output Chars** (`llm.tool_output_max_chars`, ENV `TOOL_RESULT_OFFLOAD_THRESHOLD`, default `300000` ≈ 75K tokens): tool results larger than this are written to a temp file and replaced in-context with a compact pointer (schema + sample) for `python_agent` to process, so a single large result never overflows the context window. Raise it to keep more inline; lower it to offload sooner.
- **Supported Providers**: `openrouter`, `groq`, `ollama`, `vllm`, `custom`
- **Local providers**: `ollama` (default base URL `http://localhost:11434/v1`) and `vllm` (default `http://localhost:8000/v1`) need no API key. For both, the media/worker/writer models always fall back to the main model since each endpoint serves a single model.

### 6. Google Integration (Gmail, Calendar)
- **Category**: `GOOGLE`
- **Keys**: `google.enabled`, `google.client_id`, `google.client_secret`, `google.project_id`
- **Note**: OAuth tokens are stored encrypted in the database (no file path needed)
- **Credentials**: OAuth tokens stored encrypted in `service_credentials` table
- **Required Scopes** (Gmail):
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/gmail.compose`

### 7. Outlook Integration
- **Category**: `OUTLOOK`
- **Keys**: `outlook.enabled`, `outlook.client_id`, `outlook.client_secret`, `outlook.tenant_id`
- **Credentials**: OAuth tokens stored encrypted
- **Required Scopes**:
  - `https://graph.microsoft.com/Mail.Read`
  - `https://graph.microsoft.com/Mail.ReadWrite`
  - `https://graph.microsoft.com/Calendars.Read` (for calendar)
  - `https://graph.microsoft.com/Calendars.ReadWrite` (for calendar)

### 8. Notion Integration
- **Category**: `NOTION`
- **Keys**: `notion.enabled`, `notion.api_key`, `notion.default_database_id`
- **Credentials**: API keys stored encrypted

### 9. Nextcloud Integration
- **Category**: `NEXTCLOUD`
- **Keys**: `nextcloud.enabled`, `nextcloud.url`, `nextcloud.username`, `nextcloud.password`
- **Credentials**: App passwords stored encrypted
- **Note**: Use app-specific password, not main account password

### 10. WhatsApp Integration
- **Category**: `WHATSAPP`
- **Keys**: `whatsapp.enabled`, `whatsapp.wacli_path`, `whatsapp.phone_number`
- **Description**: WhatsApp integration using wacli CLI tool

## Encrypted Credentials Storage

Sensitive credentials (OAuth tokens, API keys, passwords) are stored separately from general settings:

### Credential Types

1. **OAuth Tokens**: Automatically managed during OAuth flows
   - Stored in `service_credentials` table
   - Encrypted using Fernet encryption
   - Auto-refresh when expired

2. **API Keys**: Stored encrypted for services like Notion
   - Set via Settings API with `is_sensitive=true`
   - Never returned in plain text via API

3. **App Passwords**: For services like Nextcloud
   - Stored encrypted
   - Used for basic authentication

### OAuth Credentials Setup

OAuth credentials (client IDs, secrets) should be stored in `config/credentials/`:

```
config/
└── credentials/
    └── google_token.json           # OAuth tokens (auto-generated, stored in DB)
```

**Google Integration (Gmail/Calendar):**
- Credentials are now configured directly in Settings UI
- No JSON files needed - enter Client ID and Client Secret directly
- OAuth tokens are automatically stored in the database

**Important**: Never commit credentials or tokens to version control.

## Initial Setup Checklist

### Core Setup
- [ ] Create `.env` file with bootstrap settings
- [ ] Generate encryption key using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- [ ] Set `DATABASE_URL` (SQLite or PostgreSQL)
- [ ] Set `ENCRYPTION_KEY`
- [ ] Start application to initialize database
- [ ] Migrate settings to database (manual or auto)

### Integration Setup
- [ ] **Google (Gmail/Calendar)**:
  - Set up Google Cloud Console project
  - Create OAuth 2.0 Desktop App credentials
  - Copy Client ID and Client Secret
  - Enter credentials in Settings UI under Google integration
  - Set `google.enabled=true`
  - Complete OAuth flow to generate tokens (stored in DB)

- [ ] **Outlook/OneDrive**:
  - Set up Azure App Registration
  - Configure `outlook.client_id`, `outlook.client_secret`, `outlook.tenant_id`
  - Set `outlook.enabled=true`
  - Complete OAuth flow to generate tokens (stored in DB)

- [ ] **Notion**:
  - Create Notion integration at https://www.notion.so/my-integrations
  - Set `notion.api_key` via Settings API (stored encrypted)
  - Set `notion.enabled=true`
  - Optional: Configure `notion.default_database_id`

- [ ] **Nextcloud**:
  - Generate app-specific password in Nextcloud
  - Set `nextcloud.url`, `nextcloud.username`, `nextcloud.password` (stored encrypted)
  - Set `nextcloud.enabled=true`

- [ ] **WhatsApp**:
  - Install and configure wacli CLI tool
  - Set `whatsapp.wacli_path` to wacli binary location
  - Set `whatsapp.phone_number` to your WhatsApp number
  - Set `whatsapp.enabled=true`

### LLM Configuration
- [ ] Choose LLM provider: `llm.provider` (openrouter, groq, ollama, vllm, custom)
- [ ] Set model: `llm.model` (e.g., `anthropic/claude-sonnet-4.6`)
- [ ] Configure API key for chosen provider (stored encrypted; not needed for `ollama`/`vllm`)
- [ ] Optional: Set `llm.base_url` (auto-filled per provider; required for `custom`)
- [ ] Optional: Adjust `llm.temperature`, `llm.max_tokens`
- [ ] Optional: Set `llm.media_model` / `llm.worker_model` / `llm.writer_model` (ignored on `ollama`/`vllm`)

### Testing
- [ ] Verify database migration: `curl http://localhost:8000/api/settings/definitions`
- [ ] Test each integration independently via API or Web UI
- [ ] Check logs for any configuration warnings: `tail -f logs/assistant.log`

## Settings API Reference

### Base URL
```
http://localhost:8000/api/settings
```

### Endpoints

#### List All Categories
```bash
GET /api/settings/categories
```

#### Get Settings by Category
```bash
GET /api/settings/category/{category}
# Example: GET /api/settings/category/llm
```

#### Get All Setting Definitions
```bash
GET /api/settings/definitions
```
Returns metadata for all settings including:
- Display name, description
- Value type, validation rules
- Default values
- UI widget hints

#### Get Specific Setting
```bash
GET /api/settings/{key}
# Example: GET /api/settings/llm.provider
```

#### Update Setting
```bash
PUT /api/settings/{key}
Content-Type: application/json

{
  "value": "new-value"
}
```

**Validation:**
- Type checking (string, int, float, bool, json)
- Range validation (min/max for numbers)
- Enum/options validation
- Regex pattern matching
- Required field validation

**Security:**
- Bootstrap settings cannot be updated via API
- Sensitive values are encrypted in database
- Audit log maintained for all changes

#### Validate Setting
```bash
POST /api/settings/validate/{key}
Content-Type: application/json

{
  "value": "test-value"
}
```
Validates without saving to database.

#### Trigger Migration
```bash
POST /api/settings/migrate
Content-Type: application/json

{
  "conflict_strategy": "env"  # or "db", "skip"
}
```

## Domain and CORS Configuration

### APP_URL Configuration

The `APP_URL` environment variable specifies the base URL where your application is deployed:

```bash
# Development (default)
APP_URL=http://localhost:8080

# Production examples
APP_URL=https://assistant.yourdomain.com
APP_URL=https://example.com:8443
```

**Used for:**
- Automatic CORS configuration
- OAuth redirect URIs (future enhancement)
- Generating absolute URLs in notifications and webhooks

### CORS Configuration

**Current Implementation:**
CORS origins are configured via the `CORS_ORIGINS` environment variable:

```bash
# Single origin
CORS_ORIGINS=http://localhost:3000

# Multiple origins (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:8000,https://app.example.com
```

**Default Behavior:**
If `CORS_ORIGINS` is not set, the application automatically allows:
- Common localhost development ports (3000, 8000, 8080)
- The URL specified in `APP_URL`

This means for most deployments, you only need to set `APP_URL` and CORS will be configured automatically.

**Production Best Practice:**
For production deployments, explicitly set both `APP_URL` and `CORS_ORIGINS`:

```bash
# Set your application URL
APP_URL=https://assistant.yourdomain.com

# Explicitly allow specific origins for CORS
CORS_ORIGINS=https://assistant.yourdomain.com,https://app.yourdomain.com
```

## Troubleshooting

### Database Issues

**Problem: Database locked (SQLite)**
```
sqlite3.OperationalError: database is locked
```
**Solution:**
- Use PostgreSQL for production environments
- Ensure only one application instance is running (SQLite doesn't support concurrent writes)
- Check for stale lock files: `rm data/assistant.db-journal`

### Settings Issues

**Problem: Setting not found**
```
404 Not Found: Setting 'xyz' not found
```
**Solution:**
- Check available settings: `curl http://localhost:8000/api/settings/definitions`
- Verify key spelling and category
- Check if setting is defined in `src/models/config.py`

**Problem: Validation error**
```
400 Bad Request: Value must be between 0.0 and 2.0
```
**Solution:**
- Check setting definition for valid ranges, types, and options
- Use validate endpoint before updating: `POST /api/settings/validate/{key}`

**Problem: Bootstrap setting cannot be updated**
```
403 Forbidden: Bootstrap settings cannot be modified via API
```
**Solution:**
- Bootstrap settings (`DATABASE_URL`, `ENCRYPTION_KEY`) must be set in `.env` file
- Restart application after changing bootstrap settings

### OAuth Token Issues

**Problem: OAuth tokens not refreshing**
```
Token expired and refresh failed
```
**Solution:**
- Check that credentials file exists and is valid
- Verify OAuth app credentials (client ID/secret)
- Re-run OAuth flow: Visit `/auth/{service}/login` endpoint
- Check encrypted credentials: Query `service_credentials` table

**Problem: Invalid OAuth scopes**
```
Insufficient permissions: Missing required scopes
```
**Solution:**
- Verify all required scopes are configured in OAuth app
- Re-authorize the application with correct scopes
- Check scope definitions in Settings API

### Encryption Issues

**Problem: Cannot decrypt credentials**
```
cryptography.fernet.InvalidToken
```
**Solution:**
- Verify `ENCRYPTION_KEY` in `.env` matches the key used to encrypt data
- If key is lost, you must delete encrypted credentials and re-authenticate
- Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### Connection Issues

**Problem: Integration API calls failing**
```
Connection timeout / Connection refused
```
**Solution:**
- Check firewall settings for outbound HTTPS (port 443)
- Verify API endpoints are accessible: `curl https://api.notion.com/v1/users`
- Check service status pages
- Verify rate limits haven't been exceeded
- Review proxy settings if behind corporate firewall

### CORS Issues

**Problem: CORS errors in browser console**
```
Access-Control-Allow-Origin header is missing
```
**Solution:**
- Add your frontend origin to `CORS_ORIGINS` environment variable
- Format: `CORS_ORIGINS=http://localhost:3000,https://app.example.com`
- Restart application after changing `CORS_ORIGINS`
- Check browser console for actual origin being requested

### Logging and Debugging

**Enable debug logging:**
```bash
# Via Settings API
curl -X PUT http://localhost:8000/api/settings/logging.level \
  -H "Content-Type: application/json" \
  -d '{"value": "DEBUG"}'

# Or via environment variable
LOG_LEVEL=DEBUG python -m src.main
```

**Check application logs:**
```bash
# View logs
tail -f logs/assistant.log

# Search for errors
grep ERROR logs/assistant.log

# Filter by category
grep "settings" logs/assistant.log
```

## Next Steps

See the [Integration Guides](../integrations/index.md) for detailed setup instructions for each service.

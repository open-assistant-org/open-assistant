# Solution Architecture

This document describes the technology stack, frameworks, and tools used to build Open Assistant.

## Technology Stack Overview

```mermaid
graph TB
    subgraph "Frontend"
        UI[Web UI]
        VanillaJS[Vanilla JavaScript]
        HTML5[HTML5]
        CSS3[CSS3]
        Fetch[Fetch API]
        WS[WebSocket Client]
    end

    subgraph "Backend"
        API[REST API]
        FastAPI[FastAPI 0.104+]
        Uvicorn[Uvicorn ASGI]
        Pydantic[Pydantic V2]
    end

    subgraph "Data Layer"
        DB[Database]
        SQLite[SQLite 3]
        DBManager[DatabaseManager]
    end

    subgraph "Task Management"
        Scheduler[Task Scheduler]
        APS[APScheduler 3.10]
        AsyncIO[AsyncIO]
    end

    subgraph "External APIs"
        Google[Google APIs]
        Microsoft[Microsoft Graph]
        NotionAPI[Notion API]
        WebDAV[WebDAV Client]
    end

    UI --> VanillaJS
    UI --> HTML5
    UI --> CSS3
    VanillaJS --> Fetch
    VanillaJS --> WS

    API --> FastAPI
    FastAPI --> Uvicorn
    FastAPI --> Pydantic

    DB --> SQLite
    DB --> DBManager

    Scheduler --> APS
    Scheduler --> AsyncIO

    FastAPI --> Google
    FastAPI --> Microsoft
    FastAPI --> NotionAPI
    FastAPI --> WebDAV
```

## Backend Framework

### FastAPI - Core Web Framework

```mermaid
graph LR
    subgraph "FastAPI Application"
        Router[API Router]
        Middleware[Middleware Stack]
        WebSocket[WebSocket Support]
        OpenAPI[OpenAPI/Swagger]
    end

    subgraph "ASGI Server"
        Uvicorn[Uvicorn]
        Workers[Worker Processes]
    end

    subgraph "Features"
        Async[Async/Await]
        Validation[Request Validation]
        Docs[Auto Documentation]
        CORS[CORS Support]
    end

    Router --> Middleware
    Middleware --> WebSocket
    Middleware --> OpenAPI

    Uvicorn --> Workers
    Workers --> Router

    Router --> Async
    Router --> Validation
    Router --> Docs
    Router --> CORS
```

## Frontend Framework

### Vanilla JavaScript - UI Framework

**Deployment Model**: Static HTML, CSS, and JavaScript files served directly by FastAPI via `StaticFiles` middleware. No build process required.

```mermaid
graph TB
    subgraph "Static Files"
        HTML[HTML Files]
        CSS[CSS Files]
        JS[JavaScript Files]
        StaticDir[src/ui/static/]
    end

    subgraph "Runtime"
        FastAPI[FastAPI Server]
        StaticMiddleware[StaticFiles Middleware]
        API[API Endpoints]
    end

    HTML --> StaticDir
    CSS --> StaticDir
    JS --> StaticDir

    StaticDir --> StaticMiddleware
    StaticMiddleware --> FastAPI
    API --> FastAPI

    Browser[Browser] -->|/| StaticMiddleware
    Browser -->|/api/*| API

    subgraph "JavaScript Architecture"
        APIClient[API Client Class]
        ToastManager[Toast Manager]
        Storage[LocalStorage Utils]
        DOMUtils[DOM Utilities]
    end

    subgraph "State Management"
        LocalState[Local Variables]
        LocalStorageState[LocalStorage]
        DOMState[DOM as State]
    end

    subgraph "API Communication"
        FetchAPI[Fetch API]
        WSClient[WebSocket Client]
        ErrorHandling[Error Handling]
    end

    subgraph "UI Features"
        Navigation[Navigation Bar]
        Modals[Modal Dialogs]
        Toasts[Toast Notifications]
        Tabs[Tab Interface]
    end

    JS --> APIClient
    JS --> ToastManager
    APIClient --> FetchAPI
    LocalState --> LocalStorageState
    LocalState --> DOMState
```

**Key Files**:
```
src/ui/static/
├── index.html          # Chat UI
├── settings.html       # Settings page
├── monitoring.html     # Monitoring dashboard
├── css/
│   ├── common.css      # Shared styles
│   ├── chat.css        # Chat-specific styles
│   └── settings.css    # Settings styles
└── js/
    ├── common.js       # Shared utilities (API client, toast, etc.)
    ├── chat.js         # Chat functionality
    └── settings.js     # Settings management
```


## Database

### SQLite - Development & Single-User

```mermaid
graph TB
    subgraph "SQLite Configuration"
        File[(SQLite File)]
        WAL[WAL Mode]
        Pragma[Pragma Settings]
    end

    subgraph "Features"
        Embedded[Embedded Database]
        NoServer[No Server Required]
        Atomic[Atomic Transactions]
        Reliable[Reliable & Proven]
    end

    File --> WAL
    File --> Pragma

    File --> Embedded
    File --> NoServer
    File --> Atomic
    File --> Reliable
```

**Why SQLite**:
- Zero configuration
- Single file database
- Perfect for single-user deployments
- No separate database server needed
- Reliable and battle-tested
- Supports full SQL

**Configuration**:
```python
# SQLite with WAL mode
DATABASE_URL = "sqlite:///data/assistant.db"

# Pragma settings
PRAGMA journal_mode=WAL
PRAGMA synchronous=NORMAL
PRAGMA temp_store=MEMORY
PRAGMA mmap_size=30000000000
```


## Database Access - Raw SQLite3 via DatabaseManager

The application uses raw `sqlite3` via `DatabaseManager` — no ORM layer.

```mermaid
graph LR
    subgraph "Application"
        Repos[Repositories]
        DBManager[DatabaseManager]
    end

    subgraph "SQLite3"
        Connection[sqlite3 Connection]
        WAL[WAL Mode]
        Migrations[SQL Migration Files]
    end

    subgraph "Database"
        SQLite[(SQLite)]
    end

    Repos --> DBManager
    DBManager --> Connection
    Connection --> WAL
    DBManager --> Migrations

    Connection --> SQLite
```

## Task Scheduling - APScheduler

```mermaid
graph TB
    subgraph "APScheduler"
        Scheduler[Scheduler Instance]
        JobStore[(Job Store)]
        Executor[Job Executor]
        Triggers[Triggers]
    end

    subgraph "Job Types"
        Cron[Cron Jobs]
        Interval[Interval Jobs]
        Date[Date Jobs]
    end

    subgraph "Storage"
        Memory[In-Memory]
        SQLiteStore[(SQLite Store)]
    end

    Scheduler --> JobStore
    Scheduler --> Executor
    Scheduler --> Triggers

    Triggers --> Cron
    Triggers --> Interval
    Triggers --> Date

    JobStore --> Memory
    JobStore --> SQLiteStore
```

**Configuration**:
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///data/jobs.db')
}

scheduler = AsyncIOScheduler(jobstores=jobstores)
```

## External API Integrations

### Google APIs (Gmail, Calendar)

```mermaid
graph LR
    subgraph "Google Client"
        Auth[OAuth2 Client]
        Gmail[Gmail API]
        Calendar[Calendar API]
    end

    subgraph "Authentication"
        Credentials[Credentials File]
        Token[Token Storage]
        Refresh[Auto Refresh]
    end

    Auth --> Credentials
    Auth --> Token
    Auth --> Refresh

    Auth --> Gmail
    Auth --> Calendar
```

**Library**: `google-api-python-client`

**Dependencies**:
```python
google-api-python-client==2.108.0
google-auth-httplib2==0.1.1
google-auth-oauthlib==1.1.0
```

### Microsoft Graph API (Outlook, OneDrive, Calendar)

```mermaid
graph LR
    subgraph "MSAL Client"
        Auth[MSAL Authentication]
        Acquire[Acquire Token]
        Cache[Token Cache]
    end

    subgraph "Microsoft Graph"
        Mail[Mail API]
        CalendarAPI[Calendar API]
        Files[Files API]
    end

    Auth --> Acquire
    Acquire --> Cache

    Cache --> Mail
    Cache --> CalendarAPI
    Cache --> Files
```

**Library**: `msal` (Microsoft Authentication Library)

**Dependencies**:
```python
msal==1.25.0
requests==2.31.0
```

### Notion API

```mermaid
graph LR
    subgraph "Notion Client"
        Client[Notion Client]
        Auth[API Token Auth]
    end

    subgraph "Notion Resources"
        Pages[Pages API]
        Databases[Databases API]
        Blocks[Blocks API]
        Search[Search API]
    end

    Client --> Auth

    Auth --> Pages
    Auth --> Databases
    Auth --> Blocks
    Auth --> Search
```

**Library**: `notion-client`

**Dependencies**:
```python
notion-client==2.2.1
```

### Nextcloud (WebDAV)

```mermaid
graph LR
    subgraph "WebDAV Client"
        Client[WebDAV Client]
        Auth[Basic Auth]
    end

    subgraph "Operations"
        List[List Files]
        Download[Download]
        Upload[Upload]
        Delete[Delete]
    end

    Client --> Auth

    Auth --> List
    Auth --> Download
    Auth --> Upload
    Auth --> Delete
```

**Library**: `webdavclient3`

**Dependencies**:
```python
webdavclient3==3.14.6
```

## Security & Encryption

### Cryptography - Fernet Encryption

```mermaid
graph TB
    subgraph "Encryption Flow"
        PlainText[Plain Text Credentials]
        Key[Encryption Key]
        Fernet[Fernet Cipher]
        Encrypted[Encrypted Data]
    end

    subgraph "Storage"
        DB[(Database)]
        EnvVar[Environment Variable]
    end

    PlainText --> Fernet
    Key --> Fernet
    Fernet --> Encrypted
    Encrypted --> DB

    Key -.Stored in.-> EnvVar
```

**Library**: `cryptography`

**Dependencies**:
```python
cryptography>=42.0.0
```

**Usage**:
```python
from cryptography.fernet import Fernet

# Generate key (once)
key = Fernet.generate_key()

# Encrypt
cipher = Fernet(key)
encrypted = cipher.encrypt(b"sensitive data")

# Decrypt
decrypted = cipher.decrypt(encrypted)
```

## Configuration Management

### PyYAML + Pydantic

```mermaid
graph LR
    subgraph "Configuration Sources"
        YAMLFile[config.yaml]
        EnvFile[.env]
        EnvVars[Environment Variables]
    end

    subgraph "Parser"
        PyYAML[PyYAML]
        Pydantic[Pydantic Settings]
    end

    subgraph "Application"
        Config[Config Object]
    end

    YAMLFile --> PyYAML
    EnvFile --> Pydantic
    EnvVars --> Pydantic

    PyYAML --> Config
    Pydantic --> Config
```

**Libraries**:
- `pyyaml` - YAML parsing
- `pydantic` - Configuration validation
- `python-dotenv` - Environment file loading

**Dependencies**:
```python
pyyaml==6.0.1
python-dotenv==1.0.0
pydantic-settings==2.1.0
```

## Communication Protocols

### HTTP/REST

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant Agent
    participant Database

    Client->>FastAPI: POST /api/v1/messages
    FastAPI->>FastAPI: Validate request
    FastAPI->>Agent: Process message
    Agent->>Database: Store data
    Database-->>Agent: Success
    Agent-->>FastAPI: Result
    FastAPI-->>Client: JSON Response
```

**Features**:
- RESTful endpoints
- JSON request/response
- HTTP status codes
- Request validation
- Auto-generated OpenAPI docs

### WebSocket

WebSocket support is used by the Slack integration (Slack Socket Mode), not as a general FastAPI feature. The main API uses polling or server-sent events for real-time updates.

**Library**: Built into FastAPI

**Usage**:
```python
from fastapi import WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_json()
        await websocket.send_json({"type": "update", "data": data})
```

## Logging

### Structured Logging

```mermaid
graph TB
    subgraph "Application Logs"
        Logger[Python Logger]
        Formatter[Formatter]
    end

    subgraph "Log Destinations"
        File[Log Files]
        Console[Console/Stdout]
        Syslog[Syslog]
    end

    subgraph "Log Rotation"
        RotatingHandler[Rotating File Handler]
        TimedHandler[Timed Rotating Handler]
    end

    Logger --> Formatter
    Formatter --> File
    Formatter --> Console
    Formatter --> Syslog

    File --> RotatingHandler
    File --> TimedHandler
```

**Python Logging Configuration**:
```python
import logging
from logging.handlers import TimedRotatingFileHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        TimedRotatingFileHandler(
            'logs/app.log',
            when='midnight',
            interval=1,
            backupCount=30  # Keep 30 days
        ),
        logging.StreamHandler()
    ]
)
```

## Development Tools

### Code Quality

```mermaid
graph LR
    subgraph "Linting"
        Ruff[Ruff]
        MyPy[MyPy]
    end

    subgraph "Formatting"
        Black[Black]
    end

    subgraph "Pre-commit"
        Hooks[Git Hooks]
    end

    Ruff --> Hooks
    MyPy --> Hooks
    Black --> Hooks
```

**Web Capabilities**:
```python
# Web browsing and search
playwright==1.40.0    # Browser automation (Apache 2.0 - Free)
brave-search==1.0.0   # Web search API (optional, has free tier)
# or duckduckgo-search==3.9.0  # Alternative web search
```

**Development Dependencies**:
```python
# Development tools
ruff==0.1.6           # Fast Python linter
black==23.11.0        # Code formatter
mypy==1.7.1           # Type checker
pre-commit==3.5.0     # Git hooks framework
```

## Build and Deployment

### Docker

```mermaid
graph TB
    subgraph "Build Process"
        Dockerfile[Dockerfile]
        BaseImage[Python 3.11-slim]
        Dependencies[Install Dependencies]
        AppCode[Copy Application]
        Build[Docker Build]
    end

    subgraph "Image"
        Image[open-assistant:latest]
    end

    subgraph "Registry"
        Local[Local Registry]
        Remote[Docker Hub / GHCR]
    end

    Dockerfile --> BaseImage
    BaseImage --> Dependencies
    Dependencies --> AppCode
    AppCode --> Build
    Build --> Image

    Image --> Local
    Image --> Remote
```

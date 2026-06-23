# Software Architecture

This document describes the internal software design, components, and their interactions within the Open Assistant application.

## Component Overview

```mermaid
graph TB
    subgraph "Presentation Layer"
        WebUI[Web UI<br/>Vanilla JS/HTML/CSS]
        WhatsApp[WhatsApp Interface<br/>wacli Handler]
    end

    subgraph "API Layer"
        REST[REST API<br/>FastAPI Routes]
        Middleware[Middleware Stack]
    end

    subgraph "Business Logic Layer"
        MessageHandler[MessageHandler<br/>Orchestration & LLM Loop]
        ToolExecutor[ToolExecutor<br/>Tool Routing]
        Agents[Specialized Agents<br/>DB-stored definitions]
    end

    subgraph "Integration Layer"
        ServiceClients[Service Clients]
        AuthManager[Auth Manager<br/>OAuth & Tokens]
    end

    subgraph "Data Layer"
        DBManager[Database Manager]
        Migrations[Migration System]
    end

    WebUI --> REST
    WhatsApp --> REST
    REST --> Middleware
    Middleware --> MessageHandler

    MessageHandler --> ToolExecutor
    MessageHandler --> Agents
    ToolExecutor --> ServiceClients
    Agents --> ServiceClients

    ServiceClients --> AuthManager
    MessageHandler --> DBManager
    ToolExecutor --> DBManager
    DBManager --> Migrations
```

## Layered Architecture

```mermaid
graph TD
    subgraph "Layer 1: Presentation"
        UI[User Interfaces]
    end

    subgraph "Layer 2: API"
        API[HTTP API]
    end

    subgraph "Layer 3: Business Logic"
        Agents[Agents & Orchestration]
    end

    subgraph "Layer 4: Integration"
        Services[External Service Clients]
    end

    subgraph "Layer 5: Data"
        Data[Database & Storage]
    end

    UI --> API
    API --> Agents
    Agents --> Services
    Agents --> Data
    Services --> Data
```

## Core Components

### MessageHandler (Core Orchestration)

The central orchestrator that manages all LLM interactions and tool execution.

```mermaid
stateDiagram-v2
    [*] --> Idle

    Idle --> ReceiveRequest: User request arrives
    ReceiveRequest --> GetConversation: Get or create conversation
    GetConversation --> StoreMessage: Store user message

    StoreMessage --> LoadContext: Load memory, prompts, history
    LoadContext --> SelectAgents: Match intent keywords

    SelectAgents --> BuildPrompt: Build system prompt
    BuildPrompt --> GetTools: Get tools from selected agents

    GetTools --> PlanCheck: Check if planning needed
    PlanCheck --> ConversationLoop: Execute LLM loop

    ConversationLoop --> ToolCall: LLM requests tool
    ToolCall --> ExecuteTool: ToolExecutor runs tool
    ExecuteTool --> ConversationLoop: Continue with result

    ConversationLoop --> FinalResponse: LLM returns text
    FinalResponse --> StoreResponse: Save assistant message
    StoreResponse --> Idle: Complete
```

**Responsibilities**:
- Conversation context management
- Agent selection via intent matching
- System prompt construction
- LLM conversation loop execution with tool calling
- Stuck detection and recovery
- Multimodal support (image handling)

### Agent Definitions & Tool Execution

Agents are data-driven configurations stored in the database. Each agent has:
- **Role**: A one-line description of its specialty
- **Goal**: What it aims to achieve
- **Backstory**: Detailed system prompt/instructions
- **Tools**: List of tools it can use
- **Intent Keywords**: Words that trigger this agent
- **Priority**: Higher priority agents are selected first

```mermaid
classDiagram
    class AgentDefinition {
        +name: str
        +display_name: str
        +role: str
        +goal: str
        +backstory: str
        +tools: List[str]
        +enabled: bool
        +priority: int
        +intent_keywords: List[str]
    }

    class AgentRegistry {
        +get_all_agents()
        +get_enabled_agents()
        +update_agent()
        +assign_tool_to_agent()
    }

    class ToolExecutor {
        +execute(tool_name, args)
    }

    AgentRegistry --> AgentDefinition
    ToolExecutor --> Services
```

#### Tool Execution Flow

```mermaid
sequenceDiagram
    participant LLM
    participant MessageHandler
    participant ToolExecutor
    participant Service as Service Layer
    participant API as External API

    LLM-->>MessageHandler: Tool call request
    MessageHandler->>ToolExecutor: execute(tool_name, args)

    ToolExecutor->>Service: Call service method
    Service->>API: External API call
    API-->>Service: Response
    Service-->>ToolExecutor: Processed result

    ToolExecutor-->>MessageHandler: Tool result
    MessageHandler->>LLM: Continue with result
```

### Service Integration Layer

#### Authentication Manager

The auth manager handles credential storage, token refresh, and encryption:

- Credentials are encrypted at rest using Fernet encryption
- OAuth tokens are automatically refreshed when expired
- Token caching reduces API calls to auth providers
- Each service has its own authentication strategy (OAuth2, API keys, etc.)

```mermaid
graph TB
    Auth[Auth Manager] --> TokenStore[Token Store]
    Auth --> TokenRefresh[Token Refresh]
    Auth --> Encryption[Encryption Service]

    TokenStore --> DB[(Encrypted DB)]
    TokenRefresh --> GoogleOAuth[Google OAuth2]
    TokenRefresh --> MicrosoftOAuth[Microsoft OAuth]
    TokenRefresh --> GenericAPI[API Key Auth]
```

#### Service Client Pattern

Each external service (email, calendar, files, etc.) has a dedicated client:

1. Client requests credentials from Auth Manager
2. Client checks if token is expired and refreshes if needed
3. Client makes API request with current credentials
4. Client handles errors (rate limits, auth failures) with retry logic

### Data Access Layer

#### Database Manager

The database layer uses raw SQLite with a repository pattern:

```mermaid
graph TB
    DBManager[Database Manager]
    Repositories[Repositories]
    Connection[SQLite Connection]

    DBManager --> Repositories
    Repositories --> Conversations[Conversations]
    Repositories --> Messages[Messages]
    Repositories --> Agents[Agents]
    Repositories --> Tasks[Tasks]
    Repositories --> Settings[Settings]

    Conversations --> Connection
    Messages --> Connection
    Connection --> WAL[WAL Mode]
```

**Key characteristics**:
- WAL mode for better concurrency
- Repository pattern for clean data access
- Automatic migrations on startup
- Encrypted credential storage

### API Layer

The REST API is built with FastAPI and organized into route modules:

```mermaid
graph TB
    FastAPI[FastAPI App]
    Routers[Routers]

    FastAPI --> Routers
    Routers --> Chat[chat]
    Routers --> Conversations[conversations]
    Routers --> Settings[settings]
    Routers --> Agents[agents]
    Routers --> Cron[cron-jobs]
    Routers --> Monitoring[monitoring]
```

**Middleware includes**:
- CORS handling
- Request logging
- Error handling

## Request Flow Patterns

### Simple Request Flow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant MH as MessageHandler
    participant LLM
    participant TE as ToolExecutor
    participant Service
    participant DB

    User->>API: "Find emails about budget"
    API->>MH: handle_message()
    MH->>DB: Get/create conversation
    MH->>MH: Load context + select agents
    MH->>LLM: complete_with_tools()
    LLM-->>MH: Tool call
    MH->>TE: execute tool
    TE->>Service: Query service
    Service-->>TE: Results
    TE-->>MH: Formatted results
    MH->>LLM: Continue with results
    LLM-->>MH: Final response
    MH->>DB: Store response
    MH-->>API: Response
    API-->>User: Natural language response
```

### Complex Multi-Step Flow

For complex requests, the LLM loop executes iteratively:

```mermaid
sequenceDiagram
    participant User
    participant MH as MessageHandler
    participant LLM
    participant TE as ToolExecutor

    User->>MH: "Summarize emails and save to Notion"
    MH->>MH: Load context + select agents
    MH->>LLM: complete_with_tools()

    loop Until final response
        LLM-->>MH: Tool call
        MH->>TE: Execute tool
        TE-->>MH: Result
        MH->>LLM: Continue with result
    end

    LLM-->>MH: Final response
    MH-->>User: Summary with link
```

### Error Handling Flow

Tool execution errors are caught and returned as structured failure results. Error recovery varies by component:

```mermaid
flowchart TD
    Start[Execute Task] --> Try{Try}
    Try -->|Success| Store[Store Result]
    Try -->|Error| Fail[Return Error Result]
    Store --> Success[Return Success]
    Fail --> Log[Log Error]
    Log --> Notify[Notify User]
    Notify --> ReturnError[Return Formatted Error]
```

**Per-component behavior**:
- **Brave Search**: Retries once on HTTP 429 (rate limit) with `Retry-After` backoff, capped at 10s
- **Groq LLM**: Retries once on `tool_use_failed` with a format nudge
- **All other tools**: Errors are caught, logged, and returned as failure results without retry

No structured error classification (Transient/Auth/RateLimit/Permanent) or exponential backoff retry system is implemented at the tool layer.

## Task Scheduling

### Cron Job Lifecycle

Jobs go through a lifecycle of scheduling, execution, and tracking:

```mermaid
stateDiagram-v2
    [*] --> Created: User creates job

    Created --> Scheduled: APScheduler picks up

    Scheduled --> Pending: Execution time reached
    Pending --> Running: Job starts

    Running --> Completed: Success
    Running --> Failed: Error
    Running --> Timeout: Exceeded time limit

    Completed --> Scheduled: Calculate next run
    Failed --> Retry: Recoverable error
    Failed --> Scheduled: Non-recoverable

    Retry --> Running: Retry attempt
    Retry --> Scheduled: Max retries exceeded

    Scheduled --> [*]: User disables (skipped at execution)
    Scheduled --> [*]: User deletes
```

### Job Execution

Scheduled jobs execute through the APScheduler integration:

1. Scheduler triggers job at scheduled time
2. System creates execution record
3. Job action is performed via agent tool execution
4. Result or error is recorded
5. Job state is updated (last run, next run)

## Configuration Management

Configuration follows a priority chain:

```
Database Settings > Environment Variables > Code Defaults
```

**Key aspects**:
- Bootstrap settings (database URL, encryption key) must come from environment variables — they cannot be stored in the database
- Most settings can be managed via the Settings UI
- Credentials are encrypted at rest
- Settings changes take effect immediately (no restart needed for most)
- `.env` file values are loaded as environment variables — they are not a separate config layer

## Observability

### Logging

All application components log through a centralized logger:

- **API Layer**: Request/response logging
- **Business Logic**: Decision and routing logs
- **Agents**: Operation and result logs
- **Services**: API call and response logs
- **Database**: Error logging only

Logs are written to files with daily rotation.

### Monitoring

The monitoring system tracks:
- System health (API, database, external services)
- Job execution history
- Conversation metrics
- Service connection status

## Design Patterns

### Key Patterns

1. **Repository Pattern**: Clean data access abstraction
2. **Registry Pattern**: Centralized management of agent and tool definitions
3. **Strategy Pattern**: Different authentication approaches per service
4. **Dependency Injection**: FastAPI dependencies for testability
5. **Data-Driven Configuration**: Agents stored in database, not code

### SOLID Principles

- **Single Responsibility**: Each service handles one integration domain
- **Open/Closed**: Easy to add new agents/tools
- **Interface Segregation**: Small, focused tool definitions
- **Dependency Inversion**: Services depend on abstractions

## Extension Points

### Adding a New Service Integration

1. Create service client in `src/integrations/<service>/`
2. Implement authentication (OAuth, API key, etc.)
3. Add service methods for each operation
4. Register tools in `src/core/tools/definitions.py`
5. Add tool routing in `src/core/tools/executor.py`
6. Add settings and configuration
7. Update Settings UI if needed

### Adding a New Agent

1. Add agent definition to database seed
2. Assign relevant tools to the agent
3. Configure intent keywords for selection
4. Agent becomes available immediately (no code change needed)

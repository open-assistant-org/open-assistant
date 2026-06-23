# Open Assistant Documentation

Welcome to the Open Assistant documentation. This documentation covers architecture, setup, and integrations.

## Quick Links

### Getting Started
- [Configuration Guide](setup/configuration.md) - Configure services and credentials
- [Development Setup](setup/development.md) - Set up development environment
- [Development Checklist](development-checklist.md) - Pre-flight checks before deploying

### Architecture
- Architecture Overview
  - [System Architecture](architecture/system-architecture.md) - Deployment, containers, infrastructure
  - [Solution Architecture](architecture/solution-architecture.md) - Technology stack and frameworks
  - [Software Architecture](architecture/software-architecture.md) - Application design and components
  - [Agent Architecture](architecture/agents.md) - Multi-agent system
- [Database Schema](architecture/database-schema.md) - Database structure and tables
- [Capabilities](architecture/capabilities.md) - Implemented and planned capabilities

### Integrations (by Platform)
- [Google Platform](integrations/google.md) - Gmail and Google Calendar
- [Google Ads](integrations/google_ads.md) - Google Ads campaign data
- [Google News](integrations/google_news.md) - News search
- [Microsoft Platform](integrations/microsoft.md) - Outlook, OneDrive, and Outlook Calendar
- [Google Navigator](integrations/google_navigator.md) - Places, Directions, and Geocoding
- [Notion](integrations/notion.md) - Note-taking and knowledge management
- [Nextcloud](integrations/nextcloud.md) - Self-hosted file storage
- [Browser Automation](integrations/browser.md) - Web browsing with Playwright
- [WhatsApp Messaging](integrations/whatsapp.md) - WhatsApp integration (text, voice, images)
- [Whisper Transcription](integrations/whisper.md) - Voice message transcription via OpenAI Whisper
- [Mistral OCR](integrations/mistral_ocr.md) - PDF text extraction
- [Brave Search](integrations/brave.md) - Web search
- [Slack](integrations/slack.md) - Slack messaging
- [Toggl](integrations/toggl.md) - Time tracking
- [LLM Providers](integrations/llm-providers.md) - LLM configuration

## Documentation Structure

```
docs/
├── README.md                              # This file
├── development-checklist.md                # Pre-flight checks before deploying
├── architecture/
│   ├── system-architecture.md             # Deployment and infrastructure
│   ├── solution-architecture.md           # Technology stack and frameworks
│   ├── software-architecture.md            # Application design and components
│   ├── agents.md                         # Multi-agent system
│   ├── database-schema.md                 # Database tables and relationships
│   └── capabilities.md                    # Implemented and planned capabilities
├── integrations/
│   ├── google.md                         # Google platform (Gmail, Calendar)
│   ├── google_ads.md                     # Google Ads campaign data
│   ├── google_news.md                    # Google News search
│   ├── microsoft.md                      # Microsoft platform (Outlook, OneDrive, Calendar)
│   ├── google_navigator.md               # Google Places, Directions, Geocoding
│   ├── notion.md                         # Notion integration
│   ├── nextcloud.md                      # Nextcloud file storage
│   ├── browser.md                        # Browser automation with Playwright
│   ├── whatsapp.md                       # WhatsApp messaging (text, voice, images)
│   ├── whisper.md                        # Voice message transcription (Whisper)
│   ├── mistral_ocr.md                    # Mistral OCR for PDF extraction
│   ├── brave.md                          # Brave Search integration
│   ├── slack.md                          # Slack messaging
│   ├── toggl.md                          # Toggl time tracking
│   └── llm-providers.md                  # LLM provider configuration
└── setup/
    ├── configuration.md                   # Configuration reference
    └── development.md                    # Development environment setup
```

## Contributing to Documentation

**🚨 IMPORTANT**: This project follows documentation-first development.

### Documentation-First Workflow

1. **Before implementing ANY feature**:
   - Document it in relevant `docs/` files
   - Add diagrams (Mermaid)
   - Get user approval
   - THEN implement

2. **When adding new features**:
   - Update architecture docs
   - Add code examples
   - Update API reference if applicable
   - Add troubleshooting notes
   - Keep implementation in sync

3. **Development Guidelines**:
   - Read [`CONTRIBUTING.md`](https://github.com/open-assistant-org/open-assistant/blob/main/CONTRIBUTING.md) - Contribution guidelines
   - Read [Development Setup](setup/development.md) - Environment setup and workflow

## Need Help?

For issues or questions:
1. Check the troubleshooting section in integration guides
2. Review the architecture documentation
3. Open an issue in the repository

## Version Information

Documentation follows the project's tag-based versioning system. Each release tag corresponds to the state of documentation at that time.
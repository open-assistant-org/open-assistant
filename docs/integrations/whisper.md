# Whisper Integration Guide

This guide covers setting up OpenAI Whisper for automatic voice message transcription via WhatsApp.

## Overview

When enabled, Whisper automatically:
1. Transcribes incoming WhatsApp voice messages to text
2. Saves the transcription as a new page in your default Notion database
3. Falls back to uploading a markdown file to Nextcloud if Notion is unavailable
4. Sends you the URL of the saved note directly in the WhatsApp chat

## Prerequisites

- An OpenAI API key (or any OpenAI-compatible endpoint that supports the Whisper API)
- WhatsApp integration configured and connected
- Notion and/or Nextcloud integration configured (for saving transcriptions)

## Setup Steps

### Step 1: Get an OpenAI API Key

1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Click **Create new secret key**
3. Copy the key (starts with `sk-`)

> **Note**: If you already use OpenAI as your LLM provider, you can skip this step — Whisper will fall back to your main LLM API key automatically.

### Step 2: Configure in Settings

1. Go to **Settings > Integrations > Whisper**
2. Enable the **Whisper** toggle
3. Paste your API key in the **API Key** field
4. (Optional) Adjust the **Base URL** if using a compatible third-party endpoint
5. (Optional) Change the **Model** (default: `whisper-1`)
6. Click **Save Settings**

### Step 3: Configure Transcription Storage

Transcriptions are saved automatically. Configure at least one of these:

**Notion (primary)**:
- Go to **Settings > Integrations > Notion**
- Ensure Notion is enabled and connected
- Set a **Database ID** if you want transcriptions in a specific database
- If no database is configured, Notion will use the first accessible page

**Nextcloud (fallback)**:
- Go to **Settings > Integrations > Nextcloud**
- Ensure Nextcloud is enabled and connected
- Transcriptions are saved as markdown files under `/Voice Notes/`

### Step 4: Test

1. Send a voice message to the WhatsApp number linked to your assistant
2. You should receive a reply with a link to the saved transcription
3. The transcribed text also enters the normal chat pipeline, so the assistant can respond to what you said

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `whisper.enabled` | `false` | Enable/disable Whisper transcription |
| `whisper.api_key` | _(empty)_ | OpenAI API key. Falls back to main LLM key if empty |
| `whisper.base_url` | _(empty)_ | Custom API base URL. Leave empty for `https://api.openai.com/v1` |
| `whisper.model` | `whisper-1` | Whisper model to use |

### Environment Variables

These can also be set via environment variables:

```bash
WHISPER_ENABLED=true
WHISPER_API_KEY=sk-...
WHISPER_BASE_URL=          # Leave empty for default OpenAI
WHISPER_MODEL=whisper-1
```

## How It Works

### Voice Message Flow

```
WhatsApp voice message received
    ↓
Node.js bridge downloads audio (base64)
    ↓
Python webhook receives audio + mimetype
    ↓
Check whisper.enabled → skip if disabled
    ↓
Transcribe via Whisper API
    ↓
Save transcription:
    ├─→ Notion: new page in default database → get page URL
    └─→ (fallback) Nextcloud: markdown file in /Voice Notes/ → get file URL
    ↓
Send URL back to user via WhatsApp
    ↓
Transcribed text enters normal chat pipeline
(classifier → conversational LLM or CrewAI action)
```

### Supported Audio Formats

WhatsApp voice messages are typically sent as `audio/ogg; codecs=opus`. The following formats are supported:

| Format | MIME Type | Extension |
|--------|-----------|-----------|
| Ogg/Opus | `audio/ogg` | `.ogg` |
| MP3 | `audio/mpeg` | `.mp3` |
| M4A | `audio/mp4` | `.m4a` |
| WAV | `audio/wav` | `.wav` |
| WebM | `audio/webm` | `.webm` |
| AAC | `audio/aac` | `.aac` |
| AMR | `audio/amr` | `.amr` |

### Transcription Storage

**Notion pages** are created with:
- Title: `Voice Note - YYYY-MM-DD HH:MM`
- Content: The transcription text in markdown, plus any caption from the voice message

**Nextcloud files** (fallback) are created as:
- Path: `/Voice Notes/voice_note_YYYYMMDD_HHMMSS.md`
- Content: Markdown with heading and transcription text

## Other Media Types

In addition to audio, the WhatsApp integration handles other media types. See the [WhatsApp Integration Guide](whatsapp.md#media-support) for full details.

**Images**: Analyzed by the vision LLM to generate a text description, which is embedded in the message for both conversational and action paths. Send an image with a caption like "save this receipt" and the assistant will understand what's in the image.

**Documents (PDF & DOCX)**: Text is automatically extracted and embedded in the message. Send a PDF with "summarize this" and the assistant will have the full document text to work with.

## Compatible Providers

Any OpenAI-compatible API that implements the `/v1/audio/transcriptions` endpoint works. Examples:

| Provider | Base URL | Notes |
|----------|----------|-------|
| OpenAI | _(default, leave empty)_ | Official Whisper API |
| Azure OpenAI | `https://{resource}.openai.azure.com/openai/deployments/{deployment}` | Requires Azure deployment |
| Local Whisper | `http://localhost:8000/v1` | Self-hosted via faster-whisper-server, etc. |

## Troubleshooting

### Transcription Not Working

1. Check that **Whisper is enabled** in Settings > Integrations
2. Verify the API key is set (or that your main LLM key supports Whisper)
3. Check application logs for `[WhatsApp] Audio transcription failed` errors
4. Ensure the WhatsApp bridge is running and connected

### No URL Sent Back

1. Check that Notion or Nextcloud is configured and enabled
2. Look for `[WhatsApp] Notion save failed` or `Nextcloud fallback also failed` in logs
3. Verify your Notion database is accessible to the integration
4. For Nextcloud, verify the credentials and that WebDAV is enabled

### Poor Transcription Quality

- Whisper works best with clear audio and minimal background noise
- Very short voice messages (< 1 second) may not transcribe well
- Try specifying a language hint if transcriptions are in the wrong language
- Consider using a larger/newer Whisper model if available

### API Errors

**Error: `invalid_api_key`**
- Verify the API key in Settings > Integrations > Whisper
- Ensure the key has access to the audio/transcriptions endpoint

**Error: `model_not_found`**
- Check the model name is correct (default: `whisper-1`)
- If using a custom provider, verify which models are available

**Error: Audio transcription failed**
- The audio file may be corrupted or in an unsupported format
- Check the MIME type in the logs
- WhatsApp occasionally sends very short or empty audio clips

## Pricing

OpenAI Whisper API pricing (as of 2025):
- `whisper-1`: $0.006 per minute of audio
- Typical WhatsApp voice message (30 seconds): ~$0.003

---

**Last Updated**: February 2026

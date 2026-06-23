# Mistral OCR Integration

This guide covers setting up Mistral AI OCR for extracting text from PDF documents.

## Overview

Mistral OCR provides high-quality text extraction from PDFs, including scanned documents. When enabled, the assistant can process PDF documents sent via WhatsApp, Slack, or uploaded directly.

**Capabilities**:
- Extract text from PDFs (including scanned/image-based PDFs)
- No character limit on extracted text
- Configurable model and API endpoint

## Prerequisites

- Mistral AI account (or any OpenAI-compatible API endpoint)
- PDF documents to process

## Step 1: Get an API Key

### Option A: Mistral AI (Recommended)

1. Go to [https://console.mistral.ai/](https://console.mistral.ai/)
2. Sign up or log in
3. Go to **API Keys**
4. Click **Create new key**
5. Copy the API key

### Option B: Azure OpenAI (with Mistral model)

If using Azure OpenAI with a Mistral deployment:
- Set the **Base URL** to your Azure endpoint
- Use your Azure API key

### Option C: Self-hosted Compatible Endpoint

Any OpenAI-compatible API that implements the Mistral OCR endpoint format:
- Set the **Base URL** to your server endpoint
- Ensure it supports the `/v1/ocr` or equivalent endpoint

## Step 2: Configure in Settings

1. Go to **Settings > Integrations > Mistral OCR**
2. Enable the Mistral OCR integration
3. Paste your API key
4. (Optional) Adjust the **Base URL** if using Azure or a custom endpoint
5. (Optional) Set the **Model** (default: `mistral-ocr-latest`)
6. Click **Save**
7. Click **Test Connection** to verify

Or use environment variables:

```bash
MISTRAL_OCR_ENABLED=true
MISTRAL_OCR_API_KEY=your-api-key
MISTRAL_OCR_BASE_URL=           # Leave empty for default Mistral AI
MISTRAL_OCR_MODEL=mistral-ocr-latest
```

## How It Works

### Automatic PDF Processing

When a PDF is sent via WhatsApp or Slack, the assistant automatically:

1. Downloads and processes the PDF using Mistral OCR
2. Extracts the text content
3. Returns the extracted text to you for further use (e.g., summarization, analysis)

You can then ask the assistant to save the result to Notion or Nextcloud separately.

### Example Conversations

```
You: Can you read this invoice? [attaches invoice.pdf]
Assistant: I've extracted the text from the PDF. Here's what it says:
[full extracted text]

You: Summarize this document [attaches report.pdf]
Assistant: [Extracts text, then summarizes the content]
```

### Manual PDF Processing

You can also ask the assistant to process PDFs explicitly:

```
You: Extract all text from the PDF I sent earlier
Assistant: [Returns the extracted text]
```

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `mistral_ocr.enabled` | `false` | Enable/disable Mistral OCR |
| `mistral_ocr.api_key` | _(empty)_ | API key. Falls back to main LLM key if empty |
| `mistral_ocr.base_url` | _(empty)_ | API base URL. Leave empty for Mistral AI |
| `mistral_ocr.model` | `mistral-ocr-latest` | OCR model to use |

## Compatible Providers

Any OpenAI-compatible API that implements the Mistral OCR endpoint format works:

| Provider | Base URL | Notes |
|----------|----------|-------|
| Mistral AI | _(default)_ | Official Mistral OCR API |
| Azure OpenAI | `https://{resource}.openai.azure.com/openai/deployments/{deployment}/` | Requires Mistral model deployment |
| Local server | `http://localhost:8000/v1` | Self-hosted compatible server |

## Troubleshooting

### "Mistral OCR connection failed"

- Verify the API key is correct
- Check that you have billing set up on Mistral AI (free tier has limits)
- If using Azure, verify the endpoint URL is correct

### "No API key configured"

- Set `mistral_ocr.api_key` in Settings
- Or ensure your main LLM API key is set (Mistral OCR falls back to it)

### PDF text extraction returns empty

- The PDF may be a scanned image without text
- Mistral OCR should handle most scanned PDFs, but some low-quality scans may fail
- Try a higher quality scan if available

### Model not found error

- Verify the model name is correct (`mistral-ocr-latest`)
- If using a custom provider, check which models are available

## Rate Limits

Mistral AI OCR pricing is based on pages processed. Check current pricing at [https://mistral.ai/pricing](https://mistral.ai/pricing).

Azure OpenAI uses standard Azure pricing for the deployed model.

## Security Considerations

- **API Key**: Store securely — it grants access to your Mistral AI quota
- **PDF Content**: PDF files are sent to the Mistral API for processing

## API References

- [Mistral AI OCR Documentation](https://docs.mistral.ai/api/)
- [Mistral OCR API](https://platform.mistral.ai/)
- [Azure OpenAI OCR](https://learn.microsoft.com/en-us/azure/ai-services/mistral)

---

**Last Updated**: March 2026

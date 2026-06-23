# LLM Provider Setup Guide

This guide explains how to obtain API credentials for different LLM providers.

## Table of Contents
- [OpenRouter (Recommended)](#openrouter-recommended)
- [Groq](#groq)
- [Local LLM (Ollama)](#local-llm-ollama)
- [Self-Hosted Inference (vLLM)](#self-hosted-inference-vllm)
- [Ollama vs. vLLM](#ollama-vs-vllm)
- [Auxiliary Models on Local Providers](#auxiliary-models-on-local-providers)

---

## OpenRouter (Recommended)

OpenRouter provides access to multiple LLM models (Claude, GPT-4, Llama, etc.) through a single API.

### Setup Steps

1. **Sign up**: Visit [https://openrouter.ai/](https://openrouter.ai/)
2. **Get API Key**:
   - Log in to your account
   - Go to [Keys](https://openrouter.ai/keys)
   - Click "Create Key"
   - Copy your API key
3. **Configure in Settings**:
   - Provider: `openrouter`
   - API Key: Your OpenRouter API key
   - Model: `anthropic/claude-sonnet-4.6` (or browse available models)
   - Base URL: `https://openrouter.ai/api/v1`
   - Site Name: Your app name (for rankings)
   - Site URL: Your app URL (optional)

### Available Models

Browse all available models at [https://openrouter.ai/models](https://openrouter.ai/models)

Popular choices:
- `anthropic/claude-sonnet-4.6` - Best for complex reasoning
- `anthropic/claude-3.5-sonnet` - Great balance of intelligence and speed
- `openai/gpt-4-turbo` - Great all-around model
- `google/gemini-pro` - Good balance of speed and quality
- `meta-llama/llama-3.1-70b-instruct` - Open source, cost-effective

### Pricing

Pay-as-you-go pricing varies by model. Check current pricing at [https://openrouter.ai/models](https://openrouter.ai/models)

**Benefits**:
- Single API for multiple providers
- No vendor lock-in
- Automatic failover
- Usage tracking

---

## Groq

Fast, affordable inference with Groq's LPU (Language Processing Unit) hardware.

### Setup Steps

1. **Sign up**: Visit [https://console.groq.com/](https://console.groq.com/)
2. **Get API Key**:
   - Log in to your account
   - Go to [API Keys](https://console.groq.com/keys)
   - Click "Create API Key"
   - Copy your API key
3. **Configure in Settings**:
   - Provider: `groq`
   - API Key: Your Groq API key
   - Model: `llama-3.3-70b-versatile` (or browse available models)
   - Base URL: `https://api.groq.com/openai/v1`

### Available Models

- `llama-3.3-70b-versatile` - Fast, long context
- `llama-3.1-8b-instant` - Very fast, cost-effective
- `mixtral-8x7b-32768` - Good balance

Browse all models at [https://console.groq.com/docs/models](https://console.groq.com/docs/models)

### Pricing

Groq offers extremely competitive pricing with fast inference. See [https://groq.com/pricing/](https://groq.com/pricing/)

**Benefits**:
- Extremely fast inference
- Very low latency
- Cost-effective for high-volume use

---

## Local LLM (Ollama)

Run LLM models locally on your machine - no API keys needed!

### Setup Steps

1. **Install Ollama**:
   - Visit [https://ollama.ai/](https://ollama.ai/)
   - Download installer for your OS (Windows, Mac, Linux)
   - Run the installer

2. **Download a model**:
   ```bash
   # Download Llama 3.1 (8B parameters)
   ollama pull llama3.1

   # Or download Mistral
   ollama pull mistral

   # Or download CodeLlama for coding tasks
   ollama pull codellama
   ```

3. **Verify it's running**:
   ```bash
   ollama list
   ```

   Ollama runs on `http://localhost:11434` by default.

4. **Configure in Settings**:
   - Provider: `ollama`
   - Model: `llama3.1` (or your chosen model)
   - Base URL: `http://localhost:11434/v1` (pre-filled automatically)
   - API Key: Leave blank (not required)

### Available Models

Browse models at [https://ollama.ai/library](https://ollama.ai/library)

Popular choices:
- `llama3.1` (8B) - Meta's latest, good balance
- `llama3.1:70b` - More capable but needs 40GB+ RAM
- `mistral` - Fast and efficient
- `codellama` - Specialized for code
- `phi3` - Microsoft's small but capable model

### Hardware Requirements

Model size determines RAM requirements:
- 7-8B models: 8GB RAM minimum
- 13B models: 16GB RAM minimum
- 70B models: 64GB RAM minimum

**GPU Acceleration**: Ollama automatically uses your GPU if available (NVIDIA, AMD, or Apple Silicon).

### Pricing

**Free!** All models run locally on your hardware.

**Pros**:
- Complete privacy (no data leaves your machine)
- No API costs
- No rate limits
- Works offline

**Cons**:
- Requires decent hardware
- Slower than cloud APIs (unless you have a powerful GPU)
- Limited to available local models

---

## Self-Hosted Inference (vLLM)

[vLLM](https://docs.vllm.ai/) is a high-throughput inference and serving engine
for LLMs. It exposes an **OpenAI-compatible API**, so Open Assistant talks to it
exactly like any other OpenAI-style provider — just point it at your server.

vLLM is aimed at production / GPU serving (PagedAttention, continuous batching,
tensor parallelism) rather than easy desktop use. Each server process serves a
**single model**, specified when you launch it.

### Setup Steps

1. **Install vLLM** (requires a CUDA-capable GPU for most models):
   ```bash
   pip install vllm
   ```

2. **Start the OpenAI-compatible server**:
   ```bash
   # Serves the model on http://localhost:8000 by default
   vllm serve mistralai/Mistral-7B-Instruct-v0.2

   # Optional: expose it under a friendly name and require an API key
   vllm serve mistralai/Mistral-7B-Instruct-v0.2 \
     --served-model-name my-model \
     --api-key token-abc123
   ```

   The OpenAI-compatible endpoints live under `http://localhost:8000/v1`.

3. **Configure in Settings**:
   - Provider: `vllm`
   - Model: the model id you launched with (e.g. `mistralai/Mistral-7B-Instruct-v0.2`),
     or the `--served-model-name` if you set one
   - Base URL: `http://localhost:8000/v1` (pre-filled automatically)
   - API Key: Leave blank — **unless** you started vLLM with `--api-key`
     (or the `VLLM_API_KEY` env var), in which case enter that key

### Notes

- **Model name must match.** vLLM only answers requests for the model it is
  serving. The `Model` setting must equal the `--model` argument (or
  `--served-model-name`); an unknown model name returns an error.
- **API key is optional.** By default vLLM does not check for a key. It only
  requires one if you start it with `--api-key`/`VLLM_API_KEY`.
- **Single model per server.** To serve more than one model, run multiple vLLM
  instances on different ports.

### Pricing

**Free!** Like Ollama, vLLM runs on your own hardware — no per-token API costs.

**Pros**:
- High throughput and low latency under concurrent load
- Production-grade serving features (batching, tensor parallelism)
- Complete privacy — data stays on your infrastructure

**Cons**:
- Heavier to set up than Ollama; typically needs a CUDA GPU
- One model per server process
- No built-in model management (you bring your own weights)

---

## Ollama vs. vLLM

Both are OpenAI-compatible local providers, but they target different use cases:

| | **Ollama** | **vLLM** |
|---|---|---|
| Best for | Desktop / personal, easy setup | Production / high-throughput serving |
| Default base URL | `http://localhost:11434/v1` | `http://localhost:8000/v1` |
| Default port | `11434` | `8000` |
| API key | Never required | Optional (`--api-key` / `VLLM_API_KEY`) |
| Models per endpoint | Swaps between pulled models on demand | One model per server process |
| Model management | Built in (`ollama pull` / `ollama list`) | Bring your own weights (HF id or path) |
| Hardware | CPU or GPU (auto-detected) | Typically a CUDA GPU |

**Rule of thumb:** use **Ollama** for the quickest local setup, and **vLLM**
when you need throughput, batching, or are deploying on GPU infrastructure.

---

## Auxiliary Models on Local Providers

Open Assistant lets you pick separate models for some roles — the **Media
Model** (images), **Worker Model** (background tasks), and **Writer Model**
(document composition). These default to the main model when left blank.

For **Ollama** and **vLLM**, these auxiliary settings are **ignored** and the
main model is always used. Both serve a single model per endpoint, so routing a
sub-task to a different model name would either trigger a costly reload (Ollama)
or simply fail (vLLM). If you want a dedicated worker/media/writer model with a
local provider, run a second server (e.g. another vLLM instance on a different
port) and point a `custom` provider at it.

---

## Choosing a Provider

### Use OpenRouter if:
- You want access to multiple models
- You want to try different providers easily
- You want automatic failover

### Use Groq if:
- You need ultra-low latency responses
- You want fast inference at low cost
- You're building high-throughput applications

### Use Ollama if:
- Privacy is critical
- You want to avoid API costs
- You have adequate hardware
- You need offline functionality
- You want the simplest local setup with built-in model management

### Use vLLM if:
- You need high throughput / low latency under concurrent load
- You're serving a model on GPU infrastructure
- You want production-grade serving (batching, tensor parallelism)
- Privacy is critical and you want to avoid API costs

---

## Testing Your Configuration

After configuring any provider:

1. Go to **Settings > LLM**
2. Click **Test Connection**
3. Verify you see a successful response

Common issues:
- **Invalid API Key**: Double-check you copied the entire key
- **Rate Limit**: Wait a moment and try again
- **Insufficient Credits**: Add billing to your provider account
- **Connection Timeout**: Check your internet connection (or that your local Ollama/vLLM server is running)
- **Model Not Found (vLLM)**: The `Model` setting must match the model vLLM was launched with (`--model` / `--served-model-name`)

---

## Security Best Practices

### API Key Security
- Store keys in the Settings UI (encrypted in database)
- Use environment variables for `ENCRYPTION_KEY`
- Never commit API keys to Git
- Never share API keys publicly

### Monitor Usage
- Check your provider's dashboard regularly
- Set up billing alerts
- Rotate API keys periodically

### Local Models (Ollama / vLLM)
- No API key needed (unless vLLM was started with `--api-key`)
- All data stays on your machine
- Best option for sensitive data

---

## Need Help?

- **OpenRouter**: [Documentation](https://openrouter.ai/docs)
- **Groq**: [Documentation](https://console.groq.com/docs)
- **Ollama**: [Documentation](https://ollama.ai/docs)
- **vLLM**: [Documentation](https://docs.vllm.ai/)

---

**Last Updated**: June 2026
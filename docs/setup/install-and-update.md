# Installation & Updates

This page explains what the one-liner installer does, how to update a running instance safely, and what lives inside each volume so you know exactly what data you own.

---

## install.sh — what it does

The one-liner installer is designed to get you from zero to a running assistant in a single command, with no prior Docker experience required.

```bash
curl -fsSL https://raw.githubusercontent.com/open-assistant-org/open-assistant/main/install.sh | bash
```

It runs the following steps in order:

### 1. Prerequisite check
Verifies Docker is present and reachable. On Linux, if Docker is missing and the script is running as root, it auto-installs it via the distribution's package manager or the official `get.docker.com` script. On macOS, it exits early with a link to Docker Desktop.

### 2. Configuration prompts
Asks two things:

- **Application URL** — where the assistant will be reachable (defaults to your local IP and port). Used for OAuth redirects and CORS.
- **LLM provider** — OpenRouter, Anthropic, Groq, or a custom OpenAI-compatible endpoint. After choosing a provider, you pick a model and enter your API key (input is hidden).

No configuration files to edit by hand.

### 3. Generate encryption key
A fresh Fernet key is generated using `python3`, `openssl`, or a throwaway Docker container as a fallback. This key is written to `.env` once and must never change — see [the encryption note below](#encryption-key).

### 4. Write `.env`
A minimal `.env` file is created in the current directory with exactly three variables:

```
DATABASE_URL=sqlite:///data/assistant.db
ENCRYPTION_KEY=<generated>
APP_URL=<your URL>
CORS_ORIGINS=<your URL>
```

All other settings (LLM provider, API keys, integrations) are stored in the database and managed through the Settings UI at `/settings`.

### 5. Start the container
Three host directories are created — `data/`, `logs/`, `tmp/` — and bind-mounted into the container. See [Volume contents](#volume-contents) below for what goes where. The container is started with `--restart unless-stopped`, so it comes back automatically after a reboot.

### 6. Wait for health
Polls `GET /health` every two seconds for up to two minutes.

### 7. Push LLM settings
POSTs your LLM provider/model/key to the settings API so the assistant is ready to use immediately without opening the UI.

### 8. Test the connection
Sends a test request to confirm the LLM is reachable and the key is valid.

---

## update.sh — safe, zero-data-loss updates

```bash
curl -fsSL https://raw.githubusercontent.com/open-assistant-org/open-assistant/main/update.sh | bash
```

Or if you have a local copy:

```bash
bash update.sh
```

The updater never touches your data. It only replaces the container image.

### How it works

1. **Detect the installation** — reads the running `open-assistant` container's bind-mount paths and port binding via `docker inspect`. The install directory and `.env` file are derived automatically; you do not need to supply them.

2. **Pull the new image** — downloads `ghcr.io/open-assistant-org/open-assistant:latest` before stopping anything. If the pull fails (no network, registry issue), the script exits and the running container is left untouched.

3. **Check if an update is available** — compares the running container's image digest against the freshly pulled one. If they match, the script exits cleanly with "already up to date". Set `FORCE_UPDATE=1` to restart anyway.

4. **Replace the container** — stops the old container, removes it, and starts a new one with the identical bind mounts, port, and `.env` file. The window between stop and start is typically under five seconds.

5. **Wait for health** — same polling loop as the installer.

6. **Prune dangling layers** — removes the old image layers to free disk space.

### Rollback

Docker does not automatically keep the previous image tag. If you need to roll back to a specific release, pin the image tag:

```bash
docker stop open-assistant
docker rm open-assistant
docker run -d \
  --name open-assistant \
  --restart unless-stopped \
  -p 8080:8080 \
  -v "$PWD/data:/app/data" \
  -v "$PWD/logs:/app/logs" \
  -v "$PWD/tmp:/app/tmp" \
  --env-file .env \
  -e LOG_LEVEL=INFO \
  -e ENVIRONMENT=production \
  -e WHATSAPP_BRIDGE_PORT=3001 \
  -e WHATSAPP_SESSION_DIR=/app/data/whatsapp_session \
  -e TMP_DIR=/app/tmp \
  ghcr.io/open-assistant-org/open-assistant:<tag>
```

Replace `<tag>` with the release tag you want (e.g. `v1.2.0`). Your data is unaffected.

---

## Volume contents

The installer creates three directories next to your `.env` file and bind-mounts them into the container. Because they are bind mounts on your host, the data is entirely yours — no `docker volume` commands needed to access or back it up.

```
<install dir>/
├── .env          ← bootstrap config (DB URL, encryption key, app URL)
├── data/         ← persistent data (mounted at /app/data)
├── logs/         ← application logs (mounted at /app/logs)
└── tmp/          ← ephemeral scratch space (mounted at /app/tmp)
```

### `data/`

Everything that must survive a container restart or update lives here.

| Path | Contents |
|------|----------|
| `data/assistant.db` | SQLite database — all settings, conversation history, scheduled jobs, audit log |
| `data/whatsapp_session/` | WhatsApp Web session files (keeps you logged in across restarts) |

The database holds the complete state of the assistant: LLM configuration, integration credentials, memory, cron jobs, and OAuth tokens. All sensitive values (API keys, OAuth tokens, passwords) are stored encrypted — see [Encryption key](#encryption-key).

### `logs/`

Structured application logs written by the assistant process. Safe to rotate or clear at any time — the running assistant is unaffected.

### `tmp/`

Ephemeral working files: downloaded attachments, intermediate tool outputs, and large tool results that are offloaded from the LLM context window. This directory can be cleared at any time and will be recreated on the next relevant operation.

---

## Migrating to a new host

Because everything persistent is in `data/`, migration is straightforward:

1. **Copy** your `data/` directory and `.env` file to the new host.
2. **Run the installer** on the new host, but choose **not** to overwrite the existing `.env` when prompted.
3. The assistant starts with all your settings, history, and credentials intact.

Alternatively, after a fresh install on the new host, stop the container, replace the new `data/` with your copy, and restart.

---

## Encryption key

!!! warning "Never change the encryption key after first run"
    All credentials stored in the database — OAuth tokens, API keys, passwords — are encrypted with the Fernet key in `ENCRYPTION_KEY`. If you change this value (or lose it), the assistant cannot decrypt any stored credentials and all integrations will stop working. You would need to re-authenticate every service from scratch.

    The key is generated once by `install.sh` and written to `.env`. Back up your `.env` file alongside your `data/` directory. Together, these two artefacts are everything you need to restore or migrate a running instance.

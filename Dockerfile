# Multi-stage Dockerfile for Open Assistant
# Stage 1: Builder - Install dependencies with uv
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files and source code
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Create virtual environment and install dependencies
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install .

# Stage 2: Runtime - Minimal production image
FROM python:3.11-slim

# Install Node.js, curl, supervisor, and Chromium dependencies for Puppeteer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        supervisor \
        dumb-init \
        chromium \
        chromium-sandbox \
        fonts-liberation \
        fonts-dejavu \
        fontconfig \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libwayland-client0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        xdg-utils && \
    fc-cache -f && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Install WhatsApp bridge Node.js dependencies (package-lock.json is committed so
# npm ci gives a reproducible install — no silent dep upgrades between builds).
WORKDIR /app/src/integrations/whatsapp/bridge
COPY src/integrations/whatsapp/bridge/package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
WORKDIR /app

# Create necessary directories
RUN mkdir -p data logs tmp && \
    chmod 755 data logs tmp

# Install Playwright's Chromium browser binary (must run as root, before USER switch)
# The system Chromium libs are already installed above; this downloads the exact
# Chromium revision that Playwright is tested against.
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers
RUN . /app/.venv/bin/activate && \
    playwright install chromium && \
    chmod -R o+rx /app/.playwright-browsers

# Install patchright's Chromium binary — required by scrapling's StealthyFetcher
# (stealth mode) and PlayWrightFetcher (dynamic mode).
# mkdir -p ensures the target directory exists before chmod, since patchright may
# not create it when PATCHRIGHT_BROWSERS_PATH points to an empty/new path.
ENV PATCHRIGHT_BROWSERS_PATH=/app/.patchright-browsers
RUN mkdir -p /app/.patchright-browsers && \
    . /app/.venv/bin/activate && \
    python -m patchright install chromium && \
    chmod -R o+rx /app/.patchright-browsers

# Install Scrapling's Camoufox browser for stealth fetching (optional but recommended)
RUN . /app/.venv/bin/activate && \
    python -c "import scrapling; scrapling.StealthyFetcher.setup()" || \
    echo "Camoufox setup skipped (stealth mode will fall back to dynamic/http)"

# Pre-download the ONNX embedding model so it's cached in the image (~80MB)
ENV HF_HOME=/app/.hf-cache
RUN . /app/.venv/bin/activate && \
    python -c "from huggingface_hub import hf_hub_download; hf_hub_download('sentence-transformers/all-MiniLM-L6-v2', 'onnx/model.onnx'); hf_hub_download('sentence-transformers/all-MiniLM-L6-v2', 'tokenizer.json')"

# Create non-root user
RUN useradd -m -u 1000 assistant && \
    chown -R assistant:assistant /app && \
    mkdir -p /var/log/supervisor && \
    chown -R assistant:assistant /var/log/supervisor

# Switch to non-root user
USER assistant

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# Expose application ports
EXPOSE 8080
# Note: Port 3001 (WhatsApp bridge) is internal only, no external exposure needed

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# dumb-init is PID 1: it reaps orphaned processes correctly without interfering
# with Chrome's own child-process tracking. Supervisord runs as its child so it
# never sees Chrome's helper processes as "unknown pids" to steal.
CMD ["/usr/bin/dumb-init", "--", "/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

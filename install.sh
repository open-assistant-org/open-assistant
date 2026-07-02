#!/usr/bin/env bash
# =============================================================================
# Open Assistant — Installer
# https://open-assistant.org
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/open-assistant-org/open-assistant/main/install.sh | bash
#   bash install.sh
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
DOCKER_IMAGE="ghcr.io/open-assistant-org/open-assistant:latest"
CONTAINER_NAME="open-assistant"
APP_PORT=8080
INSTALL_DIR="${INSTALL_DIR:-$PWD}"
ENV_FILE="$INSTALL_DIR/.env"

# -----------------------------------------------------------------------------
# Colors & formatting
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

print_banner() {
  echo ""
  echo -e "${CYAN}${BOLD}"
  echo "  ╔═══════════════════════════════════════════╗"
  echo "  ║          Open Assistant Setup             ║"
  echo "  ║       Self-hosted AI assistant bot        ║"
  echo "  ╚═══════════════════════════════════════════╝"
  echo -e "${RESET}"
}

info()    { echo -e "  ${BLUE}ℹ${RESET}  $*"; }
success() { echo -e "  ${GREEN}✔${RESET}  $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "  ${RED}✖${RESET}  $*" >&2; }
step()    { echo -e "\n${BOLD}${CYAN}▶ $*${RESET}"; }

prompt() {
  local var="$1" question="$2" default="${3:-}"
  local hint=""
  [[ -n "$default" ]] && hint=" ${DIM}[${default}]${RESET}"
  echo -ne "  ${BOLD}${YELLOW}?${RESET}  ${question}${hint}: "
  read -r input
  if [[ -z "$input" && -n "$default" ]]; then
    eval "$var=\"$default\""
  else
    eval "$var=\"$input\""
  fi
}

prompt_secret() {
  local var="$1" question="$2"
  echo -ne "  ${BOLD}${YELLOW}?${RESET}  ${question} ${DIM}(hidden)${RESET}: "
  read -rs input; echo ""
  eval "$var=\"$input\""
}

prompt_choice() {
  local var="$1" question="$2" options="$3" default="${4:-}"
  IFS=',' read -ra opts <<< "$options"
  echo -e "  ${BOLD}${YELLOW}?${RESET}  ${question}"
  local i=1
  for opt in "${opts[@]}"; do
    if [[ "$opt" == "$default" ]]; then
      echo -e "      ${GREEN}$i)${RESET} $opt ${DIM}(default)${RESET}"
    else
      echo -e "      ${DIM}$i)${RESET} $opt"
    fi
    i=$((i + 1))
  done
  echo -ne "  ${BOLD}${YELLOW}?${RESET}  Enter number${default:+ or press Enter for default}: "
  read -r choice
  if [[ -z "$choice" && -n "$default" ]]; then
    eval "$var=\"$default\""
  elif [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#opts[@]} )); then
    eval "$var=\"${opts[$((choice-1))]}\""
  else
    eval "$var=\"$default\""
  fi
}

prompt_yn() {
  local var="$1" question="$2" default="${3:-n}"
  local hint
  [[ "$default" == "y" ]] && hint="${GREEN}Y${RESET}/n" || hint="y/${GREEN}N${RESET}"
  echo -ne "  ${BOLD}${YELLOW}?${RESET}  ${question} [${hint}]: "
  read -r yn
  [[ -z "$yn" ]] && yn="$default"
  [[ "$yn" =~ ^[Yy] ]] && eval "$var=true" || eval "$var=false"
}

# -----------------------------------------------------------------------------
# Prerequisite detection & installation
# -----------------------------------------------------------------------------
has_cmd() { command -v "$1" &>/dev/null; }

detect_os() {
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_LIKE="${ID_LIKE:-}"
  elif [[ "$(uname)" == "Darwin" ]]; then
    OS_ID="macos"
  else
    OS_ID="unknown"
  fi
}

install_docker_linux() {
  info "Installing Docker..."
  if [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" || "${OS_LIKE:-}" == *"debian"* ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io
  elif [[ "$OS_ID" == "centos" || "$OS_ID" == "rhel" || "${OS_LIKE:-}" == *"rhel"* ]]; then
    yum install -y -q yum-utils
    yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    yum install -y -q docker-ce docker-ce-cli containerd.io
    systemctl enable --now docker
  elif [[ "$OS_ID" == "fedora" ]]; then
    dnf install -y -q dnf-plugins-core
    dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
    dnf install -y -q docker-ce docker-ce-cli containerd.io
    systemctl enable --now docker
  else
    curl -fsSL https://get.docker.com | sh
  fi
}

ensure_docker() {
  step "Checking prerequisites"

  if has_cmd docker; then
    local ver
    ver=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
    success "Docker ${ver} found"
  else
    warn "Docker not found"
    if [[ "$(uname)" == "Darwin" ]]; then
      error "Please install Docker Desktop for Mac: https://docs.docker.com/desktop/mac/install/"
      exit 1
    fi
    if [[ $EUID -ne 0 ]]; then
      error "Docker is not installed. Re-run as root/sudo to auto-install, or install Docker first."
      exit 1
    fi
    detect_os
    install_docker_linux
    success "Docker installed"
  fi

  if ! has_cmd curl; then
    [[ $EUID -ne 0 ]] && { error "curl is required. Please install it and re-run."; exit 1; }
    detect_os
    [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" || "${OS_LIKE:-}" == *"debian"* ]] \
      && apt-get install -y -qq curl || yum install -y -q curl
  fi

  if ! has_cmd jq && [[ $EUID -eq 0 ]]; then
    detect_os
    [[ "$OS_ID" == "ubuntu" || "$OS_ID" == "debian" || "${OS_LIKE:-}" == *"debian"* ]] \
      && apt-get install -y -qq jq || yum install -y -q jq 2>/dev/null || true
  fi
}

# -----------------------------------------------------------------------------
# Encryption key generation
# -----------------------------------------------------------------------------
generate_fernet_key() {
  if has_cmd python3; then
    python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
  elif has_cmd openssl; then
    openssl rand 32 | base64 | tr '+/' '-_' | tr -d '\n' | head -c 44
  else
    docker run --rm python:3.11-slim \
      python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null
  fi
}

# -----------------------------------------------------------------------------
# Auto-detect local IP
# -----------------------------------------------------------------------------
get_local_ip() {
  local ip=""
  has_cmd ip && ip=$(ip route get 1.1.1.1 2>/dev/null \
    | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')
  [[ -z "$ip" ]] && has_cmd hostname \
    && ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  [[ -z "$ip" ]] \
    && ip=$(ifconfig 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | head -1)
  echo "${ip:-localhost}"
}

# -----------------------------------------------------------------------------
# Find an available port
# -----------------------------------------------------------------------------
find_free_port() {
  local port="${1:-8080}"
  while docker ps --format '{{.Ports}}' | grep -q ":${port}->"; do
    port=$((port + 1))
  done
  echo "$port"
}

# -----------------------------------------------------------------------------
# LLM provider prompts
# -----------------------------------------------------------------------------
collect_llm_config() {
  local local_ip
  local_ip=$(get_local_ip)

  APP_PORT=$(find_free_port "$APP_PORT")
  [[ "$APP_PORT" != "8080" ]] && warn "Port 8080 is in use — using port ${APP_PORT} instead"

  echo ""
  echo -e "  ${BOLD}Application URL${RESET}"
  echo -e "  ${DIM}Where the assistant will be reachable (used for OAuth redirects and CORS).${RESET}"
  prompt CFG_APP_URL "URL" "http://${local_ip}:${APP_PORT}"

  echo ""
  echo -e "  ${BOLD}LLM Provider${RESET}"
  prompt_choice CFG_LLM_PROVIDER "Which provider?" \
    "openrouter,groq,custom" "openrouter"

  case "$CFG_LLM_PROVIDER" in
    openrouter)
      CFG_LLM_BASE_URL="https://openrouter.ai/api/v1"
      prompt_choice CFG_LLM_MODEL "Model" \
        "anthropic/claude-sonnet-4.6,anthropic/claude-3.5-sonnet,z-ai/glm-5-turbo,openai/gpt-4o,openai/gpt-4o-mini,google/gemini-2.0-flash-001,meta-llama/llama-3.3-70b-instruct" \
        "anthropic/claude-sonnet-4.6"
      ;;
    groq)
      CFG_LLM_BASE_URL="https://api.groq.com/openai/v1"
      prompt_choice CFG_LLM_MODEL "Model" \
        "llama-3.3-70b-versatile,llama-3.1-8b-instant,mixtral-8x7b-32768" \
        "llama-3.3-70b-versatile"
      ;;
    custom)
      prompt CFG_LLM_BASE_URL "API base URL" "http://localhost:11434/v1"
      prompt CFG_LLM_MODEL "Model identifier" "llama3"
      ;;
  esac

  prompt_secret CFG_LLM_API_KEY "API key for ${CFG_LLM_PROVIDER}"
  while [[ -z "$CFG_LLM_API_KEY" ]]; do
    warn "API key is required."
    prompt_secret CFG_LLM_API_KEY "API key for ${CFG_LLM_PROVIDER}"
  done
}

# -----------------------------------------------------------------------------
# Write .env (bootstrap vars only)
# -----------------------------------------------------------------------------
write_env() {
  step "Writing .env"

  if [[ -f "$ENV_FILE" ]]; then
    warn ".env already exists"
    prompt_yn OVERWRITE_ENV "Overwrite it?" "n"
    if [[ "$OVERWRITE_ENV" == "false" ]]; then
      info "Keeping existing .env"
      ENCRYPTION_KEY=$(grep '^ENCRYPTION_KEY=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' || true)
      return
    fi
  fi

  info "Generating encryption key..."
  ENCRYPTION_KEY=$(generate_fernet_key)

  cat > "$ENV_FILE" <<EOF
# Open Assistant — Bootstrap Configuration
# Generated by install.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# These are the ONLY vars that must live here.
# All other settings are managed through the Settings UI at /settings

# Database (SQLite — persisted in a local volume)
DATABASE_URL=sqlite:///data/assistant.db

# Encryption key for credentials stored in the database
# WARNING: Changing this after initial setup will invalidate all stored credentials.
ENCRYPTION_KEY=${ENCRYPTION_KEY}

# Application URL (used for OAuth redirects and CORS)
APP_URL=${CFG_APP_URL}
CORS_ORIGINS=${CFG_APP_URL}
EOF

  success ".env written"
}

# -----------------------------------------------------------------------------
# Start the container
# -----------------------------------------------------------------------------
run_container() {
  step "Starting container"

  local data_dir="$INSTALL_DIR/data"
  local logs_dir="$INSTALL_DIR/logs"
  local tmp_dir="$INSTALL_DIR/tmp"

  mkdir -p "$data_dir" "$logs_dir" "$tmp_dir"
  chmod 777 "$data_dir" "$logs_dir" "$tmp_dir"
  info "Created directories: data/, logs/, tmp/"

  # Stop and remove existing container if present
  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    warn "Existing container found — stopping and removing..."
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker rm   "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi

  info "Pulling image (${DOCKER_IMAGE})..."
  docker pull --quiet "$DOCKER_IMAGE" || { error "Failed to pull image. Make sure you're logged in to the container registry."; exit 1; }

  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "${APP_PORT}:8080" \
    -v "${data_dir}:/app/data" \
    -v "${logs_dir}:/app/logs" \
    -v "${tmp_dir}:/app/tmp" \
    --env-file "$ENV_FILE" \
    -e "LOG_LEVEL=${LOG_LEVEL:-INFO}" \
    -e "ENVIRONMENT=${ENVIRONMENT:-production}" \
    -e "WHATSAPP_BRIDGE_PORT=3001" \
    -e "WHATSAPP_SESSION_DIR=/app/data/whatsapp_session" \
    -e "TMP_DIR=/app/tmp" \
    -e "CRON_MAX_CONCURRENT_JOBS=${CRON_MAX_CONCURRENT_JOBS:-5}" \
    -e "CRON_JOB_TIMEOUT_SECONDS=${CRON_JOB_TIMEOUT_SECONDS:-600}" \
    -e "INSTANCE_ID=${HOSTNAME:-instance-1}" \
    --health-cmd "curl -f http://localhost:8080/health" \
    --health-interval 30s \
    --health-timeout 10s \
    --health-retries 3 \
    --health-start-period 40s \
    "$DOCKER_IMAGE" >/dev/null

  success "Container started"
}

# -----------------------------------------------------------------------------
# Wait for health check
# -----------------------------------------------------------------------------
wait_for_health() {
  step "Waiting for application to be ready"

  local max=60 attempt=0 ok=false
  echo -ne "  ${CYAN}⠋${RESET}  Starting up"
  while (( attempt < max )); do
    if curl -sf "http://localhost:${APP_PORT}/health" -o /tmp/oa_health.json 2>/dev/null; then
      ok=true; break
    fi
    echo -ne "."; sleep 2; attempt=$((attempt + 1))
  done
  echo ""

  if [[ "$ok" == "false" ]]; then
    error "App did not become healthy after $((max * 2))s"
    error "Check logs: docker logs ${CONTAINER_NAME}"
    exit 1
  fi

  local status="ok"
  has_cmd jq && [[ -f /tmp/oa_health.json ]] \
    && status=$(jq -r '.status // "ok"' /tmp/oa_health.json 2>/dev/null || echo "ok")
  success "Application is healthy (${status})"
}

# -----------------------------------------------------------------------------
# Push settings to the database via API
# -----------------------------------------------------------------------------
push_settings() {
  step "Configuring LLM settings"

  local settings="{}"
  add_setting() {
    local key="$1" value="$2"
    [[ -z "$value" ]] && return
    local escaped
    escaped=$(printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')
    settings="${settings%\}},\"${key}\":\"${escaped}\"}"
    settings="${settings/\{,/\{}"
  }

  add_setting "llm.provider" "$CFG_LLM_PROVIDER"
  add_setting "llm.api_key"  "$CFG_LLM_API_KEY"
  add_setting "llm.model"    "$CFG_LLM_MODEL"
  add_setting "llm.base_url" "$CFG_LLM_BASE_URL"

  local response http_code body
  response=$(curl -sf -w "\n%{http_code}" \
    -X POST "http://localhost:${APP_PORT}/api/settings/bulk-update" \
    -H "Content-Type: application/json" \
    -d "{\"settings\": ${settings}}" 2>/dev/null) || true

  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -n -1)

  if [[ "$http_code" == "200" ]]; then
    success "LLM settings saved"
  else
    warn "Settings push returned HTTP ${http_code:-unknown}"
    warn "Configure manually at: ${CFG_APP_URL}/settings"
  fi
}

# -----------------------------------------------------------------------------
# LLM connection test
# -----------------------------------------------------------------------------
test_llm() {
  step "Testing LLM connection"

  local response http_code body
  response=$(curl -sf -w "\n%{http_code}" \
    -X POST "http://localhost:${APP_PORT}/api/settings/test-llm" \
    -H "Content-Type: application/json" 2>/dev/null) || true

  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -n -1)

  if [[ "$http_code" == "200" ]] && has_cmd jq; then
    local status msg
    status=$(echo "$body" | jq -r '.status'  2>/dev/null || echo "unknown")
    msg=$(echo "$body"    | jq -r '.message' 2>/dev/null || echo "")
    if [[ "$status" == "success" ]]; then
      success "LLM connection OK (${CFG_LLM_PROVIDER} / ${CFG_LLM_MODEL})"
    else
      warn "LLM test: ${msg}"
      warn "Verify your API key in the Settings UI at ${CFG_APP_URL}/settings"
    fi
  elif [[ "$http_code" == "200" ]]; then
    success "LLM connection test passed"
  else
    warn "Could not test LLM connection — check your API key at ${CFG_APP_URL}/settings"
  fi
}

# -----------------------------------------------------------------------------
# Final summary
# -----------------------------------------------------------------------------
print_summary() {
  echo ""
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${RESET}"
  echo -e "${GREEN}${BOLD}  Open Assistant is running!${RESET}"
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${RESET}"
  echo ""

  local lines header_rows
  header_rows=7
  lines=$(tput lines 2>/dev/null || echo 24)

  # Pin the URLs to the top of the terminal using an ANSI scroll region: the
  # header (rows 1..header_rows) stays fixed while docker logs scrolls inside
  # the region below it. The WhatsApp QR code is printed by the WhatsApp
  # bridge into the log stream, so it appears here without burying the URLs.
  printf '\033[2J\033[H'                              # clear screen, cursor home
  echo -e "${GREEN}${BOLD}  Open Assistant is running!${RESET}"
  echo -e "  ${BOLD}Chat UI:${RESET}     ${CYAN}${CFG_APP_URL}${RESET}"
  echo -e "  ${BOLD}Settings:${RESET}    ${CYAN}${CFG_APP_URL}/settings${RESET}"
  echo -e "  ${BOLD}Stop:${RESET}        ${DIM}docker stop ${CONTAINER_NAME}${RESET}"
  echo -e "  ${DIM}WhatsApp QR appears in the log stream below when ready.${RESET}"
  echo -e "${DIM}────────────────────────────────────────────────────────────${RESET}"

  printf '\033[%d;%dr' "$((header_rows + 1))" "$lines"   # set scroll region
  printf '\033[%d;1H' "$((header_rows + 1))"             # cursor into region

  # On Ctrl+C / TERM, restore the full-screen scroll region so the terminal
  # isn't left in a broken state after the user detaches.
  trap 'printf "\033[1;%dr" "$lines"; echo' INT TERM

  echo -e "${DIM}Following logs (Ctrl+C detaches — the container keeps running)${RESET}"
  echo ""
  docker logs -f "$CONTAINER_NAME"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
  print_banner
  mkdir -p "$INSTALL_DIR"
  cd "$INSTALL_DIR"

  ensure_docker

  step "Configuration"
  echo ""
  echo -e "  ${DIM}We just need your LLM key — everything else is configured via the Settings UI.${RESET}"

  collect_llm_config
  write_env
  run_container
  wait_for_health
  push_settings
  test_llm
  print_summary
}

main "$@"

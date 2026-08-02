#!/usr/bin/env bash
# =============================================================================
# Open Assistant — Updater
# https://open-assistant.org
#
# Usage:
#   bash update.sh
#   curl -fsSL https://raw.githubusercontent.com/open-assistant-org/open-assistant/main/update.sh | bash
#
# Updates a running Open Assistant instance that was installed with install.sh.
# Your data, settings, and credentials are never touched — only the container
# image is replaced.
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
DOCKER_IMAGE="ghcr.io/open-assistant-org/open-assistant:latest"
CONTAINER_NAME="open-assistant"

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
  echo "  ║          Open Assistant Update            ║"
  echo "  ║       Self-hosted AI assistant bot        ║"
  echo "  ╚═══════════════════════════════════════════╝"
  echo -e "${RESET}"
}

info()    { echo -e "  ${BLUE}ℹ${RESET}  $*"; }
success() { echo -e "  ${GREEN}✔${RESET}  $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
error()   { echo -e "  ${RED}✖${RESET}  $*" >&2; }
step()    { echo -e "\n${BOLD}${CYAN}▶ $*${RESET}"; }

# -----------------------------------------------------------------------------
# Detect the running installation from the existing container
# -----------------------------------------------------------------------------
detect_installation() {
  step "Detecting installation"

  if ! command -v docker &>/dev/null; then
    error "Docker is not installed or not in PATH."
    exit 1
  fi

  if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    error "No running container named '${CONTAINER_NAME}' found."
    error "Make sure Open Assistant is running, or install it first:"
    error "  curl -fsSL https://raw.githubusercontent.com/open-assistant-org/open-assistant/main/install.sh | bash"
    exit 1
  fi

  # Read host port from the container's port bindings
  APP_PORT=$(docker inspect "$CONTAINER_NAME" \
    --format '{{range $p, $conf := .HostConfig.PortBindings}}{{if eq $p "8080/tcp"}}{{(index $conf 0).HostPort}}{{end}}{{end}}' \
    2>/dev/null || true)
  APP_PORT="${APP_PORT:-8080}"

  # Derive install dir from the bind-mount source for /app/data
  local data_src
  data_src=$(docker inspect "$CONTAINER_NAME" \
    --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}' \
    2>/dev/null || true)

  if [[ -z "$data_src" ]]; then
    error "Could not read bind-mount info from container '${CONTAINER_NAME}'."
    error "Was it installed with install.sh? Named Docker volumes are not supported by this updater."
    exit 1
  fi

  INSTALL_DIR="${data_src%/data}"
  ENV_FILE="${INSTALL_DIR}/.env"

  if [[ ! -f "$ENV_FILE" ]]; then
    error ".env not found at ${ENV_FILE}"
    error "Expected it next to the data/ directory created by install.sh."
    exit 1
  fi

  success "Installation directory: ${INSTALL_DIR}"
  success "Port: ${APP_PORT}"
}

# -----------------------------------------------------------------------------
# Check whether an update is available
# -----------------------------------------------------------------------------
check_for_update() {
  step "Checking for updates"

  local running_id new_id
  running_id=$(docker inspect "$CONTAINER_NAME" --format '{{.Image}}' 2>/dev/null || true)

  info "Pulling latest image manifest..."
  if ! docker pull --quiet "$DOCKER_IMAGE" 2>/dev/null; then
    error "Failed to pull image. Check your internet connection or registry access."
    exit 1
  fi

  new_id=$(docker inspect "$DOCKER_IMAGE" --format '{{.Id}}' 2>/dev/null || true)

  if [[ "$running_id" == "$new_id" ]]; then
    success "Already running the latest version — nothing to do."
    echo ""
    echo -e "  ${DIM}To force a restart anyway, run:${RESET}"
    echo -e "  ${DIM}  FORCE_UPDATE=1 bash update.sh${RESET}"
    echo ""
    if [[ "${FORCE_UPDATE:-0}" != "1" ]]; then
      exit 0
    fi
    warn "FORCE_UPDATE=1 — restarting anyway."
  else
    success "New version available — proceeding with update."
  fi
}

# -----------------------------------------------------------------------------
# Replace the container (stop old → start new, data untouched)
# -----------------------------------------------------------------------------
replace_container() {
  step "Applying update"

  local data_dir="${INSTALL_DIR}/data"
  local logs_dir="${INSTALL_DIR}/logs"
  local tmp_dir="${INSTALL_DIR}/tmp"

  # Re-create dirs in case any went missing (safe no-op if they exist)
  mkdir -p "$data_dir" "$logs_dir" "$tmp_dir"

  info "Stopping container..."
  docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker rm   "$CONTAINER_NAME" >/dev/null 2>&1 || true
  success "Old container removed"

  info "Starting updated container..."
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
# Wait for the new container to pass its health check
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
    error "App did not become healthy after $((max * 2))s."
    error "Check logs: docker logs ${CONTAINER_NAME}"
    exit 1
  fi

  local status="ok"
  command -v jq &>/dev/null && [[ -f /tmp/oa_health.json ]] \
    && status=$(jq -r '.status // "ok"' /tmp/oa_health.json 2>/dev/null || echo "ok")
  success "Application is healthy (${status})"
}

# -----------------------------------------------------------------------------
# Prune the old (now-dangling) image to free disk space
# -----------------------------------------------------------------------------
prune_old_image() {
  step "Cleaning up"
  if docker image prune -f --filter "dangling=true" >/dev/null 2>&1; then
    success "Old image layers removed"
  else
    info "Nothing to prune"
  fi
}

# -----------------------------------------------------------------------------
# Final summary
# -----------------------------------------------------------------------------
print_summary() {
  local app_url
  app_url=$(grep '^APP_URL=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '"' || true)
  app_url="${app_url:-http://localhost:${APP_PORT}}"

  echo ""
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${RESET}"
  echo -e "${GREEN}${BOLD}  Open Assistant updated successfully!${RESET}"
  echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════${RESET}"
  echo ""
  echo -e "  ${BOLD}Chat UI:${RESET}     ${CYAN}${app_url}${RESET}"
  echo -e "  ${BOLD}Settings:${RESET}    ${CYAN}${app_url}/settings${RESET}"
  echo -e "  ${BOLD}Logs:${RESET}        ${DIM}docker logs -f ${CONTAINER_NAME}${RESET}"
  echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
  print_banner
  detect_installation
  check_for_update
  replace_container
  wait_for_health
  prune_old_image
  print_summary
}

main "$@"

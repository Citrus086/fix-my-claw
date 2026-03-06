#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
One-click installer for fix-my-claw monitor hook (macOS).

Usage:
  ./deploy/launchd/install.sh [--rc-file <path>] [--fix-my-claw-bin <path>] [--force]

Options:
  --rc-file         Target rc file. Default: detect from current shell (~/.zshrc or ~/.bashrc)
  --fix-my-claw-bin Absolute path to fix-my-claw. Default: resolve from current shell.
  --force           Replace existing hook block if present
  -h, --help
EOF
}

RC_FILE=""
FIX_MY_CLAW_BIN=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rc-file)
      [[ $# -ge 2 ]] || { echo "missing value for --rc-file" >&2; exit 2; }
      RC_FILE="$2"
      shift 2
      ;;
    --fix-my-claw-bin)
      [[ $# -ge 2 ]] || { echo "missing value for --fix-my-claw-bin" >&2; exit 2; }
      FIX_MY_CLAW_BIN="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "this installer is for macOS (launchd) only" >&2
  exit 1
fi

if [[ -z "$FIX_MY_CLAW_BIN" ]]; then
  FIX_MY_CLAW_BIN="$(command -v fix-my-claw || true)"
fi
if [[ -n "$FIX_MY_CLAW_BIN" && "$FIX_MY_CLAW_BIN" != */* ]]; then
  FIX_MY_CLAW_BIN="$(command -v "$FIX_MY_CLAW_BIN" || true)"
fi

if [[ -z "$FIX_MY_CLAW_BIN" ]]; then
  echo "fix-my-claw command not found; install package first (pip install .)" >&2
  exit 1
fi
FIX_MY_CLAW_BIN="$(cd -- "$(dirname -- "$FIX_MY_CLAW_BIN")" && pwd)/$(basename -- "$FIX_MY_CLAW_BIN")"
[[ -x "$FIX_MY_CLAW_BIN" ]] || { echo "fix-my-claw is not executable: $FIX_MY_CLAW_BIN" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
CONFIG_PATH="$HOME/.fix-my-claw/config.toml"
PLIST_NAME="com.fix-my-claw.monitor.plist"
LABEL="com.fix-my-claw.monitor"
SRC_PLIST="$SCRIPT_DIR/$PLIST_NAME"
DST_PLIST="$PLIST_DIR/$PLIST_NAME"

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|]/\\&/g'
}

gateway_running_state() {
  local status_json compact_json
  if ! command -v openclaw >/dev/null 2>&1; then
    return 2
  fi
  if ! status_json="$(command openclaw gateway status --json 2>/dev/null)"; then
    return 2
  fi
  compact_json="$(printf '%s' "$status_json" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  case "$compact_json" in
    *'"running":true'*|*'"running":"true"'*|*'"status":"running"'*|*'"state":"running"'*|*'"active":true'*|*'"active":"true"'*|*'"gatewayrunning":true'*|*'"gatewayrunning":"true"'*)
      return 0
      ;;
    *'"running":false'*|*'"running":"false"'*|*'"status":"stopped"'*|*'"state":"stopped"'*|*'"active":false'*|*'"active":"false"'*|*'"gatewayrunning":false'*|*'"gatewayrunning":"false"'*)
      return 1
      ;;
    *)
      return 2
      ;;
  esac
}

start_watchdog_job() {
  if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    launchctl bootstrap "$DOMAIN" "$DST_PLIST" >/dev/null 2>&1 || true
  fi
  launchctl enable "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  launchctl kickstart -k "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
}

stop_watchdog_job() {
  launchctl disable "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
  launchctl bootout "$DOMAIN" "$DST_PLIST" >/dev/null 2>&1 || launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
}

sync_watchdog_to_gateway_state() {
  local state_rc
  if gateway_running_state; then
    state_rc=0
  else
    state_rc=$?
  fi
  case "$state_rc" in
    0)
      start_watchdog_job
      ;;
    *)
      # If current gateway state cannot be determined during install, keep monitor idle.
      stop_watchdog_job
      ;;
  esac
}

if [[ ! -f "$SRC_PLIST" ]]; then
  echo "template not found: $SRC_PLIST" >&2
  exit 1
fi

if [[ -z "$RC_FILE" ]]; then
  case "${SHELL:-}" in
    */zsh) RC_FILE="$HOME/.zshrc" ;;
    */bash) RC_FILE="$HOME/.bashrc" ;;
    *)
      echo "cannot auto-detect rc file from SHELL=${SHELL:-unknown}; use --rc-file" >&2
      exit 2
      ;;
  esac
fi

mkdir -p "$(dirname "$RC_FILE")"

START_MARKER="# >>> fix-my-claw openclaw hook >>>"
END_MARKER="# <<< fix-my-claw openclaw hook <<<"
RC_TMP=""
HOOK_PRESENT=0
HOOK_SHOULD_WRITE=1

if [[ -f "$RC_FILE" ]] && grep -qF "$START_MARKER" "$RC_FILE"; then
  HOOK_PRESENT=1
  if [[ $FORCE -eq 0 ]]; then
    HOOK_SHOULD_WRITE=0
    echo "hook already exists in $RC_FILE (use --force to replace)"
  else
    RC_TMP="$(mktemp)"
    awk -v s="$START_MARKER" -v e="$END_MARKER" '
      index($0, s) {skip=1; next}
      index($0, e) {skip=0; next}
      !skip {print}
    ' "$RC_FILE" > "$RC_TMP"
  fi
fi

mkdir -p "$PLIST_DIR"
"$FIX_MY_CLAW_BIN" init --config "$CONFIG_PATH" >/dev/null
BIN_ESCAPED="$(escape_sed_replacement "$FIX_MY_CLAW_BIN")"
CONFIG_ESCAPED="$(escape_sed_replacement "$CONFIG_PATH")"
sed \
  -e "s|@FIX_MY_CLAW_BIN@|$BIN_ESCAPED|g" \
  -e "s|@CONFIG_PATH@|$CONFIG_ESCAPED|g" \
  "$SRC_PLIST" > "$DST_PLIST"

if [[ $HOOK_SHOULD_WRITE -eq 1 ]]; then
  if [[ -z "$RC_TMP" ]]; then
    RC_TMP="$(mktemp)"
    if [[ $HOOK_PRESENT -eq 1 ]]; then
      cat "$RC_FILE" > "$RC_TMP"
    elif [[ -f "$RC_FILE" ]]; then
      cat "$RC_FILE" > "$RC_TMP"
    fi
  fi
  cat >> "$RC_TMP" <<'EOF'

# >>> fix-my-claw openclaw hook >>>
# Auto-manage watchdog based on actual gateway state after lifecycle commands.
fix_my_claw_gateway_running_state() {
  local status_json compact_json
  if ! command -v openclaw >/dev/null 2>&1; then
    return 2
  fi
  if ! status_json="$(command openclaw gateway status --json 2>/dev/null)"; then
    return 2
  fi
  compact_json="$(printf '%s' "$status_json" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  case "$compact_json" in
    *'"running":true'*|*'"running":"true"'*|*'"status":"running"'*|*'"state":"running"'*|*'"active":true'*|*'"active":"true"'*|*'"gatewayrunning":true'*|*'"gatewayrunning":"true"'*)
      return 0
      ;;
    *'"running":false'*|*'"running":"false"'*|*'"status":"stopped"'*|*'"state":"stopped"'*|*'"active":false'*|*'"active":"false"'*|*'"gatewayrunning":false'*|*'"gatewayrunning":"false"'*)
      return 1
      ;;
    *)
      return 2
      ;;
  esac
}

fix_my_claw_start_watchdog() {
  local domain="gui/$(id -u)"
  local label="com.fix-my-claw.monitor"
  local plist="$HOME/Library/LaunchAgents/com.fix-my-claw.monitor.plist"

  if ! launchctl print "$domain/$label" >/dev/null 2>&1; then
    launchctl bootstrap "$domain" "$plist" >/dev/null 2>&1 || true
  fi
  launchctl enable "$domain/$label" >/dev/null 2>&1 || true
  launchctl kickstart -k "$domain/$label" >/dev/null 2>&1 || true
}

fix_my_claw_stop_watchdog() {
  local domain="gui/$(id -u)"
  local label="com.fix-my-claw.monitor"
  local plist="$HOME/Library/LaunchAgents/com.fix-my-claw.monitor.plist"

  launchctl disable "$domain/$label" >/dev/null 2>&1 || true
  launchctl bootout "$domain" "$plist" >/dev/null 2>&1 || launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
}

fix_my_claw_sync_watchdog() {
  local state_rc
  if fix_my_claw_gateway_running_state; then
    state_rc=0
  else
    state_rc=$?
  fi
  case "$state_rc" in
    0)
      fix_my_claw_start_watchdog
      ;;
    1)
      fix_my_claw_stop_watchdog
      ;;
    *)
      ;;
  esac
}

openclaw() {
  command openclaw "$@"
  local rc=$?

  if [ "$rc" -eq 0 ] && [ "${1:-}" = "gateway" ]; then
    if [ "${2:-}" = "start" ] || [ "${2:-}" = "restart" ] || [ "${2:-}" = "stop" ]; then
      fix_my_claw_sync_watchdog
    fi
  fi
  return "$rc"
}
# <<< fix-my-claw openclaw hook <<<
EOF
fi

if [[ -n "$RC_TMP" ]]; then
  mv "$RC_TMP" "$RC_FILE"
fi

# Sync monitor state to the current gateway state right after installation.
sync_watchdog_to_gateway_state

cat <<EOF
Installed launchd template: $DST_PLIST
Installed shell hook in: $RC_FILE
Config: $CONFIG_PATH
fix-my-claw executable: $FIX_MY_CLAW_BIN

Apply now:
  source "$RC_FILE"

Behavior:
  - if gateway is already running now -> start watchdog immediately
  - openclaw gateway start/restart/stop -> re-sync watchdog to actual gateway state

Check status:
  launchctl print "$DOMAIN/$LABEL"
EOF

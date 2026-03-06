#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
One-click installer for fix-my-claw monitor hook (macOS).

Usage:
  ./deploy/launchd/install.sh [--rc-file <path>] [--force]

Options:
  --rc-file  Target rc file. Default: detect from current shell (~/.zshrc or ~/.bashrc)
  --force    Replace existing hook block if present
  -h, --help
EOF
}

RC_FILE=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rc-file)
      [[ $# -ge 2 ]] || { echo "missing value for --rc-file" >&2; exit 2; }
      RC_FILE="$2"
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

if ! command -v fix-my-claw >/dev/null 2>&1; then
  echo "fix-my-claw command not found; install package first (pip install .)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
CONFIG_PATH="$HOME/.fix-my-claw/config.toml"
PLIST_NAME="com.fix-my-claw.monitor.plist"
LABEL="com.fix-my-claw.monitor"
SRC_PLIST="$SCRIPT_DIR/$PLIST_NAME"
DST_PLIST="$PLIST_DIR/$PLIST_NAME"

if [[ ! -f "$SRC_PLIST" ]]; then
  echo "template not found: $SRC_PLIST" >&2
  exit 1
fi

mkdir -p "$PLIST_DIR"
fix-my-claw init --config "$CONFIG_PATH" >/dev/null
cp "$SRC_PLIST" "$DST_PLIST"

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
touch "$RC_FILE"

START_MARKER="# >>> fix-my-claw openclaw hook >>>"
END_MARKER="# <<< fix-my-claw openclaw hook <<<"

if grep -qF "$START_MARKER" "$RC_FILE"; then
  if [[ $FORCE -eq 0 ]]; then
    echo "hook already exists in $RC_FILE (use --force to replace)"
  else
    tmp="$(mktemp)"
    awk -v s="$START_MARKER" -v e="$END_MARKER" '
      index($0, s) {skip=1; next}
      index($0, e) {skip=0; next}
      !skip {print}
    ' "$RC_FILE" > "$tmp"
    mv "$tmp" "$RC_FILE"
  fi
fi

if ! grep -qF "$START_MARKER" "$RC_FILE"; then
  cat >> "$RC_FILE" <<'EOF'

# >>> fix-my-claw openclaw hook >>>
# Auto-manage watchdog based on gateway lifecycle.
openclaw() {
  command openclaw "$@"
  local rc=$?
  local domain="gui/$(id -u)"
  local label="com.fix-my-claw.monitor"
  local plist="$HOME/Library/LaunchAgents/com.fix-my-claw.monitor.plist"

  if [ "$rc" -eq 0 ] && [ "${1:-}" = "gateway" ]; then
    if [ "${2:-}" = "start" ] || [ "${2:-}" = "restart" ]; then
      if ! launchctl print "$domain/$label" >/dev/null 2>&1; then
        launchctl bootstrap "$domain" "$plist" >/dev/null 2>&1 || true
      fi
      launchctl enable "$domain/$label" >/dev/null 2>&1 || true
      launchctl kickstart -k "$domain/$label" >/dev/null 2>&1 || true
    elif [ "${2:-}" = "stop" ]; then
      launchctl disable "$domain/$label" >/dev/null 2>&1 || true
      launchctl bootout "$domain" "$plist" >/dev/null 2>&1 || launchctl bootout "$domain/$label" >/dev/null 2>&1 || true
    fi
  fi
  return "$rc"
}
# <<< fix-my-claw openclaw hook <<<
EOF
fi

# Keep monitor idle right after installation; hook will start it on gateway start/restart.
launchctl disable "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "$DOMAIN" "$DST_PLIST" >/dev/null 2>&1 || launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true

cat <<EOF
Installed launchd template: $DST_PLIST
Installed shell hook in: $RC_FILE
Config: $CONFIG_PATH

Apply now:
  source "$RC_FILE"

Behavior:
  - openclaw gateway start/restart -> start watchdog
  - openclaw gateway stop          -> stop watchdog

Check status:
  launchctl print "$DOMAIN/$LABEL"
EOF

#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
One-click uninstaller for fix-my-claw launchd jobs (macOS).

Usage:
  ./deploy/launchd/uninstall.sh [--keep-hook] [--rc-file <path>]

Options:
  --keep-hook    Keep shell hook block in rc file
  --rc-file      Target rc file for hook removal (default: detect from current shell)
  -h, --help
EOF
}

REMOVE_HOOK=1
RC_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-hook)
      REMOVE_HOOK=0
      shift
      ;;
    --rc-file)
      [[ $# -ge 2 ]] || { echo "missing value for --rc-file" >&2; exit 2; }
      RC_FILE="$2"
      shift 2
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
  echo "this uninstaller is for macOS (launchd) only" >&2
  exit 1
fi

PLIST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"

MONITOR_LABEL="com.fix-my-claw.monitor"
MONITOR_PLIST="$PLIST_DIR/$MONITOR_LABEL.plist"
REPAIR_LABEL="com.fix-my-claw.repair"
REPAIR_PLIST="$PLIST_DIR/$REPAIR_LABEL.plist"

remove_job() {
  local label="$1"
  local plist="$2"
  launchctl disable "$DOMAIN/$label" >/dev/null 2>&1 || true
  launchctl bootout "$DOMAIN" "$plist" >/dev/null 2>&1 || launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
  rm -f "$plist"
  echo "removed: $label"
}

remove_job "$MONITOR_LABEL" "$MONITOR_PLIST"
remove_job "$REPAIR_LABEL" "$REPAIR_PLIST"

if [[ $REMOVE_HOOK -eq 1 ]]; then
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

  START_MARKER="# >>> fix-my-claw openclaw hook >>>"
  END_MARKER="# <<< fix-my-claw openclaw hook <<<"

  if [[ -f "$RC_FILE" ]] && grep -qF "$START_MARKER" "$RC_FILE"; then
    tmp="$(mktemp)"
    awk -v s="$START_MARKER" -v e="$END_MARKER" '
      index($0, s) {skip=1; next}
      index($0, e) {skip=0; next}
      !skip {print}
    ' "$RC_FILE" > "$tmp"
    mv "$tmp" "$RC_FILE"
    echo "removed shell hook from: $RC_FILE"
    echo "reload shell config: source \"$RC_FILE\""
  else
    echo "shell hook not found in: $RC_FILE"
  fi
fi

echo "done"

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

if grep -qF "$START_MARKER" "$RC_FILE"; then
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

if [[ -n "$RC_TMP" ]]; then
  mv "$RC_TMP" "$RC_FILE"
fi

# Keep monitor idle right after installation; hook will start it on gateway start/restart.
launchctl disable "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "$DOMAIN" "$DST_PLIST" >/dev/null 2>&1 || launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true

cat <<EOF
Installed launchd template: $DST_PLIST
Installed shell hook in: $RC_FILE
Config: $CONFIG_PATH
fix-my-claw executable: $FIX_MY_CLAW_BIN

Apply now:
  source "$RC_FILE"

Behavior:
  - openclaw gateway start/restart -> start watchdog
  - openclaw gateway stop          -> stop watchdog

Check status:
  launchctl print "$DOMAIN/$LABEL"
EOF

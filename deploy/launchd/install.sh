#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
One-click installer for fix-my-claw launchd monitor job (macOS).

Usage:
  ./deploy/launchd/install.sh [--fix-my-claw-bin <path>] [--force]

Options:
  --fix-my-claw-bin Absolute path to fix-my-claw. Default: resolve from current shell.
  --force           Replace existing plist if present and restart the launchd job
  -h, --help
EOF
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
APP_BUNDLED_CLI="$PROJECT_ROOT/dist/FixMyClawGUI.app/Contents/MacOS/fix-my-claw"

FIX_MY_CLAW_BIN=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
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

if [[ -z "$FIX_MY_CLAW_BIN" && -x "$APP_BUNDLED_CLI" ]]; then
  FIX_MY_CLAW_BIN="$APP_BUNDLED_CLI"
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

PLIST_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
CONFIG_PATH="$HOME/.fix-my-claw/config.toml"
PLIST_NAME="com.fix-my-claw.monitor.plist"
LABEL="com.fix-my-claw.monitor"
DST_PLIST="$PLIST_DIR/$PLIST_NAME"
STABLE_SERVICE_BIN="$HOME/.fix-my-claw/bin/fix-my-claw-service"

if [[ -e "$DST_PLIST" && $FORCE -eq 0 ]]; then
  echo "exists: $DST_PLIST (use --force to overwrite)" >&2
  exit 2
fi

mkdir -p "$PLIST_DIR"
"$FIX_MY_CLAW_BIN" init --config "$CONFIG_PATH" >/dev/null
"$FIX_MY_CLAW_BIN" start --config "$CONFIG_PATH" >/dev/null
if [[ $FORCE -eq 1 ]]; then
  "$FIX_MY_CLAW_BIN" service reconcile --config "$CONFIG_PATH" >/dev/null
else
  "$FIX_MY_CLAW_BIN" service install --config "$CONFIG_PATH" >/dev/null
fi

cat <<EOF
Installed launchd job: $DST_PLIST
Config: $CONFIG_PATH
Install-time CLI: $FIX_MY_CLAW_BIN
Stable service executable: $STABLE_SERVICE_BIN

Monitoring is enabled by default. Control it with:
  fix-my-claw status --config "$CONFIG_PATH"
  fix-my-claw stop --config "$CONFIG_PATH"
  fix-my-claw start --config "$CONFIG_PATH"
  fix-my-claw service reconcile --config "$CONFIG_PATH"

Check status:
  launchctl print "$DOMAIN/$LABEL"
EOF

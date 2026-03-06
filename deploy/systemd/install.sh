#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Render and install fix-my-claw systemd units with an absolute fix-my-claw path.

Usage:
  ./deploy/systemd/install.sh [--fix-my-claw-bin <path>] [--config-path <path>] [--output-dir <path>] [--force]

Options:
  --fix-my-claw-bin  Absolute path to fix-my-claw. Default: resolve from current shell.
  --config-path      Config path to bake into rendered units. Default: /etc/fix-my-claw/config.toml
  --output-dir       Where to write rendered units. Default: /etc/systemd/system
  --force            Overwrite existing rendered units
  -h, --help
EOF
}

FIX_MY_CLAW_BIN=""
CONFIG_PATH="/etc/fix-my-claw/config.toml"
OUTPUT_DIR="/etc/systemd/system"
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix-my-claw-bin)
      [[ $# -ge 2 ]] || { echo "missing value for --fix-my-claw-bin" >&2; exit 2; }
      FIX_MY_CLAW_BIN="$2"
      shift 2
      ;;
    --config-path)
      [[ $# -ge 2 ]] || { echo "missing value for --config-path" >&2; exit 2; }
      CONFIG_PATH="$2"
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || { echo "missing value for --output-dir" >&2; exit 2; }
      OUTPUT_DIR="$2"
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

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "this installer is for Linux/systemd only" >&2
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

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|]/\\&/g'
}

render_unit() {
  local src="$1"
  local dst="$2"
  local bin_escaped config_escaped
  bin_escaped="$(escape_sed_replacement "$FIX_MY_CLAW_BIN")"
  config_escaped="$(escape_sed_replacement "$CONFIG_PATH")"
  sed \
    -e "s|@FIX_MY_CLAW_BIN@|$bin_escaped|g" \
    -e "s|@CONFIG_PATH@|$config_escaped|g" \
    "$src" > "$dst"
}

targets=(
  "$OUTPUT_DIR/fix-my-claw.service"
  "$OUTPUT_DIR/fix-my-claw-oneshot.service"
  "$OUTPUT_DIR/fix-my-claw.timer"
)

if [[ $FORCE -eq 0 ]]; then
  for target in "${targets[@]}"; do
    if [[ -e "$target" ]]; then
      echo "exists: $target (use --force to overwrite)" >&2
      exit 2
    fi
  done
fi

mkdir -p "$OUTPUT_DIR"

for unit in fix-my-claw.service fix-my-claw-oneshot.service; do
  src="$SCRIPT_DIR/$unit"
  dst="$OUTPUT_DIR/$unit"
  render_unit "$src" "$dst"
done

timer_dst="$OUTPUT_DIR/fix-my-claw.timer"
cp "$SCRIPT_DIR/fix-my-claw.timer" "$timer_dst"

cat <<EOF
Rendered units into: $OUTPUT_DIR
fix-my-claw executable: $FIX_MY_CLAW_BIN
Config path: $CONFIG_PATH

Next steps:
  sudo systemctl daemon-reload
  sudo systemctl enable --now fix-my-claw.service

Optional cron-style mode:
  sudo systemctl enable --now fix-my-claw.timer
EOF

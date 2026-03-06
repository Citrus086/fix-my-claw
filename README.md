# 🦀 fix-my-claw

[中文](README_ZH.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.9-blue.svg)](#requirements)

A plug-and-play watchdog for OpenClaw — keep it healthy automatically.





## ✨ Highlights

- 🩹 **Auto-heal**: detects unhealthy states and runs recovery steps automatically.
- 🧱 **Layered recovery**: command-level terminate, then `/new`, then official structural repair steps.
- 🔁 **Anomaly guard**: detects "healthy probes but agent ping-pong/repeat loops" from recent logs.
- 🔔 **Human approval gate**: optional Discord notification + `yes/no` reply before enabling Codex repair.
- 🧾 **Operator-friendly**: writes a timestamped incident folder under `~/.fix-my-claw/attempts/` for debugging.
- 🧯 **Safe defaults**: repair cooldown + daily attempt limits + single-instance lock to avoid flapping.
- 🧷 **Service-ready**: ships with Linux `systemd` and macOS `launchd` templates.

- One command to start: `fix-my-claw up`
- Probes `openclaw gateway health --json` + `openclaw gateway status --json`
- Recovers using your official steps (defaults included)
- Optional: Codex-assisted remediation for stubborn cases (off by default, restricted by default)

## 🚀 Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install .

fix-my-claw up
```

Default paths:

- Config: `~/.fix-my-claw/config.toml` (auto-created by `fix-my-claw up`)
- Logs: `~/.fix-my-claw/fix-my-claw.log`
- Attempts: `~/.fix-my-claw/attempts/<timestamp>/`

## ✅ Requirements

- Python 3.9+
- OpenClaw installed and available as `openclaw` in `PATH`

## 🧰 Commands

```bash
fix-my-claw up      # init (if needed) + monitor
fix-my-claw check   # one-time probe
fix-my-claw repair  # one-time recovery attempt
fix-my-claw monitor # long-running loop (requires config)
fix-my-claw init    # write default config
```

## 🧭 How it works (high-level)

```mermaid
flowchart TD
  A["timer / monitor loop"] --> B["health probe"]
  B --> C["status probe"]
  C -->|healthy| D["sleep"]
  C -->|unhealthy| E["command stop (/stop)"]
  E --> F["reset context (/new)"]
  F --> G["official recovery steps"]
  G --> H{"healthy?"}
  H -->|yes| D
  H -->|no| I["notify + ask yes/no"]
  I -->|yes| J["backup ~/.openclaw then Codex remediation"]
  I -->|no| D
  J --> D
```

## ⚙️ Configuration

All settings live in a single TOML file.

- Default: `~/.fix-my-claw/config.toml`
- Example: `examples/fix-my-claw.toml`
- New: `[anomaly_guard]` can mark ping-pong/repetition patterns as unhealthy even when gateway probes still pass.
- `auto_dispatch_check` now analyzes real handoffs: who delegated, who was the target, and whether an unexpected agent keeps speaking afterwards.
- New: `[notify]` supports Discord notifications and yes/no approval prompts.
- Note: status notifications are always sent; `yes/no` approval is only used when `ai.enabled = true`.
- Note: when `notify.target` is a channel (`channel:...`), yes/no replies must mention the notify account (for example, `@fix-my-claw yes`).
- Note: only strict replies `yes/no` or `是/否` are accepted; non-matching replies trigger a re-ask, and after 3 invalid replies AI repair is skipped for this incident.
- Extended: `[repair]` adds session-level control knobs for `/stop`, `/new`, and active-session filtering.
- Compatibility: legacy key `[loop_guard]` is still accepted.

Tip: if `openclaw` isn’t on `PATH` under systemd/launchd, set `[openclaw].command` to an absolute path.

## 🖥️ Run it on a server (systemd)

Two options in `deploy/systemd/`:

- **Option A (recommended)**: `fix-my-claw.service` runs a long-lived monitor loop.
- **Option B**: `fix-my-claw-oneshot.service` + `fix-my-claw.timer` runs `fix-my-claw repair` periodically (cron-style).

Example (Option A):

```bash
sudo mkdir -p /etc/fix-my-claw
sudo cp examples/fix-my-claw.toml /etc/fix-my-claw/config.toml

FIX_MY_CLAW_BIN="$(command -v fix-my-claw)"
sudo ./deploy/systemd/install.sh --fix-my-claw-bin "$FIX_MY_CLAW_BIN"
sudo systemctl daemon-reload
sudo systemctl enable --now fix-my-claw.service
```

## 🍎 Run it on macOS (launchd)

One-click install (single entrypoint):

```bash
./deploy/launchd/install.sh
source ~/.zshrc
```

If `fix-my-claw` is not resolvable from your shell, pass it explicitly:

```bash
./deploy/launchd/install.sh --fix-my-claw-bin "$(command -v fix-my-claw)"
```

Behavior:

- `openclaw gateway start` / `restart`: auto-start watchdog
- `openclaw gateway stop`: auto-stop watchdog

One-click uninstall:

```bash
./deploy/launchd/uninstall.sh
```

Keep hook block in shell rc:

```bash
./deploy/launchd/uninstall.sh --keep-hook
```

Useful commands:

```bash
# Status
launchctl print "gui/$(id -u)/com.fix-my-claw.monitor"

# Stop/disable
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.fix-my-claw.monitor.plist
```

## 🧩 Codex-assisted remediation (optional)

When enabled, `fix-my-claw` runs Codex CLI non-interactively.

- Default config uses `codex exec` with `approval_policy="never"`.
- Stage 1 is restricted to OpenClaw config/state + workspace + fix-my-claw state directory.
- Stage 2 is disabled by default (`ai.allow_code_changes=false`).

## 🩺 Troubleshooting

- `command not found: openclaw`
  - Ensure OpenClaw is installed and `openclaw` is on `PATH` (especially under systemd/launchd).
  - Or set `[openclaw].command` to an absolute path.
- `another fix-my-claw instance is running`
  - A lock file in `[monitor].state_dir` prevents concurrent repairs.
  - If you believe it’s stale, confirm no instance is running, then remove the lock file.

## 🤝 Contributing

See `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md`.

## 📄 License

MIT, see `LICENSE`.

#!/usr/bin/env bash
# Claude HQ launcher — one command that:
#   * builds both binaries if needed,
#   * (re)installs the Claude Code hooks so sessions show up,
#   * runs the daemon in the foreground.
#
# Closing the window, ⌘Q-ing the tray, or pressing Ctrl-C here all exit cleanly.

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAURI_DIR="$HERE/src-tauri"
BIN="$TAURI_DIR/target/debug/claude-hq"

color_red()    { printf '\033[31m%s\033[0m' "$*"; }
color_green()  { printf '\033[32m%s\033[0m' "$*"; }
color_yellow() { printf '\033[33m%s\033[0m' "$*"; }
color_dim()    { printf '\033[2m%s\033[0m' "$*"; }

# Ensure cargo is available
if ! command -v cargo >/dev/null 2>&1; then
    if [[ -f "$HOME/.cargo/env" ]]; then
        # shellcheck disable=SC1091
        source "$HOME/.cargo/env"
    fi
fi

if ! command -v cargo >/dev/null 2>&1; then
    color_red "error: cargo not found." ; echo
    echo "Install Rust: https://rustup.rs"
    exit 1
fi

# Always run `cargo build --bins` — it's incremental and free when nothing
# changed, but it picks up:
#   * Rust source edits
#   * Frontend edits (Tauri embeds src/*.html|js|css into the daemon binary
#     at compile time, so renderer.js changes don't appear otherwise).
color_yellow "Building binaries (incremental)..." ; echo
(cd "$TAURI_DIR" && cargo build --bins)

# Keep the Claude Code hooks (and the embedded hook script) in sync with this
# build so sessions show up. Idempotent — preserves your other hooks, dedupes
# on re-run. Honors edits to hooks/claude_hq_hook.py once it's rebuilt above.
echo "Ensuring Claude Code hooks are installed..."
"$BIN" install >/dev/null || color_yellow "  (hook install reported a problem)"

if ! command -v python3 >/dev/null 2>&1; then
    color_yellow "Note:" ; echo " python3 not found — the hooks need it (preinstalled on macOS)."
fi

color_green "Starting Claude HQ — close the window or press Ctrl-C to quit."
echo
# exec hands the terminal to the daemon; signals (Ctrl-C) go straight to it.
exec "$BIN"

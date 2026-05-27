#!/usr/bin/env bash
# Claude HQ — clean installer.
#   * builds release binaries
#   * copies them to ~/.claude-hq/bin
#   * installs Claude Code hooks (default integration; needs no PATH change and
#     captures sessions launched from terminals AND editors)
#
# Re-running is safe. Use `--debug` for a faster (unoptimized) build.
# The legacy PTY shim is still built; install it instead with:
#   ~/.claude-hq/bin/claude-hq install-shim

set -e

DEBUG_BUILD=0
if [[ "${1:-}" == "--debug" ]]; then
    DEBUG_BUILD=1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAURI_DIR="$HERE/src-tauri"
INSTALL_DIR="$HOME/.claude-hq"
BIN_DIR="$INSTALL_DIR/bin"

color_red()    { printf '\033[31m%s\033[0m' "$*"; }
color_green()  { printf '\033[32m%s\033[0m' "$*"; }
color_yellow() { printf '\033[33m%s\033[0m' "$*"; }
color_dim()    { printf '\033[2m%s\033[0m' "$*"; }
step()         { printf '\033[36m==>\033[0m %s\n' "$*"; }

echo
color_green "Claude HQ installer"; echo
echo "──────────────────────"

# Ensure cargo is on PATH.
if ! command -v cargo >/dev/null 2>&1; then
    [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"
fi
if ! command -v cargo >/dev/null 2>&1; then
    color_red "error: cargo not found." ; echo
    echo "Install Rust first: https://rustup.rs"
    exit 1
fi

# Pick build profile.
if [[ $DEBUG_BUILD -eq 1 ]]; then
    PROFILE="debug"
    step "Building debug binaries (--debug flag)..."
    (cd "$TAURI_DIR" && cargo build --bins)
else
    PROFILE="release"
    step "Building release binaries (this may take a few minutes the first time)..."
    color_dim "    Use ./install.sh --debug if you want a faster, unoptimized build."; echo
    (cd "$TAURI_DIR" && cargo build --release --bins)
fi
DAEMON_SRC="$TAURI_DIR/target/$PROFILE/claude-hq"
SHIM_SRC="$TAURI_DIR/target/$PROFILE/claude-hq-shim"

if [[ ! -x "$DAEMON_SRC" || ! -x "$SHIM_SRC" ]]; then
    color_red "error: build did not produce expected binaries." ; echo
    exit 1
fi

# Stop a running installed daemon (don't touch dev-mode debug runs).
if pgrep -f "$BIN_DIR/claude-hq" >/dev/null 2>&1; then
    step "Stopping running daemon..."
    pkill -f "$BIN_DIR/claude-hq" 2>/dev/null || true
    sleep 0.3
fi

step "Installing binaries to $BIN_DIR"
mkdir -p "$BIN_DIR"
cp "$DAEMON_SRC" "$BIN_DIR/claude-hq"
cp "$SHIM_SRC"   "$BIN_DIR/claude-hq-shim"
chmod 0755 "$BIN_DIR/claude-hq" "$BIN_DIR/claude-hq-shim"

# On Apple Silicon, copying an ad-hoc-signed Mach-O can invalidate its signature
# and macOS will SIGKILL it on launch. Re-sign ad-hoc to fix.
if [[ "$(uname -s)" == "Darwin" ]] && command -v codesign >/dev/null 2>&1; then
    step "Re-signing binaries (ad-hoc) for macOS"
    codesign --force --sign - "$BIN_DIR/claude-hq"      >/dev/null 2>&1 || true
    codesign --force --sign - "$BIN_DIR/claude-hq-shim" >/dev/null 2>&1 || true
fi

# Default integration: Claude Code hooks (no PATH change required). This writes
# the hook into ~/.claude/settings.json and a helper under ~/.claude-hq/hooks.
step "Installing Claude Code hooks"
"$BIN_DIR/claude-hq" install || color_yellow "  (hook install reported a problem; see output above)"

if ! command -v python3 >/dev/null 2>&1; then
    echo
    color_yellow "Note:" ; echo " python3 was not found on PATH."
    echo "The hooks need python3 (preinstalled on macOS via Command Line Tools)."
fi

echo
color_green "✓ Installed."; echo
echo
echo "Next steps:"
echo "  1. Start the daemon:    $BIN_DIR/claude-hq"
echo "     (it appears in the menu bar and opens a window)"
echo "  2. In any terminal/editor, run Claude Code as usual — sessions appear in"
echo "     the office automatically. No PATH change or shell reload needed."
echo
echo "Prefer the old PTY shim instead?   $BIN_DIR/claude-hq install-shim"
echo "Uninstall with:                    ./uninstall.sh"

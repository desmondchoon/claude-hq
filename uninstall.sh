#!/usr/bin/env bash
# Claude HQ — clean uninstaller.
#   * stops any running installed daemon
#   * removes ~/.claude-hq entirely (binaries, future config)
#   * strips the PATH block from your shell rc (only what install.sh added)
#
# Safe to re-run. Doesn't touch source or build artifacts in the project dir.
# Use `--yes` to skip the confirmation prompt.

set -e

YES=0
if [[ "${1:-}" == "--yes" || "${1:-}" == "-y" ]]; then
    YES=1
fi

INSTALL_DIR="$HOME/.claude-hq"

color_red()    { printf '\033[31m%s\033[0m' "$*"; }
color_green()  { printf '\033[32m%s\033[0m' "$*"; }
color_yellow() { printf '\033[33m%s\033[0m' "$*"; }
step()         { printf '\033[36m==>\033[0m %s\n' "$*"; }

echo
color_red "Claude HQ uninstaller"; echo
echo "──────────────────────────"
echo
echo "This will:"
echo "  • stop any running daemon at $INSTALL_DIR/bin/claude-hq"
echo "  • delete $INSTALL_DIR (including the installed shim)"
echo "  • remove the # claude-hq PATH block from ~/.zshrc and ~/.bashrc (if present)"
echo
echo "It will NOT touch the project source directory or its build artifacts."
echo

if [[ $YES -ne 1 ]]; then
    printf "Proceed? [y/N] "
    read -r REPLY
    case "$REPLY" in
        y|Y|yes|YES) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
fi

if pgrep -f "$INSTALL_DIR/bin/claude-hq" >/dev/null 2>&1; then
    step "Stopping running daemon..."
    pkill -f "$INSTALL_DIR/bin/claude-hq" 2>/dev/null || true
    sleep 0.3
fi

# Remove the Claude Code hooks from ~/.claude/settings.json before we delete the
# binary (the binary knows exactly which entries are ours).
if [[ -x "$INSTALL_DIR/bin/claude-hq" ]]; then
    step "Removing Claude Code hooks"
    "$INSTALL_DIR/bin/claude-hq" uninstall >/dev/null 2>&1 || true
fi

if [[ -d "$INSTALL_DIR" ]]; then
    step "Removing $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
else
    step "$INSTALL_DIR not present (nothing to remove)"
fi

# Strip PATH block from shell rc files (between our markers only).
for RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [[ -f "$RC" ]] && grep -q '# claude-hq:start' "$RC"; then
        step "Removing PATH entry from $RC"
        # Use awk for portability (sed -i differs between BSD/GNU).
        awk '
            /# claude-hq:start/ { skip = 1; next }
            /# claude-hq:end/   { skip = 0; next }
            !skip               { print }
        ' "$RC" > "$RC.tmp"
        mv "$RC.tmp" "$RC"
    fi
done

echo
color_green "✓ Uninstalled."; echo
echo "Open a new terminal (or run 'exec \$SHELL') so the PATH change takes effect."

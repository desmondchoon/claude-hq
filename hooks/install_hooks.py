#!/usr/bin/env python3
"""
Install the Claude HQ hook bridge.

  1. Copies claude_hq_hook.py to ~/.claude-hq/hooks/
  2. Merges the hook commands into ~/.claude/settings.json (backing up first,
     preserving any hooks you already have, and de-duplicating on re-run).

Run once:  python3 hooks/install_hooks.py
Uninstall: python3 hooks/install_hooks.py --uninstall

Honors $HOME, so it's safe to run with a custom HOME for testing.
"""
import os, sys, json, shutil, time

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.environ.get("HOME") or os.path.expanduser("~")
HOOK_SRC = os.path.join(HERE, "claude_hq_hook.py")
SNIPPET = os.path.join(HERE, "settings.snippet.json")
HOOK_DEST_DIR = os.path.join(HOME, ".claude-hq", "hooks")
HOOK_DEST = os.path.join(HOOK_DEST_DIR, "claude_hq_hook.py")
SETTINGS = os.path.join(HOME, ".claude", "settings.json")


def _is_ours(group):
    for h in group.get("hooks", []):
        if "claude_hq_hook.py" in (h.get("command") or ""):
            return True
    return False


def load_settings():
    if os.path.exists(SETTINGS):
        try:
            with open(SETTINGS) as f:
                return json.load(f)
        except Exception:
            print("! existing settings.json is not valid JSON; aborting so we "
                  "don't clobber it. Fix or move it, then re-run.")
            sys.exit(1)
    return {}


def save_settings(data):
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    if os.path.exists(SETTINGS):
        shutil.copy2(SETTINGS, SETTINGS + ".bak-%d" % int(time.time()))
    with open(SETTINGS, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def install():
    os.makedirs(HOOK_DEST_DIR, exist_ok=True)
    shutil.copy2(HOOK_SRC, HOOK_DEST)
    os.chmod(HOOK_DEST, 0o755)
    print("• installed hook script ->", HOOK_DEST)

    with open(SNIPPET) as f:
        snippet = json.load(f)
    settings = load_settings()
    hooks = settings.setdefault("hooks", {})
    for ev, groups in snippet["hooks"].items():
        lst = [g for g in hooks.get(ev, []) if not _is_ours(g)]  # drop stale ours
        lst.extend(groups)
        hooks[ev] = lst
    save_settings(settings)
    print("• merged hooks into ->", SETTINGS, "(backup written)")
    print("\nDone. Start Claude HQ, then run `claude` anywhere — it'll appear in the office.")


def uninstall():
    settings = load_settings()
    hooks = settings.get("hooks", {})
    changed = False
    for ev in list(hooks.keys()):
        kept = [g for g in hooks[ev] if not _is_ours(g)]
        if len(kept) != len(hooks[ev]):
            changed = True
        if kept:
            hooks[ev] = kept
        else:
            del hooks[ev]
    if changed:
        save_settings(settings)
        print("• removed Claude HQ hooks from", SETTINGS)
    if os.path.exists(HOOK_DEST):
        os.remove(HOOK_DEST)
        print("• removed", HOOK_DEST)
    print("Uninstalled.")


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall()
    else:
        install()

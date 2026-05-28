#!/usr/bin/env python3
"""
Claude HQ — hook bridge.

Installed as a Claude Code hook command (see settings.snippet.json). Claude Code
runs it on lifecycle events, passing a JSON payload on stdin. We translate that
into a Claude HQ activity event and POST it to the running daemon, so any
`claude` session — launched from a terminal, an editor, anywhere — shows up in
the office, with accurate tool names instead of screen-scraped guesses.

Dependency-free (stdlib only). Always exits 0 and never blocks Claude: if the
daemon isn't running, it silently no-ops.

Env (for testing):
  CLAUDE_HQ_DEBUG=1    print the events it would send to stderr
  CLAUDE_HQ_DRYRUN=1   don't actually POST
"""
import sys, os, json, urllib.request

PORTS = range(7823, 7834)  # matches the daemon's DEFAULT_PORT_START..END
DEBUG = bool(os.environ.get("CLAUDE_HQ_DEBUG"))
DRYRUN = bool(os.environ.get("CLAUDE_HQ_DRYRUN"))


def post(session_id, event, agent_id=None):
    body = {"session_id": session_id, "event": event}
    if agent_id:
        body["agent_id"] = agent_id
    if DEBUG:
        sys.stderr.write("[claude-hq-hook] " + json.dumps(body) + "\n")
    if DRYRUN:
        return True
    data = json.dumps(body).encode()
    for p in PORTS:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:%d/event" % p,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=0.3)
            return True
        except Exception:
            continue
    return False


def events_for(ev, d):
    """Map a hook event + payload to zero or more activity events."""
    cwd = d.get("cwd")
    out = []
    if ev == "SessionStart":
        out.append({"type": "start"})
        if cwd:
            out.append({"type": "cwd", "path": cwd})
    elif ev == "UserPromptSubmit":
        if cwd:
            out.append({"type": "cwd", "path": cwd})
        out.append({"type": "thinking"})
    elif ev == "PreToolUse":
        out.append({"type": "tool_call", "tool": d.get("tool_name") or "tool"})
    elif ev == "PostToolUse":
        out.append({"type": "thinking"})  # Claude resumes after the tool returns
    elif ev == "PreCompact":
        out.append({"type": "compacting"})
    elif ev == "Notification":
        msg = (d.get("message") or "").lower()
        # idle "waiting for your input" vs a permission/approval prompt
        out.append({"type": "asking"} if "waiting" in msg or "idle" in msg
                   else {"type": "awaiting_permission"})
    elif ev == "Stop":
        out.append({"type": "done"})
    elif ev == "SessionEnd":
        # Session is terminating — walk the agent out so orphans don't pile up
        # when an external `claude` exits without finishing a turn (Ctrl-C,
        # window closed, etc.).
        out.append({"type": "session_end"})
    # SubagentStart/SubagentStop: left for the transcript tailer (it has stable ids)
    return out


def main():
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
    except Exception:
        raw = ""
    try:
        d = json.loads(raw) if raw.strip() else {}
    except Exception:
        d = {}
    ev = d.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "")
    # If claude was spawned from inside Claude HQ, prefer the HQ-owned session
    # id (set by pty_spawn via env) so the hook events correlate with the
    # on-screen agent the app already created.
    sid = os.environ.get("CLAUDE_HQ_OWNER") or d.get("session_id") or "claude-code"
    for e in events_for(ev, d):
        try:
            post(sid, e)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)  # never block Claude, whatever happened

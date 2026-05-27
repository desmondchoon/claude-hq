#!/usr/bin/env python3
"""
Claude HQ — session-transcript tailer.

Watches ~/.claude/projects/**/*.jsonl (Claude Code's per-session transcripts)
and turns new lines into Claude HQ activity events, POSTed to the running
daemon. This is a *passive, zero-config* producer: every `claude` session that
writes a transcript shows up in the office — no shim, no hooks, no matter how it
was launched — with real tool names, model, and working directory.

Run alongside the app:   python3 tools/transcript_tailer.py
Test once (no daemon):   CLAUDE_HQ_DEBUG=1 CLAUDE_HQ_DRYRUN=1 \
                         python3 tools/transcript_tailer.py --once [--root DIR]

Dependency-free (stdlib only).
"""
import os, sys, re, json, glob, time, urllib.request

PORTS = range(7823, 7834)
HOME = os.environ.get("HOME") or os.path.expanduser("~")
ROOT = os.path.join(HOME, ".claude", "projects")
DEBUG = bool(os.environ.get("CLAUDE_HQ_DEBUG"))
DRYRUN = bool(os.environ.get("CLAUDE_HQ_DRYRUN"))
IDLE_DONE = float(os.environ.get("CLAUDE_HQ_IDLE_DONE", "180"))  # secs; 0 disables
POLL = 1.0

offsets = {}            # path -> byte offset already consumed
seen = set()            # session ids we've emitted 'start' for
modeled = set()         # session ids we've emitted 'model' for
last_seen = {}          # session id -> last activity monotonic time
done_sent = set()


def post(session_id, event, agent_id=None):
    body = {"session_id": session_id, "event": event}
    if agent_id:
        body["agent_id"] = agent_id
    if DEBUG:
        sys.stderr.write("[tailer] " + json.dumps(body) + "\n")
    if DRYRUN:
        return
    data = json.dumps(body).encode()
    for p in PORTS:
        try:
            req = urllib.request.Request("http://127.0.0.1:%d/event" % p,
                                         data=data, headers={"Content-Type": "application/json"},
                                         method="POST")
            urllib.request.urlopen(req, timeout=0.3)
            return
        except Exception:
            continue


def shorten_model(m):
    m = (m or "").lower()
    base = next((b for b in ("opus", "sonnet", "haiku") if b in m), None)
    if not base:
        return m or None
    ver = re.search(r"(\d+)[-.](\d+)", m)
    return "%s-%s.%s" % (base, ver.group(1), ver.group(2)) if ver else base


def handle_record(rec):
    sid = rec.get("sessionId") or rec.get("session_id")
    if not sid:
        return
    # subagent (Task) entries are sidechains; give them their own lane if we can
    agent_id = None
    if rec.get("isSidechain"):
        agent_id = "sub-" + str(rec.get("parentUuid") or rec.get("uuid") or "x")[:6]

    if sid not in seen:
        seen.add(sid)
        post(sid, {"type": "start"})
        if rec.get("cwd"):
            post(sid, {"type": "cwd", "path": rec["cwd"]})

    msg = rec.get("message") or {}
    model = msg.get("model")
    if model and sid not in modeled:
        modeled.add(sid)
        nm = shorten_model(model)
        if nm:
            post(sid, {"type": "model", "name": nm})

    typ = rec.get("type")
    if typ == "assistant":
        content = msg.get("content")
        blocks = content if isinstance(content, list) else ([{"type": "text", "text": content}] if isinstance(content, str) else [])
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "tool_use":
                post(sid, {"type": "tool_call", "tool": b.get("name") or "tool"}, agent_id)
            elif bt == "thinking":
                post(sid, {"type": "thinking"}, agent_id)
            elif bt == "text":
                txt = b.get("text") or ""
                if txt.strip():
                    post(sid, {"type": "output", "chars": len(txt)}, agent_id)
    # 'user'/'system'/'summary' records: ignore content, but they still count as activity

    last_seen[sid] = time.monotonic()
    done_sent.discard(sid)


def read_new(path):
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    off = offsets.get(path, 0)
    if size < off:          # file truncated/rotated
        off = 0
    if size == off:
        return
    try:
        with open(path, "r", errors="replace") as f:
            f.seek(off)
            chunk = f.read()
            offsets[path] = f.tell()
    except OSError:
        return
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            handle_record(json.loads(line))
        except Exception:
            continue


def sweep_idle():
    if IDLE_DONE <= 0:
        return
    now = time.monotonic()
    for sid, t in list(last_seen.items()):
        if sid not in done_sent and now - t > IDLE_DONE:
            post(sid, {"type": "done"})
            done_sent.add(sid)


def main():
    root = ROOT
    once = "--once" in sys.argv
    if "--root" in sys.argv:
        root = sys.argv[sys.argv.index("--root") + 1]
    if DEBUG:
        sys.stderr.write("[tailer] watching %s (once=%s)\n" % (root, once))
    # First pass: on a normal run, skip to end of existing files so we only
    # report *new* activity. In --once mode we read everything (for testing).
    if not once:
        for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            try:
                offsets[path] = os.path.getsize(path)
            except OSError:
                pass
    while True:
        for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            read_new(path)
        sweep_idle()
        if once:
            break
        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

//! HQ-spawned PTY sessions exposed to the frontend.
//!
//! The frontend asks for a new agent via `pty_spawn(cwd, args)`. We launch
//! `claude` in a real PTY, return an HQ-owned session id, and stream output
//! back over Tauri events (`pty:output` / `pty:exit`). Input is pushed in
//! with `pty_write` and the terminal is resized with `pty_resize`.
//!
//! Correlation with Claude Code: we set `CLAUDE_HQ_OWNER=<session-id>` in the
//! spawned process's env. The hook (see hooks/claude_hq_hook.py) reads that
//! and uses it as the session_id, so the hook-emitted activity events line up
//! with the on-screen agent we created here.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use portable_pty::{native_pty_system, ChildKiller, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};

use claude_hq_core::event::{to_json, wrap_payload, EventPayload};
use claude_hq_core::parser::ActivityEvent;

use crate::ws::EventTx;

pub struct PtySession {
    /// Writer side of the master PTY. We keep it behind a mutex so multiple
    /// `pty_write` calls don't interleave.
    writer: Mutex<Box<dyn Write + Send>>,
    /// Owning handle on the master — used for resize.
    master: Mutex<Box<dyn MasterPty + Send>>,
    /// Separate killer handle; the child itself is moved into the waiter
    /// thread (which blocks on wait()), so we can't share it for kill.
    killer: Mutex<Box<dyn ChildKiller + Send + Sync>>,
}

#[derive(Default)]
pub struct PtyState {
    sessions: Mutex<HashMap<String, Arc<PtySession>>>,
}

#[derive(Clone, Serialize)]
struct PtyOutput {
    session_id: String,
    /// base64-encoded raw PTY bytes (binary-safe; xterm.js decodes).
    data_b64: String,
}

#[derive(Clone, Serialize)]
struct PtyExit {
    session_id: String,
    code: i32,
}

fn make_id() -> String {
    let pid = std::process::id();
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("hq-{}-{}", pid, ts)
}

/// Ask the user's login shell for its PATH.
///
/// macOS app bundles start with a stripped system PATH. We try the shell with
/// both interactive+login flags (sources .zshrc AND .zprofile) and fall back
/// to login-only. Returns None if the subprocess fails or produces no output.
fn shell_path() -> Option<std::ffi::OsString> {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/zsh".to_string());
    // Try interactive+login first so that .zshrc is sourced (nvm, rbenv, etc.
    // are commonly configured there rather than in .zprofile).
    for args in [
        vec!["-i", "-l", "-c", "echo $PATH"],
        vec!["-l", "-c", "echo $PATH"],
    ] {
        if let Ok(out) = std::process::Command::new(&shell).args(&args).output() {
            if out.status.success() {
                if let Ok(s) = String::from_utf8(out.stdout) {
                    let trimmed = s.trim();
                    if !trimmed.is_empty() {
                        return Some(trimmed.into());
                    }
                }
            }
        }
    }
    None
}

/// Return well-known directories where `claude` is commonly installed,
/// regardless of the current PATH. Used as a last-resort fallback when the
/// app bundle's PATH and the login-shell PATH both come up empty.
fn common_claude_dirs() -> Vec<std::path::PathBuf> {
    let mut dirs = Vec::new();
    let home = match dirs::home_dir() {
        Some(h) => h,
        None => return dirs,
    };

    // Explicit well-known prefixes (order = search priority)
    for rel in [
        ".local/bin",
        ".volta/bin",
        ".npm-global/bin",
        ".yarn/bin",
    ] {
        dirs.push(home.join(rel));
    }
    dirs.push(std::path::PathBuf::from("/opt/homebrew/bin"));
    dirs.push(std::path::PathBuf::from("/usr/local/bin"));

    // nvm: scan all installed node versions (newest first by lexicographic sort)
    let nvm_root = std::env::var_os("NVM_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| home.join(".nvm"));
    let versions_dir = nvm_root.join("versions/node");
    if let Ok(entries) = std::fs::read_dir(&versions_dir) {
        let mut versions: Vec<_> = entries.flatten().map(|e| e.path()).collect();
        versions.sort_by(|a, b| b.cmp(a));
        for v in versions {
            dirs.push(v.join("bin"));
        }
    }

    dirs
}

/// Build a merged, deduplicated PATH: process PATH, then login-shell PATH,
/// then common install locations. Keeps the first occurrence of each dir.
pub fn expanded_path() -> std::ffi::OsString {
    let mut result: Vec<std::path::PathBuf> = Vec::new();
    let mut seen = std::collections::HashSet::new();

    let proc = std::env::var_os("PATH").unwrap_or_default();
    let shell = shell_path().unwrap_or_default();

    for raw in [proc.as_os_str(), shell.as_os_str()] {
        for d in std::env::split_paths(raw) {
            if seen.insert(d.clone()) {
                result.push(d);
            }
        }
    }
    for d in common_claude_dirs() {
        if seen.insert(d.clone()) {
            result.push(d);
        }
    }

    std::env::join_paths(result).unwrap_or(proc)
}

/// Find the real `claude` on PATH, skipping the HQ shim install dir so we
/// don't end up wrapping ourselves twice.
fn find_real_claude() -> Option<std::path::PathBuf> {
    let path = expanded_path();
    let shim_dir = dirs::home_dir().map(|h| h.join(".claude-hq").join("bin"));
    for dir in std::env::split_paths(&path) {
        if let Some(ref sd) = shim_dir {
            if &dir == sd {
                continue;
            }
        }
        let candidate = dir.join("claude");
        if let Ok(meta) = std::fs::metadata(&candidate) {
            use std::os::unix::fs::PermissionsExt;
            if meta.is_file() && meta.permissions().mode() & 0o111 != 0 {
                return Some(candidate);
            }
        }
    }
    None
}

#[tauri::command]
pub fn pty_spawn(
    app: AppHandle,
    state: State<'_, PtyState>,
    cwd: Option<String>,
    args: Option<Vec<String>>,
    rows: Option<u16>,
    cols: Option<u16>,
) -> Result<String, String> {
    let real_claude = find_real_claude()
        .ok_or_else(|| "could not find `claude` on PATH — install Claude Code first".to_string())?;

    let pty_system = native_pty_system();
    let size = PtySize {
        rows: rows.unwrap_or(30),
        cols: cols.unwrap_or(100),
        pixel_width: 0,
        pixel_height: 0,
    };
    let pair = pty_system
        .openpty(size)
        .map_err(|e| format!("openpty failed: {e}"))?;

    let session_id = make_id();

    let mut cmd = CommandBuilder::new(&real_claude);
    if let Some(args) = args {
        for a in args {
            cmd.arg(a);
        }
    }
    let cwd_path: std::path::PathBuf = cwd
        .as_deref()
        .map(Path::new)
        .filter(|p| p.is_dir())
        .map(|p| p.to_path_buf())
        .or_else(dirs::home_dir)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| ".".into()));
    cmd.cwd(&cwd_path);

    // Inherit current env so users get their API keys / etc.
    for (k, v) in std::env::vars_os() {
        cmd.env(k, v);
    }
    // Override PATH with the expanded shell PATH so that claude and anything
    // it spawns can find node, git, and other tools the user has on their PATH.
    cmd.env("PATH", expanded_path());
    // Tag the spawn so the hook can re-key its events onto our session id.
    cmd.env("CLAUDE_HQ_OWNER", &session_id);
    // xterm.js identifies as xterm-256color — claude renders well there.
    cmd.env("TERM", "xterm-256color");

    let mut child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("spawn failed: {e}"))?;
    drop(pair.slave);

    let killer = child.clone_killer();

    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("clone_reader failed: {e}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|e| format!("take_writer failed: {e}"))?;

    let session = Arc::new(PtySession {
        writer: Mutex::new(writer),
        master: Mutex::new(pair.master),
        killer: Mutex::new(killer),
    });
    state
        .sessions
        .lock()
        .unwrap()
        .insert(session_id.clone(), session.clone());

    // Emit a synthetic start + cwd through the WS broadcast so the office
    // shows the agent immediately, before any hook fires.
    if let Some(tx) = app.try_state::<EventTx>() {
        let start = wrap_payload(EventPayload {
            session_id: session_id.clone(),
            agent_id: None,
            parent_id: None,
            event: ActivityEvent::Start,
        });
        let _ = tx.send(to_json(&start));
        let cwd_ev = wrap_payload(EventPayload {
            session_id: session_id.clone(),
            agent_id: None,
            parent_id: None,
            event: ActivityEvent::Cwd {
                path: cwd_path.display().to_string(),
            },
        });
        let _ = tx.send(to_json(&cwd_ev));
    }

    // Reader thread: pump PTY bytes to the webview as a `pty:output` event.
    {
        let session_id = session_id.clone();
        let app = app.clone();
        std::thread::spawn(move || {
            let mut buf = [0u8; 4096];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        let payload = PtyOutput {
                            session_id: session_id.clone(),
                            data_b64: B64.encode(&buf[..n]),
                        };
                        let _ = app.emit("pty:output", payload);
                    }
                    Err(_) => break,
                }
            }
        });
    }

    // Waiter thread owns the child outright so it can block on wait()
    // without holding any session lock — kill goes through the separate
    // killer handle stored on the session.
    {
        let session_id = session_id.clone();
        let app = app.clone();
        std::thread::spawn(move || {
            let code = match child.wait() {
                Ok(s) if s.success() => 0,
                Ok(s) => s.exit_code() as i32,
                Err(_) => 1,
            };
            // Drop the child so the master EOFs and the reader thread exits.
            drop(child);
            let _ = app.emit(
                "pty:exit",
                PtyExit {
                    session_id: session_id.clone(),
                    code,
                },
            );
            if let Some(state) = app.try_state::<PtyState>() {
                state.sessions.lock().unwrap().remove(&session_id);
            }
        });
    }

    Ok(session_id)
}

#[tauri::command]
pub fn pty_write(
    state: State<'_, PtyState>,
    session_id: String,
    data_b64: String,
) -> Result<(), String> {
    let session = {
        let map = state.sessions.lock().unwrap();
        map.get(&session_id).cloned()
    }
    .ok_or_else(|| format!("unknown session {session_id}"))?;
    let bytes = B64
        .decode(data_b64.as_bytes())
        .map_err(|e| format!("bad base64: {e}"))?;
    let mut w = session.writer.lock().unwrap();
    w.write_all(&bytes).map_err(|e| format!("write: {e}"))?;
    w.flush().map_err(|e| format!("flush: {e}"))?;
    Ok(())
}

#[tauri::command]
pub fn pty_resize(
    state: State<'_, PtyState>,
    session_id: String,
    rows: u16,
    cols: u16,
) -> Result<(), String> {
    let session = {
        let map = state.sessions.lock().unwrap();
        map.get(&session_id).cloned()
    }
    .ok_or_else(|| format!("unknown session {session_id}"))?;
    let master = session.master.lock().unwrap();
    master
        .resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("resize: {e}"))?;
    Ok(())
}

#[tauri::command]
pub fn pty_kill(state: State<'_, PtyState>, session_id: String) -> Result<(), String> {
    let session = {
        let map = state.sessions.lock().unwrap();
        map.get(&session_id).cloned()
    }
    .ok_or_else(|| format!("unknown session {session_id}"))?;
    let mut killer = session.killer.lock().unwrap();
    let _ = killer.kill();
    Ok(())
}

/// List immediate subdirectory names of `path`. Powers the spawn dialog's
/// path autocomplete. Returns just basenames so the frontend can compose the
/// full path itself. Hidden entries (leading dot) are omitted unless
/// `include_hidden` is set — the frontend toggles this on when the user is
/// typing a leaf that starts with `.`.
#[tauri::command]
pub fn list_dir(path: String, include_hidden: Option<bool>) -> Result<Vec<String>, String> {
    let p = Path::new(&path);
    if !p.is_dir() {
        return Err(format!("not a directory: {path}"));
    }
    let show_hidden = include_hidden.unwrap_or(false);
    let mut out: Vec<String> = std::fs::read_dir(p)
        .map_err(|e| format!("read_dir: {e}"))?
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().map(|t| t.is_dir()).unwrap_or(false))
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|name| show_hidden || !name.starts_with('.'))
        .collect();
    out.sort_by_key(|s| s.to_lowercase());
    Ok(out)
}

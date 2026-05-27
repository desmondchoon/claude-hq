use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;

use serde_json::{json, Value};

const SHIM_BIN_NAME: &str = "claude-hq-shim";
const INSTALLED_NAME: &str = "claude";

// The hook bridge, embedded at compile time so the daemon binary is fully
// self-contained — `install` writes this out and points settings.json at it.
const HOOK_SCRIPT: &str = include_str!("../../hooks/claude_hq_hook.py");

// (Claude Code hook event, whether the entry needs a `matcher` field)
const HOOK_EVENTS: &[(&str, bool)] = &[
    ("SessionStart", false),
    ("UserPromptSubmit", false),
    ("PreToolUse", true),
    ("PostToolUse", true),
    ("Notification", false),
    ("PreCompact", false),
    ("Stop", false),
];

fn home() -> Option<PathBuf> {
    dirs::home_dir()
}
fn hq_dir() -> Option<PathBuf> {
    home().map(|h| h.join(".claude-hq"))
}
fn install_dir() -> Option<PathBuf> {
    hq_dir().map(|d| d.join("bin"))
}

// =====================================================================
// Default install path: Claude Code hooks → daemon /event
// =====================================================================

fn group_is_ours(g: &Value) -> bool {
    g.get("hooks")
        .and_then(|h| h.as_array())
        .map_or(false, |arr| {
            arr.iter().any(|h| {
                h.get("command")
                    .and_then(|c| c.as_str())
                    .map_or(false, |c| c.contains("claude_hq_hook.py"))
            })
        })
}

fn read_settings(path: &PathBuf) -> Value {
    match std::fs::read_to_string(path) {
        Ok(s) if !s.trim().is_empty() => serde_json::from_str(&s).unwrap_or_else(|_| json!({})),
        _ => json!({}),
    }
}

fn write_settings(path: &PathBuf, v: &Value) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    if path.exists() {
        let _ = std::fs::copy(path, path.with_extension("json.bak"));
    }
    let mut s = serde_json::to_string_pretty(v).unwrap_or_else(|_| "{}".into());
    s.push('\n');
    std::fs::write(path, s)
}

fn remove_shim_quiet() {
    if let Some(dir) = install_dir() {
        let _ = std::fs::remove_file(dir.join(INSTALLED_NAME));
    }
}

pub fn install_hooks() -> i32 {
    let Some(hq) = hq_dir() else {
        eprintln!("[claude-hq install] could not resolve home directory");
        return 1;
    };

    // 1) write the hook bridge script
    let hooks_dir = hq.join("hooks");
    if let Err(e) = std::fs::create_dir_all(&hooks_dir) {
        eprintln!("[claude-hq install] failed to create {}: {}", hooks_dir.display(), e);
        return 1;
    }
    let script = hooks_dir.join("claude_hq_hook.py");
    if let Err(e) = std::fs::write(&script, HOOK_SCRIPT) {
        eprintln!("[claude-hq install] failed to write {}: {}", script.display(), e);
        return 1;
    }
    if let Ok(meta) = std::fs::metadata(&script) {
        let mut perms = meta.permissions();
        perms.set_mode(0o755);
        let _ = std::fs::set_permissions(&script, perms);
    }

    // 2) merge our hook commands into ~/.claude/settings.json (preserving the
    //    user's own hooks, de-duplicating on re-install).
    let Some(h) = home() else {
        eprintln!("[claude-hq install] could not resolve home directory");
        return 1;
    };
    let settings_path = h.join(".claude").join("settings.json");
    let mut settings = read_settings(&settings_path);
    if !settings.is_object() {
        settings = json!({});
    }
    {
        let obj = settings.as_object_mut().unwrap();
        let hooks_entry = obj.entry("hooks").or_insert_with(|| json!({}));
        if !hooks_entry.is_object() {
            *hooks_entry = json!({});
        }
        let hooks_obj = hooks_entry.as_object_mut().unwrap();
        for (event, needs_matcher) in HOOK_EVENTS {
            let cmd = format!("python3 $HOME/.claude-hq/hooks/claude_hq_hook.py {}", event);
            let group = if *needs_matcher {
                json!({ "matcher": "", "hooks": [ { "type": "command", "command": cmd } ] })
            } else {
                json!({ "hooks": [ { "type": "command", "command": cmd } ] })
            };
            let arr_entry = hooks_obj.entry((*event).to_string()).or_insert_with(|| json!([]));
            if !arr_entry.is_array() {
                *arr_entry = json!([]);
            }
            let list = arr_entry.as_array_mut().unwrap();
            list.retain(|g| !group_is_ours(g)); // drop stale copies of ours
            list.push(group);
        }
    }
    if let Err(e) = write_settings(&settings_path, &settings) {
        eprintln!("[claude-hq install] failed to write {}: {}", settings_path.display(), e);
        return 1;
    }

    // 3) retire any previously-installed shim so a session isn't counted twice
    remove_shim_quiet();

    println!("[claude-hq install] installed hooks → {}", settings_path.display());
    println!();
    println!("Done. With Claude HQ open, run `claude ...` anywhere — terminal or an");
    println!("editor that uses Claude Code — and the session shows up in the office.");
    println!("No PATH changes needed. Requires python3 (preinstalled on macOS).");
    println!("Uninstall any time with:  claude-hq uninstall");
    0
}

pub fn uninstall_hooks() -> i32 {
    let Some(h) = home() else {
        eprintln!("[claude-hq uninstall] could not resolve home directory");
        return 1;
    };
    let settings_path = h.join(".claude").join("settings.json");
    if settings_path.exists() {
        let mut settings = read_settings(&settings_path);
        if let Some(obj) = settings.as_object_mut() {
            if let Some(hooks_obj) = obj.get_mut("hooks").and_then(|v| v.as_object_mut()) {
                let keys: Vec<String> = hooks_obj.keys().cloned().collect();
                for k in keys {
                    let mut empty = false;
                    if let Some(arr) = hooks_obj.get_mut(&k).and_then(|v| v.as_array_mut()) {
                        arr.retain(|g| !group_is_ours(g));
                        empty = arr.is_empty();
                    }
                    if empty {
                        hooks_obj.remove(&k);
                    }
                }
            }
        }
        let _ = write_settings(&settings_path, &settings);
        println!(
            "[claude-hq uninstall] removed Claude HQ hooks from {}",
            settings_path.display()
        );
    }
    if let Some(hq) = hq_dir() {
        let _ = std::fs::remove_file(hq.join("hooks").join("claude_hq_hook.py"));
    }
    0
}

// =====================================================================
// Legacy: PTY shim install (kept for `claude-hq install-shim`)
// =====================================================================

fn locate_shim_binary() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    let candidates = [
        dir.join(SHIM_BIN_NAME),
        dir.join(format!("{}.exe", SHIM_BIN_NAME)),
    ];
    candidates.into_iter().find(|p| p.exists())
}

pub fn install_shim() -> i32 {
    let Some(src) = locate_shim_binary() else {
        eprintln!(
            "[claude-hq install-shim] could not find `{}` next to the daemon binary.",
            SHIM_BIN_NAME
        );
        eprintln!("  Make sure you've built it: cargo build --bin claude-hq-shim");
        return 1;
    };

    let Some(dir) = install_dir() else {
        eprintln!("[claude-hq install-shim] could not resolve home directory");
        return 1;
    };

    if let Err(e) = std::fs::create_dir_all(&dir) {
        eprintln!("[claude-hq install-shim] failed to create {}: {}", dir.display(), e);
        return 1;
    }

    let dst = dir.join(INSTALLED_NAME);
    let _ = std::fs::remove_file(&dst);

    if let Err(e) = std::fs::copy(&src, &dst) {
        eprintln!("[claude-hq install-shim] failed to copy shim to {}: {}", dst.display(), e);
        return 1;
    }

    if let Ok(meta) = std::fs::metadata(&dst) {
        let mut perms = meta.permissions();
        perms.set_mode(0o755);
        let _ = std::fs::set_permissions(&dst, perms);
    }

    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("codesign")
            .args(["--force", "--sign", "-"])
            .arg(&dst)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }

    println!("[claude-hq install-shim] installed shim → {}", dst.display());
    println!();
    println!("Add this line to ~/.zshrc (or ~/.bashrc) if not present, then restart your shell:");
    println!();
    println!("    export PATH=\"$HOME/.claude-hq/bin:$PATH\"");
    println!();
    println!("Note: the default integration is now hooks (`claude-hq install`), which");
    println!("needs no PATH change and also captures editor-launched sessions.");
    0
}

pub fn uninstall_shim() -> i32 {
    let Some(dir) = install_dir() else {
        eprintln!("[claude-hq uninstall-shim] could not resolve home directory");
        return 1;
    };
    let dst = dir.join(INSTALLED_NAME);
    match std::fs::remove_file(&dst) {
        Ok(()) => {
            println!("[claude-hq uninstall-shim] removed {}", dst.display());
            0
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            println!("[claude-hq uninstall-shim] nothing to remove at {}", dst.display());
            0
        }
        Err(e) => {
            eprintln!("[claude-hq uninstall-shim] failed: {}", e);
            1
        }
    }
}

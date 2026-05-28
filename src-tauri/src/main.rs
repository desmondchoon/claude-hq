#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod git;
mod install;
mod pty;
mod ws;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, WindowEvent,
};
use tokio::sync::broadcast;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if let Some(sub) = args.first() {
        match sub.as_str() {
            "install" => std::process::exit(install::install_hooks()),
            "uninstall" => std::process::exit(install::uninstall_hooks()),
            "install-shim" => std::process::exit(install::install_shim()),
            "uninstall-shim" => std::process::exit(install::uninstall_shim()),
            "--help" | "-h" | "help" => {
                print_help();
                return;
            }
            _ => {}
        }
    }

    let (tx, _rx) = broadcast::channel::<String>(256);
    let tx_ws = tx.clone();
    let tx_state = tx.clone();

    tauri::Builder::default()
        .manage(tx_state)
        .manage(pty::PtyState::default())
        .invoke_handler(tauri::generate_handler![
            pty::pty_spawn,
            pty::pty_write,
            pty::pty_resize,
            pty::pty_kill,
            pty::list_dir,
            git::git_exec,
        ])
        .setup(move |app| {
            // First launch from a freshly-installed .app: wire up Claude Code
            // hooks automatically so the user doesn't have to find the tray
            // menu. Idempotent — guarded by a marker file.
            install::first_run_setup_if_needed();

            // WS + HTTP server on tokio runtime.
            let tx_ws = tx_ws.clone();
            tauri::async_runtime::spawn(async move {
                ws::start_ws_server(tx_ws).await;
            });

            // Catch SIGINT / SIGTERM so Ctrl-C in a terminal exits cleanly.
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                use tokio::signal::unix::{signal, SignalKind};
                let mut term = match signal(SignalKind::terminate()) {
                    Ok(s) => s,
                    Err(_) => return,
                };
                let mut intr = match signal(SignalKind::interrupt()) {
                    Ok(s) => s,
                    Err(_) => return,
                };
                tokio::select! {
                    _ = term.recv() => {}
                    _ = intr.recv() => {}
                }
                eprintln!("[claude-hq] shutting down");
                app_handle.exit(0);
            });

            // Tray
            let install_i = MenuItem::with_id(
                app,
                "install",
                "Install Claude HQ hooks…",
                true,
                None::<&str>,
            )?;
            let uninstall_i = MenuItem::with_id(
                app,
                "uninstall",
                "Uninstall hooks",
                true,
                None::<&str>,
            )?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit Claude HQ", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&install_i, &uninstall_i, &quit_i])?;

            // Dedicated monochrome menu-bar glyph (a clean person bust). Raw
            // 44x44 RGBA so it needs no image-decode cargo features; macOS
            // themes it for light/dark via icon_as_template.
            let tray_icon =
                tauri::image::Image::new(include_bytes!("../icons/tray.rgba"), 44, 44);

            let _tray = TrayIconBuilder::new()
                .icon(tray_icon)
                .icon_as_template(true)
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => app.exit(0),
                    "install" => {
                        let _ = install::install_hooks();
                    }
                    "uninstall" => {
                        let _ = install::uninstall_hooks();
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        // Closing the window quits the whole app (instead of leaving the
        // daemon running in the tray).
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                window.app_handle().exit(0);
            }
        })
        .run(tauri::generate_context!())
        .expect("Failed to run Tauri app");
}

fn print_help() {
    println!(
        r#"claude-hq — pixel art companion for Claude Code

USAGE:
  claude-hq                Run the daemon (window + menu bar)
  claude-hq install        Install Claude Code hooks (default integration)
  claude-hq uninstall      Remove the hooks
  claude-hq install-shim   (legacy) install the PTY `claude` shim instead
  claude-hq uninstall-shim (legacy) remove the shim
  claude-hq help           Show this message

`install` writes a small hook into ~/.claude/settings.json (and a helper
script under ~/.claude-hq/hooks). No PATH change needed. With the daemon
running, every `claude` session — from a terminal or an editor that uses
Claude Code — shows up in the office. Requires python3 (preinstalled on
macOS). If the daemon is closed, the hooks just no-op.

The daemon exits when you close the window, quit from the menu bar,
or press Ctrl-C in the terminal it was launched from."#
    );
}

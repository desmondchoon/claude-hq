//! `claude-hq-shim` — transparent wrapper that runs the real `claude` inside a
//! PTY, mirrors all I/O to the user's terminal, and reports parsed activity
//! events to the Claude HQ daemon over HTTP. If the daemon isn't running, it
//! degrades silently — `claude` still works.
//!
//! Installed as `~/.claude-hq/bin/claude` so users keep typing `claude` as normal.

use std::io::{Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::sync::Arc;
use std::time::Duration;

use nix::sys::signal::{self, SigHandler, Signal};
use nix::sys::termios::{self, SetArg};
use nix::unistd::isatty;
use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};

use claude_hq_core::{
    event::{make_session_id, EventPayload},
    parser::{normalize_model_name, ActivityEvent, ParseOutput, Parser},
};

const DAEMON_HOST: &str = "127.0.0.1";

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();

    let real_claude = match find_real_claude() {
        Some(p) => p,
        None => {
            eprintln!(
                "claude-hq-shim: cannot find real `claude` on PATH (excluding ~/.claude-hq/bin)."
            );
            eprintln!("  Install Claude Code, then re-run.");
            std::process::exit(127);
        }
    };

    let stdin_tty = isatty(0).unwrap_or(false);
    let stdout_tty = isatty(1).unwrap_or(false);
    if !stdin_tty || !stdout_tty {
        let err = std::process::Command::new(&real_claude).args(&args).exec();
        eprintln!(
            "claude-hq-shim: failed to exec {}: {}",
            real_claude.display(),
            err
        );
        std::process::exit(127);
    }

    std::process::exit(run_wrapped(&real_claude, args));
}

// ---- locate real claude ----

fn find_real_claude() -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    let install_dir = dirs::home_dir().map(|h| h.join(".claude-hq").join("bin"));
    for dir in std::env::split_paths(&path) {
        if let Some(ref id) = install_dir {
            if dir == *id {
                continue;
            }
        }
        let candidate = dir.join("claude");
        if is_executable_file(&candidate) {
            return Some(candidate);
        }
    }
    None
}

fn is_executable_file(p: &Path) -> bool {
    match std::fs::metadata(p) {
        Ok(meta) if meta.is_file() => meta.permissions().mode() & 0o111 != 0,
        _ => false,
    }
}

/// Inspect args + env for an explicit model selection so we can label the agent
/// before claude's own startup output (if any) tells us.
fn detect_model_from_args(args: &[String]) -> Option<String> {
    for (i, a) in args.iter().enumerate() {
        if a == "--model" || a == "-m" {
            if let Some(v) = args.get(i + 1) {
                return Some(normalize_model_name(v));
            }
        }
        if let Some(v) = a.strip_prefix("--model=") {
            return Some(normalize_model_name(v));
        }
    }
    if let Ok(v) = std::env::var("ANTHROPIC_MODEL") {
        if !v.is_empty() {
            return Some(normalize_model_name(&v));
        }
    }
    None
}

// ---- termios RAII ----

struct TermiosGuard {
    fd: i32,
    original: termios::Termios,
}

impl TermiosGuard {
    fn enter_raw(fd: i32) -> Option<Self> {
        let bf = unsafe { std::os::fd::BorrowedFd::borrow_raw(fd) };
        let original = termios::tcgetattr(bf).ok()?;
        let mut raw = original.clone();
        termios::cfmakeraw(&mut raw);
        termios::tcsetattr(bf, SetArg::TCSANOW, &raw).ok()?;
        Some(Self { fd, original })
    }
}

impl Drop for TermiosGuard {
    fn drop(&mut self) {
        let bf = unsafe { std::os::fd::BorrowedFd::borrow_raw(self.fd) };
        let _ = termios::tcsetattr(bf, SetArg::TCSANOW, &self.original);
    }
}

// ---- SIGWINCH ----

static WINCH_FIRED: AtomicBool = AtomicBool::new(false);

extern "C" fn handle_winch(_: i32) {
    WINCH_FIRED.store(true, Ordering::Relaxed);
}

fn install_winch_handler() {
    unsafe {
        let _ = signal::signal(Signal::SIGWINCH, SigHandler::Handler(handle_winch));
    }
}

fn current_winsize(fd: i32) -> PtySize {
    let mut ws: libc::winsize = unsafe { std::mem::zeroed() };
    let r = unsafe { libc::ioctl(fd, libc::TIOCGWINSZ, &mut ws) };
    if r == 0 && ws.ws_row > 0 && ws.ws_col > 0 {
        PtySize {
            rows: ws.ws_row,
            cols: ws.ws_col,
            pixel_width: ws.ws_xpixel,
            pixel_height: ws.ws_ypixel,
        }
    } else {
        PtySize {
            rows: 24,
            cols: 80,
            pixel_width: 0,
            pixel_height: 0,
        }
    }
}

// ---- HTTP event sender ----

#[derive(Clone)]
struct OutboundEvent {
    agent_id: Option<String>,
    event: ActivityEvent,
}

fn spawn_event_sender(
    session_id: String,
    port_start: u16,
    port_end: u16,
) -> mpsc::Sender<OutboundEvent> {
    let (tx, rx) = mpsc::channel::<OutboundEvent>();
    std::thread::spawn(move || {
        let mut dead = false;
        let mut active_port: Option<u16> = None;
        for outbound in rx {
            if dead {
                continue;
            }
            let payload = EventPayload {
                session_id: session_id.clone(),
                agent_id: outbound.agent_id,
                parent_id: None,
                event: outbound.event,
            };
            let body = match serde_json::to_string(&payload) {
                Ok(b) => b,
                Err(_) => continue,
            };
            let ports: Vec<u16> = match active_port {
                Some(p) => std::iter::once(p).chain(port_start..=port_end).collect(),
                None => (port_start..=port_end).collect(),
            };
            let mut sent = false;
            for port in ports {
                if post_event(DAEMON_HOST, port, &body).is_ok() {
                    active_port = Some(port);
                    sent = true;
                    break;
                }
            }
            if !sent {
                dead = true;
            }
        }
    });
    tx
}

fn post_event(host: &str, port: u16, body: &str) -> std::io::Result<()> {
    use std::net::TcpStream;
    let addr_str = format!("{}:{}", host, port);
    let socket_addr: std::net::SocketAddr = addr_str.parse().map_err(|e| {
        std::io::Error::new(std::io::ErrorKind::InvalidInput, format!("{}", e))
    })?;
    let mut stream = TcpStream::connect_timeout(&socket_addr, Duration::from_millis(150))?;
    stream.set_write_timeout(Some(Duration::from_millis(300)))?;
    stream.set_read_timeout(Some(Duration::from_millis(300)))?;
    let req = format!(
        "POST /event HTTP/1.1\r\n\
         Host: {}\r\n\
         Content-Type: application/json\r\n\
         Content-Length: {}\r\n\
         Connection: close\r\n\
         \r\n\
         {}",
        host,
        body.len(),
        body
    );
    stream.write_all(req.as_bytes())?;
    stream.flush()?;
    let mut buf = [0u8; 64];
    let _ = stream.read(&mut buf);
    Ok(())
}

// ---- main wrap ----

fn run_wrapped(real_claude: &Path, args: Vec<String>) -> i32 {
    let pty_system = native_pty_system();
    let initial_size = current_winsize(0);

    let pair = match pty_system.openpty(initial_size) {
        Ok(p) => p,
        Err(e) => {
            eprintln!(
                "claude-hq-shim: openpty failed ({}); falling back to direct exec",
                e
            );
            let err = std::process::Command::new(real_claude).args(&args).exec();
            eprintln!("claude-hq-shim: exec failed: {}", err);
            return 127;
        }
    };

    let mut cmd = CommandBuilder::new(real_claude);
    for a in &args {
        cmd.arg(a);
    }
    if let Ok(cwd) = std::env::current_dir() {
        cmd.cwd(cwd);
    }
    for (k, v) in std::env::vars_os() {
        cmd.env(k, v);
    }

    let mut child = match pair.slave.spawn_command(cmd) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("claude-hq-shim: failed to spawn claude: {}", e);
            return 127;
        }
    };
    drop(pair.slave);

    let reader = match pair.master.try_clone_reader() {
        Ok(r) => r,
        Err(e) => {
            eprintln!("claude-hq-shim: clone_reader failed: {}", e);
            return 1;
        }
    };
    let mut master_writer = match pair.master.take_writer() {
        Ok(w) => w,
        Err(e) => {
            eprintln!("claude-hq-shim: take_writer failed: {}", e);
            return 1;
        }
    };

    let session_id = make_session_id();
    let event_tx = spawn_event_sender(
        session_id.clone(),
        claude_hq_core::DEFAULT_PORT_START,
        claude_hq_core::DEFAULT_PORT_END,
    );
    let _ = event_tx.send(OutboundEvent {
        agent_id: None,
        event: ActivityEvent::Start,
    });
    // Report the working directory so the UI roster can show where each agent is.
    if let Ok(cwd) = std::env::current_dir() {
        let _ = event_tx.send(OutboundEvent {
            agent_id: None,
            event: ActivityEvent::Cwd {
                path: cwd.display().to_string(),
            },
        });
    }
    // If we can determine the model up front, send it now so the UI labels the
    // agent before any output is parsed.
    if let Some(name) = detect_model_from_args(&args) {
        let _ = event_tx.send(OutboundEvent {
            agent_id: None,
            event: ActivityEvent::Model { name },
        });
    }

    let _termios_guard = TermiosGuard::enter_raw(0);
    install_winch_handler();

    // stdin → PTY master writer
    std::thread::spawn(move || {
        let stdin = std::io::stdin();
        let mut handle = stdin.lock();
        let mut buf = [0u8; 4096];
        loop {
            match handle.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    if master_writer.write_all(&buf[..n]).is_err() {
                        break;
                    }
                    let _ = master_writer.flush();
                }
                Err(_) => break,
            }
        }
    });

    // SIGWINCH-driven resize loop owns the master.
    let master: Box<dyn MasterPty + Send> = pair.master;
    let resize_done = Arc::new(AtomicBool::new(false));
    {
        let resize_done = resize_done.clone();
        std::thread::spawn(move || {
            while !resize_done.load(Ordering::Relaxed) {
                std::thread::sleep(Duration::from_millis(200));
                if WINCH_FIRED.swap(false, Ordering::Relaxed) {
                    let size = current_winsize(0);
                    let _ = master.resize(size);
                }
            }
        });
    }

    // PTY master → stdout (raw passthrough) + line-buffer parser → event_tx.
    let parser_tx = event_tx.clone();
    let reader_thread = std::thread::spawn(move || {
        let mut reader = reader;
        let stdout = std::io::stdout();
        let mut line_buf: Vec<u8> = Vec::with_capacity(4096);
        let mut chunk = [0u8; 4096];
        let mut parser = Parser::new();
        loop {
            match reader.read(&mut chunk) {
                Ok(0) => break,
                Ok(n) => {
                    {
                        let mut out = stdout.lock();
                        let _ = out.write_all(&chunk[..n]);
                        let _ = out.flush();
                    }
                    for &b in &chunk[..n] {
                        if b == b'\n' {
                            if let Ok(s) = std::str::from_utf8(&line_buf) {
                                if let Some(ParseOutput { agent_id, event }) = parser.parse(s) {
                                    let _ = parser_tx.send(OutboundEvent { agent_id, event });
                                }
                            }
                            line_buf.clear();
                        } else if b != b'\r' {
                            line_buf.push(b);
                        }
                    }
                }
                Err(_) => break,
            }
        }
    });

    let exit_code = match child.wait() {
        Ok(s) if s.success() => 0,
        Ok(s) => s.exit_code() as i32,
        Err(_) => 1,
    };

    let _ = reader_thread.join();
    resize_done.store(true, Ordering::Relaxed);

    let final_event = if exit_code == 0 {
        ActivityEvent::Done
    } else {
        ActivityEvent::Error {
            message: format!("claude exited with code {}", exit_code),
        }
    };
    let _ = event_tx.send(OutboundEvent {
        agent_id: None,
        event: final_event,
    });
    drop(event_tx);
    std::thread::sleep(Duration::from_millis(50));

    exit_code
}

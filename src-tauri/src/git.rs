use serde::Serialize;
use crate::pty::expanded_path;

#[derive(Serialize)]
pub struct GitOutput {
    pub stdout: String,
    pub stderr: String,
    pub code: i32,
}

#[tauri::command]
pub fn git_exec(cwd: String, args: Vec<String>) -> Result<GitOutput, String> {
    let output = std::process::Command::new("git")
        .args(&args)
        .current_dir(&cwd)
        .env("PATH", expanded_path())
        .env("GIT_TERMINAL_PROMPT", "0")
        .output()
        .map_err(|e| format!("git exec failed: {e}"))?;
    Ok(GitOutput {
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        code: output.status.code().unwrap_or(-1),
    })
}

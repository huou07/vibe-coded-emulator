// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
//! Nintendo Switch companion control.
//!
//! Switch is a **separate process**, never linked into this binary: the AN3 app
//! launches `an3_switch_companion` (which embeds the Eden bridge and owns its
//! own window, input and saves) and controls its lifecycle. This is the
//! documented `CompanionSystem` boundary, deliberately separate from the
//! libretro `azahar` native path.
//!
//! Only legal homebrew content is runnable without user-supplied keys/firmware;
//! this module never bundles or reads those.

use serde::Serialize;
use std::{
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
};

/// Executable name of the companion on every desktop platform.
const COMPANION_BINARY: &str = "an3_switch_companion";

/// A launch in flight. Only one companion runs at a time.
static COMPANION: Mutex<Option<Child>> = Mutex::new(None);

#[derive(Clone, Serialize)]
pub struct CompanionInfo {
    pub available: bool,
    pub path: Option<String>,
}

#[derive(Clone, Serialize)]
pub struct CompanionStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub exit_code: Option<i32>,
}

/// Candidate locations for the companion, most specific first.
///
/// `AN3_SWITCH_COMPANION` is an explicit override (development and tests). In a
/// packaged app the binary sits next to the main executable or under the macOS
/// bundle's `Resources`/`Frameworks` directory.
pub(crate) fn companion_candidates() -> Vec<PathBuf> {
    let mut paths: Vec<PathBuf> = Vec::new();
    if let Ok(explicit) = std::env::var("AN3_SWITCH_COMPANION") {
        if !explicit.is_empty() {
            paths.push(PathBuf::from(explicit));
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            paths.push(dir.join(COMPANION_BINARY));
            paths.push(dir.join("../Resources").join(COMPANION_BINARY));
            paths.push(dir.join("../Frameworks").join(COMPANION_BINARY));
        }
    }
    paths
}

/// Returns the first candidate that exists and is a file.
pub(crate) fn find_companion() -> Option<PathBuf> {
    companion_candidates()
        .into_iter()
        .find(|candidate| candidate.is_file())
}

/// Argv for a bounded companion run. Kept pure so it is testable.
pub(crate) fn build_args(content: &str, visible: bool, seconds: Option<u32>) -> Vec<String> {
    let mut args = vec![content.to_string(), "--no-stdin".to_string()];
    if visible {
        args.push("--visible".to_string());
    }
    if let Some(seconds) = seconds {
        args.push("--seconds".to_string());
        args.push(seconds.to_string());
    }
    args
}

/// Reports whether the companion can be launched on this machine.
pub fn detect() -> CompanionInfo {
    match find_companion() {
        Some(path) => CompanionInfo {
            available: true,
            path: Some(path.to_string_lossy().into_owned()),
        },
        None => CompanionInfo {
            available: false,
            path: None,
        },
    }
}

/// Launches the companion for `content`. `visible` requests an on-screen
/// window; without it the companion still runs (useful for automation).
pub fn launch(content: &str, visible: bool) -> Result<CompanionStatus, String> {
    let path = find_companion().ok_or_else(|| {
        "The Nintendo Switch companion is not installed in this build".to_string()
    })?;
    if !Path::new(content).is_file() {
        return Err("The Switch content file does not exist".to_string());
    }
    // Never leave a previous companion running.
    stop();
    let child = Command::new(&path)
        .args(build_args(content, visible, None))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Could not start the Switch companion: {error}"))?;
    let pid = child.id();
    *COMPANION.lock().map_err(|_| "companion state is poisoned")? = Some(child);
    Ok(CompanionStatus {
        running: true,
        pid: Some(pid),
        exit_code: None,
    })
}

/// Current companion state, reaping the child if it exited on its own.
pub fn status() -> CompanionStatus {
    let mut guard = match COMPANION.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    };
    match guard.as_mut() {
        None => CompanionStatus {
            running: false,
            pid: None,
            exit_code: None,
        },
        Some(child) => match child.try_wait() {
            Ok(Some(exit)) => {
                let code = exit.code();
                *guard = None;
                CompanionStatus {
                    running: false,
                    pid: None,
                    exit_code: code,
                }
            }
            Ok(None) => CompanionStatus {
                running: true,
                pid: Some(child.id()),
                exit_code: None,
            },
            Err(_) => CompanionStatus {
                running: false,
                pid: None,
                exit_code: None,
            },
        },
    }
}

/// Stops the companion if it is running. Safe to call when nothing is running.
pub fn stop() {
    let mut guard = match COMPANION.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    };
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn args_default_to_hidden_and_non_interactive() {
        let args = build_args("/tmp/title.nro", false, None);
        assert_eq!(args, vec!["/tmp/title.nro", "--no-stdin"]);
    }

    #[test]
    fn args_request_a_window_and_a_bounded_run() {
        let args = build_args("/tmp/title.nro", true, Some(30));
        assert_eq!(
            args,
            vec!["/tmp/title.nro", "--no-stdin", "--visible", "--seconds", "30"]
        );
    }

    #[test]
    fn detection_reports_unavailable_without_a_binary() {
        let previous = std::env::var("AN3_SWITCH_COMPANION").ok();
        std::env::set_var("AN3_SWITCH_COMPANION", "/nonexistent/an3-switch-companion");
        let info = detect();
        assert!(!info.available);
        assert!(info.path.is_none());
        match previous {
            Some(value) => std::env::set_var("AN3_SWITCH_COMPANION", value),
            None => std::env::remove_var("AN3_SWITCH_COMPANION"),
        }
    }

    #[test]
    fn launch_rejects_missing_content() {
        // Detection may or may not succeed; a missing file must always fail.
        let result = launch("/nonexistent/title.nro", false);
        assert!(result.is_err());
    }

    #[test]
    fn status_is_not_running_before_launch() {
        stop();
        let status = status();
        assert!(!status.running);
        assert!(status.pid.is_none());
    }
}

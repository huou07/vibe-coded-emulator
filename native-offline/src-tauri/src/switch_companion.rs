// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
//! Nintendo Switch companion control.
//!
//! Switch is a **separate process**, never linked into this binary: AN3
//! launches `an3_switch_companion` (which embeds the Eden bridge and owns its
//! own window, input, audio and saves) and controls its lifecycle over a line
//! protocol on the child's stdin/stdout. This is the documented
//! `CompanionSystem` boundary, deliberately separate from the libretro
//! `azahar` native path.
//!
//! Only legal homebrew content is runnable without user-supplied keys/firmware;
//! this module never bundles or reads those.

use serde::Serialize;
use std::{
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, Command, Stdio},
    sync::mpsc::{self, Receiver, RecvTimeoutError},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

/// Executable name of the companion on every desktop platform.
const COMPANION_BINARY: &str = "an3_switch_companion";
/// Bundled location inside the app resources (mirrors the other native cores).
const COMPANION_RESOURCE_PATH: &str = "switch/macos-arm64/an3_switch_companion";
/// Development fallback next to the (gitignored) prepared vendor artifacts.
const COMPANION_DEVELOPMENT_PATH: &str = "../vendor/switch/macos-arm64/an3_switch_companion";
/// MoltenVK the companion's Eden backend loads on macOS.
const MOLTENVK_RESOURCE_PATH: &str = "azahar/macos-arm64/libMoltenVK.dylib";
const MOLTENVK_DEVELOPMENT_PATH: &str = "../vendor/moltenvk/macos-arm64/libMoltenVK.dylib";
/// Default timeout for a single control-protocol round trip.
const IPC_TIMEOUT: Duration = Duration::from_secs(5);
/// How long a graceful stop may take before the process is killed.
const STOP_TIMEOUT: Duration = Duration::from_secs(4);

/// A launch in flight. Only one companion runs at a time.
static COMPANION: Mutex<Option<CompanionProcess>> = Mutex::new(None);

struct CompanionProcess {
    child: Child,
    stdin: ChildStdin,
    lines: Receiver<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CompanionInfo {
    pub available: bool,
    pub path: Option<String>,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct CompanionStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub exit_code: Option<i32>,
    pub frames: Option<u64>,
    pub note: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CompanionAudio {
    pub available: bool,
    pub backend: Option<String>,
    pub device: Option<String>,
    pub channels: Option<u32>,
    pub volume: Option<f64>,
}

/// Argv for a companion run. Kept pure so it is testable. The control channel
/// stays open (no `--no-stdin`) so AN3 can send input and stop commands.
pub(crate) fn build_args(content: &str, visible: bool) -> Vec<String> {
    let mut args = vec![content.to_string()];
    if visible {
        args.push("--visible".to_string());
    }
    args
}

fn existing_file(path: &Path) -> Option<PathBuf> {
    if path.is_file() {
        Some(path.to_path_buf())
    } else {
        None
    }
}

/// Resolves the companion from an explicit resource directory. `allow_dev_fallback`
/// is true only for development builds, so a packaged app never resolves a
/// source-tree path.
pub(crate) fn resolve_from(resource_dir: Option<&Path>, allow_dev_fallback: bool) -> Result<PathBuf, String> {
    if let Ok(explicit) = std::env::var("AN3_SWITCH_COMPANION") {
        if let Some(path) = existing_file(Path::new(&explicit)) {
            return Ok(path);
        }
    }
    if let Some(dir) = resource_dir {
        if let Some(path) = existing_file(&dir.join(COMPANION_RESOURCE_PATH)) {
            return Ok(path);
        }
        if let Some(path) = existing_file(&dir.join(COMPANION_BINARY)) {
            return Ok(path);
        }
    }
    if allow_dev_fallback {
        if let Some(path) =
            existing_file(&Path::new(env!("CARGO_MANIFEST_DIR")).join(COMPANION_DEVELOPMENT_PATH))
        {
            return Ok(path);
        }
    }
    Err("The Nintendo Switch companion is not installed in this build. Re-run the packaging step so `an3_switch_companion` is bundled.".to_string())
}

/// Resolves the companion from the installed app layout.
pub(crate) fn resolve_companion(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    use tauri::Manager;
    let resource_dir = app.path().resource_dir().ok();
    resolve_from(resource_dir.as_deref(), cfg!(debug_assertions))
}

/// Resolves the MoltenVK runtime the companion's Eden backend needs. Returns
/// None when the environment already provides one or none is bundled.
fn resolve_moltenvk(app: &tauri::AppHandle) -> Option<PathBuf> {
    use tauri::Manager;
    if let Ok(explicit) = std::env::var("LIBVULKAN_PATH") {
        if !explicit.is_empty() {
            return None;
        }
    }
    if let Ok(resources) = app.path().resource_dir() {
        if let Some(path) = existing_file(&resources.join(MOLTENVK_RESOURCE_PATH)) {
            return Some(path);
        }
    }
    existing_file(&Path::new(env!("CARGO_MANIFEST_DIR")).join(MOLTENVK_DEVELOPMENT_PATH))
}

/// Reports whether the companion can be launched on this machine.
pub fn detect(app: &tauri::AppHandle) -> CompanionInfo {
    use tauri::Manager;
    match resolve_companion(app) {
        Ok(path) => CompanionInfo {
            available: true,
            path: Some(path.to_string_lossy().into_owned()),
            detail: "Switch companion is available".to_string(),
        },
        Err(detail) => {
            let resources = app
                .path()
                .resource_dir()
                .map(|path| path.display().to_string())
                .unwrap_or_else(|error| format!("<resource_dir error: {error}>"));
            CompanionInfo {
                available: false,
                path: None,
                detail: format!("{detail} resources={resources}"),
            }
        }
    }
}

fn lock() -> std::sync::MutexGuard<'static, Option<CompanionProcess>> {
    match COMPANION.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    }
}

/// Parses the `frames` field out of an `AN3CTL_STATUS` line.
fn frames_from_line(line: &str) -> Option<u64> {
    let marker = "\"frames\":";
    let start = line.find(marker)? + marker.len();
    let rest = &line[start..];
    let end = rest.find(|c: char| !c.is_ascii_digit()).unwrap_or(rest.len());
    rest[..end].parse().ok()
}

/// Sends one command and collects response lines until a terminal one arrives,
/// bounded by `timeout` so a stalled companion can never hang the app.
fn request(process: &mut CompanionProcess, command: &str, timeout: Duration) -> Result<Vec<String>, String> {
    writeln!(process.stdin, "{command}").map_err(|error| format!("companion channel write failed: {error}"))?;
    process.stdin.flush().map_err(|error| format!("companion channel flush failed: {error}"))?;
    let deadline = Instant::now() + timeout;
    let mut lines = Vec::new();
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("companion did not answer in time".to_string());
        }
        match process.lines.recv_timeout(remaining) {
            Ok(line) => {
                let terminal = line.contains("AN3CTL_ACK")
                    || line.contains("AN3CTL_STATUS")
                    || line.contains("AN3CTL_AUDIO")
                    || line.contains("AN3CTL_ERROR");
                lines.push(line);
                if terminal {
                    return Ok(lines);
                }
            }
            Err(RecvTimeoutError::Timeout) => {
                return Err("companion did not answer in time".to_string());
            }
            Err(RecvTimeoutError::Disconnected) => {
                return Err("the companion closed its control channel".to_string());
            }
        }
    }
}

fn reap(process: &mut CompanionProcess) -> Option<i32> {
    match process.child.try_wait() {
        Ok(Some(exit)) => exit.code(),
        _ => None,
    }
}

/// Waits for an unsolicited line matching `predicate` (used for the ready
/// signal) so later request/reply round trips stay aligned.
fn wait_for(
    process: &mut CompanionProcess,
    predicate: impl Fn(&str) -> bool,
    timeout: Duration,
) -> Result<String, String> {
    let deadline = Instant::now() + timeout;
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("the companion did not become ready in time".to_string());
        }
        match process.lines.recv_timeout(remaining) {
            Ok(line) => {
                if predicate(&line) {
                    return Ok(line);
                }
            }
            Err(RecvTimeoutError::Timeout) => {
                return Err("the companion did not become ready in time".to_string())
            }
            Err(RecvTimeoutError::Disconnected) => {
                return Err("the companion closed its control channel".to_string())
            }
        }
    }
}

/// Launches the companion for `content`. `visible` requests an on-screen
/// window. An already-running companion is stopped first so a duplicate is
/// never started.
pub fn launch(app: &tauri::AppHandle, content: &str, visible: bool) -> Result<CompanionStatus, String> {
    let path = resolve_companion(app)?;
    let moltenvk = resolve_moltenvk(app);
    launch_with(&path, moltenvk.as_deref(), content, visible)
}

/// Core launch used by both the app and the automated E2E test.
pub(crate) fn launch_with(
    binary: &Path,
    moltenvk: Option<&Path>,
    content: &str,
    visible: bool,
) -> Result<CompanionStatus, String> {
    if !binary.is_file() {
        return Err(format!(
            "The Nintendo Switch companion is not installed at {}.",
            binary.display()
        ));
    }
    if !Path::new(content).is_file() {
        return Err("The Switch content file does not exist".to_string());
    }
    stop();
    let mut command = Command::new(binary);
    command
        .args(build_args(content, visible))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    if let Some(moltenvk) = moltenvk {
        command.env("LIBVULKAN_PATH", moltenvk);
    }
    let mut child = command
        .spawn()
        .map_err(|error| format!("Could not start the Switch companion: {error}"))?;
    let stdin = child.stdin.take().ok_or("companion stdin was not available")?;
    let stdout = child.stdout.take().ok_or("companion stdout was not available")?;
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(line) => {
                    if sender.send(line).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });
    let pid = child.id();
    let mut process = CompanionProcess { child, stdin, lines: receiver };
    // The companion prints AN3CTL_STATUS once it is running. Drain that ready
    // signal (it is not a reply) so request/reply stays aligned.
    let note = match wait_for(&mut process, |line| line.contains("AN3CTL_STATUS"), Duration::from_secs(20)) {
        Ok(line) => Some(line),
        Err(error) => {
            let _ = process.child.kill();
            let _ = process.child.wait();
            return Err(error);
        }
    };
    *lock() = Some(process);
    Ok(CompanionStatus {
        running: true,
        pid: Some(pid),
        exit_code: None,
        frames: None,
        note,
    })
}

/// Launches the companion for an imported ROM id from the app's private
/// storage. Only `.nro` homebrew is accepted.
#[cfg(not(mobile))]
pub fn launch_rom(app: &tauri::AppHandle, rom_id: &str, visible: bool) -> Result<CompanionStatus, String> {
    use tauri::Manager;
    crate::validate_rom_id(rom_id)?;
    let directory = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot locate VibeCodedEmulator local storage: {error}"))?
        .join("an3-roms");
    let rom = crate::native_rom_path(&directory, rom_id, None)
        .ok_or_else(|| format!("The imported Switch homebrew is unavailable in {}.", directory.display()))?;
    let extension = rom.extension().and_then(|value| value.to_str()).unwrap_or_default();
    if !extension.eq_ignore_ascii_case("nro") {
        return Err("Only Nintendo Switch .nro homebrew can run in the companion.".to_string());
    }
    launch(app, &rom.to_string_lossy(), visible)
}

/// Current companion state, reaping the child if it exited on its own.
pub fn status() -> CompanionStatus {
    let mut guard = lock();
    let Some(process) = guard.as_mut() else {
        return CompanionStatus::default();
    };
    if let Some(code) = reap(process) {
        let note = format!("companion exited with code {code}");
        *guard = None;
        return CompanionStatus {
            running: false,
            pid: None,
            exit_code: Some(code),
            frames: None,
            note: Some(note),
        };
    }
    let pid = process.child.id();
    match request(process, "status", IPC_TIMEOUT) {
        Ok(lines) => {
            let frames = lines.iter().find_map(|line| frames_from_line(line));
            CompanionStatus {
                running: true,
                pid: Some(pid),
                exit_code: None,
                frames,
                note: None,
            }
        }
        Err(error) => CompanionStatus {
            running: true,
            pid: Some(pid),
            exit_code: None,
            frames: None,
            note: Some(error),
        },
    }
}

/// Sends one button transition. `button` uses the companion's names
/// (`A`, `B`, `X`, `Y`, `L`, `R`, `ZL`, `ZR`, `PLUS`, `MINUS`, d-pad names).
pub fn input_button(button: &str, pressed: bool) -> Result<String, String> {
    let mut guard = lock();
    let process = guard.as_mut().ok_or("No Switch companion is running")?;
    if let Some(code) = reap(process) {
        *guard = None;
        return Err(format!("The companion exited with code {code}"));
    }
    let command = format!("button {} {}", button.trim().to_uppercase(), if pressed { "down" } else { "up" });
    let lines = request(process, &command, IPC_TIMEOUT)?;
    Ok(lines.join("\n"))
}

/// Sends an analog stick position in the range -1.0 .. 1.0.
pub fn input_analog(stick: &str, x: f64, y: f64) -> Result<String, String> {
    let mut guard = lock();
    let process = guard.as_mut().ok_or("No Switch companion is running")?;
    if let Some(code) = reap(process) {
        *guard = None;
        return Err(format!("The companion exited with code {code}"));
    }
    let axis = if stick.eq_ignore_ascii_case("R") { "R" } else { "L" };
    let command = format!("analog {axis} {x} {y}");
    let lines = request(process, &command, IPC_TIMEOUT)?;
    Ok(lines.join("\n"))
}

/// Brings the running companion window to the front.
pub fn focus() -> Result<String, String> {
    let mut guard = lock();
    let process = guard.as_mut().ok_or("No Switch companion is running")?;
    let lines = request(process, "focus", IPC_TIMEOUT)?;
    Ok(lines.join("\n"))
}

/// Reads the companion's audio diagnostics.
pub fn audio() -> Result<CompanionAudio, String> {
    let mut guard = lock();
    let process = guard.as_mut().ok_or("No Switch companion is running")?;
    let lines = request(process, "audio", IPC_TIMEOUT)?;
    let line = lines
        .iter()
        .find(|line| line.contains("AN3CTL_AUDIO"))
        .ok_or("the companion did not report audio state")?;
    // The companion emits compact JSON; parse the fields we need.
    let field = |name: &str| -> Option<String> {
        let marker = format!("\"{name}\":");
        let start = line.find(&marker)? + marker.len();
        let rest = &line[start..];
        if let Some(text) = rest.strip_prefix('"') {
            let end = text.find('"')?;
            Some(text[..end].to_string())
        } else {
            let end = rest.find([',', '}']).unwrap_or(rest.len());
            Some(rest[..end].trim().to_string())
        }
    };
    Ok(CompanionAudio {
        available: field("available").as_deref() == Some("true"),
        backend: field("backend"),
        device: field("device"),
        channels: field("channels").and_then(|value| value.parse().ok()),
        volume: field("volume").and_then(|value| value.parse().ok()),
    })
}

/// Stops the companion if it is running. Safe to call when nothing is running.
pub fn stop() {
    let mut guard = lock();
    let Some(mut process) = guard.take() else {
        return;
    };
    // Ask nicely first so Eden shuts down cleanly.
    let _ = writeln!(process.stdin, "quit");
    let _ = process.stdin.flush();
    let deadline = Instant::now() + STOP_TIMEOUT;
    loop {
        match process.child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(50)),
            _ => break,
        }
    }
    let _ = process.child.kill();
    let _ = process.child.wait();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn args_open_the_control_channel() {
        let args = build_args("/tmp/title.nro", false);
        assert_eq!(args, vec!["/tmp/title.nro"]);
    }

    #[test]
    fn args_request_a_window() {
        let args = build_args("/tmp/title.nro", true);
        assert_eq!(args, vec!["/tmp/title.nro", "--visible"]);
    }

    #[test]
    fn frames_are_parsed_from_the_status_line() {
        let line = "AN3CTL_STATUS {\"target\":\"switch\",\"frames\":3821,\"result\":\"PASS\"}";
        assert_eq!(frames_from_line(line), Some(3821));
        assert_eq!(frames_from_line("AN3CTL_ACK {\"focus\":true}"), None);
    }

    #[test]
    fn stop_is_a_noop_without_a_companion() {
        stop();
        let status = status();
        assert!(!status.running);
        assert!(status.pid.is_none());
    }

    #[test]
    fn input_and_focus_require_a_running_companion() {
        stop();
        assert!(input_button("A", true).is_err());
        assert!(input_analog("L", 0.0, 0.0).is_err());
        assert!(focus().is_err());
        assert!(audio().is_err());
    }

    #[test]
    fn launch_reports_a_missing_binary_instead_of_crashing() {
        let content = concat!(env!("CARGO_MANIFEST_DIR"), "/Cargo.toml");
        let result = launch_with(Path::new("/nonexistent/an3_switch_companion"), None, content, false);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("not installed"));
    }

    #[test]
    fn a_missing_companion_is_a_structured_error() {
        // An isolated installation without the companion resolves to an error,
        // never a panic; the dev fallback is off for packaged builds.
        std::env::remove_var("AN3_SWITCH_COMPANION");
        let empty = std::env::temp_dir().join("an3-switch-empty-resources");
        std::fs::create_dir_all(&empty).unwrap();
        let result = resolve_from(Some(&empty), false);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("not installed"));
    }

    #[test]
    #[ignore = "set AN3_SWITCH_APP_RESOURCES to a built .app Resources dir"]
    fn the_installed_layout_resolves_the_companion() {
        std::env::remove_var("AN3_SWITCH_COMPANION");
        let resources = std::env::var("AN3_SWITCH_APP_RESOURCES").expect("resource dir");
        let resolved = resolve_from(Some(Path::new(&resources)), false).expect("resolve");
        assert!(resolved.is_file());
        assert!(resolved.to_string_lossy().ends_with("an3_switch_companion"));
    }

    /// End-to-end CompanionSystem lifecycle against the real bundled companion.
    /// Ignored by default (it launches a process and needs a legal homebrew
    /// fixture); run with `--ignored` when both env vars are set.
    #[test]
    #[ignore = "requires AN3_SWITCH_COMPANION and AN3_SWITCH_HOMEBREW"]
    fn e2e_launch_input_stop_relaunch() {
        let binary = PathBuf::from(std::env::var("AN3_SWITCH_COMPANION").expect("binary"));
        let content = std::env::var("AN3_SWITCH_HOMEBREW").expect("homebrew nro");
        let moltenvk = std::env::var("AN3_SWITCH_MOLTENVK").ok().map(PathBuf::from);

        let started = launch_with(&binary, moltenvk.as_deref(), &content, false).expect("launch");
        assert!(started.running);
        assert!(started.pid.is_some());

        // Sustained rendering: frames advance.
        let deadline = Instant::now() + Duration::from_secs(20);
        let mut frames = 0;
        while Instant::now() < deadline {
            let status = status();
            assert!(status.running, "the companion stopped unexpectedly");
            frames = status.frames.unwrap_or(0);
            if frames > 0 {
                break;
            }
            thread::sleep(Duration::from_millis(200));
        }
        assert!(frames > 0, "the companion never rendered a frame");

        // Input reaches Eden through the control channel.
        input_button("A", true).expect("button down");
        input_button("A", false).expect("button up");
        input_analog("L", 0.5, -0.25).expect("analog");
        input_analog("L", 0.0, 0.0).expect("analog reset");
        input_button("ZR", true).expect("trigger");
        input_button("ZR", false).expect("trigger release");
        focus().expect("focus");
        let audio = audio().expect("audio");
        assert!(audio.available, "the companion reported no audio sink");

        // Clean stop and relaunch.
        stop();
        assert!(!status().running);
        let again = launch_with(&binary, moltenvk.as_deref(), &content, false).expect("relaunch");
        assert!(again.running);
        assert_ne!(
            again.pid, started.pid,
            "relaunch must replace the previous companion, never duplicate it"
        );
        stop();
        assert!(!status().running);
    }
}

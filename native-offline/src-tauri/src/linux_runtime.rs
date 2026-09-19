// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Own the bundled portable player on Linux. The Tauri shell owns the local-ROM
//! library and import UI; gameplay runs in the bundled native SDL/GTK player.
//! No shell, external emulator lookup, or browser frame transport participates
//! in native gameplay.
use super::{NativeCapabilities, NativeInput, NativeStart};
use crate::{native_rom_path, validate_rom_id};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager};

static SESSION: Mutex<Option<Child>> = Mutex::new(None);
static ACTIVE_SYSTEM: Mutex<Option<String>> = Mutex::new(None);

fn runtime_relative() -> &'static str {
    "runtime/linux-x86_64/an3-offline-native"
}

fn runtime_path(app: &AppHandle) -> Result<PathBuf, String> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(resources) = app.path().resource_dir() {
        candidates.push(resources.join(runtime_relative()));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(directory) = exe.parent() {
            // Tauri's Linux deb installs the binary under `/usr/bin` and the
            // bundled runtime under `/usr/lib/<productName>`; Flatpak mirrors
            // that shape beneath `/app`.
            candidates.push(directory.join(runtime_relative()));
            candidates.push(directory.join("../lib/VibeCodedEmulator").join(runtime_relative()));
            candidates.push(directory.join("../lib/vibecodedemulator").join(runtime_relative()));
        }
    }
    #[cfg(debug_assertions)]
    candidates.push(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../vendor/runtime/linux-x86_64/an3-offline-native"),
    );
    for candidate in candidates {
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    Err("The bundled Linux native player is missing. Reinstall the verified Linux package.".into())
}

fn schemas_directory(runtime: &Path) -> Option<PathBuf> {
    runtime
        .parent()
        .map(|parent| parent.join("share/glib-2.0/schemas"))
        .filter(|path| path.is_dir())
}

pub(super) fn capabilities(app: &AppHandle) -> Result<NativeCapabilities, String> {
    let runtime = runtime_path(app)?;
    for name in ["mgba_libretro.so", "melondsds_libretro.so", "azahar_libretro.so"] {
        if !runtime.parent().unwrap().join("libretro").join(name).is_file() {
            return Err(format!("The bundled Linux core {name} is missing."));
        }
    }
    let mut session = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
    let active = match session.as_mut() {
        Some(child) => child.try_wait().map_err(|e| e.to_string())?.is_none(),
        None => false,
    };
    Ok(NativeCapabilities {
        available: true,
        active,
        engine: "Integrated mGBA, melonDS DS, and Azahar libretro cores".into(),
        renderer: "Native Vulkan preferred; OpenGL fallback for GBA/NDS".into(),
        detail: "Linux x64 portable player installed. GPU support is checked when a game starts.".into(),
    })
}

pub(super) fn stop() -> Result<(), String> {
    if let Ok(mut slot) = ACTIVE_SYSTEM.lock() { *slot = None; }
    let mut session = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
    if let Some(mut child) = session.take() {
        if let Some(mut input) = child.stdin.take() {
            let _ = writeln!(input, "QUIT");
        }
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if child.try_wait().map_err(|e| e.to_string())?.is_some() {
                break;
            }
            if Instant::now() >= deadline {
                child.kill().map_err(|e| format!("Cannot stop unresponsive native player: {e}"))?;
                let _ = child.wait();
                break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }
    }
    Ok(())
}

pub(super) fn start(app: &AppHandle, rom_id: &str, system: &str, layout: Option<&str>) -> Result<NativeStart, String> {
    if let Ok(mut slot) = ACTIVE_SYSTEM.lock() { *slot = Some(system.to_string()); }
    validate_rom_id(rom_id)?;
    let core = super::native_core(system)?;
    let runtime = runtime_path(app)?;
    let data = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let rom = native_rom_path(&data.join("an3-roms"), rom_id, None)
        .ok_or("The imported native ROM is unavailable.")?;
    if !super::native_file_matches_system(system, &rom) {
        return Err("The ROM does not match the selected system.".into());
    }
    let storage = data.join("native-player").join(system).join(rom_id);
    fs::create_dir_all(&storage).map_err(|e| format!("Cannot prepare native save storage: {e}"))?;
    stop()?;
    let log = storage.join("runtime.log");
    let errors = fs::File::create(&log).map_err(|e| e.to_string())?;
    let layout = match layout {
        Some("left-right" | "side_by_side") => "left-right",
        Some("top-bottom" | "top_bottom") => "top-bottom",
        _ => "preserve",
    };
    let mut command = Command::new(&runtime);
    command
        .args(["--rom"]).arg(&rom).args(["--system", system, "--layout", layout, "--storage"])
        .arg(&storage).arg("--control-stdin")
        .current_dir(runtime.parent().unwrap())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(errors);
    if let Some(schemas) = schemas_directory(&runtime) {
        command.env("GSETTINGS_SCHEMA_DIR", schemas);
    }
    let mut child = command
        .spawn()
        .map_err(|e| format!("Cannot start the bundled Linux player: {e}"))?;
    let output = child.stdout.take().ok_or("Native startup channel unavailable")?;
    let (tx, rx) = std::sync::mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut sender = Some(tx);
        for line in BufReader::new(output).lines().map_while(Result::ok) {
            if let Some(renderer) = line.strip_prefix("AN3_NATIVE_READY ") {
                if let Some(tx) = sender.take() {
                    let _ = tx.send(renderer.to_string());
                }
            }
        }
    });
    *SESSION.lock().map_err(|_| "Native session lock unavailable")? = Some(child);
    match rx.recv_timeout(Duration::from_secs(45)) {
        Ok(renderer) => Ok(NativeStart {
            active: true,
            engine: core.engine.into(),
            renderer,
            detail: "Native game window opened. Menu: F2 · Pad: F3 · Next Layout: F1".into(),
        }),
        Err(_) => {
            let _ = stop();
            let detail = fs::read_to_string(log).unwrap_or_default();
            let tail: String = detail.chars().rev().take(1600).collect::<Vec<_>>().into_iter().rev().collect();
            Err(format!("The native player could not initialize this game. {tail}"))
        }
    }
}

pub(super) fn input(value: NativeInput) -> Result<(), String> {
    let mut session = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
    if let Some(pipe) = session.as_mut().and_then(|child| child.stdin.as_mut()) {
        writeln!(
            pipe,
            "INPUT {} {} {} {} {} {}",
            value.buttons, value.circle_x, value.circle_y, value.touch_x, value.touch_y,
            u8::from(value.touch_pressed)
        )
        .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Send one canonical Phone Controller utility action to the bundled player
/// over the private `--control-stdin` channel. The player maps the command onto
/// its existing quick-save/speed/menu operations; an unknown action is rejected
/// before anything is written.
pub(super) fn utility(action: &str) -> Result<(), String> {
    let command = match action {
        "QUICK_SAVE" | "SPEED_UP" | "SPEED_DOWN" | "OPEN_MENU" => action,
        _ => {
            return Err(format!(
                "The desktop player does not support the '{action}' utility action."
            ))
        }
    };
    let mut session = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
    let pipe = session
        .as_mut()
        .and_then(|child| child.stdin.as_mut())
        .ok_or_else(|| "No native game is running.".to_string())?;
    writeln!(pipe, "{command}").map_err(|error| error.to_string())?;
    Ok(())
}

/// True while the native player child process is still alive.
/// The system the active native game is running, if any.
pub(super) fn active_system() -> Option<String> {
    ACTIVE_SYSTEM.lock().ok().and_then(|value| value.clone())
}

pub(super) fn running() -> bool {
    let Ok(mut session) = SESSION.lock() else { return false };
    match session.as_mut() {
        Some(child) => matches!(child.try_wait(), Ok(None)),
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The shell must deliver controller input to the bundled player over the
    /// documented `--control-stdin` protocol. A fake child (`cat`) stands in for
    /// the native player so this runs without a GPU or a real game.
    #[test]
    fn input_writes_the_control_stdin_protocol() {
        let mut child = Command::new("cat")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .expect("spawn cat");
        let stdout = child.stdout.take().expect("cat stdout");
        *SESSION.lock().expect("session lock") = Some(child);

        let frame = NativeInput {
            buttons: 8, // GBA "start", the bit the phone controller sends
            circle_x: 1234,
            circle_y: -1234,
            cstick_x: 0,
            cstick_y: 0,
            touch_x: 7,
            touch_y: 9,
            touch_pressed: true,
        };
        input(frame).expect("input");
        // Close stdin so cat flushes and exits.
        if let Ok(mut guard) = SESSION.lock() {
            if let Some(child) = guard.as_mut() {
                drop(child.stdin.take());
            }
        }

        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        reader.read_line(&mut line).expect("read echo");
        assert_eq!(line.trim(), "INPUT 8 1234 -1234 7 9 1");

        if let Ok(mut guard) = SESSION.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

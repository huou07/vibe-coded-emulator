// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Own the bundled portable player. No shell, external emulator lookup, or
//! browser frame transport participates in native Windows gameplay.
use super::{NativeCapabilities, NativeStart};
use crate::{native_rom_path, validate_rom_id};
use std::{fs, io::{BufRead, BufReader, Write}, os::windows::process::CommandExt,
    path::PathBuf, process::{Child, ChildStdin, Command, Stdio}, sync::{mpsc, Arc, Mutex}, time::{Duration, Instant}};
use tauri::{AppHandle, Manager};

type PendingControlResponses = Arc<Mutex<std::collections::HashMap<u64, mpsc::SyncSender<Result<String, String>>>>>;

struct NativeSession {
    child: Child,
    input: ChildStdin,
    pending: PendingControlResponses,
    next_control_id: u64,
}

static SESSION: Mutex<Option<NativeSession>> = Mutex::new(None);

fn runtime_path(app: &AppHandle) -> Result<PathBuf, String> {
    let bundled = app.path().resource_dir().map_err(|e| e.to_string())?
        .join("runtime/windows-x64/an3-native-runtime.exe");
    if bundled.is_file() { return Ok(bundled); }
    #[cfg(debug_assertions)]
    {
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../vendor/runtime/windows-x64/an3-native-runtime.exe");
        if dev.is_file() { return Ok(dev); }
    }
    Err("The bundled Windows native player is missing. Reinstall the verified Windows package.".into())
}

pub(super) fn capabilities(app: &AppHandle) -> Result<NativeCapabilities, String> {
    let runtime = runtime_path(app)?;
    for name in ["mgba_libretro.dll", "melondsds_libretro.dll", "azahar_libretro.dll"] {
        if !runtime.parent().unwrap().join("libretro").join(name).is_file() {
            return Err(format!("The bundled Windows core {name} is missing."));
        }
    }
    let mut session = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
    let active = match session.as_mut() { Some(session) => session.child.try_wait().map_err(|e| e.to_string())?.is_none(), None => false };
    Ok(NativeCapabilities {available:true, active,
        engine:"Integrated mGBA, melonDS DS, and Azahar libretro cores".into(),
        renderer:"Native Vulkan preferred; OpenGL fallback for GBA/NDS".into(),
        detail:"Windows x64 portable player installed. GPU support is checked when a game starts.".into()})
}

pub(super) fn stop() -> Result<(), String> {
    let mut session = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
    if let Some(mut session) = session.take() {
        let _ = writeln!(session.input, "QUIT");
        let mut child = session.child;
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if child.try_wait().map_err(|e| e.to_string())?.is_some() { break; }
            if Instant::now() >= deadline {
                child.kill().map_err(|e| format!("Cannot stop unresponsive native player: {e}"))?;
                let _ = child.wait(); break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }
    }
    Ok(())
}

pub(super) fn start(app: &AppHandle, rom_id: &str, system: &str, layout: Option<&str>) -> Result<NativeStart, String> {
    validate_rom_id(rom_id)?;
    let core = super::native_core(system)?;
    let runtime = runtime_path(app)?;
    let data = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let rom = native_rom_path(&data.join("an3-roms"), rom_id, None)
        .ok_or("The imported native ROM is unavailable.")?;
    if !super::native_file_matches_system(system, &rom) { return Err("The ROM does not match the selected system.".into()); }
    let storage = data.join("native-player").join(system).join(rom_id);
    fs::create_dir_all(&storage).map_err(|e| format!("Cannot prepare native save storage: {e}"))?;
    let settings_args = crate::native_settings::launch_arguments(
        &data.join("native-settings.json"),
        system,
    )?;
    stop()?;
    let log = storage.join("runtime.log");
    let errors = fs::File::create(&log).map_err(|e| e.to_string())?;
    let layout = match layout { Some("left-right" | "side_by_side") => "left-right", Some("top-bottom" | "top_bottom") => "top-bottom", _ => "preserve" };
    let mut child = Command::new(&runtime)
        .args(["--rom"]).arg(&rom).args(["--system",system,"--layout",layout,"--storage"])
        .arg(&storage).args(settings_args).args(["--control-stdin", "--no-controls"])
        .current_dir(runtime.parent().unwrap())
        .env("GSETTINGS_SCHEMA_DIR", runtime.parent().unwrap().join("share/glib-2.0/schemas"))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(errors)
        .creation_flags(0x08000000) // Hide the console; SDL and GTK create the native GUI.
        .spawn().map_err(|e| format!("Cannot start the bundled Windows player: {e}"))?;
    let output = child.stdout.take().ok_or("Native startup channel unavailable")?;
    let input = child.stdin.take().ok_or("Native control channel unavailable")?;
    let (tx, rx) = std::sync::mpsc::sync_channel(1);
    let pending: PendingControlResponses = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let pending_output = Arc::clone(&pending);
    std::thread::spawn(move || {
        let mut sender = Some(tx);
        for line in BufReader::new(output).lines().map_while(Result::ok) {
            if let Some(renderer) = line.strip_prefix("AN3_NATIVE_READY ") {
                if let Some(tx) = sender.take() { let _ = tx.send(renderer.to_string()); }
            } else if let Some(response) = line.strip_prefix("AN3_NATIVE_CONTROL_RESULT ") {
                let mut fields = response.splitn(3, ' ');
                let id = fields.next().and_then(|value| value.parse::<u64>().ok());
                let status = fields.next().unwrap_or_default();
                let message = fields.next().unwrap_or("Native control failed.").to_string();
                if let Some(id) = id {
                    let response_sender = pending_output.lock().ok().and_then(|mut responses| responses.remove(&id));
                    if let Some(response_sender) = response_sender {
                        let result = if status == "OK" { Ok(message) } else { Err(message) };
                        let _ = response_sender.send(result);
                    }
                }
            }
        }
    });
    *SESSION.lock().map_err(|_| "Native session lock unavailable")? = Some(NativeSession {
        child, input, pending, next_control_id: 1,
    });
    match rx.recv_timeout(Duration::from_secs(45)) {
        Ok(renderer) => Ok(NativeStart {active:true, engine:core.engine.into(), renderer,
            detail:"Game window opened. Use the VCE Play page for session controls.".into()}),
        Err(_) => {
            let _ = stop();
            let detail = fs::read_to_string(log).unwrap_or_default();
            let tail: String = detail.chars().rev().take(1600).collect::<Vec<_>>().into_iter().rev().collect();
            Err(format!("The native player could not initialize this game. {tail}"))
        }
    }
}

/// True while the native player child process is still alive.
pub(super) fn running() -> bool {
    let Ok(mut session) = SESSION.lock() else { return false };
    match session.as_mut() {
        Some(session) => matches!(session.child.try_wait(), Ok(None)),
        None => false,
    }
}

/// Apply a validated desktop action on the SDL owner thread and await its acknowledgement.
pub(super) fn control(action: &str, value: Option<&str>) -> Result<String, String> {
    let value = value.unwrap_or_default();
    if value.len() > 128 || value.bytes().any(|byte| matches!(byte, b'\n' | b'\r' | b'\t')) {
        return Err("Native control value is invalid.".into());
    }
    match action {
        "pause" if matches!(value, "true" | "false") => {}
        "speed" if matches!(value, "0.5" | "1" | "2" | "4" | "8") => {}
        "save" | "load" if value.parse::<u8>().is_ok_and(|slot| (1..=10).contains(&slot)) => {}
        "layout" if matches!(value, "left-right" | "top-bottom") => {}
        "auto-save" if matches!(value, "off" | "exit" | "30" | "10" | "5") => {}
        "volume" if value.parse::<f32>().is_ok_and(|level| level.is_finite() && (0.0..=1.0).contains(&level)) => {}
        "mute" if matches!(value, "true" | "false") => {}
        "button" if value.split_once(':').is_some_and(|(button, pressed)| {
            button.parse::<u8>().is_ok_and(|id| id < 16) && matches!(pressed, "0" | "1")
        }) => {}
        "clear-input" | "fullscreen" | "load-auto" if value.is_empty() => {}
        _ => return Err("Unsupported or invalid native control action.".into()),
    }

    let (id, receiver) = {
        let mut active = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
        let session = active.as_mut().ok_or("No native game session is running.")?;
        if session.child.try_wait().map_err(|error| error.to_string())?.is_some() {
            return Err("The native game session has stopped.".into());
        }
        let id = session.next_control_id;
        session.next_control_id = session.next_control_id.wrapping_add(1).max(1);
        let (sender, receiver) = mpsc::sync_channel(1);
        session.pending.lock().map_err(|_| "Native control response lock unavailable")?.insert(id, sender);
        if let Err(error) = writeln!(session.input, "{id}\t{action}\t{value}") {
            session.pending.lock().ok().map(|mut responses| responses.remove(&id));
            return Err(format!("Could not send the native control action: {error}"));
        }
        (id, receiver)
    };
    match receiver.recv_timeout(Duration::from_secs(60)) {
        Ok(result) => result,
        Err(_) => {
            if let Ok(mut active) = SESSION.lock() {
                if let Some(session) = active.as_mut() {
                    if let Ok(mut pending) = session.pending.lock() { pending.remove(&id); }
                }
            }
            Err("The native player did not confirm the control action in time.".into())
        }
    }
}

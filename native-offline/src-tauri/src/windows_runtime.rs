// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Own the bundled portable player. No shell, external emulator lookup, or
//! browser frame transport participates in native Windows gameplay.
use super::{NativeCapabilities, NativeInput, NativeStart};
use crate::{native_rom_path, validate_rom_id};
use std::{fs, io::{BufRead, BufReader, Write}, os::windows::process::CommandExt,
    path::PathBuf, process::{Child, Command, Stdio}, sync::Mutex, time::{Duration, Instant}};
use tauri::{AppHandle, Manager};

static SESSION: Mutex<Option<Child>> = Mutex::new(None);

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
    let active = match session.as_mut() { Some(child) => child.try_wait().map_err(|e| e.to_string())?.is_none(), None => false };
    Ok(NativeCapabilities {available:true, active,
        engine:"Integrated mGBA, melonDS DS, and Azahar libretro cores".into(),
        renderer:"Native Vulkan preferred; OpenGL fallback for GBA/NDS".into(),
        detail:"Windows x64 portable player installed. GPU support is checked when a game starts.".into()})
}

pub(super) fn stop() -> Result<(), String> {
    let mut session = SESSION.lock().map_err(|_| "Native session lock unavailable")?;
    if let Some(mut child) = session.take() {
        if let Some(mut input) = child.stdin.take() { let _ = writeln!(input, "QUIT"); }
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
    stop()?;
    let log = storage.join("runtime.log");
    let errors = fs::File::create(&log).map_err(|e| e.to_string())?;
    let layout = match layout { Some("left-right" | "side_by_side") => "left-right", Some("top-bottom" | "top_bottom") => "top-bottom", _ => "preserve" };
    let mut child = Command::new(&runtime)
        .args(["--rom"]).arg(&rom).args(["--system",system,"--layout",layout,"--storage"])
        .arg(&storage).arg("--control-stdin")
        .current_dir(runtime.parent().unwrap())
        .env("GSETTINGS_SCHEMA_DIR", runtime.parent().unwrap().join("share/glib-2.0/schemas"))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(errors)
        .creation_flags(0x08000000) // Hide the console; SDL and GTK create the native GUI.
        .spawn().map_err(|e| format!("Cannot start the bundled Windows player: {e}"))?;
    let output = child.stdout.take().ok_or("Native startup channel unavailable")?;
    let (tx, rx) = std::sync::mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut sender = Some(tx);
        for line in BufReader::new(output).lines().map_while(Result::ok) {
            if let Some(renderer) = line.strip_prefix("AN3_NATIVE_READY ") {
                if let Some(tx) = sender.take() { let _ = tx.send(renderer.to_string()); }
            }
        }
    });
    *SESSION.lock().map_err(|_| "Native session lock unavailable")? = Some(child);
    match rx.recv_timeout(Duration::from_secs(45)) {
        Ok(renderer) => Ok(NativeStart {active:true, engine:core.engine.into(), renderer,
            detail:"Native game window opened. Menu: F2 · Pad: F3 · Next Layout: F1".into()}),
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
        writeln!(pipe,"INPUT {} {} {} {} {} {}", value.buttons, value.circle_x, value.circle_y,
            value.touch_x, value.touch_y, u8::from(value.touch_pressed)).map_err(|e| e.to_string())?;
    }
    Ok(())
}

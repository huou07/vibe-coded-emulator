// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
use serde::{Deserialize, Serialize};
use std::{
    ffi::{CStr, CString},
    fs,
    path::{Path, PathBuf},
};
use tauri::{AppHandle, Manager};

#[cfg(target_os = "macos")]
use crate::{native_rom_path, native_system_from_extension, validate_rom_id};
use crate::NATIVE_3DS_FILE_EXTENSIONS;
#[cfg(target_os = "windows")]
#[path = "windows_runtime.rs"]
mod windows_runtime;
#[cfg(target_os = "linux")]
#[path = "linux_runtime.rs"]
mod linux_runtime;

const MOLTENVK_RELATIVE_PATH: &str = "azahar/macos-arm64/libMoltenVK.dylib";

#[derive(Clone, Copy)]
struct NativeCore {
    system: &'static str,
    engine: &'static str,
    resource_path: &'static str,
    development_path: &'static str,
    setup_hint: &'static str,
}

fn native_core(system: &str) -> Result<NativeCore, String> {
    match system {
        "gba" => Ok(NativeCore {
            system: "gba",
            engine: "mGBA libretro 0.11-219-e31759b",
            resource_path: "libretro/macos-arm64/mgba_libretro.dylib",
            development_path: "../vendor/libretro/macos-arm64/mgba_libretro.dylib",
            setup_hint: "npm run prepare-native-cores",
        }),
        "nds" => Ok(NativeCore {
            system: "nds",
            engine: "melonDS DS libretro 1.3.1",
            resource_path: "libretro/macos-arm64/melondsds_libretro.dylib",
            development_path: "../vendor/libretro/macos-arm64/melondsds_libretro.dylib",
            setup_hint: "npm run prepare-native-cores",
        }),
        "3ds" => Ok(NativeCore {
            system: "3ds",
            engine: "Azahar libretro 2126.1.1",
            resource_path: "azahar/macos-arm64/azahar_libretro.dylib",
            development_path: "../vendor/azahar/macos-arm64/azahar_libretro.dylib",
            setup_hint: "npm run prepare-azahar",
        }),
        _ => Err("Choose a supported native system: GBA, NDS, or 3DS.".into()),
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeCapabilities {
    pub available: bool,
    pub active: bool,
    pub engine: String,
    pub renderer: String,
    pub detail: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeStart {
    pub active: bool,
    pub engine: String,
    pub renderer: String,
    pub detail: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeInput {
    pub buttons: u32,
    pub circle_x: i16,
    pub circle_y: i16,
    pub cstick_x: i16,
    pub cstick_y: i16,
    pub touch_x: i16,
    pub touch_y: i16,
    pub touch_pressed: bool,
}

#[cfg(target_os = "macos")]
unsafe extern "C" {
    fn an3_native_probe(
        core_path: *const std::ffi::c_char,
        details: *mut std::ffi::c_char,
        details_length: usize,
    ) -> i32;
    fn an3_native_start(
        content_view: *mut std::ffi::c_void,
        core_path: *const std::ffi::c_char,
        moltenvk_path: *const std::ffi::c_char,
        rom_path: *const std::ffi::c_char,
        rom_id: *const std::ffi::c_char,
        save_directory: *const std::ffi::c_char,
        system_directory: *const std::ffi::c_char,
        system: *const std::ffi::c_char,
        layout: *const std::ffi::c_char,
        details: *mut std::ffi::c_char,
        details_length: usize,
    ) -> i32;
    fn an3_native_stop();
    fn an3_native_is_running() -> i32;
    fn an3_native_active_system() -> i32;
    fn an3_native_apply_utility(
        action: *const std::ffi::c_char,
        details: *mut std::ffi::c_char,
        details_length: usize,
    ) -> i32;
    fn an3_native_set_input(
        buttons: u32,
        circle_x: i16,
        circle_y: i16,
        cstick_x: i16,
        cstick_y: i16,
        touch_x: i16,
        touch_y: i16,
        touch_pressed: i32,
    );
}

fn native_moltenvk_path(app: &AppHandle) -> Result<PathBuf, String> {
    #[cfg(target_os = "macos")]
    {
        let bundled = app
            .path()
            .resource_dir()
            .map_err(|error| format!("Cannot locate VibeCodedEmulator resources: {error}"))?
            .join(MOLTENVK_RELATIVE_PATH);
        if bundled.is_file() {
            return Ok(bundled);
        }
        let development = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../vendor/moltenvk/macos-arm64/libMoltenVK.dylib");
        if development.is_file() {
            return Ok(development);
        }
        Err("The bundled MoltenVK runtime is unavailable. Re-run `npm run prepare-moltenvk` before building VibeCodedEmulator.".into())
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = app;
        Err("The bundled MoltenVK runtime is only available in the macOS native player.".into())
    }
}

fn native_core_path(app: &AppHandle, core: NativeCore) -> Result<PathBuf, String> {
    #[cfg(target_os = "macos")]
    {
        let bundled = app
            .path()
            .resource_dir()
            .map_err(|error| format!("Cannot locate VibeCodedEmulator resources: {error}"))?
            .join(core.resource_path);
        if bundled.is_file() {
            return Ok(bundled);
        }
        // `tauri dev` does not always materialize macOS bundle resources. The
        // verified build artifact is the only development fallback: never
        // search for a separately installed emulator.
        let development = Path::new(env!("CARGO_MANIFEST_DIR")).join(core.development_path);
        if development.is_file() {
            return Ok(development);
        }
        Err(format!(
            "The bundled {} native core is unavailable. Re-run `{}` before building VibeCodedEmulator.",
            core.system, core.setup_hint
        ))
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (app, core);
        Err("Integrated native cores are currently implemented for macOS only.".into())
    }
}

fn c_string(path: &Path, label: &str) -> Result<CString, String> {
    CString::new(path.to_string_lossy().as_bytes())
        .map_err(|_| format!("{label} contains an unsupported NUL character"))
}

fn c_text(value: &str, label: &str) -> Result<CString, String> {
    CString::new(value).map_err(|_| format!("{label} contains an unsupported NUL character"))
}

#[cfg(target_os = "macos")]
fn ffi_detail(buffer: &[std::ffi::c_char]) -> String {
    // Every exported Objective-C++ call receives an owned, zeroed buffer. Keep
    // the conversion defensive so a third-party core message cannot compromise
    // the native UI bridge.
    unsafe { CStr::from_ptr(buffer.as_ptr()) }
        .to_string_lossy()
        .trim()
        .to_string()
}

#[cfg(target_os = "macos")]
fn probe_core(path: &Path) -> Result<String, String> {
    let core = c_string(path, "native core path")?;
    let mut details = [0_i8; 512];
    let api_version = unsafe { an3_native_probe(core.as_ptr(), details.as_mut_ptr(), details.len()) };
    if api_version <= 0 {
        let detail = ffi_detail(&details);
        return Err(if detail.is_empty() {
            "The bundled native core cannot be loaded.".into()
        } else {
            detail
        });
    }
    let detail = ffi_detail(&details);
    Ok(if detail.is_empty() {
        format!("libretro ABI {api_version}")
    } else {
        detail
    })
}

fn native_file_matches_system(system: &str, path: &Path) -> bool {
    let extension = path.extension().and_then(|extension| extension.to_str());
    match (system, extension) {
        ("gba", Some(extension)) => extension.eq_ignore_ascii_case("gba") || extension.eq_ignore_ascii_case("raw"),
        ("nds", Some(extension)) => extension.eq_ignore_ascii_case("nds"),
        ("3ds", Some(extension)) => NATIVE_3DS_FILE_EXTENSIONS
            .iter()
            .any(|allowed| extension.eq_ignore_ascii_case(allowed)),
        _ => false,
    }
}

fn native_paths(app: &AppHandle, system: &str) -> Result<(PathBuf, PathBuf), String> {
    let component = match system {
        // Keep the 3DS storage location stable so existing Azahar saves and
        // system files remain available after this generalized native host.
        "3ds" => "azahar",
        "gba" => "mgba",
        "nds" => "melondsds",
        _ => return Err("Unsupported native system storage request.".into()),
    };
    let root = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot locate VibeCodedEmulator local storage: {error}"))?
        .join(component);
    let saves = root.join("saves");
    let system_directory = root.join("system");
    fs::create_dir_all(&saves)
        .map_err(|error| format!("Cannot prepare native save storage: {error}"))?;
    fs::create_dir_all(&system_directory)
        .map_err(|error| format!("Cannot prepare native system storage: {error}"))?;
    Ok((saves, system_directory))
}

fn renderer_description(system: &str) -> String {
    if system == "3ds" {
        "Vulkan 1.1 via bundled MoltenVK / Metal".into()
    } else {
        "Native CPU core; software frames uploaded through Vulkan 1.1 via bundled MoltenVK / Metal".into()
    }
}

#[tauri::command]
pub fn native_capabilities(app: AppHandle) -> Result<NativeCapabilities, String> {
    #[cfg(target_os = "windows")]
    { return windows_runtime::capabilities(&app); }
    #[cfg(target_os = "linux")]
    { return linux_runtime::capabilities(&app); }
    #[cfg(target_os = "macos")]
    {
        let mut details = Vec::new();
        for system in ["gba", "nds", "3ds"] {
            let core = native_core(system)?;
            let path = native_core_path(&app, core)?;
            details.push(probe_core(&path)?);
        }
        let _moltenvk = native_moltenvk_path(&app)?;
        let active = unsafe { an3_native_is_running() != 0 };
        return Ok(NativeCapabilities {
            available: true,
            active,
            engine: "Integrated mGBA, melonDS DS, and Azahar libretro cores".into(),
            renderer: "Vulkan 1.1 via bundled MoltenVK / Metal".into(),
            detail: details.join(" · "),
        });
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        let _ = app;
        Ok(NativeCapabilities {
            available: false,
            active: false,
            engine: "Integrated libretro cores".into(),
            renderer: "Unavailable on this platform".into(),
            detail: "Integrated GBA, NDS, and 3DS cores are currently implemented for macOS, Windows, and Linux.".into(),
        })
    }
}

#[tauri::command]
pub fn start_native_game(
    app: AppHandle,
    rom_id: String,
    system: String,
    layout: Option<String>,
) -> Result<NativeStart, String> {
    #[cfg(target_os = "windows")]
    { return windows_runtime::start(&app, &rom_id, &system, layout.as_deref()); }
    #[cfg(target_os = "linux")]
    { return linux_runtime::start(&app, &rom_id, &system, layout.as_deref()); }
    #[cfg(target_os = "macos")]
    {
        validate_rom_id(&rom_id)?;
        let system = system.trim().to_ascii_lowercase();
        let core_spec = native_core(&system)?;
        let directory = app
            .path()
            .app_data_dir()
            .map_err(|error| format!("Cannot locate VibeCodedEmulator local storage: {error}"))?
            .join("an3-roms");
        let rom = native_rom_path(&directory, &rom_id, None)
            .ok_or_else(|| "The imported native ROM is unavailable.".to_string())?;
        if !native_file_matches_system(core_spec.system, &rom) {
            return Err(format!(
                "The selected local ROM does not match the requested {} native core.",
                core_spec.system.to_ascii_uppercase()
            ));
        }
        if native_system_from_extension(
            rom.extension().and_then(|extension| extension.to_str()).unwrap_or_default(),
        ) != Some(core_spec.system)
        {
            return Err("The selected local ROM has an unsupported native file type.".into());
        }
        let core = native_core_path(&app, core_spec)?;
        let moltenvk = native_moltenvk_path(&app)?;
        let (saves, system_directory) = native_paths(&app, core_spec.system)?;
        // Layout is a per-system native preference. An unspecified launch
        // must preserve it; do not derive a new portrait/default choice from
        // the WebView's current dimensions.
        let layout = match layout.as_deref() {
            Some("left-right") | Some("side_by_side") => "left-right",
            Some("top-bottom") | Some("top_bottom") => "top-bottom",
            _ => "preserve",
        };
        let core = c_string(&core, "native core path")?;
        let moltenvk = c_string(&moltenvk, "MoltenVK runtime path")?;
        let rom = c_string(&rom, "native ROM path")?;
        let rom_id = c_text(&rom_id, "native ROM identifier")?;
        let saves = c_string(&saves, "native save path")?;
        let system_directory = c_string(&system_directory, "native system path")?;
        let system_text = c_text(core_spec.system, "native system")?;
        let layout = c_text(layout, "native screen layout")?;
        let window = app
            .get_webview_window("main")
            .ok_or_else(|| "VibeCodedEmulator main window is unavailable.".to_string())?;
        let content_view = window
            .ns_view()
            .map_err(|error| format!("Cannot access VibeCodedEmulator's macOS content view: {error}"))?
            as usize;
        let (sender, receiver) = std::sync::mpsc::sync_channel(1);
        app.run_on_main_thread(move || {
            let mut details = [0_i8; 512];
            let started = unsafe {
                an3_native_start(
                    content_view as *mut std::ffi::c_void,
                    core.as_ptr(),
                    moltenvk.as_ptr(),
                    rom.as_ptr(),
                    rom_id.as_ptr(),
                    saves.as_ptr(),
                    system_directory.as_ptr(),
                    system_text.as_ptr(),
                    layout.as_ptr(),
                    details.as_mut_ptr(),
                    details.len(),
                ) != 0
            };
            let _ = sender.send((started, ffi_detail(&details)));
        })
        .map_err(|error| format!("Cannot schedule native game startup: {error}"))?;
        let (started, detail) = receiver
            .recv_timeout(std::time::Duration::from_secs(15))
            .map_err(|_| "Native game startup did not reach the macOS UI thread.".to_string())?;
        if !started {
            return Err(if detail.is_empty() {
                format!("{} could not start this local ROM.", core_spec.engine)
            } else {
                detail
            });
        }
        return Ok(NativeStart {
            active: true,
            engine: core_spec.engine.into(),
            renderer: renderer_description(core_spec.system),
            detail,
        });
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        let _ = (app, rom_id, system, layout);
        Err("Integrated native cores are currently implemented for macOS, Windows, and Linux.".into())
    }
}

#[tauri::command]
pub fn stop_native_game(app: AppHandle) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    { let _ = app; return windows_runtime::stop(); }
    #[cfg(target_os = "linux")]
    { let _ = app; return linux_runtime::stop(); }
    #[cfg(target_os = "macos")]
    {
        let (sender, receiver) = std::sync::mpsc::sync_channel(1);
        app.run_on_main_thread(move || {
            unsafe { an3_native_stop() };
            let _ = sender.send(());
        })
        .map_err(|error| format!("Cannot schedule native game shutdown: {error}"))?;
        receiver
            .recv_timeout(std::time::Duration::from_secs(5))
            .map_err(|_| "Native game shutdown did not reach the macOS UI thread.".to_string())?;
        return Ok(());
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        let _ = app;
        Ok(())
    }
}

/// True while a native game is actually running, so the phone controller only
/// acknowledges frames that the emulator could really apply.
pub fn native_input_ready() -> bool {
    #[cfg(target_os = "windows")]
    { return windows_runtime::running(); }
    #[cfg(target_os = "linux")]
    { return linux_runtime::running(); }
    #[cfg(target_os = "macos")]
    { return unsafe { an3_native_is_running() != 0 }; }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    { false }
}

/// The system the active native game is running, for the phone pad layout.
pub fn native_active_system() -> Option<String> {
    #[cfg(target_os = "windows")]
    { return windows_runtime::active_system(); }
    #[cfg(target_os = "linux")]
    { return linux_runtime::active_system(); }
    #[cfg(target_os = "macos")]
    {
        return match unsafe { an3_native_active_system() } {
            1 => Some("gba".to_string()),
            2 => Some("nds".to_string()),
            3 => Some("3ds".to_string()),
            _ => None,
        };
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    { None }
}

/// Canonical Phone Controller utility actions, matching
/// `shared/input-actions-schema.json`. A desktop host may only apply these; an
/// unknown action is rejected before it reaches any platform runtime.
pub const UTILITY_ACTIONS: &[&str] = &["QUICK_SAVE", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"];

/// True when `action` is a canonical, dispatchable Phone Controller action.
pub fn is_known_utility(action: &str) -> bool {
    UTILITY_ACTIONS.contains(&action)
}

/// Apply one canonical Phone Controller utility action to the running native
/// host. The desktop hosts reuse the same quick-save, speed and menu operations
/// as their on-screen controls; an unknown action fails explicitly instead of
/// being silently ignored.
pub fn apply_utility(action: &str) -> Result<(), String> {
    if !is_known_utility(action) {
        return Err(format!("Unsupported utility action '{action}'."));
    }
    #[cfg(target_os = "windows")]
    { return windows_runtime::utility(action); }
    #[cfg(target_os = "linux")]
    { return linux_runtime::utility(action); }
    #[cfg(target_os = "macos")]
    {
        let action = c_text(action, "utility action")?;
        let mut details = [0_i8; 256];
        let applied =
            unsafe { an3_native_apply_utility(action.as_ptr(), details.as_mut_ptr(), details.len()) };
        if applied != 0 {
            return Ok(());
        }
        let detail = ffi_detail(&details);
        return Err(if detail.is_empty() {
            "The native player could not apply that utility action.".into()
        } else {
            detail
        });
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        let _ = action;
        Err("Phone Controller utility actions are unavailable on this host.".into())
    }
}

#[tauri::command]
pub fn set_native_input(input: NativeInput) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    { return windows_runtime::input(input); }
    #[cfg(target_os = "linux")]
    { return linux_runtime::input(input); }
    #[cfg(target_os = "macos")]
    unsafe {
        an3_native_set_input(
            input.buttons,
            input.circle_x,
            input.circle_y,
            input.cstick_x,
            input.cstick_y,
            input.touch_x,
            input.touch_y,
            i32::from(input.touch_pressed),
        );
    }
    Ok(())
}

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::{native_core, probe_core};
    use std::path::Path;

    #[test]
    fn pinned_native_cores_expose_the_libretro_abi() {
        for system in ["gba", "nds", "3ds"] {
            let core = native_core(system).expect("known native core");
            let path = Path::new(env!("CARGO_MANIFEST_DIR")).join(core.development_path);
            let detail = probe_core(&path).expect("the verified upstream core should load");
            assert!(!detail.is_empty());
        }
    }
}

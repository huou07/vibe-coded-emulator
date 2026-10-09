// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
//! AN3-side hosted-frame consumer.
//!
//! The Eden companion publishes a POSIX shared-memory ring of IOSurface ids.
//! This module drives the native consumer that attaches to that ring, imports
//! each id as an `MTLTexture` on a background thread and draws the newest one
//! into a pointer-inert overlay in the player's content view. The app never
//! links Eden and no pixels cross the control channel.

use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HostedConsumerStats {
    pub attached: bool,
    pub presenting: bool,
    pub imported_frames: u64,
    pub readback_frames: u64,
    pub presented_frames: u64,
    pub last_sequence: u32,
    pub last_slot: u32,
    pub width: u32,
    pub height: u32,
    pub last_surface_id: u64,
    pub last_nonzero: u64,
    pub last_hash: u64,
}

#[cfg(target_os = "macos")]
mod imp {
    use super::HostedConsumerStats;
    use std::ffi::{c_char, c_int, c_void, CString};

    #[repr(C)]
    #[derive(Clone, Copy, Default)]
    struct RawStats {
        imported_frames: u64,
        readback_frames: u64,
        last_sequence: u32,
        last_slot: u32,
        width: u32,
        height: u32,
        last_surface_id: u64,
        last_nonzero: u64,
        last_hash: u64,
    }

    extern "C" {
        fn an3_eden_hosted_consumer_attach(shm: *const c_char) -> c_int;
        fn an3_eden_hosted_consumer_detach();
        fn an3_eden_hosted_consumer_is_attached() -> c_int;
        fn an3_eden_hosted_consumer_get_stats(out: *mut RawStats) -> c_int;
        fn an3_eden_hosted_consumer_verify_latest(out: *mut RawStats) -> c_int;
        fn an3_eden_hosted_consumer_present_start(content_view: *mut c_void) -> c_int;
        fn an3_eden_hosted_consumer_present_stop();
        fn an3_eden_hosted_consumer_present_is_running() -> c_int;
        fn an3_eden_hosted_consumer_presented_frames() -> u64;
    }

    fn merge(raw: RawStats) -> HostedConsumerStats {
        HostedConsumerStats {
            attached: unsafe { an3_eden_hosted_consumer_is_attached() } != 0,
            presenting: unsafe { an3_eden_hosted_consumer_present_is_running() } != 0,
            presented_frames: unsafe { an3_eden_hosted_consumer_presented_frames() },
            imported_frames: raw.imported_frames,
            readback_frames: raw.readback_frames,
            last_sequence: raw.last_sequence,
            last_slot: raw.last_slot,
            width: raw.width,
            height: raw.height,
            last_surface_id: raw.last_surface_id,
            last_nonzero: raw.last_nonzero,
            last_hash: raw.last_hash,
        }
    }

    pub fn attach(shm: &str) -> Result<(), String> {
        let name = CString::new(shm).map_err(|_| "invalid shared-memory name".to_string())?;
        if unsafe { an3_eden_hosted_consumer_attach(name.as_ptr()) } != 0 {
            Ok(())
        } else {
            Err("The hosted-frame consumer could not attach to the companion's ring.".to_string())
        }
    }

    pub fn detach() {
        unsafe { an3_eden_hosted_consumer_detach() }
    }

    pub fn stats() -> Option<HostedConsumerStats> {
        let mut raw = RawStats::default();
        if unsafe { an3_eden_hosted_consumer_get_stats(&mut raw) } == 0 {
            return None;
        }
        Some(merge(raw))
    }

    pub fn verify_latest() -> Option<HostedConsumerStats> {
        let mut raw = RawStats::default();
        if unsafe { an3_eden_hosted_consumer_verify_latest(&mut raw) } == 0 {
            return None;
        }
        Some(merge(raw))
    }

    pub fn present_start(content_view: *mut c_void) -> Result<(), String> {
        if unsafe { an3_eden_hosted_consumer_present_start(content_view) } != 0 {
            Ok(())
        } else {
            Err("The hosted-frame overlay could not start.".to_string())
        }
    }

    pub fn present_stop() {
        unsafe { an3_eden_hosted_consumer_present_stop() }
    }

    /// Waits off the UI thread for the companion to publish its ring, then
    /// starts the overlay. Bounded so a companion that never renders cannot
    /// leave a thread running forever.
    pub fn start_when_ready(app: &tauri::AppHandle) {
        let app = app.clone();
        std::thread::spawn(move || {
            if super::wait_for_hosted_ring(std::time::Duration::from_secs(20)).is_some() {
                let _ = super::start(&app);
            }
        });
    }
}

#[cfg(not(target_os = "macos"))]
mod imp {
    use super::HostedConsumerStats;
    use std::ffi::c_void;

    pub fn attach(_shm: &str) -> Result<(), String> {
        Err("The Nintendo Switch hosted frame is only supported on macOS.".to_string())
    }
    pub fn detach() {}
    pub fn stats() -> Option<HostedConsumerStats> {
        None
    }
    pub fn verify_latest() -> Option<HostedConsumerStats> {
        None
    }
    pub fn present_start(_content_view: *mut c_void) -> Result<(), String> {
        Err("The Nintendo Switch hosted frame is only supported on macOS.".to_string())
    }
    pub fn present_stop() {}
    pub fn start_when_ready(_app: &tauri::AppHandle) {}
}

/// Attach the native consumer to a published ring. Used by the app command and
/// by the runtime test.
pub fn attach(shm: &str) -> Result<(), String> {
    imp::attach(shm)
}

pub fn detach() {
    imp::detach()
}

pub fn stats() -> Option<HostedConsumerStats> {
    imp::stats()
}

pub fn verify_latest() -> Option<HostedConsumerStats> {
    imp::verify_latest()
}

/// Attach to the running companion's ring and start presenting the newest frame
/// in a pointer-inert overlay over the player's content view.
pub fn start(app: &tauri::AppHandle) -> Result<HostedConsumerStats, String> {
    let info = crate::switch_companion::hosted_frame()
        .ok_or_else(|| "The companion has not published a hosted-frame ring yet.".to_string())?;
    imp::attach(&info.shm)?;

    #[cfg(target_os = "macos")]
    {
        use tauri::Manager;
        let window = app
            .get_webview_window("main")
            .ok_or_else(|| "VibeCodedEmulator main window is unavailable.".to_string())?;
        let content_view = window
            .ns_view()
            .map_err(|error| format!("Cannot access the macOS content view: {error}"))?
            as usize;
        let (sender, receiver) = std::sync::mpsc::sync_channel(1);
        app.run_on_main_thread(move || {
            let started = imp::present_start(content_view as *mut std::ffi::c_void).is_ok();
            let _ = sender.send(started);
        })
        .map_err(|error| format!("Cannot schedule hosted-frame presentation: {error}"))?;
        let started = receiver
            .recv_timeout(std::time::Duration::from_secs(5))
            .map_err(|_| "Hosted-frame presentation did not reach the macOS UI thread.".to_string())?;
        if !started {
            imp::detach();
            return Err("The hosted-frame overlay could not start.".to_string());
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = app;
    }

    stats().ok_or_else(|| "The hosted-frame consumer is not reporting state.".to_string())
}

/// Stop presenting and detach from the ring.
pub fn stop() {
    imp::present_stop();
    imp::detach();
}

/// Start presenting once the companion publishes its ring (off the UI thread,
/// bounded). Used when the companion is launched hidden.
pub fn start_when_ready(app: &tauri::AppHandle) {
    imp::start_when_ready(app);
}

/// Waits (bounded) for the running companion to publish its ring. Pure besides
/// the companion state, so it is directly testable.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
pub(crate) fn wait_for_hosted_ring(
    timeout: std::time::Duration,
) -> Option<crate::switch_companion::HostedFrameInfo> {
    let deadline = std::time::Instant::now() + timeout;
    while std::time::Instant::now() < deadline {
        if let Some(info) = crate::switch_companion::hosted_frame() {
            return Some(info);
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    None
}

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    /// End-to-end: the app's native consumer attaches to the real companion's
    /// ring, imports frames into an MTLTexture and verifies real pixels.
    #[test]
    #[ignore = "requires AN3_SWITCH_COMPANION and AN3_SWITCH_HOMEBREW"]
    fn e2e_consumer_imports_frames_over_shm() {
        let binary =
            std::path::PathBuf::from(std::env::var("AN3_SWITCH_COMPANION").expect("companion"));
        let content = std::env::var("AN3_SWITCH_HOMEBREW").expect("homebrew nro");
        let moltenvk = std::env::var("AN3_SWITCH_MOLTENVK")
            .ok()
            .map(std::path::PathBuf::from);

        let started =
            crate::switch_companion::launch_with(&binary, moltenvk.as_deref(), &content, false)
                .expect("launch");
        assert!(started.running);

        let deadline = Instant::now() + Duration::from_secs(20);
        let mut info = None;
        while Instant::now() < deadline {
            if let Some(value) = crate::switch_companion::hosted_frame() {
                info = Some(value);
                break;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        let info = info.expect("the companion never published a hosted-frame ring");

        attach(&info.shm).expect("attach");
        let deadline = Instant::now() + Duration::from_secs(20);
        let mut imported = 0_u64;
        while Instant::now() < deadline {
            if let Some(current) = stats() {
                imported = current.imported_frames;
                if imported > 0 {
                    break;
                }
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        assert!(imported > 0, "the native consumer imported no frames");

        let verified = verify_latest().expect("verify latest frame");
        assert!(verified.last_nonzero > 0, "the imported frame was empty");
        assert_eq!(verified.width, 1280);
        assert_eq!(verified.height, 720);

        stop();
        crate::switch_companion::stop();
    }

    /// End-to-end: the bounded wait used when a hidden companion is launched
    /// resolves the ring name from the real companion.
    #[test]
    #[ignore = "requires AN3_SWITCH_COMPANION and AN3_SWITCH_HOMEBREW"]
    fn e2e_wait_for_hosted_ring_resolves() {
        let binary =
            std::path::PathBuf::from(std::env::var("AN3_SWITCH_COMPANION").expect("companion"));
        let content = std::env::var("AN3_SWITCH_HOMEBREW").expect("homebrew nro");
        let moltenvk = std::env::var("AN3_SWITCH_MOLTENVK")
            .ok()
            .map(std::path::PathBuf::from);

        let started =
            crate::switch_companion::launch_with(&binary, moltenvk.as_deref(), &content, false)
                .expect("launch");
        assert!(started.running);

        let info = wait_for_hosted_ring(std::time::Duration::from_secs(20))
            .expect("the companion never published a ring");
        assert!(info.shm.starts_with("/an3hf_"));
        assert_eq!(info.slots, 3);
        assert_ne!(info.epoch, 0);

        crate::switch_companion::stop();
    }
}

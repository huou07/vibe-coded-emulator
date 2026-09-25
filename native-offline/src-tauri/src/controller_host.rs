// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Legacy development/test phone-controller client for the desktop shells.
//!
//! This module is retained only for explicit development/test adapters. The
//! installed desktop app uses `lan_host` for direct peer sessions.
//! The same module serves macOS, Linux, and Windows; the platform difference is
//! already handled by `set_native_input`.
//!
//! Its plain HTTP implementation must not be selected by normal product UI.

use serde::Serialize;
use std::{
    io::{Read, Write},
    net::TcpStream,
    sync::{
        atomic::{AtomicBool, AtomicI8, AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread::JoinHandle,
    time::Duration,
};

use crate::azahar::{set_native_input, NativeInput};
use crate::host_actions::{self, HostAction, ReplayGuard};

const POLL_INTERVAL: Duration = Duration::from_millis(250);
const IO_TIMEOUT: Duration = Duration::from_secs(4);
const NATIVE_SESSION_TTL_SECONDS: u64 = 3600;
const AXIS_THRESHOLD: f32 = 0.35;

/// libretro joypad indices, identical to the web player and the phone page.
const BUTTONS: &[(&str, u32)] = &[
    ("b", 0),
    ("y", 1),
    ("select", 2),
    ("start", 3),
    ("up", 4),
    ("down", 5),
    ("left", 6),
    ("right", 7),
    ("a", 8),
    ("x", 9),
    ("l", 10),
    ("r", 11),
];

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ControllerSession {
    pub code: String,
    pub join_path: String,
    pub ttl_seconds: u64,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ControllerStatus {
    pub running: bool,
    pub paired: bool,
    pub code: String,
    pub input: String,
    /// True only when the host has actually applied and acknowledged frames,
    /// i.e. a native game is running and keeping up with the phone.
    pub input_active: bool,
    pub expires_in_seconds: u64,
    pub error: String,
}

type InputSink = Arc<dyn Fn(NativeInput) + Send + Sync>;
/// Executes one canonical utility action and reports whether the host actually
/// performed it. Returning `false` keeps an unsupported action from being
/// acknowledged as successful.
pub(crate) type UtilitySink = Arc<dyn Fn(&HostAction) -> bool + Send + Sync>;

struct Host {
    stop: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
    code: String,
    paired: Arc<AtomicBool>,
    input: Arc<Mutex<String>>,
    input_active: Arc<AtomicBool>,
    expires: Arc<AtomicU64>,
    error: Arc<Mutex<String>>,
}

static HOST: Mutex<Option<Host>> = Mutex::new(None);

/// Test seam: -1 uses the platform runtime, 0 forces "no game", 1 forces
/// "game running". Production always leaves it at -1.
static INPUT_READY_OVERRIDE: AtomicI8 = AtomicI8::new(-1);

fn input_ready() -> bool {
    match INPUT_READY_OVERRIDE.load(Ordering::Relaxed) {
        0 => false,
        1 => true,
        _ => crate::azahar::native_input_ready(),
    }
}

fn sink_default() -> InputSink {
    Arc::new(|input| {
        let _ = set_native_input(input);
    })
}

pub(crate) fn utility_sink_default() -> UtilitySink {
    Arc::new(|command| {
        if !input_ready() {
            let reason = "No native game is running on the host.";
            #[cfg(target_os = "macos")]
            crate::controller_utility_queue::record_rejected(
                &command.command_id,
                &command.action,
                command.slot,
                reason,
            );
            eprintln!("AN3 controller utility '{}' failed: {reason}", command.action);
            return false;
        }
        // On macOS, keep discrete actions out of the LAN reader. The native
        // frame owner consumes this bounded queue at its state_mutex_ boundary;
        // completion is returned only after that frame operation and any
        // asynchronous save-file write have finished. Normal input continues
        // to update lock-free atomics in parallel.
        #[cfg(target_os = "macos")]
        let result = crate::controller_utility_queue::enqueue(
            &command.action,
            command.slot,
            &command.command_id,
        );
        #[cfg(not(target_os = "macos"))]
        let result = crate::azahar::apply_utility_at_slot(&command.action, command.slot);
        match result {
            Ok(()) => true,
            Err(reason) => {
                #[cfg(target_os = "macos")]
                crate::controller_utility_queue::record_rejected(
                    &command.command_id,
                    &command.action,
                    command.slot,
                    &reason,
                );
                eprintln!("AN3 controller utility '{}' failed: {reason}", command.action);
                false
            }
        }
    })
}

/// Apply each not-yet-seen host action once and return the newest sequence that
/// the host actually executed. Direct peers identify commands with
/// `command_id`; legacy staging frames fall back to their numeric sequence.
///
/// Both direct-LAN (`u`) and staging-server (`utilities`) frame shapes carry
/// `{action, command_id, slot, sequence}` entries.
pub(crate) fn dispatch_utilities(
    payload: &serde_json::Value,
    replay: &mut ReplayGuard,
    sink: &UtilitySink,
) -> i64 {
    host_actions::dispatch(payload, replay, &|command| sink(command))
}

fn set_error(slot: &Arc<Mutex<String>>, message: impl Into<String>) {
    if let Ok(mut guard) = slot.lock() {
        *guard = message.into();
    }
}

/// Turn one host-state payload into a complete native input snapshot.
pub(crate) fn frame_input(frame: &serde_json::Value) -> NativeInput {
    let state = frame.get("state");
    let mut buttons = 0u32;
    if let Some(list) = state.and_then(|value| value.get("b")).and_then(|value| value.as_array()) {
        for name in list.iter().filter_map(|value| value.as_str()) {
            if let Some((_, index)) = BUTTONS.iter().find(|(candidate, _)| *candidate == name) {
                buttons |= 1u32 << index;
            }
        }
    }
    let axes = state.and_then(|value| value.get("a")).and_then(|value| value.as_array());
    let axis = |index: usize| {
        axes.and_then(|values| values.get(index))
            .and_then(|value| value.as_f64())
            .unwrap_or(0.0) as f32
    };
    let (left_x, left_y, right_x, right_y) = (axis(0), axis(1), axis(2), axis(3));
    // Mirror the web pad: an engaged analogue stick also presses the matching
    // d-pad direction so cores that only read the d-pad still respond.
    if left_y < -AXIS_THRESHOLD {
        buttons |= 1 << 4;
    }
    if left_y > AXIS_THRESHOLD {
        buttons |= 1 << 5;
    }
    if left_x < -AXIS_THRESHOLD {
        buttons |= 1 << 6;
    }
    if left_x > AXIS_THRESHOLD {
        buttons |= 1 << 7;
    }
    let scale = |value: f32| (value.clamp(-1.0, 1.0) * 32767.0) as i16;
    // Normalized phone touch (0..1) maps to the libretro absolute Pointer
    // contract used by the in-app NDS/3DS touch screen.
    let touch = state.and_then(|value| value.get("t")).and_then(|value| value.as_array());
    let (touch_x, touch_y, touch_pressed) = match touch {
        Some(values) if values.len() == 2 => {
            let nx = values[0].as_f64().unwrap_or(0.0).clamp(0.0, 1.0) as f32;
            let ny = values[1].as_f64().unwrap_or(0.0).clamp(0.0, 1.0) as f32;
            (
                (nx * 65534.0 - 32767.0).round() as i16,
                (ny * 65534.0 - 32767.0).round() as i16,
                true,
            )
        }
        _ => (0, 0, false),
    };
    NativeInput {
        buttons,
        circle_x: scale(left_x),
        circle_y: scale(left_y),
        cstick_x: scale(right_x),
        cstick_y: scale(right_y),
        touch_x,
        touch_y,
        touch_pressed,
    }
}

#[cfg(test)]
pub(crate) fn buttons_bitmask(names: &[&str]) -> u32 {
    let mut buttons = 0u32;
    for name in names {
        if let Some((_, index)) = BUTTONS.iter().find(|(candidate, _)| candidate == name) {
            buttons |= 1u32 << index;
        }
    }
    buttons
}

#[cfg(test)]
mod button_map_tests {
    use super::*;

    #[test]
    fn button_map_matches_the_shared_indices() {
        assert_eq!(buttons_bitmask(&["b"]), 1 << 0);
        assert_eq!(buttons_bitmask(&["a"]), 1 << 8);
        assert_eq!(buttons_bitmask(&["right"]), 1 << 7);
        assert_eq!(BUTTONS.len(), 12);
    }
}

fn parse_base(base: &str) -> Result<(String, u16), String> {
    let trimmed = base.trim().trim_end_matches('/');
    if trimmed.is_empty() {
        return Err("Set an explicit development controller fixture URL.".into());
    }
    let rest = trimmed
        .strip_prefix("http://")
        .ok_or("The desktop controller client requires a plain http:// LAN origin.")?;
    let host_port = rest.split('/').next().unwrap_or(rest);
    match host_port.rsplit_once(':') {
        Some((host, port)) => {
            if host.is_empty() {
                return Err("Invalid controller server host.".into());
            }
            let port = port.parse::<u16>().map_err(|_| "Invalid controller server port.")?;
            Ok((host.to_string(), port))
        }
        None if !host_port.is_empty() => Ok((host_port.to_string(), 80)),
        None => Err("Invalid controller server host.".into()),
    }
}

fn http_request(base: &str, method: &str, path: &str, body: Option<&str>) -> Result<(u16, String), String> {
    let (host, port) = parse_base(base)?;
    let mut stream = TcpStream::connect((host.as_str(), port)).map_err(|error| error.to_string())?;
    let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
    let _ = stream.set_write_timeout(Some(IO_TIMEOUT));
    let mut request = format!(
        "{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\nAccept: application/json\r\nConnection: close\r\n"
    );
    if let Some(payload) = body {
        request.push_str(&format!(
            "Content-Type: application/json\r\nContent-Length: {}\r\n",
            payload.as_bytes().len()
        ));
    }
    request.push_str("\r\n");
    if let Some(payload) = body {
        request.push_str(payload);
    }
    stream.write_all(request.as_bytes()).map_err(|error| error.to_string())?;
    let mut response = String::new();
    stream.read_to_string(&mut response).map_err(|error| error.to_string())?;
    let (head, payload) = response.split_once("\r\n\r\n").ok_or("Malformed controller response.")?;
    let status = head
        .split_whitespace()
        .nth(1)
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or("Malformed controller status line.")?;
    Ok((status, payload.to_string()))
}

fn json_field<'a>(value: &'a serde_json::Value, key: &str) -> String {
    value
        .get(key)
        .and_then(|item| item.as_str())
        .unwrap_or("")
        .to_string()
}

/// Start a host session. `base_url` is the staging controller origin.
pub fn start(base_url: String) -> Result<ControllerSession, String> {
    start_with(base_url, sink_default(), utility_sink_default())
}

pub(crate) fn start_with(base_url: String, sink: InputSink, utility_sink: UtilitySink) -> Result<ControllerSession, String> {
    stop();
    let base = base_url.trim().trim_end_matches('/').to_string();
    let payload = format!("{{\"deviceId\":\"desktop-native\",\"ttlSeconds\":{NATIVE_SESSION_TTL_SECONDS}}}");
    let (status, body) = http_request(&base, "POST", "/api/controller/session", Some(&payload))?;
    if status != 201 {
        return Err(format!("Controller session failed (HTTP {status})."));
    }
    let session: serde_json::Value =
        serde_json::from_str(&body).map_err(|_| "Controller session response was not JSON.".to_string())?;
    let code = json_field(&session, "code");
    let host_token = json_field(&session, "hostToken");
    if code.is_empty() || host_token.is_empty() {
        return Err("Controller session response was incomplete.".into());
    }
    let join_path = json_field(&session, "joinPath");
    let ttl_seconds = session.get("ttlSeconds").and_then(|value| value.as_u64()).unwrap_or(120);
    let query = format!("/api/controller/state?code={code}&hostToken={host_token}");

    let stop = Arc::new(AtomicBool::new(false));
    let paired = Arc::new(AtomicBool::new(false));
    let input = Arc::new(Mutex::new(String::new()));
    let input_active = Arc::new(AtomicBool::new(false));
    let expires = Arc::new(AtomicU64::new(ttl_seconds));
    let error = Arc::new(Mutex::new(String::new()));

    let thread_base = base.clone();
    let thread_stop = stop.clone();
    let thread_paired = paired.clone();
    let thread_input = input.clone();
    let thread_input_active = input_active.clone();
    let thread_expires = expires.clone();
    let thread_error = error.clone();
    let ack_code = code.clone();
    let ack_token = host_token.clone();
    let handle = std::thread::spawn(move || {
        let mut last_acked: i64 = -1;
        let mut last_utility = ReplayGuard::default();
        let mut last_utility_acked: i64 = 0;
        while !thread_stop.load(Ordering::Relaxed) {
            match http_request(&thread_base, "GET", &query, None) {
                Ok((200, body)) => {
                    let payload: serde_json::Value = serde_json::from_str(&body).unwrap_or(serde_json::Value::Null);
                    let is_paired = payload.get("paired").and_then(|value| value.as_bool()).unwrap_or(false);
                    thread_paired.store(is_paired, Ordering::Relaxed);
                    let remaining = payload
                        .get("expiresInSeconds")
                        .and_then(|value| value.as_u64())
                        .unwrap_or(0);
                    thread_expires.store(remaining, Ordering::Relaxed);
                    if is_paired {
                        if let Ok(mut guard) = thread_input.lock() {
                            *guard = describe(&payload);
                        }
                        // Only acknowledge when a native game can really apply
                        // the frame; otherwise the phone would be told "input
                        // available" while nothing is running.
                        let ready = input_ready();
                        if ready {
                            sink(frame_input(&payload));
                            let sequence = payload
                                .get("lastSequence")
                                .and_then(|value| value.as_i64())
                                .unwrap_or(0);
                            let utility_sequence =
                                dispatch_utilities(&payload, &mut last_utility, &utility_sink);
                            if (sequence > last_acked && sequence > 0)
                                || utility_sequence > last_utility_acked
                            {
                                // Tell the phone which system is running so it
                                // can pick the matching pad layout.
                                let system_clause = match crate::azahar::native_active_system() {
                                    Some(system) => format!(",\"system\":\"{system}\""),
                                    None => String::new(),
                                };
                                let applied_sequence = sequence.max(last_acked).max(0);
                                let ack_body = format!(
                                    "{{\"code\":\"{ack_code}\",\"hostToken\":\"{ack_token}\",\"sequence\":{applied_sequence},\"utilitySequence\":{utility_sequence}{system_clause}}}"
                                );
                                let _ = http_request(&thread_base, "POST", "/api/controller/ack", Some(&ack_body));
                                last_acked = applied_sequence;
                                last_utility_acked = utility_sequence;
                            }
                        } else {
                            sink(frame_input(&serde_json::Value::Null));
                        }
                        let active = ready
                            && payload.get("inputActive").and_then(|value| value.as_bool()).unwrap_or(false);
                        thread_input_active.store(active, Ordering::Relaxed);
                    } else {
                        if let Ok(mut guard) = thread_input.lock() {
                            guard.clear();
                        }
                        sink(frame_input(&serde_json::Value::Null));
                        thread_input_active.store(false, Ordering::Relaxed);
                        last_acked = -1;
                        last_utility.reset();
                        last_utility_acked = 0;
                    }
                }
                Ok((403, _)) | Ok((404, _)) => {
                    // The session ended or expired. Release before stopping.
                    set_error(&thread_error, "Controller session ended");
                    sink(frame_input(&serde_json::Value::Null));
                    thread_paired.store(false, Ordering::Relaxed);
                    thread_input_active.store(false, Ordering::Relaxed);
                    thread_expires.store(0, Ordering::Relaxed);
                    break;
                }
                Ok((status, _)) => {
                    set_error(&thread_error, format!("Controller server returned HTTP {status}"));
                }
                Err(_) => {}
            }
            std::thread::sleep(POLL_INTERVAL);
        }
        sink(frame_input(&serde_json::Value::Null));
    });

    *HOST.lock().map_err(|_| "Controller state lock unavailable".to_string())? = Some(Host {
        stop,
        handle: Some(handle),
        code: code.clone(),
        paired,
        input,
        input_active,
        expires,
        error,
    });
    Ok(ControllerSession { code, join_path, ttl_seconds })
}

/// Stop the host session and release every input.
pub fn stop() {
    let previous = HOST.lock().ok().and_then(|mut guard| guard.take());
    if let Some(mut host) = previous {
        host.stop.store(true, Ordering::Relaxed);
        if let Some(handle) = host.handle.take() {
            let _ = handle.join();
        }
        let _ = set_native_input(frame_input(&serde_json::Value::Null));
    }
}

pub fn status() -> ControllerStatus {
    match HOST.lock() {
        Ok(guard) => match guard.as_ref() {
            Some(host) => ControllerStatus {
                running: true,
                paired: host.paired.load(Ordering::Relaxed),
                code: host.code.clone(),
                input: host.input.lock().map(|value| value.clone()).unwrap_or_default(),
                input_active: host.input_active.load(Ordering::Relaxed),
                expires_in_seconds: host.expires.load(Ordering::Relaxed),
                error: host.error.lock().map(|value| value.clone()).unwrap_or_default(),
            },
            None => ControllerStatus {
                running: false,
                paired: false,
                code: String::new(),
                input: String::new(),
                input_active: false,
                expires_in_seconds: 0,
                error: String::new(),
            },
        },
        Err(_) => ControllerStatus {
            running: false,
            paired: false,
            code: String::new(),
            input: String::new(),
            input_active: false,
            expires_in_seconds: 0,
            error: "Controller state lock unavailable".into(),
        },
    }
}

fn describe(frame: &serde_json::Value) -> String {
    frame
        .get("state")
        .and_then(|state| state.get("b"))
        .and_then(|value| value.as_array())
        .map(|list| {
            list.iter()
                .filter_map(|value| value.as_str())
                .collect::<Vec<_>>()
                .join(",")
        })
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::BufRead;

    /// `HOST` and `INPUT_READY_OVERRIDE` are process-global, so the tests that
    /// drive a session must not run in parallel with each other.
    static SESSION_TEST_LOCK: Mutex<()> = Mutex::new(());

    fn serialize() -> std::sync::MutexGuard<'static, ()> {
        SESSION_TEST_LOCK.lock().unwrap_or_else(|error| error.into_inner())
    }

    /// A tiny scripted HTTP server: every request is answered with the next
    /// scripted response (the last one repeats).
    fn scripted_server(responses: Vec<(u16, &'static str)>) -> (String, Arc<AtomicU64>) {
        use std::net::TcpListener;
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let address = listener.local_addr().expect("addr");
        let served = Arc::new(AtomicU64::new(0));
        let counter = served.clone();
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { continue };
                let index = counter.fetch_add(1, Ordering::SeqCst) as usize;
                let (status, body) = responses[index.min(responses.len() - 1)];
                // Read the request head (and body) before answering.
                let mut reader = std::io::BufReader::new(stream.try_clone().expect("clone"));
                let mut line = String::new();
                let mut length = 0usize;
                while reader.read_line(&mut line).unwrap_or(0) > 0 {
                    if let Some(value) = line.to_ascii_lowercase().strip_prefix("content-length:") {
                        length = value.trim().parse().unwrap_or(0);
                    }
                    if line == "\r\n" {
                        break;
                    }
                    line.clear();
                }
                if length > 0 {
                    let mut body = vec![0u8; length];
                    let _ = reader.read_exact(&mut body);
                }
                let reason = if status == 201 { "Created" } else if status == 200 { "OK" } else { "Error" };
                let response = format!(
                    "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                let _ = stream.write_all(response.as_bytes());
            }
        });
        (format!("http://{address}"), served)
    }

    #[test]
    fn frame_input_maps_buttons_and_axes() {
        let frame = serde_json::json!({"state": {"s": 3, "b": ["start", "a"], "a": [0.0, 1.0, 0.0, 0.0]}});
        let input = frame_input(&frame);
        assert_eq!(input.buttons & (1 << 3), 1 << 3, "start bit");
        assert_eq!(input.buttons & (1 << 8), 1 << 8, "a bit");
        assert_eq!(input.circle_y, 32767);
        assert_eq!(input.buttons & (1 << 5), 1 << 5, "down from the engaged axis");
        assert_eq!(input.circle_x, 0);
    }

    #[test]
    fn frame_input_is_empty_for_an_unpaired_payload() {
        let input = frame_input(&serde_json::Value::Null);
        assert_eq!(input.buttons, 0);
        assert_eq!(input.circle_x, 0);
        assert_eq!(input.circle_y, 0);
    }

    #[test]
    fn frame_input_maps_normalized_touch_to_the_pointer_contract() {
        let frame = serde_json::json!({"state": {"s": 2, "b": [], "t": [0.0, 1.0]}});
        let input = frame_input(&frame);
        assert!(input.touch_pressed);
        assert_eq!(input.touch_x, -32767);
        assert_eq!(input.touch_y, 32767);
        let released = frame_input(&serde_json::json!({"state": {"s": 3, "b": []}}));
        assert!(!released.touch_pressed);
    }

    #[test]
    fn a_missing_game_never_acknowledges_input() {
        let _guard = serialize();
        INPUT_READY_OVERRIDE.store(0, Ordering::Relaxed);
        let (base, _) = scripted_server(vec![
            (201, "{\"code\":\"ABC123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/controller/join?code=ABC123\"}"),
            (200, "{\"paired\":true,\"lastSequence\":4,\"ackSequence\":0,\"inputActive\":false,\"state\":{\"s\":4,\"b\":[\"a\"]}}"),
        ]);
        let seen: Arc<Mutex<Vec<u32>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: InputSink = Arc::new(move |input| collector.lock().unwrap().push(input.buttons));
        let _session = start_with(base, sink, utility_sink_default()).expect("session");
        std::thread::sleep(Duration::from_millis(600));
        assert!(seen.lock().unwrap().iter().all(|buttons| *buttons == 0));
        assert!(!status().input_active);
        stop();
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);
    }

    #[test]
    fn utilities_dispatch_once_and_track_the_newest_sequence() {
        let seen: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: UtilitySink = Arc::new(move |action| {
            collector.lock().unwrap().push(action.action.clone());
            true
        });
        let payload = serde_json::json!({
            "utilities": [
                {"action": "quick_save", "sequence": 2},
                {"action": "speed_up", "sequence": 3},
                {"action": "quick_save", "sequence": 3},
                {"action": "open_menu", "sequence": 1}
            ]
        });
        let mut last = ReplayGuard::default();
        let newest = dispatch_utilities(&payload, &mut last, &sink);
        assert_eq!(newest, 3);
        assert_eq!(seen.lock().unwrap().clone(), vec!["QUICK_SAVE", "SPEED_UP"]);
        // A retried/duplicated frame must not repeat the side effects.
        dispatch_utilities(&payload, &mut last, &sink);
        assert_eq!(seen.lock().unwrap().len(), 2);
    }

    /// The canonical action list is exactly the shared schema; an action outside
    /// it must never reach a platform runtime.
    #[test]
    fn only_canonical_utility_actions_are_dispatchable() {
        assert_eq!(
            crate::azahar::UTILITY_ACTIONS,
            &["QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"]
        );
        for action in crate::azahar::UTILITY_ACTIONS {
            assert!(crate::azahar::is_known_utility(action));
        }
        assert!(!crate::azahar::is_known_utility("quick_save"));
        assert!(!crate::azahar::is_known_utility("NOPE"));
    }

    /// Every canonical action fires its side effect exactly once, and retried or
    /// duplicated frames never repeat a one-shot action.
    #[test]
    fn each_utility_action_dispatches_exactly_once() {
        let seen: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: UtilitySink =
            Arc::new(move |action| { collector.lock().unwrap().push(action.action.clone()); true });
        let payload = serde_json::json!({
            "utilities": [
                {"action": "QUICK_SAVE", "sequence": 1},
                {"action": "QUICK_LOAD", "sequence": 2},
                {"action": "SPEED_UP", "sequence": 3},
                {"action": "SPEED_DOWN", "sequence": 4},
                {"action": "OPEN_MENU", "sequence": 5}
            ]
        });
        let mut last = ReplayGuard::default();
        assert_eq!(dispatch_utilities(&payload, &mut last, &sink), 5);
        assert_eq!(
            seen.lock().unwrap().clone(),
            vec!["QUICK_SAVE", "QUICK_LOAD", "SPEED_UP", "SPEED_DOWN", "OPEN_MENU"]
        );
        dispatch_utilities(&payload, &mut last, &sink);
        assert_eq!(seen.lock().unwrap().len(), 5, "a retry must not repeat a one-shot action");
    }

    #[test]
    fn a_duplicate_sequence_is_ignored() {
        let seen: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: UtilitySink =
            Arc::new(move |action| { collector.lock().unwrap().push(action.action.clone()); true });
        let payload = serde_json::json!({
            "utilities": [
                {"action": "QUICK_SAVE", "sequence": 5},
                {"action": "SPEED_UP", "sequence": 5}
            ]
        });
        let mut last = ReplayGuard::default();
        dispatch_utilities(&payload, &mut last, &sink);
        assert_eq!(seen.lock().unwrap().clone(), vec!["QUICK_SAVE"]);
    }

    #[test]
    fn command_ids_allow_same_sequence_and_preserve_save_slots() {
        let seen: Arc<Mutex<Vec<(String, u8)>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: UtilitySink = Arc::new(move |action| {
            collector.lock().unwrap().push((action.action.clone(), action.slot));
            true
        });
        let payload = serde_json::json!({
            "u": [
                {"action": "QUICK_SAVE", "sequence": 7, "command_id": "phone-a", "slot": 3},
                {"action": "QUICK_LOAD", "sequence": 7, "command_id": "phone-b", "slot": 10}
            ]
        });
        let mut replay = ReplayGuard::default();
        assert_eq!(dispatch_utilities(&payload, &mut replay, &sink), 7);
        assert_eq!(
            seen.lock().unwrap().clone(),
            vec![("QUICK_SAVE".into(), 3), ("QUICK_LOAD".into(), 10)]
        );
        assert_eq!(dispatch_utilities(&payload, &mut replay, &sink), 0);
        assert_eq!(seen.lock().unwrap().len(), 2);
    }

    fn utility_collector() -> (UtilitySink, Arc<Mutex<Vec<String>>>) {
        let seen: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        (
            Arc::new(move |action| { collector.lock().unwrap().push(action.action.clone()); true }),
            seen,
        )
    }

    #[test]
    fn a_missing_game_never_dispatches_utilities() {
        let _guard = serialize();
        INPUT_READY_OVERRIDE.store(0, Ordering::Relaxed);
        let (base, _) = scripted_server(vec![
            (201, "{\"code\":\"ABC123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/c\"}"),
            (200, "{\"paired\":true,\"lastSequence\":3,\"ackSequence\":0,\"inputActive\":false,\"state\":{\"s\":3,\"b\":[\"a\"]},\"utilities\":[{\"action\":\"QUICK_SAVE\",\"sequence\":1}]}"),
        ]);
        let (utility_sink, seen) = utility_collector();
        let _session = start_with(base, Arc::new(|_| {}), utility_sink).expect("session");
        std::thread::sleep(Duration::from_millis(600));
        assert!(
            seen.lock().unwrap().is_empty(),
            "utilities must never run while no game can apply them"
        );
        stop();
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);
    }

    /// Both the gameplay frame and the one-shot utility in the same payload must
    /// apply, proving utilities do not displace input handling.
    #[test]
    fn gameplay_input_and_a_utility_apply_together() {
        let _guard = serialize();
        INPUT_READY_OVERRIDE.store(1, Ordering::Relaxed);
        let (base, _) = scripted_server(vec![
            (201, "{\"code\":\"ABC123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/c\"}"),
            (200, "{\"paired\":true,\"lastSequence\":2,\"ackSequence\":0,\"inputActive\":false,\"state\":{\"s\":2,\"b\":[\"right\"]},\"utilities\":[{\"action\":\"SPEED_UP\",\"sequence\":1}]}"),
        ]);
        let buttons: Arc<Mutex<Vec<u32>>> = Arc::new(Mutex::new(Vec::new()));
        let button_collector = buttons.clone();
        let input_sink: InputSink =
            Arc::new(move |input| button_collector.lock().unwrap().push(input.buttons));
        let (utility_sink, seen) = utility_collector();
        let _session = start_with(base, input_sink, utility_sink).expect("session");
        let mut both_applied = false;
        for _ in 0..40 {
            let applied = seen.lock().unwrap().contains(&"SPEED_UP".to_string());
            let pressed = buttons.lock().unwrap().iter().any(|bits| bits & (1 << 7) != 0);
            if applied && pressed {
                both_applied = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        assert!(both_applied, "a gameplay frame and its utility must both apply");
        assert_eq!(seen.lock().unwrap().clone(), vec!["SPEED_UP"]);
        assert!(
            buttons.lock().unwrap().iter().any(|bits| bits & (1 << 7) != 0),
            "the phone's right press must still reach the input sink"
        );
        stop();
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);
    }

    /// A session that ends (403/404) must not re-dispatch a utility it already
    /// applied, and must clear its stale sequence tracking.
    #[test]
    fn an_ended_session_does_not_repeat_utilities() {
        let _guard = serialize();
        INPUT_READY_OVERRIDE.store(1, Ordering::Relaxed);
        let (base, _) = scripted_server(vec![
            (201, "{\"code\":\"ABC123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/c\"}"),
            (200, "{\"paired\":true,\"lastSequence\":2,\"ackSequence\":0,\"inputActive\":false,\"state\":{\"s\":2,\"b\":[]},\"utilities\":[{\"action\":\"OPEN_MENU\",\"sequence\":1}]}"),
            (403, "{}"),
        ]);
        let (utility_sink, seen) = utility_collector();
        let _session = start_with(base, Arc::new(|_| {}), utility_sink).expect("session");
        std::thread::sleep(Duration::from_millis(900));
        assert_eq!(seen.lock().unwrap().clone(), vec!["OPEN_MENU"]);
        assert_eq!(status().error, "Controller session ended");
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);
    }

    /// Disconnect then reconnect: the same per-press sequence must dispatch
    /// again because it belongs to a new session, not the previous one.
    #[test]
    fn a_reconnect_dispatches_utilities_again() {
        let _guard = serialize();
        INPUT_READY_OVERRIDE.store(1, Ordering::Relaxed);
        let session_body = "{\"code\":\"ABC123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/c\"}";
        let frame = "{\"paired\":true,\"lastSequence\":1,\"ackSequence\":0,\"inputActive\":false,\"state\":{\"s\":1,\"b\":[]},\"utilities\":[{\"action\":\"QUICK_SAVE\",\"sequence\":1}]}";

        let (first_base, _) = scripted_server(vec![(201, session_body), (200, frame)]);
        let (first_sink, first_seen) = utility_collector();
        let _first = start_with(first_base, Arc::new(|_| {}), first_sink).expect("first session");
        for _ in 0..40 {
            if !first_seen.lock().unwrap().is_empty() {
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        stop();

        let (second_base, _) = scripted_server(vec![(201, session_body), (200, frame)]);
        let (second_sink, second_seen) = utility_collector();
        let _second = start_with(second_base, Arc::new(|_| {}), second_sink).expect("second session");
        for _ in 0..40 {
            if !second_seen.lock().unwrap().is_empty() {
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        stop();
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);

        assert_eq!(first_seen.lock().unwrap().clone(), vec!["QUICK_SAVE"]);
        assert_eq!(second_seen.lock().unwrap().clone(), vec!["QUICK_SAVE"]);
    }

    #[test]
    fn an_unsupported_utility_action_is_never_acknowledged() {
        let calls: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let seen = calls.clone();
        let sink: UtilitySink = Arc::new(move |action| {
            seen.lock().unwrap().push(action.action.clone());
            // Simulate a platform that can only perform speed_up.
            action.action == "SPEED_UP"
        });
        let payload = serde_json::json!({
            "u": [
                {"action": "quick_save", "sequence": 1},
                {"action": "speed_up", "sequence": 2}
            ]
        });
        let mut last = ReplayGuard::default();
        assert_eq!(dispatch_utilities(&payload, &mut last, &sink), 2);
        assert_eq!(calls.lock().unwrap().len(), 2, "both actions are attempted once");

        // A fully unsupported action must not be reported as executed, while the
        // replay guard still advances so a retry cannot re-run it.
        let mut last = ReplayGuard::default();
        let payload = serde_json::json!({ "u": [{"action": "open_menu", "sequence": 5}] });
        let refusing: UtilitySink = Arc::new(|_| false);
        assert_eq!(dispatch_utilities(&payload, &mut last, &refusing), 0);
        let accepting: UtilitySink = Arc::new(|_| true);
        assert_eq!(
            dispatch_utilities(&payload, &mut last, &accepting),
            0,
            "a refused command is still consumed by the replay guard"
        );
    }

    #[test]
    fn the_direct_lan_utility_frame_shape_is_accepted() {
        let seen: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: UtilitySink = Arc::new(move |action| {
            collector.lock().unwrap().push(action.action.clone());
            true
        });
        let payload = serde_json::json!({
            "s": 4,
            "b": [],
            "a": [0, 0, 0, 0],
            "u": [{"action": "QUICK_SAVE", "sequence": 1}]
        });
        let mut last = ReplayGuard::default();
        assert_eq!(dispatch_utilities(&payload, &mut last, &sink), 1);
        assert_eq!(seen.lock().unwrap().clone(), vec!["QUICK_SAVE"]);
    }

    #[test]
    fn parse_base_requires_plain_http_and_keeps_the_port() {
        assert_eq!(parse_base("http://127.0.0.1:8092").unwrap(), ("127.0.0.1".into(), 8092));
        assert_eq!(parse_base("http://host").unwrap(), ("host".into(), 80));
        assert!(parse_base("https://relay.example").is_err());
        assert!(parse_base("").is_err());
        assert!(parse_base("127.0.0.1:8092").is_err());
    }

    #[test]
    fn http_request_reads_status_and_body() {
        let (base, _) = scripted_server(vec![(200, "{\"ok\":true}")]);
        let (status, body) = http_request(&base, "GET", "/health", None).unwrap();
        assert_eq!(status, 200);
        assert_eq!(body, "{\"ok\":true}");
    }

    #[test]
    fn host_session_polls_and_applies_the_phone_frame() {
        let _guard = serialize();
        INPUT_READY_OVERRIDE.store(1, Ordering::Relaxed);
        let (base, served) = scripted_server(vec![
            (201, "{\"code\":\"ABC123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/controller/join?code=ABC123\"}"),
            (200, "{\"paired\":true,\"needsResync\":false,\"lastSequence\":2,\"ackSequence\":0,\"inputActive\":false,\"expiresInSeconds\":3599,\"state\":{\"s\":2,\"b\":[\"right\"],\"a\":[0,0,0,0]}}"),
        ]);
        let seen: Arc<Mutex<Vec<u32>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: InputSink = Arc::new(move |input| {
            collector.lock().unwrap().push(input.buttons);
        });
        let session = start_with(base, sink, utility_sink_default()).expect("session");
        assert_eq!(session.code, "ABC123");
        assert_eq!(session.ttl_seconds, 3600);
        let mut applied = false;
        for _ in 0..40 {
            if seen.lock().unwrap().iter().any(|buttons| buttons & (1 << 7) != 0) {
                applied = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        assert!(applied, "the phone's right press must reach the input sink");
        assert!(served.load(Ordering::SeqCst) >= 2);
        let state = status();
        assert!(state.running);
        assert!(state.paired);
        assert_eq!(state.input, "right");
        stop();
        assert!(!status().running);
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);
    }

    /// The host must acknowledge applied frames so the phone can report a
    /// truthful connection state.
    #[test]
    fn the_host_acknowledges_the_frame_it_applied() {
        use std::io::BufRead as _;
        use std::net::TcpListener;
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let address = listener.local_addr().expect("addr");
        let requests: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let recorder = requests.clone();
        std::thread::spawn(move || {
            let mut first = true;
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { continue };
                let mut reader = std::io::BufReader::new(stream.try_clone().expect("clone"));
                let mut head = String::new();
                let mut length = 0usize;
                let mut line = String::new();
                while reader.read_line(&mut line).unwrap_or(0) > 0 {
                    if let Some(value) = line.to_ascii_lowercase().strip_prefix("content-length:") {
                        length = value.trim().parse().unwrap_or(0);
                    }
                    if line == "\r\n" { break; }
                    head.push_str(&line);
                    line.clear();
                }
                let mut body = vec![0u8; length];
                if length > 0 { let _ = reader.read_exact(&mut body); }
                recorder.lock().unwrap().push(head.clone());
                let (status, reason, payload): (u16, &str, String) = if first {
                    first = false;
                    (201, "Created", "{\"code\":\"ACK123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/c\"}".into())
                } else {
                    (200, "OK", "{\"paired\":true,\"lastSequence\":7,\"ackSequence\":0,\"inputActive\":false,\"expiresInSeconds\":3599,\"state\":{\"s\":7,\"b\":[\"start\"]}}".into())
                };
                let response = format!(
                    "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}",
                    payload.len()
                );
                let _ = stream.write_all(response.as_bytes());
            }
        });
        let _guard = serialize();
        INPUT_READY_OVERRIDE.store(1, Ordering::Relaxed);
        let sink: InputSink = Arc::new(|_| {});
        let _session = start_with(format!("http://{address}"), sink, utility_sink_default()).expect("session");
        let mut acked = false;
        for _ in 0..40 {
            if requests.lock().unwrap().iter().any(|head| head.starts_with("POST /api/controller/ack")) {
                acked = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        stop();
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);
        assert!(acked, "the host must acknowledge the applied frame");
    }

    /// Live probe against a real controller server (staging). Ignored by default
    /// because it needs the network; run with:
    ///   AN3_CONTROLLER_TEST_BASE=http://127.0.0.1:8092 \
    ///     cargo test --lib live_staging -- --ignored --nocapture
    #[test]
    #[ignore]
    fn live_staging_session_applies_a_phone_frame() {
        let _guard = serialize();
        // The probe drives the network path, not a real game, so force the
        // input-ready gate on.
        INPUT_READY_OVERRIDE.store(1, Ordering::Relaxed);
        let base = match std::env::var("AN3_CONTROLLER_TEST_BASE") {
            Ok(value) if !value.trim().is_empty() => value.trim().to_string(),
            _ => return,
        };
        let seen: Arc<Mutex<Vec<u32>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: InputSink = Arc::new(move |input| {
            collector.lock().unwrap().push(input.buttons);
        });
        let session = start_with(base.clone(), sink, utility_sink_default()).expect("live session");
        println!("live pairing code {}", session.code);
        let pair_body = format!("{{\"code\":\"{}\",\"deviceId\":\"desktop-probe\"}}", session.code);
        let (status, body) = http_request(&base, "POST", "/api/controller/pair", Some(&pair_body)).expect("pair");
        assert_eq!(status, 200, "pairing failed: {body}");
        let token = serde_json::from_str::<serde_json::Value>(&body)
            .ok()
            .and_then(|value| value.get("token").and_then(|item| item.as_str()).map(str::to_string))
            .expect("phone token");
        for sequence in 1..=4 {
            let frame = format!(
                "{{\"code\":\"{}\",\"token\":\"{}\",\"s\":{sequence},\"b\":[\"right\"],\"a\":[0,0,0,0]}}",
                session.code, token
            );
            let (status, _) = http_request(&base, "POST", "/api/controller/state", Some(&frame)).expect("state");
            assert_eq!(status, 200);
            std::thread::sleep(Duration::from_millis(200));
        }
        let mut applied = false;
        for _ in 0..40 {
            if seen.lock().unwrap().iter().any(|buttons| buttons & (1 << 7) != 0) {
                applied = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        stop();
        INPUT_READY_OVERRIDE.store(-1, Ordering::Relaxed);
        assert!(applied, "the live phone frame must reach the desktop input sink");
    }
}

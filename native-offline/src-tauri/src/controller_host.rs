// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Staging-only phone-controller host for the desktop shells.
//!
//! The desktop app is the pairing host: it creates a session on the configured
//! staging controller server, polls the host-state endpoint, and feeds the
//! phone's frame into the same `set_native_input` path the in-app controls use.
//! The same module serves macOS, Linux, and Windows; the platform difference is
//! already handled by `set_native_input`.
//!
//! The controller service is a LAN HTTP origin, so this client speaks plain
//! HTTP/1.1 over a TCP socket and never carries TLS. The raw host token stays
//! inside this module and is never logged or persisted.

use serde::Serialize;
use std::{
    io::{Read, Write},
    net::TcpStream,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread::JoinHandle,
    time::Duration,
};

use crate::azahar::{set_native_input, NativeInput};

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
    pub expires_in_seconds: u64,
    pub error: String,
}

type InputSink = Arc<dyn Fn(NativeInput) + Send + Sync>;

struct Host {
    stop: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
    code: String,
    paired: Arc<AtomicBool>,
    input: Arc<Mutex<String>>,
    expires: Arc<AtomicU64>,
    error: Arc<Mutex<String>>,
}

static HOST: Mutex<Option<Host>> = Mutex::new(None);

fn sink_default() -> InputSink {
    Arc::new(|input| {
        let _ = set_native_input(input);
    })
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
    NativeInput {
        buttons,
        circle_x: scale(left_x),
        circle_y: scale(left_y),
        cstick_x: scale(right_x),
        cstick_y: scale(right_y),
        touch_x: 0,
        touch_y: 0,
        touch_pressed: false,
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
        return Err("Set the controller server URL (for example http://192.0.2.8:8092).".into());
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
    start_with(base_url, sink_default())
}

pub(crate) fn start_with(base_url: String, sink: InputSink) -> Result<ControllerSession, String> {
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
    let expires = Arc::new(AtomicU64::new(ttl_seconds));
    let error = Arc::new(Mutex::new(String::new()));

    let thread_base = base.clone();
    let thread_stop = stop.clone();
    let thread_paired = paired.clone();
    let thread_input = input.clone();
    let thread_expires = expires.clone();
    let thread_error = error.clone();
    let handle = std::thread::spawn(move || {
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
                        let snapshot = frame_input(&payload);
                        if let Ok(mut guard) = thread_input.lock() {
                            *guard = describe(&payload);
                        }
                        sink(snapshot);
                    } else {
                        if let Ok(mut guard) = thread_input.lock() {
                            guard.clear();
                        }
                        sink(frame_input(&serde_json::Value::Null));
                    }
                }
                Ok((403, _)) | Ok((404, _)) => {
                    // The session ended or expired. Release before stopping.
                    set_error(&thread_error, "Controller session ended");
                    sink(frame_input(&serde_json::Value::Null));
                    thread_paired.store(false, Ordering::Relaxed);
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
                expires_in_seconds: host.expires.load(Ordering::Relaxed),
                error: host.error.lock().map(|value| value.clone()).unwrap_or_default(),
            },
            None => ControllerStatus {
                running: false,
                paired: false,
                code: String::new(),
                input: String::new(),
                expires_in_seconds: 0,
                error: String::new(),
            },
        },
        Err(_) => ControllerStatus {
            running: false,
            paired: false,
            code: String::new(),
            input: String::new(),
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
    fn parse_base_requires_plain_http_and_keeps_the_port() {
        assert_eq!(parse_base("http://192.0.2.8:8092").unwrap(), ("192.0.2.8".into(), 8092));
        assert_eq!(parse_base("http://host").unwrap(), ("host".into(), 80));
        assert!(parse_base("https://relay.example").is_err());
        assert!(parse_base("").is_err());
        assert!(parse_base("192.0.2.8:8092").is_err());
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
        let (base, served) = scripted_server(vec![
            (201, "{\"code\":\"ABC123\",\"hostToken\":\"tok\",\"ttlSeconds\":3600,\"joinPath\":\"/controller/join?code=ABC123\"}"),
            (200, "{\"paired\":true,\"needsResync\":false,\"expiresInSeconds\":3599,\"state\":{\"s\":2,\"b\":[\"right\"],\"a\":[0,0,0,0]}}"),
        ]);
        let seen: Arc<Mutex<Vec<u32>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: InputSink = Arc::new(move |input| {
            collector.lock().unwrap().push(input.buttons);
        });
        let session = start_with(base, sink).expect("session");
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
    }

    /// Live probe against a real controller server (staging). Ignored by default
    /// because it needs the network; run with:
    ///   AN3_CONTROLLER_TEST_BASE=http://192.0.2.8:8092 \
    ///     cargo test --lib live_staging -- --ignored --nocapture
    #[test]
    #[ignore]
    fn live_staging_session_applies_a_phone_frame() {
        let base = match std::env::var("AN3_CONTROLLER_TEST_BASE") {
            Ok(value) if !value.trim().is_empty() => value.trim().to_string(),
            _ => return,
        };
        let seen: Arc<Mutex<Vec<u32>>> = Arc::new(Mutex::new(Vec::new()));
        let collector = seen.clone();
        let sink: InputSink = Arc::new(move |input| {
            collector.lock().unwrap().push(input.buttons);
        });
        let session = start_with(base.clone(), sink).expect("live session");
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
        assert!(applied, "the live phone frame must reach the desktop input sink");
    }
}

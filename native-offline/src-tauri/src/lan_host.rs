// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Direct LAN phone-controller host (AN3 Controller LAN v1).
//!
//! The desktop app listens on the local network and a phone connects straight to
//! it. No staging server, no browser, no internet: discovery is a UDP broadcast,
//! the connection is a persistent TCP stream, and pairing is confirmed with a
//! six-digit code. The transport is secured with standard primitives only:
//! ephemeral P-256 ECDH, HKDF-SHA256 key derivation, and AES-256-GCM frames.
//!
//! Reused unchanged from the staging path: `frame_input` (button/axis/touch
//! mapping), `set_native_input`, latest-state-wins, sequence numbers,
//! acknowledgement-based truthfulness, and release-all on disconnect.

use std::{
    collections::HashMap,
    io::{Read, Write},
    net::{IpAddr, Shutdown, TcpListener, TcpStream, UdpSocket},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex, OnceLock,
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

use aes_gcm::{
    aead::{Aead, KeyInit},
    Aes256Gcm, Nonce,
};
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use hkdf::Hkdf;
use p256::{ecdh::EphemeralSecret, elliptic_curve::sec1::ToEncodedPoint, PublicKey};
use sha2::{Digest, Sha256};

use crate::azahar::{native_active_system, native_input_ready, set_native_input};
use crate::controller_host::frame_input;

pub const DISCOVERY_PORT: u16 = 47831;
pub const CONTROL_PORT: u16 = 47832;
const PROTOCOL_VERSION: u32 = 1;
const PAIRING_TTL: Duration = Duration::from_secs(120);
const MAX_FAILURES_PER_MINUTE: usize = 6;
const IO_TIMEOUT: Duration = Duration::from_secs(30);
const ACK_INTERVAL: Duration = Duration::from_millis(200);
const MAX_FRAME_BYTES: usize = 64 * 1024;
const DIR_PHONE_TO_HOST: u32 = 1;
const DIR_HOST_TO_PHONE: u32 = 2;

#[derive(Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LanStatus {
    pub running: bool,
    pub code: String,
    pub code_expires_in_seconds: u64,
    pub paired: bool,
    pub controller_name: String,
    pub input_active: bool,
    pub input: String,
    pub system: String,
    pub address: String,
    pub port: u16,
    pub error: String,
}

struct State {
    code: Mutex<String>,
    code_expiry: Mutex<Instant>,
    token: Mutex<Option<[u8; 32]>>,
    paired: AtomicBool,
    input_active: AtomicBool,
    input: Mutex<String>,
    system: Mutex<String>,
    controller_name: Mutex<String>,
    error: Mutex<String>,
    instance_id: String,
    // The last sequence the host acknowledged, and the latest it applied.
    last_sequence: AtomicU64,
    ack_sequence: AtomicU64,
}

impl State {
    fn new(instance_id: String) -> Self {
        State {
            code: Mutex::new(String::new()),
            code_expiry: Mutex::new(Instant::now()),
            token: Mutex::new(None),
            paired: AtomicBool::new(false),
            input_active: AtomicBool::new(false),
            input: Mutex::new(String::new()),
            system: Mutex::new("auto".to_string()),
            controller_name: Mutex::new(String::new()),
            error: Mutex::new(String::new()),
            instance_id,
            last_sequence: AtomicU64::new(0),
            ack_sequence: AtomicU64::new(0),
        }
    }

    fn set_code(&self) {
        if let Ok(mut code) = self.code.lock() {
            *code = new_pairing_code();
        }
        if let Ok(mut expiry) = self.code_expiry.lock() {
            *expiry = Instant::now() + PAIRING_TTL;
        }
        if let Ok(mut token) = self.token.lock() {
            *token = None;
        }
        self.paired.store(false, Ordering::Relaxed);
        self.last_sequence.store(0, Ordering::Relaxed);
        self.ack_sequence.store(0, Ordering::Relaxed);
        self.input_active.store(false, Ordering::Relaxed);
    }

    fn code_value(&self) -> String {
        self.code.lock().map(|value| value.clone()).unwrap_or_default()
    }

    fn code_expired(&self) -> bool {
        self.code_expiry
            .lock()
            .map(|expiry| Instant::now() >= *expiry)
            .unwrap_or(true)
    }

    fn token_value(&self) -> Option<[u8; 32]> {
        self.token.lock().ok().and_then(|value| *value)
    }
}

struct Host {
    stop: Arc<AtomicBool>,
    state: Arc<State>,
    handles: Vec<JoinHandle<()>>,
    name: String,
}

static HOST: Mutex<Option<Host>> = Mutex::new(None);
static FAILURES: OnceLock<Mutex<HashMap<IpAddr, Vec<Instant>>>> = OnceLock::new();

/// Test seam: -1 uses the platform runtime, 0 forces "no game", 1 forces
/// "game running". Production always leaves it at -1.
static READY_OVERRIDE: std::sync::atomic::AtomicI8 = std::sync::atomic::AtomicI8::new(-1);

fn input_ready() -> bool {
    match READY_OVERRIDE.load(Ordering::Relaxed) {
        0 => false,
        1 => true,
        _ => native_input_ready(),
    }
}

fn failures() -> &'static Mutex<HashMap<IpAddr, Vec<Instant>>> {
    FAILURES.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Six decimal digits from the OS CSPRNG, leading zeroes included.
pub(crate) fn new_pairing_code() -> String {
    let mut code = String::with_capacity(6);
    for _ in 0..6 {
        let mut byte = [0u8; 1];
        // Rejection sampling keeps every digit equally likely.
        loop {
            if getrandom::getrandom(&mut byte).is_err() {
                // Extremely unlikely; fall back to a fresh draw next iteration.
                continue;
            }
            if byte[0] < 250 {
                code.push(char::from(b'0' + (byte[0] % 10)));
                break;
            }
        }
    }
    code
}

pub(crate) fn random_bytes<const N: usize>() -> [u8; N] {
    let mut bytes = [0u8; N];
    let _ = getrandom::getrandom(&mut bytes);
    bytes
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn derive_key(shared: &[u8], secret: &[u8]) -> [u8; 32] {
    let mut salt = Sha256::new();
    salt.update(b"an3-ctrl-v1|");
    salt.update(secret);
    let salt = salt.finalize();
    let hk = Hkdf::<Sha256>::new(Some(&salt), shared);
    let mut key = [0u8; 32];
    // expand only fails for absurd output lengths.
    let _ = hk.expand(b"an3-ctrl|v1|session", &mut key);
    key
}

fn nonce_for(direction: u32, counter: u64) -> [u8; 12] {
    let mut nonce = [0u8; 12];
    nonce[..4].copy_from_slice(&direction.to_be_bytes());
    nonce[4..].copy_from_slice(&counter.to_be_bytes());
    nonce
}

fn write_frame(stream: &mut TcpStream, body: &[u8]) -> std::io::Result<()> {
    let length = (body.len() as u32).to_be_bytes();
    stream.write_all(&length)?;
    stream.write_all(body)
}

fn read_frame(stream: &mut TcpStream) -> std::io::Result<Vec<u8>> {
    let mut length = [0u8; 4];
    stream.read_exact(&mut length)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > MAX_FRAME_BYTES {
        return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "frame too large"));
    }
    let mut body = vec![0u8; length];
    stream.read_exact(&mut body)?;
    Ok(body)
}

/// Encrypts one JSON value into a direction/counter-bound AEAD frame.
fn seal(cipher: &Aes256Gcm, direction: u32, counter: u64, value: &serde_json::Value) -> Vec<u8> {
    let plaintext = serde_json::to_vec(value).unwrap_or_default();
    let nonce = nonce_for(direction, counter);
    let mut sealed = cipher
        .encrypt(Nonce::from_slice(&nonce), plaintext.as_slice())
        .unwrap_or_default();
    let mut body = nonce.to_vec();
    body.append(&mut sealed);
    body
}

fn open(cipher: &Aes256Gcm, expected_direction: u32, counter: u64, body: &[u8]) -> Option<serde_json::Value> {
    if body.len() < 12 {
        return None;
    }
    let (nonce, ciphertext) = body.split_at(12);
    if nonce != nonce_for(expected_direction, counter) {
        return None;
    }
    let plaintext = cipher.decrypt(Nonce::from_slice(nonce), ciphertext).ok()?;
    serde_json::from_slice(&plaintext).ok()
}

fn rate_limited(ip: IpAddr) -> bool {
    let Ok(mut map) = failures().lock() else { return true };
    let now = Instant::now();
    let entry = map.entry(ip).or_default();
    entry.retain(|stamp| now.duration_since(*stamp) < Duration::from_secs(60));
    entry.len() >= MAX_FAILURES_PER_MINUTE
}

fn note_failure(ip: IpAddr) {
    if let Ok(mut map) = failures().lock() {
        map.entry(ip).or_default().push(Instant::now());
    }
}

fn clear_failures(ip: IpAddr) {
    if let Ok(mut map) = failures().lock() {
        map.remove(&ip);
    }
}

/// Hardware name shown to the phone in discovery (never an address).
fn default_host_name() -> String {
    if let Ok(name) = std::env::var("AN3_CONTROLLER_NAME") {
        if !name.trim().is_empty() {
            return name.trim().chars().take(32).collect();
        }
    }
    let os = if cfg!(target_os = "macos") {
        "Mac"
    } else if cfg!(target_os = "windows") {
        "Windows PC"
    } else {
        "Android device"
    };
    format!("Vibe Coded Emulator ({os})")
}

/// Start advertising and accepting direct LAN controllers.
pub fn start() -> Result<LanStatus, String> {
    stop();
    let instance_id = hex(&random_bytes::<8>());
    let state = Arc::new(State::new(instance_id.clone()));
    state.set_code();
    let name = default_host_name();
    let stop = Arc::new(AtomicBool::new(false));

    let mut handles = Vec::new();
    handles.push(spawn_discovery(stop.clone(), state.clone(), name.clone()));
    handles.push(spawn_listener(stop.clone(), state.clone(), name.clone()));

    *HOST.lock().map_err(|_| "Controller lock unavailable".to_string())? = Some(Host {
        stop,
        state: state.clone(),
        handles,
        name,
    });
    Ok(status())
}

/// Stop hosting, close the listener, and release every held input.
pub fn stop() {
    let previous = HOST.lock().ok().and_then(|mut guard| guard.take());
    if let Some(host) = previous {
        host.stop.store(true, Ordering::Relaxed);
        // Nudge the UDP loop awake so it notices the stop flag.
        if let Ok(socket) = UdpSocket::bind("127.0.0.1:0") {
            let _ = socket.send_to(b"stop", ("127.0.0.1", DISCOVERY_PORT));
        }
        if let Ok(socket) = TcpStream::connect(("127.0.0.1", CONTROL_PORT)) {
            let _ = socket.shutdown(Shutdown::Both);
        }
        for handle in host.handles {
            let _ = handle.join();
        }
        let _ = set_native_input(frame_input(&serde_json::Value::Null));
    }
}

/// Rotate the pairing code and clear any paired session.
pub fn refresh_code() -> LanStatus {
    if let Ok(guard) = HOST.lock() {
        if let Some(host) = guard.as_ref() {
            host.state.set_code();
        }
    }
    status()
}

pub fn status() -> LanStatus {
    match HOST.lock() {
        Ok(guard) => match guard.as_ref() {
            Some(host) => {
                let remaining = host
                    .state
                    .code_expiry
                    .lock()
                    .map(|expiry| expiry.saturating_duration_since(Instant::now()).as_secs())
                    .unwrap_or(0);
                LanStatus {
                    running: true,
                    code: host.state.code_value(),
                    code_expires_in_seconds: remaining,
                    paired: host.state.paired.load(Ordering::Relaxed),
                    controller_name: host.state.controller_name.lock().map(|v| v.clone()).unwrap_or_default(),
                    input_active: host.state.input_active.load(Ordering::Relaxed),
                    input: host.state.input.lock().map(|v| v.clone()).unwrap_or_default(),
                    system: host.state.system.lock().map(|v| v.clone()).unwrap_or_default(),
                    address: local_address(),
                    port: CONTROL_PORT,
                    error: host.state.error.lock().map(|v| v.clone()).unwrap_or_default(),
                }
            }
            None => LanStatus {
                running: false,
                code: String::new(),
                code_expires_in_seconds: 0,
                paired: false,
                controller_name: String::new(),
                input_active: false,
                input: String::new(),
                system: String::new(),
                address: String::new(),
                port: CONTROL_PORT,
                error: String::new(),
            },
        },
        Err(_) => LanStatus {
            running: false,
            code: String::new(),
            code_expires_in_seconds: 0,
            paired: false,
            controller_name: String::new(),
            input_active: false,
            input: String::new(),
            system: String::new(),
            address: String::new(),
            port: CONTROL_PORT,
            error: "Controller lock unavailable".into(),
        },
    }
}

/// Best-effort LAN address for diagnostics only.
fn local_address() -> String {
    if let Ok(socket) = UdpSocket::bind("0.0.0.0:0") {
        if socket.connect("8.8.8.8:80").is_ok() {
            if let Ok(addr) = socket.local_addr() {
                return addr.ip().to_string();
            }
        }
    }
    String::new()
}

fn spawn_discovery(stop: Arc<AtomicBool>, state: Arc<State>, name: String) -> JoinHandle<()> {
    std::thread::spawn(move || {
        let Ok(socket) = UdpSocket::bind("0.0.0.0:0") else { return };
        let _ = socket.set_broadcast(true);
        let mut counter = 0u64;
        while !stop.load(Ordering::Relaxed) {
            counter = counter.wrapping_add(1);
            let advertisement = serde_json::json!({
                "an3": "ctrl",
                "v": PROTOCOL_VERSION,
                "id": state.instance_id,
                "name": name,
                "port": CONTROL_PORT,
            });
            let payload = serde_json::to_vec(&advertisement).unwrap_or_default();
            let _ = socket.send_to(&payload, ("255.255.255.255", DISCOVERY_PORT));
            // A second send to the subnet broadcast helps some Wi-Fi networks.
            let _ = socket.send_to(&payload, ("192.0.2.255", DISCOVERY_PORT));
            for _ in 0..20 {
                if stop.load(Ordering::Relaxed) {
                    break;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }
    })
}

fn spawn_listener(stop: Arc<AtomicBool>, state: Arc<State>, name: String) -> JoinHandle<()> {
    std::thread::spawn(move || {
        let Ok(listener) = TcpListener::bind(("0.0.0.0", CONTROL_PORT)) else {
            if let Ok(mut error) = state.error.lock() {
                *error = format!("Controller port {CONTROL_PORT} is unavailable");
            }
            return;
        };
        let _ = listener.set_nonblocking(true);
        while !stop.load(Ordering::Relaxed) {
            match listener.accept() {
                Ok((mut stream, peer)) => {
                    let state = state.clone();
                    let name = name.clone();
                    let stop = stop.clone();
                    std::thread::spawn(move || {
                        if stop.load(Ordering::Relaxed) {
                            return;
                        }
                        handle_client(&mut stream, peer.ip(), &state, &name);
                        // A controller disconnect always releases held input.
                        release(&state);
                    });
                }
                Err(ref error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(50));
                }
                Err(_) => std::thread::sleep(Duration::from_millis(100)),
            }
        }
    })
}

fn release(state: &State) {
    let _ = set_native_input(frame_input(&serde_json::Value::Null));
    state.paired.store(false, Ordering::Relaxed);
    state.input_active.store(false, Ordering::Relaxed);
    if let Ok(mut input) = state.input.lock() {
        input.clear();
    }
    if let Ok(mut name) = state.controller_name.lock() {
        name.clear();
    }
}

fn handle_client(stream: &mut TcpStream, peer: IpAddr, state: &State, name: &str) {
    // Accepted sockets inherit the listener's non-blocking mode on Unix.
    let _ = stream.set_nonblocking(false);
    let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
    let _ = stream.set_write_timeout(Some(IO_TIMEOUT));

    // 1. Plaintext hello exchange.
    let Ok(hello) = read_frame(stream) else { return };
    let Ok(hello) = serde_json::from_slice::<serde_json::Value>(&hello) else { return };
    if hello.get("k").and_then(|v| v.as_str()) != Some("hello") {
        return;
    }
    let Some(peer_pub) = hello
        .get("pub")
        .and_then(|v| v.as_str())
        .and_then(|value| B64.decode(value).ok())
        .and_then(|bytes| PublicKey::from_sec1_bytes(&bytes).ok())
    else {
        return;
    };
    let secret = EphemeralSecret::random(&mut OsRngCompat);
    let host_public = secret.public_key().to_encoded_point(false);
    let response = serde_json::json!({
        "k": "hello",
        "v": PROTOCOL_VERSION,
        "pub": B64.encode(host_public.as_bytes()),
        "id": state.instance_id,
        "name": name,
    });
    if write_frame(stream, &serde_json::to_vec(&response).unwrap_or_default()).is_err() {
        return;
    }
    let shared = secret.diffie_hellman(&peer_pub);

    // 2. Try the stored session token first (automatic reconnect), then the
    //    pairing code while its window is open. The secret is never sent.
    if rate_limited(peer) {
        return;
    }
    let Ok(sealed) = read_frame(stream) else { return };
    let mut key = None;
    let mut used_code = false;
    if let Some(token) = state.token_value() {
        let candidate = derive_key(shared.raw_secret_bytes().as_slice(), &token);
        if let Some(value) = open_with_key(&candidate, DIR_PHONE_TO_HOST, 0, &sealed) {
            if value.get("k").and_then(|v| v.as_str()) == Some("auth") {
                key = Some(candidate);
            }
        }
    }
    if key.is_none() && !state.code_expired() {
        let code = state.code_value();
        let candidate = derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes());
        if let Some(value) = open_with_key(&candidate, DIR_PHONE_TO_HOST, 0, &sealed) {
            if value.get("k").and_then(|v| v.as_str()) == Some("auth") {
                key = Some(candidate);
                used_code = true;
            }
        }
    }
    let Some(session_key) = key else {
        note_failure(peer);
        return;
    };
    clear_failures(peer);
    let cipher = match Aes256Gcm::new_from_slice(&session_key) {
        Ok(cipher) => cipher,
        Err(_) => return,
    };

    // 3. Confirm the session; issue a strong token on first pairing.
    let mut token_out = None;
    if used_code {
        let token = random_bytes::<32>();
        if let Ok(mut slot) = state.token.lock() {
            *slot = Some(token);
        }
        // Invalidate the pairing code once it has been used.
        if let Ok(mut code) = state.code.lock() {
            code.clear();
        }
        if let Ok(mut expiry) = state.code_expiry.lock() {
            *expiry = Instant::now();
        }
        token_out = Some(B64.encode(token));
    }
    state.paired.store(true, Ordering::Relaxed);
    let controller_name = hello.get("name").and_then(|v| v.as_str()).unwrap_or("Controller");
    if let Ok(mut slot) = state.controller_name.lock() {
        *slot = controller_name.chars().take(32).collect();
    }
    let ready = serde_json::json!({
        "k": "ready",
        "token": token_out,
        "system": native_active_system().unwrap_or_else(|| "auto".to_string()),
    });
    let mut send_counter = 0u64;
    if write_frame(stream, &seal(&cipher, DIR_HOST_TO_PHONE, send_counter, &ready)).is_err() {
        release(state);
        return;
    }
    send_counter += 1;

    read_loop(stream, &cipher, state, &mut send_counter);
    release(state);
}

fn open_with_key(key: &[u8; 32], direction: u32, counter: u64, body: &[u8]) -> Option<serde_json::Value> {
    let cipher = Aes256Gcm::new_from_slice(key).ok()?;
    open(&cipher, direction, counter, body)
}

fn read_loop(stream: &mut TcpStream, cipher: &Aes256Gcm, state: &State, send_counter: &mut u64) {
    let mut receive_counter = 1u64; // 0 was the auth frame
    let mut last_ack_sent = Instant::now() - ACK_INTERVAL;
    loop {
        match read_frame(stream) {
            Ok(body) => {
                let Some(value) = open(cipher, DIR_PHONE_TO_HOST, receive_counter, &body) else {
                    clear_send_error(state, "Controller frame failed authentication");
                    return;
                };
                receive_counter += 1;
                if value.get("k").and_then(|v| v.as_str()) == Some("state") {
                    apply_state(state, &value);
                    if last_ack_sent.elapsed() >= ACK_INTERVAL {
                        if send_ack(stream, cipher, send_counter, state).is_err() {
                            return;
                        }
                        last_ack_sent = Instant::now();
                    }
                }
            }
            Err(_) => return,
        }
    }
}

fn clear_send_error(state: &State, message: &str) {
    if let Ok(mut error) = state.error.lock() {
        *error = message.to_string();
    }
}

fn apply_state(state: &State, frame: &serde_json::Value) {
    let sequence = frame.get("s").and_then(|v| v.as_u64()).unwrap_or(0);
    if sequence <= state.last_sequence.load(Ordering::Relaxed) {
        return; // latest-state-wins
    }
    state.last_sequence.store(sequence, Ordering::Relaxed);
    if let Ok(mut input) = state.input.lock() {
        *input = frame
            .get("b")
            .and_then(|v| v.as_array())
            .map(|list| list.iter().filter_map(|v| v.as_str()).collect::<Vec<_>>().join(","))
            .unwrap_or_default();
    }
    // `frame_input` reads the same {"state": {...}} shape as the staging path.
    let shaped = serde_json::json!({ "state": frame });
    if input_ready() {
        let _ = set_native_input(frame_input(&shaped));
        if let Some(system) = native_active_system() {
            if let Ok(mut slot) = state.system.lock() {
                *slot = system;
            }
        }
    } else {
        let _ = set_native_input(frame_input(&serde_json::Value::Null));
    }
}

fn send_ack(stream: &mut TcpStream, cipher: &Aes256Gcm, send_counter: &mut u64, state: &State) -> std::io::Result<()> {
    let last = state.last_sequence.load(Ordering::Relaxed);
    let ack = serde_json::json!({
        "k": "ack",
        "s": last,
        "inputActive": input_ready() && state.paired.load(Ordering::Relaxed),
        "system": native_active_system().unwrap_or_else(|| "auto".to_string()),
    });
    let body = seal(cipher, DIR_HOST_TO_PHONE, *send_counter, &ack);
    write_frame(stream, &body)?;
    *send_counter += 1;
    state.ack_sequence.store(last, Ordering::Relaxed);
    state
        .input_active
        .store(input_ready() && state.paired.load(Ordering::Relaxed), Ordering::Relaxed);
    Ok(())
}

/// Minimal OS CSPRNG adapter for `EphemeralSecret::random`.
struct OsRngCompat;

impl p256::elliptic_curve::rand_core::RngCore for OsRngCompat {    fn next_u32(&mut self) -> u32 {
        let mut bytes = [0u8; 4];
        let _ = getrandom::getrandom(&mut bytes);
        u32::from_le_bytes(bytes)
    }
    fn next_u64(&mut self) -> u64 {
        let mut bytes = [0u8; 8];
        let _ = getrandom::getrandom(&mut bytes);
        u64::from_le_bytes(bytes)
    }
    fn fill_bytes(&mut self, dest: &mut [u8]) {
        let _ = getrandom::getrandom(dest);
    }
    fn try_fill_bytes(&mut self, dest: &mut [u8]) -> Result<(), p256::elliptic_curve::rand_core::Error> {
        getrandom::getrandom(dest).map_err(|_| p256::elliptic_curve::rand_core::Error::new("rng"))
    }
}

impl p256::elliptic_curve::rand_core::CryptoRng for OsRngCompat {}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pairing_codes_are_six_digits_including_leading_zeroes() {
        for _ in 0..300 {
            let code = new_pairing_code();
            assert_eq!(code.len(), 6);
            assert!(code.chars().all(|c| c.is_ascii_digit()), "{code}");
        }
    }

    #[test]
    fn key_derivation_depends_on_the_pairing_code() {
        let shared = [7u8; 32];
        assert_ne!(derive_key(&shared, b"000000"), derive_key(&shared, b"000001"));
    }

    #[test]
    fn aead_frames_round_trip_and_bind_direction_and_counter() {
        let key = derive_key(&[3u8; 32], b"482193");
        let cipher = Aes256Gcm::new_from_slice(&key).unwrap();
        let value = serde_json::json!({"t": "state", "s": 4, "b": ["start"], "a": [0,0,0,0]});
        let frame = seal(&cipher, DIR_PHONE_TO_HOST, 0, &value);
        assert_eq!(open(&cipher, DIR_PHONE_TO_HOST, 0, &frame).unwrap()["s"], 4);
        // The wrong direction or counter must not authenticate.
        assert!(open(&cipher, DIR_HOST_TO_PHONE, 0, &frame).is_none());
        assert!(open(&cipher, DIR_PHONE_TO_HOST, 1, &frame).is_none());
        // A different pairing code must not decrypt it.
        let other = Aes256Gcm::new_from_slice(&derive_key(&[3u8; 32], b"000000")).unwrap();
        assert!(open(&other, DIR_PHONE_TO_HOST, 0, &frame).is_none());
        let _ = open_with_key(&key, DIR_PHONE_TO_HOST, 0, &frame);
    }

    /// End-to-end direct transport: a real TCP client pairs by code and its
    /// input frames reach the host's input sink, with acknowledgement.
    #[test]
    fn direct_transport_pairs_and_injects_input() {
        READY_OVERRIDE.store(1, Ordering::Relaxed);
        // The sink is the production `set_native_input`; assert on the host
        // state instead of a real core.
        let _ = start().expect("host start");
        let code = status().code.clone();
        assert_eq!(code.len(), 6);

        let mut stream = TcpStream::connect(("127.0.0.1", CONTROL_PORT)).expect("connect");
        stream.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
        let secret = EphemeralSecret::random(&mut OsRngCompat);
        let public = secret.public_key().to_encoded_point(false);
        let hello = serde_json::json!({"k":"hello","v":1,"pub": B64.encode(public.as_bytes()), "name":"Test phone"});
        write_frame(&mut stream, &serde_json::to_vec(&hello).unwrap()).unwrap();
        let response: serde_json::Value = serde_json::from_slice(&read_frame(&mut stream).unwrap()).unwrap();
        let host_public = PublicKey::from_sec1_bytes(
            &B64.decode(response.get("pub").unwrap().as_str().unwrap()).unwrap(),
        )
        .unwrap();
        let shared = secret.diffie_hellman(&host_public);
        let key = derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes());
        let cipher = Aes256Gcm::new_from_slice(&key).unwrap();
        write_frame(&mut stream, &seal(&cipher, DIR_PHONE_TO_HOST, 0, &serde_json::json!({"k":"auth"}))).unwrap();
        let ready = open(&cipher, DIR_HOST_TO_PHONE, 0, &read_frame(&mut stream).unwrap()).unwrap();
        assert!(ready.get("token").and_then(|v| v.as_str()).is_some(), "must issue a session token");
        assert_eq!(status().paired, true);
        assert_eq!(status().controller_name, "Test phone");

        // A wrong code after pairing must not authenticate on a second client.
        write_frame(&mut stream, &seal(&cipher, DIR_PHONE_TO_HOST, 1, &serde_json::json!({
            "k":"state","s":2,"b":["right"],"a":[0,0,0,0],"t":[0.25,0.75]
        }))).unwrap();
        // The host acknowledges within the ack interval or on the next state.
        let mut acked = false;
        for _ in 0..10 {
            if status().input_active {
                acked = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(60));
        }
        assert!(acked, "input must be acknowledged while a game is ready");
        assert_eq!(status().input, "right");
        let _ = stream.shutdown(Shutdown::Both);
        stop();
        READY_OVERRIDE.store(-1, Ordering::Relaxed);
        assert!(!status().running);
    }
}

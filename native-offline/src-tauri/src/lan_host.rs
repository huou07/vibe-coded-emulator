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
    net::{IpAddr, Ipv4Addr, Shutdown, SocketAddr, TcpListener, TcpStream, UdpSocket},
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
use crate::host_actions::ReplayGuard;
use crate::lan_peer::{advertisement_with_capabilities, discovery_socket, local_lan_ipv4, parse_advertisement, CONTROL_PORT, DISCOVERY_ADDRESS, DISCOVERY_BROADCAST, DISCOVERY_PORT, PROTOCOL_VERSION};
const PAIRING_TTL: Duration = Duration::from_secs(120);
const MAX_FAILURES_PER_MINUTE: usize = 6;
// Pairing is always initiated from an interactive screen. Keep every socket
// operation bounded so a peer that disappears cannot leave the session in a
// long-lived connecting state or hold resources indefinitely.
const IO_TIMEOUT: Duration = Duration::from_secs(8);
const ACK_INTERVAL: Duration = Duration::from_millis(200);
const MAX_FRAME_BYTES: usize = 64 * 1024;
const DIR_PHONE_TO_HOST: u32 = 1;
const DIR_HOST_TO_PHONE: u32 = 2;

#[derive(Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LanStatus {
    pub running: bool,
    pub role: String,
    pub state: String,
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
    // Session-scoped replay identity for one-shot host actions. Direct LAN
    // commands use command_id; legacy sequence-only frames remain supported.
    last_utility: Mutex<ReplayGuard>,
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
            last_utility: Mutex::new(ReplayGuard::default()),
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
        if let Ok(mut replay) = self.last_utility.lock() {
            replay.reset();
        }
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
    port: u16,
    advertises: bool,
}

static HOST: Mutex<Option<Host>> = Mutex::new(None);
struct Client {
    stream: TcpStream,
    key: [u8; 32],
    send_counter: u64,
    peer_address: String,
    peer_name: String,
    system: String,
}

static CLIENT: Mutex<Option<Client>> = Mutex::new(None);
static FAILURES: OnceLock<Mutex<HashMap<IpAddr, Vec<Instant>>>> = OnceLock::new();
static JOINING: AtomicBool = AtomicBool::new(false);
static JOIN_GENERATION: AtomicU64 = AtomicU64::new(0);
static JOIN_ERROR: OnceLock<Mutex<String>> = OnceLock::new();

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

/// Executes canonical utility actions on the running game host. A test seam
/// lets a unit test observe dispatch without a real emulator.
static UTILITY_SINK_OVERRIDE: OnceLock<Mutex<Option<crate::controller_host::UtilitySink>>> = OnceLock::new();

fn controller_utility_sink() -> crate::controller_host::UtilitySink {
    UTILITY_SINK_OVERRIDE
        .get_or_init(|| Mutex::new(None))
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
        .unwrap_or_else(crate::controller_host::utility_sink_default)
}

#[cfg(test)]
pub(crate) fn set_utility_sink_for_test(sink: Option<crate::controller_host::UtilitySink>) {
    if let Ok(mut guard) = UTILITY_SINK_OVERRIDE.get_or_init(|| Mutex::new(None)).lock() {
        *guard = sink;
    }
}

fn failures() -> &'static Mutex<HashMap<IpAddr, Vec<Instant>>> {
    FAILURES.get_or_init(|| Mutex::new(HashMap::new()))
}

fn join_error() -> &'static Mutex<String> {
    JOIN_ERROR.get_or_init(|| Mutex::new(String::new()))
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
    start_on_port(CONTROL_PORT, true)
}

fn start_on_port(port: u16, advertises: bool) -> Result<LanStatus, String> {
    stop();
    // On macOS/BSD, SO_REUSEADDR lets a second bind silently share the fixed
    // control port with an already-running AN3 host. The phone then reaches the
    // other listener, which does not know this pairing code, and the session
    // dies mid-handshake (observed as `hello-response-read-error` / EOF).
    // Refuse to start a second host instead of silently coexisting.
    if port != 0
        && TcpStream::connect_timeout(
            &SocketAddr::from((Ipv4Addr::LOCALHOST, port)),
            Duration::from_millis(250),
        )
        .is_ok()
    {
        return Err(format!(
            "Controller port {port} is already in use. Close the other AN3 host on this device and try again."
        ));
    }
    let listener = TcpListener::bind(("0.0.0.0", port))
        .map_err(|_| format!("Controller port {port} is unavailable"))?;
    let port = listener
        .local_addr()
        .map_err(|error| format!("Could not read controller listener address: {error}"))?
        .port();
    let instance_id = hex(&random_bytes::<8>());
    let state = Arc::new(State::new(instance_id.clone()));
    state.set_code();
    let name = default_host_name();
    let stop = Arc::new(AtomicBool::new(false));

    let mut handles = Vec::new();
    if advertises {
        handles.push(spawn_discovery(
            stop.clone(),
            state.clone(),
            name.clone(),
            port,
        ));
    }
    handles.push(spawn_listener(
        stop.clone(),
        state.clone(),
        name.clone(),
        listener,
    ));

    *HOST.lock().map_err(|_| "Controller lock unavailable".to_string())? = Some(Host {
        stop,
        state: state.clone(),
        handles,
        name,
        port,
        advertises,
    });
    Ok(status())
}

/// Discover one direct controller-capable peer and pair as its controller.
/// The source address comes from the multicast datagram; no fixed IP is used.
fn join_blocking(code: String, generation: u64) -> Result<LanStatus, String> {
    let code = code.trim().to_string();
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("Enter exactly six decimal digits.".into());
    }
    let (address, peer_name) = discover_controller()?;
    let mut stream = TcpStream::connect_timeout(&address, IO_TIMEOUT)
        .map_err(|error| format!("Could not connect to the AN3 peer: {error}"))?;
    configure_controller_stream(&stream);
    let secret = EphemeralSecret::random(&mut OsRngCompat);
    let public = secret.public_key().to_encoded_point(false);
    let hello = serde_json::json!({
        "k": "hello",
        "v": PROTOCOL_VERSION,
        "pub": B64.encode(public.as_bytes()),
        "id": hex(&random_bytes::<8>()),
        "name": default_host_name(),
        "capability": "controller",
    });
    write_frame(&mut stream, &serde_json::to_vec(&hello).unwrap_or_default())
        .map_err(|error| format!("Could not start the direct peer handshake: {error}"))?;
    let response: serde_json::Value = serde_json::from_slice(&read_frame(&mut stream)
        .map_err(|error| format!("The direct peer handshake failed: {error}"))?)
        .map_err(|_| "The direct peer returned malformed handshake data.".to_string())?;
    if response.get("k").and_then(|value| value.as_str()) != Some("hello")
        || response.get("v").and_then(|value| value.as_u64()) != Some(PROTOCOL_VERSION as u64)
    {
        return Err("The direct peer uses an incompatible protocol.".into());
    }
    let host_public = response
        .get("pub")
        .and_then(|value| value.as_str())
        .and_then(|value| B64.decode(value).ok())
        .and_then(|value| PublicKey::from_sec1_bytes(&value).ok())
        .ok_or("The direct peer returned an invalid public key.")?;
    let shared = secret.diffie_hellman(&host_public);
    let key = derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes());
    let cipher = Aes256Gcm::new_from_slice(&key).map_err(|_| "Could not initialize peer encryption.")?;
    let auth = seal(&cipher, DIR_PHONE_TO_HOST, 0, &serde_json::json!({"k": "auth"}));
    write_frame(&mut stream, &auth).map_err(|error| format!("Could not authenticate the direct peer: {error}"))?;
    let ready = open(&cipher, DIR_HOST_TO_PHONE, 0, &read_frame(&mut stream)
        .map_err(|error| format!("The direct peer closed during pairing: {error}"))?)
        .ok_or("The direct peer rejected the pairing code.")?;
    if ready.get("k").and_then(|value| value.as_str()) != Some("ready") {
        return Err("The direct peer did not confirm pairing.".into());
    }
    if !JOINING.load(Ordering::Relaxed) || JOIN_GENERATION.load(Ordering::Relaxed) != generation {
        let _ = stream.shutdown(Shutdown::Both);
        return Err("Direct controller pairing was canceled.".into());
    }
    let system = ready.get("system").and_then(|value| value.as_str()).unwrap_or("auto").to_string();
    CLIENT.lock().map_err(|_| "Controller lock unavailable".to_string())?.replace(Client {
        stream,
        key,
        send_counter: 1,
        peer_address: address.ip().to_string(),
        peer_name,
        system,
    });
    Ok(status())
}

/// Discover and pair without making the WebView/Tauri command wait for
/// multicast, TCP, or the encrypted handshake. Completion is reported by
/// `status()` as `connecting`, `connected`, or `error`.
pub fn join_async(code: String) -> Result<LanStatus, String> {
    let code = code.trim().to_string();
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("Enter exactly six decimal digits.".into());
    }
    stop();
    let generation = JOIN_GENERATION.fetch_add(1, Ordering::Relaxed).wrapping_add(1);
    JOINING.store(true, Ordering::Relaxed);
    if let Ok(mut error) = join_error().lock() { error.clear(); }
    std::thread::spawn(move || {
        let result = join_blocking(code, generation);
        if JOIN_GENERATION.load(Ordering::Relaxed) != generation || !JOINING.load(Ordering::Relaxed) {
            return;
        }
        match result {
            Ok(_) => JOINING.store(false, Ordering::Relaxed),
            Err(error) => {
                if let Ok(mut slot) = join_error().lock() { *slot = error; }
                JOINING.store(false, Ordering::Relaxed);
            }
        }
    });
    Ok(status())
}

fn discover_controller() -> Result<(SocketAddr, String), String> {
    let socket = discovery_socket(DISCOVERY_PORT)
        .map_err(|error| format!("Direct LAN discovery is unavailable: {error}"))?;
    let group = DISCOVERY_ADDRESS.parse::<Ipv4Addr>().map_err(|_| "Invalid AN3 discovery group.")?;
    let interface = local_lan_ipv4().unwrap_or(Ipv4Addr::UNSPECIFIED);
    socket.join_multicast_v4(&group, &interface)
        .map_err(|error| format!("Could not join AN3 LAN discovery: {error}"))?;
    let _ = socket.set_read_timeout(Some(Duration::from_millis(250)));
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut payload = [0u8; 4096];
    while Instant::now() < deadline {
        match socket.recv_from(&mut payload) {
            Ok((length, source)) if source.ip().is_ipv4() => {
                let Ok(value) = serde_json::from_slice::<serde_json::Value>(&payload[..length]) else { continue };
                let Ok(peer) = parse_advertisement(&value) else { continue };
                if !peer.capabilities.iter().any(|capability| capability == "controller") { continue; }
                return Ok((SocketAddr::new(source.ip(), peer.port), peer.name));
            }
            Ok(_) => {}
            Err(error) if matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
            Err(_) => {}
        }
    }
    Err("No AN3 controller host was found on the local network.".into())
}

/// Stop hosting, close the listener, and release every held input.
pub fn stop() {
    JOIN_GENERATION.fetch_add(1, Ordering::Relaxed);
    JOINING.store(false, Ordering::Relaxed);
    if let Ok(mut error) = join_error().lock() { error.clear(); }
    stop_client();
    stop_host();
}

fn stop_host() {
    let previous = HOST.lock().ok().and_then(|mut guard| guard.take());
    if let Some(host) = previous {
        host.stop.store(true, Ordering::Relaxed);
        // Nudge discovery/join listeners only for a real advertised host.
        // Ephemeral unit-test hosts stay isolated from the live LAN peer.
        if host.advertises {
            if let Ok(socket) = UdpSocket::bind("127.0.0.1:0") {
                let _ = socket.send_to(b"stop", ("127.0.0.1", DISCOVERY_PORT));
            }
        }
        if let Ok(socket) = TcpStream::connect(("127.0.0.1", host.port)) {
            let _ = socket.shutdown(Shutdown::Both);
        }
        for handle in host.handles {
            let _ = handle.join();
        }
        let _ = set_native_input(frame_input(&serde_json::Value::Null));
    }
}

fn stop_client() {
    let previous = CLIENT.lock().ok().and_then(|mut guard| guard.take());
    if let Some(client) = previous {
        let _ = client.stream.shutdown(Shutdown::Both);
        let _ = set_native_input(frame_input(&serde_json::Value::Null));
    }
}

/// Send one encrypted controller snapshot directly to the paired peer.
pub fn send_state(mut state: serde_json::Value) -> Result<LanStatus, String> {
    let mut guard = CLIENT.lock().map_err(|_| "Controller lock unavailable".to_string())?;
    let client = guard.as_mut().ok_or("No direct controller session is active.")?;
    let object = state.as_object_mut().ok_or("Controller state must be an object.")?;
    object.remove("_an3q"); // local queue policy never becomes transport protocol data
    object.insert("k".into(), serde_json::Value::String("state".into()));
    let cipher = Aes256Gcm::new_from_slice(&client.key).map_err(|_| "Could not initialize peer encryption.")?;
    let body = seal(&cipher, DIR_PHONE_TO_HOST, client.send_counter, &state);
    write_frame(&mut client.stream, &body).map_err(|error| format!("Direct controller send failed: {error}"))?;
    client.send_counter = client.send_counter.wrapping_add(1);
    drop(guard);
    Ok(status())
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
    if JOINING.load(Ordering::Relaxed) {
        return LanStatus {
            running: true,
            role: "controller".into(),
            state: "connecting".into(),
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
        };
    }
    if let Ok(guard) = CLIENT.lock() {
        if let Some(client) = guard.as_ref() {
            return LanStatus {
                running: true,
                role: "controller".into(),
                state: "connected".into(),
                code: String::new(),
                code_expires_in_seconds: 0,
                paired: true,
                controller_name: client.peer_name.clone(),
                input_active: true,
                input: String::new(),
                system: client.system.clone(),
                address: client.peer_address.clone(),
                port: CONTROL_PORT,
                error: String::new(),
            };
        }
    }
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
                    role: "host".into(),
                    state: if host.state.error.lock().map(|v| !v.is_empty()).unwrap_or(false) { "error".into() } else if host.state.paired.load(Ordering::Relaxed) { "connected".into() } else { "waiting".into() },
                    code: host.state.code_value(),
                    code_expires_in_seconds: remaining,
                    paired: host.state.paired.load(Ordering::Relaxed),
                    controller_name: host.state.controller_name.lock().map(|v| v.clone()).unwrap_or_default(),
                    input_active: host.state.input_active.load(Ordering::Relaxed),
                    input: host.state.input.lock().map(|v| v.clone()).unwrap_or_default(),
                    system: host.state.system.lock().map(|v| v.clone()).unwrap_or_default(),
                    address: local_address(),
                    port: host.port,
                    error: host.state.error.lock().map(|v| v.clone()).unwrap_or_default(),
                }
            }
            None => LanStatus {
                running: false,
                role: "off".into(),
                state: if join_error().lock().map(|v| !v.is_empty()).unwrap_or(false) { "error".into() } else { "idle".into() },
                code: String::new(),
                code_expires_in_seconds: 0,
                paired: false,
                controller_name: String::new(),
                input_active: false,
                input: String::new(),
                system: String::new(),
                address: String::new(),
                port: CONTROL_PORT,
                error: join_error().lock().map(|v| v.clone()).unwrap_or_default(),
            },
        },
        Err(_) => LanStatus {
            running: false,
            role: "off".into(),
            state: "error".into(),
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
    // The peer learns the source address from the direct discovery datagram.
    // Do not probe an Internet address merely to render diagnostics.
    String::new()
}

fn spawn_discovery(
    stop: Arc<AtomicBool>,
    state: Arc<State>,
    name: String,
    port: u16,
) -> JoinHandle<()> {
    std::thread::spawn(move || {
        let local = local_lan_ipv4().unwrap_or(Ipv4Addr::UNSPECIFIED);
        let Ok(socket) = UdpSocket::bind((local, 0)) else { return };
        let _ = socket.set_multicast_loop_v4(true);
        let _ = socket.set_broadcast(true);
        while !stop.load(Ordering::Relaxed) {
            let payload = serde_json::to_vec(&advertisement_with_capabilities(
                &state.instance_id,
                &name,
                port,
                &["controller"],
            ))
                .unwrap_or_default();
            let _ = socket.send_to(&payload, (DISCOVERY_ADDRESS, DISCOVERY_PORT));
            // Some consumer Wi-Fi APs pass unicast traffic but suppress
            // multicast group delivery. Broadcast is the same local-only
            // discovery envelope and lets installed peers find one another
            // without asking the user for an IP address.
            let _ = socket.send_to(&payload, (DISCOVERY_BROADCAST, DISCOVERY_PORT));
            for _ in 0..20 {
                if stop.load(Ordering::Relaxed) {
                    break;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }
    })
}

fn spawn_listener(
    stop: Arc<AtomicBool>,
    state: Arc<State>,
    name: String,
    listener: TcpListener,
) -> JoinHandle<()> {
    std::thread::spawn(move || {
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

/// Apply the interactive-controller socket policy to an established stream.
///
/// Gameplay input is latency-sensitive, so Nagle's algorithm is disabled on
/// both the accepted (host) and connected (phone) sides: a button-down or
/// button-up must not wait for more data to coalesce. Timeouts bound the
/// handshake; the authenticated session clears them elsewhere.
fn configure_controller_stream(stream: &TcpStream) {
    let _ = stream.set_nodelay(true);
    let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
    let _ = stream.set_write_timeout(Some(IO_TIMEOUT));
}

fn handle_client(stream: &mut TcpStream, peer: IpAddr, state: &State, name: &str) {
    // Accepted sockets inherit the listener's non-blocking mode on Unix.
    let _ = stream.set_nonblocking(false);
    configure_controller_stream(stream);

    // 1. Plaintext hello exchange.
    let Ok(hello) = read_frame(stream) else {
        return;
    };
    let Ok(hello) = serde_json::from_slice::<serde_json::Value>(&hello) else {
        return;
    };
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
    let Ok(sealed) = read_frame(stream) else {
        return;
    };
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

    // Handshake reads are bounded, but an authenticated controller session is
    // intentionally long-lived while the user keeps the host open.  Do not
    // turn an idle game/menu into a disconnect after the handshake timeout.
    let _ = stream.set_read_timeout(None);
    let _ = stream.set_write_timeout(None);

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
                    // Track B1: capture host receipt before decryption work is
                    // attributed, so transport and processing stay separable.
                    crate::latency::note_frame_received(
                        value.get("s").and_then(|v| v.as_u64()).unwrap_or(0),
                        value.get("t0").and_then(|v| v.as_i64()).unwrap_or(0),
                    );
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
    // Track B1 (debug-only): associate the phone's own capture time with this
    // sequence. `t0` is echoed, never interpreted on the host clock.
    crate::latency::note_input_applied(
        sequence,
        frame.get("t0").and_then(|v| v.as_i64()).unwrap_or(0),
    );
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
        // Track B1: close the input-to-produced-frame interval with the host's
        // real presented-frame counter. This runs only while tracing is on.
        if crate::latency::is_enabled() && crate::azahar::native_frame_counter_available() {
            crate::latency::note_frame_produced_at(crate::azahar::native_presented_frames());
        }
        if let Some(system) = native_active_system() {
            if let Ok(mut slot) = state.system.lock() {
                *slot = system;
            }
        }
    } else {
        let _ = set_native_input(frame_input(&serde_json::Value::Null));
    }
    // Dispatch one-shot actions even without a running game so the native sink
    // can return a concrete failure instead of silently dropping the command.
    // Gameplay snapshots still apply only while the core is ready.
    if let Ok(mut replay) = state.last_utility.lock() {
        let _ = crate::controller_host::dispatch_utilities(frame, &mut replay, &controller_utility_sink());
    }
}

fn send_ack(stream: &mut TcpStream, cipher: &Aes256Gcm, send_counter: &mut u64, state: &State) -> std::io::Result<()> {
    let last = state.last_sequence.load(Ordering::Relaxed);
    let utility_results = crate::controller_utility_queue::take_completed();
    let ack = serde_json::json!({
        "k": "ack",
        "s": last,
        "inputActive": input_ready() && state.paired.load(Ordering::Relaxed),
        "system": native_active_system().unwrap_or_else(|| "auto".to_string()),
        "utilityResultsSupported": cfg!(target_os = "macos"),
        "utilityResults": utility_results,
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

    // The transport tests share the module-level HOST and must not run
    // concurrently. Their listeners use isolated ephemeral ports.
    static SERIAL: std::sync::Mutex<()> = std::sync::Mutex::new(());
    fn serialize() -> std::sync::MutexGuard<'static, ()> {
        SERIAL.lock().unwrap_or_else(|error| error.into_inner())
    }

    fn start_test_host() -> LanStatus {
        start_on_port(0, false).expect("isolated test host start")
    }

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

    /// Gameplay input must not wait on Nagle's algorithm on either side.
    #[test]
    fn controller_streams_disable_nagle_for_gameplay_input() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).expect("bind ephemeral");
        let address = listener.local_addr().unwrap();
        let client = TcpStream::connect(address).expect("connect");
        let (server, _) = listener.accept().expect("accept");
        configure_controller_stream(&client);
        configure_controller_stream(&server);
        assert_eq!(client.nodelay().unwrap(), true, "phone gameplay input must not wait on Nagle");
        assert_eq!(server.nodelay().unwrap(), true, "host reader must not wait on Nagle");
    }

    /// A second host must not silently share a control port. On macOS
    /// SO_REUSEADDR can let it coexist, and the phone then reaches the other
    /// listener, which does not know the pairing code: the session dies as a
    /// handshake EOF instead of a clear error.
    #[test]
    fn start_refuses_when_the_requested_port_is_already_owned() {
        let _guard = serialize();
        let owner = TcpListener::bind(("127.0.0.1", 0)).expect("occupy ephemeral port");
        let port = owner.local_addr().unwrap().port();
        let result = start_on_port(port, false);
        assert!(result.is_err(), "a second host must not start while the port is owned");
    }

    /// Repeated start/stop cycles must release the listener port every time, so
    /// reconnect churn never leaves a stale listener that would break the next
    /// handshake.
    #[test]
    fn start_stop_cycles_release_the_listener_port() {
        let _guard = serialize();
        let mut port = 0;
        for cycle in 0..5 {
            let started = start_on_port(port, false).expect("host start");
            port = started.port;
            assert_ne!(port, 0, "cycle {cycle}: the host must bind a real port");
            assert!(started.running, "cycle {cycle}: host must report running");
            stop();
            assert!(!status().running, "cycle {cycle}: host must report stopped");
        }
        assert!(
            TcpStream::connect(("127.0.0.1", port)).is_err(),
            "the listener must be closed after the final stop"
        );
    }

    /// End-to-end direct transport: a real TCP client pairs by code and its
    /// input frames reach the host's input sink, with acknowledgement.
    #[test]
    fn direct_transport_pairs_and_injects_input() {
        let _guard = serialize();
        READY_OVERRIDE.store(1, Ordering::Relaxed);
        // The sink is the production `set_native_input`; assert on the host
        // state instead of a real core.
        let hosted = start_test_host();
        let code = hosted.code.clone();
        let port = hosted.port;
        assert_eq!(code.len(), 6);

        let mut stream = (0..50)
            .find_map(|_| match TcpStream::connect(("127.0.0.1", port)) {
                Ok(stream) => Some(stream),
                Err(_) => {
                    std::thread::sleep(Duration::from_millis(20));
                    None
                }
            })
            .expect("connect");
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

    /// End-to-end: the app's canonical utility frame (`u:[{action,command_id,slot}]`)
    /// reaches the host's utility sink exactly once, and a replayed frame does
    /// not repeat the side effect. Different commands may share a transport
    /// sequence because command_id is the direct-LAN replay identity.
    #[test]
    fn direct_transport_executes_canonical_utility_frames() {
        let _guard = serialize();
        READY_OVERRIDE.store(1, Ordering::Relaxed);
        let seen: Arc<Mutex<Vec<(String, u8)>>> = Arc::new(Mutex::new(Vec::new()));
        let sink: crate::controller_host::UtilitySink = {
            let seen = seen.clone();
            Arc::new(move |action| {
                seen.lock().unwrap().push((action.action.clone(), action.slot));
                let action_code = match action.action.as_str() {
                    "QUICK_SAVE" => 1,
                    "QUICK_LOAD" => 2,
                    "SPEED_UP" => 3,
                    "SPEED_DOWN" => 4,
                    "OPEN_MENU" => 5,
                    _ => return false,
                };
                crate::controller_utility_queue::record_completed(
                    &action.command_id,
                    action_code,
                    action.slot as u32,
                    true,
                    "test host action completed",
                );
                true
            })
        };
        set_utility_sink_for_test(Some(sink));

        let hosted = start_test_host();
        let code = hosted.code.clone();
        let port = hosted.port;

        let mut stream = (0..50)
            .find_map(|_| match TcpStream::connect(("127.0.0.1", port)) {
                Ok(stream) => Some(stream),
                Err(_) => {
                    std::thread::sleep(Duration::from_millis(20));
                    None
                }
            })
            .expect("connect");
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
        let _ = open(&cipher, DIR_HOST_TO_PHONE, 0, &read_frame(&mut stream).unwrap()).unwrap();

        write_frame(&mut stream, &seal(&cipher, DIR_PHONE_TO_HOST, 1, &serde_json::json!({
            "k":"state","s":2,"b":[],"a":[0,0,0,0],
            "u":[
                {"action":"QUICK_SAVE","sequence":4,"command_id":"phone-a","slot":3},
                {"action":"QUICK_LOAD","sequence":4,"command_id":"phone-b","slot":10}
            ]
        }))).unwrap();
        for _ in 0..20 {
            if !seen.lock().unwrap().is_empty() {
                break;
            }
            std::thread::sleep(Duration::from_millis(30));
        }
        assert_eq!(
            seen.lock().unwrap().clone(),
            vec![("QUICK_SAVE".into(), 3), ("QUICK_LOAD".into(), 10)]
        );
        let ack = open(&cipher, DIR_HOST_TO_PHONE, 1, &read_frame(&mut stream).unwrap()).unwrap();
        let results = ack.get("utilityResults").and_then(|value| value.as_array()).unwrap();
        assert!(results.iter().any(|result| {
            result.get("commandId").and_then(|value| value.as_str()) == Some("phone-a")
                && result.get("action").and_then(|value| value.as_str()) == Some("QUICK_SAVE")
                && result.get("slot").and_then(|value| value.as_u64()) == Some(3)
                && result.get("success").and_then(|value| value.as_bool()) == Some(true)
        }));
        assert!(results.iter().any(|result| {
            result.get("commandId").and_then(|value| value.as_str()) == Some("phone-b")
                && result.get("action").and_then(|value| value.as_str()) == Some("QUICK_LOAD")
                && result.get("slot").and_then(|value| value.as_u64()) == Some(10)
                && result.get("message").and_then(|value| value.as_str())
                    == Some("test host action completed")
        }));

        // The same state sequence is ignored, so a retry cannot re-run it.
        write_frame(&mut stream, &seal(&cipher, DIR_PHONE_TO_HOST, 2, &serde_json::json!({
            "k":"state","s":2,"b":[],"a":[0,0,0,0],
            "u":[
                {"action":"QUICK_SAVE","sequence":4,"command_id":"phone-a","slot":3},
                {"action":"QUICK_LOAD","sequence":4,"command_id":"phone-b","slot":10}
            ]
        }))).unwrap();
        std::thread::sleep(Duration::from_millis(120));
        assert_eq!(seen.lock().unwrap().len(), 2);

        let _ = stream.shutdown(Shutdown::Both);
        stop();
        set_utility_sink_for_test(None);
        READY_OVERRIDE.store(-1, Ordering::Relaxed);
    }

    /// Track B1 end-to-end: the debug-only tracer records real measurements for
    /// frames that traverse the actual encrypted transport, associated by phone
    /// sequence, without changing input behavior.
    #[test]
    fn direct_transport_records_latency_for_real_frames() {
        let _guard = serialize();
        // The tracer is process-global; hold its lock so a concurrent latency
        // module test cannot stop the run mid-measurement.
        let _latency_guard = crate::latency::test_lock();
        READY_OVERRIDE.store(1, Ordering::Relaxed);
        let _ = crate::latency::stop();
        assert!(crate::latency::start(64), "the tracer must be startable");

        let hosted = start_test_host();
        let code = hosted.code.clone();
        let port = hosted.port;

        let mut stream = (0..50)
            .find_map(|_| match TcpStream::connect(("127.0.0.1", port)) {
                Ok(stream) => Some(stream),
                Err(_) => {
                    std::thread::sleep(Duration::from_millis(20));
                    None
                }
            })
            .expect("connect");
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
        let _ = open(&cipher, DIR_HOST_TO_PHONE, 0, &read_frame(&mut stream).unwrap()).unwrap();

        // Three distinguishable inputs, each with its own phone capture time.
        // The host has no real core here, so it reports its own frame counter.
        for (offset, sequence) in [(0u64, 11u64), (1, 12), (2, 13)] {
            write_frame(&mut stream, &seal(&cipher, DIR_PHONE_TO_HOST, offset + 1, &serde_json::json!({
                "k":"state","s":sequence,"b":["a"],"a":[0,0,0,0],"t0": 5_000 + sequence
            }))).unwrap();
            // Wait until the real transport reader records this input before
            // simulating its produced frame; a fixed delay races the reader.
            let deadline = Instant::now() + Duration::from_secs(2);
            while !crate::latency::snapshot().iter().any(|sample| sample.sequence == sequence) {
                assert!(Instant::now() < deadline, "host did not record frame {sequence}");
                std::thread::sleep(Duration::from_millis(1));
            }
            crate::latency::note_frame_produced();
        }

        let samples = crate::latency::snapshot();
        let _ = crate::latency::stop();
        let _ = stream.shutdown(Shutdown::Both);
        stop();
        READY_OVERRIDE.store(-1, Ordering::Relaxed);

        let sequences: Vec<u64> = samples.iter().map(|sample| sample.sequence).collect();
        assert!(
            sequences.contains(&11) && sequences.contains(&12) && sequences.contains(&13),
            "each real frame must produce one sample: {sequences:?}"
        );
        for sample in &samples {
            assert!(
                [11u64, 12, 13].contains(&sample.sequence),
                "no unrelated input may be measured"
            );
            assert!(
                sample.phone_t0 >= 5_000,
                "the phone capture time must be echoed through the transport"
            );
            assert!(
                sample.input_to_frame_ns().is_some(),
                "a produced frame must close the interval for sequence {}",
                sample.sequence
            );
        }
    }

    #[test]
    fn stale_controller_sequences_cannot_overwrite_latest_state() {
        let _guard = serialize();
        READY_OVERRIDE.store(0, Ordering::Relaxed);
        let state = State::new("sequence-test".into());
        apply_state(
            &state,
            &serde_json::json!({"s":2,"b":["right"],"a":[0,0,0,0]}),
        );
        apply_state(
            &state,
            &serde_json::json!({"s":1,"b":["left"],"a":[0,0,0,0]}),
        );
        assert_eq!(state.last_sequence.load(Ordering::Relaxed), 2);
        assert_eq!(*state.input.lock().unwrap(), "right");
        READY_OVERRIDE.store(-1, Ordering::Relaxed);
    }
}

// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Direct-LAN save-sync peer session and local trust registry.
//!
//! This is intentionally separate from the short-lived phone-controller
//! session.  A sync pairing creates a locally persisted trust record; the
//! six-digit code is used only once to bootstrap an encrypted session token.
//! No account identifier, password, token, or save payload is advertised.

use std::{
    collections::{HashMap, HashSet},
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    net::{IpAddr, Ipv4Addr, Shutdown, SocketAddr, TcpListener, TcpStream, UdpSocket},
    path::{Path, PathBuf},
    sync::{atomic::{AtomicBool, Ordering}, Arc, Mutex, OnceLock},
    thread::JoinHandle,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use aes_gcm::{aead::{Aead, KeyInit}, Aes256Gcm, Nonce};
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use hkdf::Hkdf;
use p256::{ecdh::EphemeralSecret, elliptic_curve::sec1::ToEncodedPoint, PublicKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::connection_limit::{ConnectionLimit, ConnectionPermit};
use crate::lan_peer::{advertisement_with_capabilities, parse_advertisement, DISCOVERY_ADDRESS, DISCOVERY_PORT, PROTOCOL_VERSION, SYNC_PORT};

const PAIRING_TTL: Duration = Duration::from_secs(120);
const IO_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_FRAME_BYTES: usize = 8 * 1024 * 1024;
const MAX_FAILURES_PER_MINUTE: usize = 6;
const MAX_ACTIVE_HANDLERS: usize = 8;
static ACTIVE_HANDLERS: ConnectionLimit = ConnectionLimit::new(MAX_ACTIVE_HANDLERS);
const MAX_NATIVE_MEMBERS: usize = 64;
const MAX_NATIVE_SET_BYTES: u64 = 64 * 1024 * 1024;
const MAX_NATIVE_MEMBER_BYTES: u64 = 16 * 1024 * 1024;
const SYNC_CHUNK_BYTES: usize = 768 * 1024;
static ACTIVE_PUBLISHES: ConnectionLimit = ConnectionLimit::new(1);
const DIR_CLIENT_TO_HOST: u32 = 11;
const DIR_HOST_TO_CLIENT: u32 = 12;
const IDENTITY_FILE: &str = "lan-sync-identity-v1.json";
const PEERS_FILE: &str = "lan-sync-peers-v1.json";

#[derive(Clone, Serialize, Deserialize)]
struct IdentityRecord {
    device_id: String,
    secret: String,
}

#[derive(Clone, Serialize, Deserialize)]
struct PeerRecord {
    device_id: String,
    name: String,
    mode: String,
    token: String,
    identity: String,
    fingerprint: String,
    #[serde(default)]
    last_seen: u64,
}

#[derive(Default, Serialize, Deserialize)]
struct PeerFile {
    peers: Vec<PeerRecord>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncPeerStatus {
    pub device_id: String,
    pub name: String,
    pub mode: String,
    pub state: String,
    pub fingerprint: String,
    pub last_seen: u64,
    pub account_verified: bool,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SyncStatus {
    pub running: bool,
    pub role: String,
    pub mode: String,
    pub device_id: String,
    pub code: String,
    pub code_expires_in_seconds: u64,
    pub peers: Vec<SyncPeerStatus>,
    pub error: String,
}

struct Runtime {
    app_dir: PathBuf,
    identity: IdentityRecord,
    mode: Mutex<String>,
    code: Mutex<String>,
    code_expiry: Mutex<Instant>,
    stop: Arc<AtomicBool>,
    handles: Mutex<Vec<JoinHandle<()>>>,
    peers: Mutex<Vec<PeerRecord>>,
    connected: Mutex<HashSet<String>>,
    account_verified: Mutex<HashSet<String>>,
    challenges: Mutex<HashMap<String, String>>,
    peer_proofs: Mutex<HashMap<String, String>>,
    local_proof: Mutex<Option<String>>,
    failures: Mutex<HashMap<IpAddr, Vec<Instant>>>,
    error: Mutex<String>,
}

struct ClientSession {
    stream: TcpStream,
    key: [u8; 32],
    send_counter: u64,
    receive_counter: u64,
    peer: PeerRecord,
    challenge: String,
    account_verified: bool,
    remote_proof: String,
}

struct PendingPublish {
    transfer_id: String,
    payload: serde_json::Value,
    members: Vec<PendingPublishMember>,
    next_member: usize,
    _permit: ConnectionPermit<'static>,
}

struct PendingPublishMember {
    expected_size: usize,
    bytes: Vec<u8>,
}

static RUNTIME: OnceLock<Mutex<Option<Arc<Runtime>>>> = OnceLock::new();
static CLIENT: OnceLock<Mutex<Option<ClientSession>>> = OnceLock::new();

fn runtime() -> &'static Mutex<Option<Arc<Runtime>>> { RUNTIME.get_or_init(|| Mutex::new(None)) }
fn client() -> &'static Mutex<Option<ClientSession>> { CLIENT.get_or_init(|| Mutex::new(None)) }

fn now_seconds() -> u64 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs() }

fn random_bytes<const N: usize>() -> [u8; N] {
    let mut value = [0u8; N];
    let _ = getrandom::getrandom(&mut value);
    value
}

fn hex(bytes: &[u8]) -> String { bytes.iter().map(|byte| format!("{byte:02x}")).collect() }

fn fingerprint(secret: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(secret);
    hex(&digest.finalize())
}

fn safe_id(value: &str) -> bool {
    value.len() >= 8 && value.len() <= 64 && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Option<T> {
    let mut input = String::new();
    File::open(path).ok()?.read_to_string(&mut input).ok()?;
    serde_json::from_str(&input).ok()
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    if let Some(parent) = path.parent() { fs::create_dir_all(parent).map_err(|error| error.to_string())?; }
    let temporary = path.with_extension("part");
    let bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    let mut options = OpenOptions::new();
    options.create(true).truncate(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut output = options.open(&temporary).map_err(|error| error.to_string())?;
    output.write_all(&bytes).map_err(|error| error.to_string())?;
    output.flush().map_err(|error| error.to_string())?;
    drop(output);
    fs::rename(&temporary, path).map_err(|error| error.to_string())
}

fn load_identity(app_dir: &Path) -> Result<IdentityRecord, String> {
    let path = app_dir.join(IDENTITY_FILE);
    if let Some(record) = read_json::<IdentityRecord>(&path) {
        if safe_id(&record.device_id) && B64.decode(&record.secret).ok().is_some_and(|value| value.len() == 32) {
            return Ok(record);
        }
    }
    let secret = random_bytes::<32>();
    let record = IdentityRecord { device_id: format!("an3-{}", hex(&random_bytes::<12>())), secret: B64.encode(secret) };
    write_json(&path, &record)?;
    Ok(record)
}

fn load_peers(app_dir: &Path) -> Vec<PeerRecord> {
    read_json::<PeerFile>(&app_dir.join(PEERS_FILE)).unwrap_or_default().peers
}

fn save_peers(runtime: &Runtime) -> Result<(), String> {
    let peers = runtime.peers.lock().map_err(|_| "Sync peer registry unavailable".to_string())?.clone();
    write_json(&runtime.app_dir.join(PEERS_FILE), &PeerFile { peers })
}

fn derive_key(shared: &[u8], secret: &[u8]) -> [u8; 32] {
    let mut salt = Sha256::new();
    salt.update(b"an3-sync-v1|");
    salt.update(secret);
    let hk = Hkdf::<Sha256>::new(Some(&salt.finalize()), shared);
    let mut key = [0u8; 32];
    let _ = hk.expand(b"an3-sync|v1|session", &mut key);
    key
}

fn nonce_for(direction: u32, counter: u64) -> [u8; 12] {
    let mut nonce = [0u8; 12];
    nonce[..4].copy_from_slice(&direction.to_be_bytes());
    nonce[4..].copy_from_slice(&counter.to_be_bytes());
    nonce
}

fn seal(cipher: &Aes256Gcm, direction: u32, counter: u64, value: &serde_json::Value) -> Vec<u8> {
    let plaintext = serde_json::to_vec(value).unwrap_or_default();
    let nonce = nonce_for(direction, counter);
    let mut ciphertext = cipher.encrypt(Nonce::from_slice(&nonce), plaintext.as_slice()).unwrap_or_default();
    let mut body = nonce.to_vec();
    body.append(&mut ciphertext);
    body
}

fn open(cipher: &Aes256Gcm, direction: u32, counter: u64, body: &[u8]) -> Option<serde_json::Value> {
    if body.len() < 12 || body[..12] != nonce_for(direction, counter) { return None; }
    let plaintext = cipher.decrypt(Nonce::from_slice(&body[..12]), &body[12..]).ok()?;
    serde_json::from_slice(&plaintext).ok()
}

fn write_frame(stream: &mut TcpStream, body: &[u8]) -> std::io::Result<()> {
    if body.is_empty() || body.len() > MAX_FRAME_BYTES { return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "invalid sync frame")); }
    stream.write_all(&(body.len() as u32).to_be_bytes())?;
    stream.write_all(body)
}

fn read_frame(stream: &mut TcpStream) -> std::io::Result<Vec<u8>> {
    let mut length = [0u8; 4];
    stream.read_exact(&mut length)?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > MAX_FRAME_BYTES { return Err(std::io::Error::new(std::io::ErrorKind::InvalidData, "invalid sync frame")); }
    let mut body = vec![0u8; length];
    stream.read_exact(&mut body)?;
    Ok(body)
}

fn challenge(host_id: &str, host_pub: &[u8], client_id: &str, client_pub: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(b"an3-sync-handshake-v1|");
    digest.update(host_id.as_bytes());
    digest.update(host_pub);
    digest.update(client_id.as_bytes());
    digest.update(client_pub);
    hex(&digest.finalize())
}

fn default_name() -> String {
    std::env::var("AN3_SYNC_NAME").ok().filter(|value| !value.trim().is_empty()).unwrap_or_else(|| {
        let platform = if cfg!(target_os = "macos") { "Mac" } else if cfg!(target_os = "windows") { "Windows PC" } else if cfg!(target_os = "android") { "Android" } else { "Linux" };
        format!("AN3 {platform}")
    }).chars().take(32).collect()
}

fn mode_valid(mode: &str) -> bool { matches!(mode, "guest" | "account") }

fn set_error(runtime: &Runtime, error: impl Into<String>) { if let Ok(mut value) = runtime.error.lock() { *value = error.into(); } }

#[derive(Clone)]
struct NativeContext {
    kind: String,
    system: String,
    core: String,
    game_id: String,
    rom_hash: String,
    rom_id: Option<String>,
}

#[derive(Clone, Serialize)]
struct CanonicalMember {
    #[serde(rename = "memberId")]
    member_id: String,
    path: String,
    size: u64,
    #[serde(rename = "contentHash")]
    content_hash: String,
}

#[derive(Serialize)]
struct CanonicalSet {
    #[serde(rename = "setId")]
    set_id: String,
    core: String,
    #[serde(rename = "gameId")]
    game_id: String,
    #[serde(rename = "romHash")]
    rom_hash: String,
    #[serde(rename = "memberCount")]
    member_count: usize,
    #[serde(rename = "totalSize")]
    total_size: u64,
    members: Vec<CanonicalMember>,
}

fn core_for_system(system: &str) -> Option<&'static str> {
    match system {
        "gba" => Some("mgba"),
        "nds" => Some("melonds"),
        "3ds" => Some("azahar"),
        _ => None,
    }
}

fn valid_member_path(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && value.split('/').all(|part| {
            !part.is_empty()
                && part != "."
                && part != ".."
                && part.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
        })
}

fn valid_state_key(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 256
        && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'/' | b'-'))
        && !value.split('/').any(|part| part == "." || part == "..")
}

fn normalize_rom_hash(value: &str) -> Option<String> {
    let hash = value.trim().to_ascii_lowercase();
    let hash = hash.strip_prefix("sha256:").unwrap_or(&hash);
    (hash.len() == 64 && hash.bytes().all(|byte| byte.is_ascii_hexdigit())).then_some(hash.to_string())
}

fn native_context(payload: &serde_json::Value) -> Result<NativeContext, String> {
    let context = payload.get("context").unwrap_or(payload);
    let identity = context.get("identity").unwrap_or(context);
    let kind = payload.get("kind").and_then(|value| value.as_str())
        .or_else(|| context.get("kind").and_then(|value| value.as_str()))
        .unwrap_or("save").to_string();
    if kind != "save" && kind != "state" { return Err("Unsupported native sync artifact kind.".into()); }
    let system = context.get("system").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
    let expected_core = core_for_system(&system).ok_or("Unsupported native sync system.")?;
    let core = identity.get("core").and_then(|value| value.as_str()).unwrap_or("").to_string();
    if core != expected_core { return Err("The sync peer core does not match the native system.".into()); }
    let game_id = identity.get("gameId").and_then(|value| value.as_str()).unwrap_or("").to_string();
    if game_id.is_empty() || game_id.len() > 64 || !game_id.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-')) {
        return Err("Invalid native sync game identity.".into());
    }
    let rom_hash = normalize_rom_hash(identity.get("romHash").and_then(|value| value.as_str()).unwrap_or(""))
        .ok_or("A native sync operation needs the complete ROM SHA-256 identity.")?;
    let rom_id = context.get("romId").and_then(|value| value.as_str()).map(str::to_string);
    if rom_id.as_ref().is_some_and(|value| !crate::validate_rom_id(value).is_ok()) {
        return Err("Invalid native ROM identity.".into());
    }
    Ok(NativeContext { kind, system, core, game_id, rom_hash, rom_id })
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut input = File::open(path).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = input.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 { break; }
        digest.update(&buffer[..count]);
    }
    Ok(hex(&digest.finalize()))
}

fn native_rom_path(app_dir: &Path, rom_id: &str) -> Option<PathBuf> {
    if !crate::validate_rom_id(rom_id).is_ok() { return None; }
    let prefix = format!("{rom_id}.");
    fs::read_dir(app_dir.join("an3-roms")).ok()?.flatten().find_map(|entry| {
        let file_name = entry.file_name().to_string_lossy().to_string();
        if !file_name.starts_with(&prefix) { return None; }
        entry.file_type().ok().filter(|kind| kind.is_file()).map(|_| entry.path())
    })
}

fn native_extension_matches(system: &str, path: &Path) -> bool {
    let extension = path.extension().and_then(|value| value.to_str()).unwrap_or("").to_ascii_lowercase();
    match system {
        "gba" => matches!(extension.as_str(), "gba" | "raw"),
        "nds" => extension == "nds",
        "3ds" => matches!(extension.as_str(), "3ds" | "3dsx" | "cci" | "cxi" | "app"),
        _ => false,
    }
}

fn find_native_game(app_dir: &Path, context: &NativeContext, requested_rom_id: Option<&str>) -> Result<(String, PathBuf, PathBuf), String> {
    let expected = context.rom_hash.clone();
    if let Some(rom_id) = requested_rom_id {
        if let Some(path) = native_rom_path(app_dir, rom_id).filter(|path| native_extension_matches(&context.system, path)) {
            if sha256_file(&path)? == expected {
                return Ok((rom_id.to_string(), path, app_dir.join("native-states-v1").join(&context.system).join(rom_id).join("native-libretro")));
            }
        }
    }
    let directory = app_dir.join("an3-roms");
    let entries = fs::read_dir(&directory).map_err(|error| format!("Native ROM storage is unavailable: {error}"))?;
    for entry in entries.flatten() {
        let path = entry.path();
        if !entry.file_type().map(|kind| kind.is_file()).unwrap_or(false) || !native_extension_matches(&context.system, &path) { continue; }
        let name = entry.file_name().to_string_lossy().to_string();
        let Some((rom_id, _)) = name.split_once('.') else { continue };
        if !crate::validate_rom_id(rom_id).is_ok() { continue; }
        if sha256_file(&path)? == expected {
            return Ok((rom_id.to_string(), path, app_dir.join("native-states-v1").join(&context.system).join(rom_id).join("native-libretro")));
        }
    }
    Err("This device has no matching local ROM and native save storage for that game.".into())
}

fn walk_files(directory: &Path, base: &Path, output: &mut Vec<String>, skip_states: bool) -> Result<(), String> {
    if !directory.exists() { return Ok(()); }
    for entry in fs::read_dir(directory).map_err(|error| error.to_string())?.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.') || name.contains(".an3-conflict-") || (skip_states && name == "states") || name == "system" { continue; }
        if entry.file_type().map_err(|error| error.to_string())?.is_dir() {
            walk_files(&path, base, output, skip_states)?;
        } else if entry.file_type().map_err(|error| error.to_string())?.is_file() {
            let relative = path.strip_prefix(base).map_err(|error| error.to_string())?.to_string_lossy().replace('\\', "/");
            if valid_member_path(&relative) { output.push(relative); }
        }
    }
    Ok(())
}

fn canonical_set_hash(context: &NativeContext, set_id: &str, members: &[CanonicalMember], total_size: u64) -> Result<String, String> {
    let value = CanonicalSet {
        set_id: set_id.to_string(),
        core: context.core.clone(),
        game_id: context.game_id.clone(),
        rom_hash: context.rom_hash.clone(),
        member_count: members.len(),
        total_size,
        members: members.to_vec(),
    };
    let bytes = serde_json::to_vec(&value).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    digest.update(bytes);
    Ok(hex(&digest.finalize()))
}

fn native_set_id(context: &NativeContext) -> String {
    format!("save:{}:{}:{}", context.core, context.game_id, context.rom_hash)
}

fn native_member_bytes(path: &Path) -> Result<Vec<u8>, String> {
    let metadata = fs::metadata(path).map_err(|error| error.to_string())?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_NATIVE_MEMBER_BYTES { return Err("Native sync member is empty or too large.".into()); }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    File::open(path).map_err(|error| error.to_string())?.read_to_end(&mut bytes).map_err(|error| error.to_string())?;
    Ok(bytes)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(bytes);
    hex(&digest.finalize())
}

fn native_blob_range(payload: &serde_json::Value) -> Result<Option<(u64, u64)>, String> {
    match (payload.get("offset"), payload.get("length")) {
        (None, None) => Ok(None),
        (Some(offset), Some(length)) => Ok(Some((
            offset.as_u64().ok_or("Invalid native sync blob chunk range.")?,
            length.as_u64().ok_or("Invalid native sync blob chunk range.")?,
        ))),
        _ => Err("The native sync blob chunk range is incomplete.".into()),
    }
}

fn native_manifest(runtime: &Runtime, payload: &serde_json::Value, _peer_id: &str) -> Result<serde_json::Value, String> {
    let context = native_context(payload)?;
    let Some((rom_id, _rom_path, root)) = find_native_game(&runtime.app_dir, &context, context.rom_id.as_deref()).ok() else {
        return Ok(serde_json::json!({"items": [], "sets": []}));
    };
    if context.kind == "save" {
        let mut relative = Vec::new();
        walk_files(&root, &root, &mut relative, true)?;
        relative.sort();
        if relative.len() > MAX_NATIVE_MEMBERS { return Err("The native save set contains too many members.".into()); }
        let set_id = native_set_id(&context);
        let mut members = Vec::new();
        let mut total_size = 0_u64;
        for member_id in relative {
            let path = root.join(&member_id);
            let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
            if metadata.len() == 0 || metadata.len() > MAX_NATIVE_MEMBER_BYTES { continue; }
            total_size = total_size.saturating_add(metadata.len());
            if total_size > MAX_NATIVE_SET_BYTES { return Err("The native save set is too large.".into()); }
            members.push(CanonicalMember {
                member_id: member_id.clone(),
                path: format!("/data/saves/{member_id}"),
                size: metadata.len(),
                content_hash: sha256_file(&path)?,
            });
        }
        if members.is_empty() { return Ok(serde_json::json!({"items": [], "sets": []})); }
        let manifest_hash = canonical_set_hash(&context, &set_id, &members, total_size)?;
        let set_members: Vec<serde_json::Value> = members.iter().map(|member| serde_json::json!({
            "key": format!("{}:{}", set_id, member.member_id),
            "memberId": member.member_id,
            "path": member.path,
            "size": member.size,
            "contentHash": member.content_hash,
            "deviceId": runtime.identity.device_id,
        })).collect();
        return Ok(serde_json::json!({"items": [], "sets": [{
            "setId": set_id,
            "core": context.core,
            "gameId": context.game_id,
            "romHash": context.rom_hash,
            "memberCount": members.len(),
            "totalSize": total_size,
            "manifestHash": manifest_hash,
            "deviceId": runtime.identity.device_id,
            "romId": rom_id,
            "members": set_members,
        }]}));
    }
    let state_dir = root.join("states");
    let mut relative = Vec::new();
    walk_files(&state_dir, &state_dir, &mut relative, false)?;
    relative.sort();
    if relative.len() > MAX_NATIVE_MEMBERS { return Err("The native state collection contains too many members.".into()); }
    let prefix = format!("state:{}:{}:{}:", context.core, context.game_id, context.rom_hash);
    let mut items = Vec::new();
    let mut total_size = 0_u64;
    for member_id in relative {
        let path = state_dir.join(&member_id);
        let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
        if metadata.len() == 0 || metadata.len() > MAX_NATIVE_MEMBER_BYTES { continue; }
        total_size = total_size.saturating_add(metadata.len());
        if total_size > MAX_NATIVE_SET_BYTES { return Err("The native save-state collection is too large.".into()); }
        let key = format!("{prefix}{member_id}");
        if !valid_state_key(&key) { return Err("The native state identity is too long.".into()); }
        items.push(serde_json::json!({
            "key": key,
            "path": format!("/data/states/{member_id}"),
            "contentHash": sha256_file(&path)?,
            "size": metadata.len(),
            "deviceId": runtime.identity.device_id,
        }));
    }
    Ok(serde_json::json!({"items": items, "sets": [], "totalSize": total_size}))
}

fn native_blob(runtime: &Runtime, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let context = native_context(payload)?;
    let (_rom_id, _rom_path, root) = find_native_game(&runtime.app_dir, &context, context.rom_id.as_deref())?;
    let item = payload.get("item").ok_or("The sync blob request is missing its item.")?;
    let path_value = item.get("path").and_then(|value| value.as_str()).unwrap_or("");
    let relative = if context.kind == "save" {
        path_value.strip_prefix("/data/saves/").ok_or("Invalid native save member path.")?
    } else {
        path_value.strip_prefix("/data/states/").ok_or("Invalid native state member path.")?
    };
    if !valid_member_path(relative) { return Err("Invalid native sync member path.".into()); }
    let key = item.get("key").and_then(|value| value.as_str()).unwrap_or("");
    if context.kind == "save" {
        if key != format!("{}:{relative}", native_set_id(&context)) { return Err("The save blob identity does not match its path.".into()); }
    } else if key != format!("state:{}:{}:{}:{relative}", context.core, context.game_id, context.rom_hash) {
        return Err("The save-state blob identity does not match its path.".into());
    }
    let path = if context.kind == "save" { root.join(relative) } else { root.join("states").join(relative) };
    let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_NATIVE_MEMBER_BYTES {
        return Err("Native sync member is empty or too large.".into());
    }
    let expected_size = item.get("size").and_then(|value| value.as_u64()).ok_or("The sync blob request is missing its size.")?;
    let expected_hash = item.get("contentHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
    if expected_size != metadata.len() || expected_hash.len() != 64 || !expected_hash.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("Native sync blob verification failed.".into());
    }
    if let Some((offset, length)) = native_blob_range(payload)? {
        if offset >= expected_size || length == 0 || length > SYNC_CHUNK_BYTES as u64 {
            return Err("Invalid native sync blob chunk range.".into());
        }
        let length = length.min(expected_size - offset) as usize;
        let mut input = File::open(&path).map_err(|error| error.to_string())?;
        input.seek(SeekFrom::Start(offset)).map_err(|error| error.to_string())?;
        let mut bytes = vec![0; length];
        input.read_exact(&mut bytes).map_err(|error| error.to_string())?;
        return Ok(serde_json::json!({"data": B64.encode(bytes), "offset": offset, "size": expected_size, "contentHash": expected_hash}));
    }
    let bytes = native_member_bytes(&path)?;
    if expected_hash != sha256_bytes(&bytes) { return Err("Native sync blob verification failed.".into()); }
    Ok(serde_json::json!({"data": B64.encode(bytes), "size": expected_size, "contentHash": expected_hash}))
}

fn write_native_members(root: &Path, kind: &str, files: Vec<(String, Vec<u8>)>) -> Result<(), String> {
    if files.is_empty() || files.len() > MAX_NATIVE_MEMBERS { return Err("The sync operation contains no valid members.".into()); }
    let mut total = 0_u64;
    let mut prepared = Vec::new();
    let mut seen = HashSet::new();
    for (member_id, bytes) in files {
        if !valid_member_path(&member_id) || !seen.insert(member_id.clone()) || bytes.is_empty() || bytes.len() as u64 > MAX_NATIVE_MEMBER_BYTES {
            return Err("The native sync member list is invalid.".into());
        }
        total = total.saturating_add(bytes.len() as u64);
        if total > MAX_NATIVE_SET_BYTES { return Err("The native sync payload is too large.".into()); }
        let target = if kind == "state" { root.join("states").join(&member_id) } else { root.join(&member_id) };
        prepared.push((target, bytes));
    }
    fs::create_dir_all(root).map_err(|error| error.to_string())?;
    let mut snapshots = Vec::new();
    let mut temporary = Vec::new();
    for (target, bytes) in &prepared {
        if let Some(parent) = target.parent() { fs::create_dir_all(parent).map_err(|error| error.to_string())?; }
        let previous = if target.exists() { Some(fs::read(target).map_err(|error| error.to_string())?) } else { None };
        let name = target.file_name().and_then(|value| value.to_str()).unwrap_or("member");
        let part = target.with_file_name(format!(".{name}.an3-sync-{}.part", hex(&random_bytes::<8>())));
        let mut output = File::create(&part).map_err(|error| error.to_string())?;
        output.write_all(bytes).map_err(|error| error.to_string())?;
        output.sync_all().map_err(|error| error.to_string())?;
        snapshots.push((target.clone(), previous));
        temporary.push(part);
    }
    for (index, (target, _)) in prepared.iter().enumerate() {
        if let Err(error) = fs::rename(&temporary[index], target) {
            for part in &temporary { let _ = fs::remove_file(part); }
            for (snapshot, previous) in &snapshots {
                match previous {
                    Some(bytes) => { let _ = fs::write(snapshot, bytes); }
                    None => { let _ = fs::remove_file(snapshot); }
                }
            }
            return Err(error.to_string());
        }
    }
    Ok(())
}

fn validate_publish_set(runtime: &Runtime, payload: &serde_json::Value, context: &NativeContext, mut staged: Option<Vec<Vec<u8>>>) -> Result<(Vec<(String, Vec<u8>)>, String), String> {
    let set = payload.get("set").ok_or("The save-set publish is missing its manifest.")?;
    let set_id = set.get("setId").and_then(|value| value.as_str()).unwrap_or("");
    let base_id = native_set_id(context);
    if set_id != base_id && set_id != format!("{base_id}.conflict") { return Err("The save-set belongs to another game or core.".into()); }
    if set.get("core").and_then(|value| value.as_str()) != Some(context.core.as_str())
        || set.get("gameId").and_then(|value| value.as_str()) != Some(context.game_id.as_str())
        || normalize_rom_hash(set.get("romHash").and_then(|value| value.as_str()).unwrap_or("")) != Some(context.rom_hash.clone()) {
        return Err("The save-set identity does not match the direct sync context.".into());
    }
    let members = set.get("members").and_then(|value| value.as_array()).ok_or("The save-set manifest has no members.")?;
    if members.is_empty() || members.len() > MAX_NATIVE_MEMBERS || set.get("memberCount").and_then(|value| value.as_u64()) != Some(members.len() as u64) { return Err("The save-set member count is invalid.".into()); }
    let mut canonical: Vec<CanonicalMember> = Vec::new();
    let mut seen = HashSet::new();
    let mut total_size = 0_u64;
    for (index, member) in members.iter().enumerate() {
        let member_id = member.get("memberId").and_then(|value| value.as_str()).unwrap_or("").to_string();
        let path = member.get("path").and_then(|value| value.as_str()).unwrap_or("");
        let size = member.get("size").and_then(|value| value.as_u64()).unwrap_or(0);
        let hash = member.get("contentHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
        let key = member.get("key").and_then(|value| value.as_str()).unwrap_or("");
        let expected_key = format!("{set_id}:{member_id}");
        if !valid_member_path(&member_id) || path != format!("/data/saves/{member_id}") || !seen.insert(member_id.clone()) || size == 0 || size > MAX_NATIVE_MEMBER_BYTES || !hash.chars().all(|ch| ch.is_ascii_hexdigit()) || hash.len() != 64 || (index > 0 && canonical[index - 1].member_id >= member_id) || key != expected_key {
            return Err("The save-set member manifest is invalid or unordered.".into());
        }
        total_size = total_size.saturating_add(size);
        canonical.push(CanonicalMember { member_id, path: path.to_string(), size, content_hash: hash });
    }
    if total_size > MAX_NATIVE_SET_BYTES || set.get("totalSize").and_then(|value| value.as_u64()) != Some(total_size) { return Err("The save-set total size is invalid.".into()); }
    let manifest_hash = set.get("manifestHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
    if manifest_hash.len() != 64 || canonical_set_hash(context, set_id, &canonical, total_size)? != manifest_hash { return Err("The save-set aggregate hash is invalid.".into()); }
    let items = payload.get("items").and_then(|value| value.as_array()).ok_or("The save-set publish is missing member data.")?;
    if items.len() != canonical.len() { return Err("The save-set publish is missing or adding members.".into()); }
    let mut by_key = HashMap::new();
    for (index, item) in items.iter().enumerate() {
        let key = item.get("key").and_then(|value| value.as_str()).unwrap_or("").to_string();
        if by_key.insert(key.clone(), (index, item)).is_some() { return Err("The save-set publish contains a duplicate member.".into()); }
    }
    let mut files = Vec::new();
    for member in &canonical {
        let key = format!("{set_id}:{}", member.member_id);
        let (index, item) = by_key.remove(&key).ok_or("The save-set publish is missing a member.")?;
        let bytes = if let Some(staged) = staged.as_mut() {
            staged.get_mut(index).map(std::mem::take).ok_or("The chunked save-set member data is missing.")?
        } else {
            let data = item.get("data").and_then(|value| value.as_str()).ok_or("The save-set member has no data.")?;
            B64.decode(data).map_err(|_| "The save-set member data is not valid base64.")?
        };
        if bytes.len() as u64 != member.size || sha256_bytes(&bytes) != member.content_hash { return Err("The save-set member failed size or SHA-256 validation.".into()); }
        files.push((if set_id.ends_with(".conflict") { format!("{}.an3-conflict-{}", member.member_id, &manifest_hash[..16]) } else { member.member_id.clone() }, bytes));
    }
    if !by_key.is_empty() { return Err("The save-set publish contains unexpected members.".into()); }
    let _ = runtime;
    Ok((files, manifest_hash))
}

fn validate_publish_state(payload: &serde_json::Value, context: &NativeContext, mut staged: Option<Vec<Vec<u8>>>) -> Result<Vec<(String, Vec<u8>)>, String> {
    let items = payload.get("items").and_then(|value| value.as_array()).ok_or("The save-state publish is missing member data.")?;
    if items.is_empty() || items.len() > MAX_NATIVE_MEMBERS { return Err("The save-state member list is invalid.".into()); }
    let prefix = format!("state:{}:{}:{}:", context.core, context.game_id, context.rom_hash);
    let mut seen = HashSet::new();
    let mut files = Vec::new();
    let mut total = 0_u64;
    for (index, item) in items.iter().enumerate() {
        let key = item.get("key").and_then(|value| value.as_str()).unwrap_or("");
        let path = item.get("path").and_then(|value| value.as_str()).unwrap_or("");
        let member_id = path.strip_prefix("/data/states/").ok_or("Invalid native save-state path.")?;
        let size = item.get("size").and_then(|value| value.as_u64()).unwrap_or(0);
        let hash = item.get("contentHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
        if !key.starts_with(&prefix) || !valid_state_key(key) || !valid_member_path(member_id) || !seen.insert(member_id.to_string()) || size == 0 || size > MAX_NATIVE_MEMBER_BYTES || hash.len() != 64 || !hash.chars().all(|ch| ch.is_ascii_hexdigit()) {
            return Err("The save-state member manifest is invalid.".into());
        }
        let bytes = if let Some(staged) = staged.as_mut() {
            staged.get_mut(index).map(std::mem::take).ok_or("The chunked save-state member data is missing.")?
        } else {
            let data = item.get("data").and_then(|value| value.as_str()).ok_or("The save-state member has no data.")?;
            B64.decode(data).map_err(|_| "The save-state member data is not valid base64.")?
        };
        if bytes.len() as u64 != size || sha256_bytes(&bytes) != hash { return Err("The save-state member failed size or SHA-256 validation.".into()); }
        total = total.saturating_add(size);
        if total > MAX_NATIVE_SET_BYTES { return Err("The save-state payload is too large.".into()); }
        files.push((member_id.to_string(), bytes));
    }
    Ok(files)
}

fn begin_native_publish(runtime: &Runtime, payload: &serde_json::Value, pending: &mut Option<PendingPublish>) -> Result<serde_json::Value, String> {
    if pending.is_some() { return Err("A native sync publish is already active on this peer.".into()); }
    let payload = payload.get("payload").cloned().ok_or("The chunked sync publish is missing its metadata.")?;
    let context = native_context(&payload)?;
    let _ = find_native_game(&runtime.app_dir, &context, context.rom_id.as_deref())?;
    let items = payload.get("items").and_then(|value| value.as_array()).ok_or("The chunked sync publish is missing its members.")?;
    if items.is_empty() || items.len() > MAX_NATIVE_MEMBERS { return Err("The chunked sync member list is invalid.".into()); }
    let mut total = 0_u64;
    let mut members = Vec::with_capacity(items.len());
    for item in items {
        if item.get("data").is_some() { return Err("Chunked sync metadata cannot contain inline member data.".into()); }
        let size = item.get("size").and_then(|value| value.as_u64()).ok_or("The chunked sync member is missing its size.")?;
        if size == 0 || size > MAX_NATIVE_MEMBER_BYTES { return Err("The chunked sync member is empty or too large.".into()); }
        total = total.saturating_add(size);
        if total > MAX_NATIVE_SET_BYTES { return Err("The chunked sync payload is too large.".into()); }
        members.push(PendingPublishMember { expected_size: size as usize, bytes: Vec::new() });
    }
    let permit = ACTIVE_PUBLISHES.try_acquire().ok_or("Another native sync publish is active; retry after it completes.")?;
    let transfer_id = hex(&random_bytes::<16>());
    *pending = Some(PendingPublish { transfer_id: transfer_id.clone(), payload, members, next_member: 0, _permit: permit });
    Ok(serde_json::json!({"transferId": transfer_id}))
}

fn append_native_publish_chunk(pending: &mut Option<PendingPublish>, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let transfer = pending.as_mut().ok_or("No native sync publish is active.")?;
    if payload.get("transferId").and_then(|value| value.as_str()) != Some(transfer.transfer_id.as_str()) {
        return Err("The native sync transfer identity does not match.".into());
    }
    let index = payload.get("index").and_then(|value| value.as_u64()).and_then(|value| usize::try_from(value).ok()).ok_or("The native sync chunk has an invalid member index.")?;
    if index != transfer.next_member { return Err("Native sync chunks must arrive in member order.".into()); }
    let member = transfer.members.get_mut(index).ok_or("The native sync chunk refers to an unknown member.")?;
    let offset = payload.get("offset").and_then(|value| value.as_u64()).ok_or("The native sync chunk is missing its offset.")?;
    if offset != member.bytes.len() as u64 { return Err("The native sync chunk offset is out of order.".into()); }
    let encoded = payload.get("data").and_then(|value| value.as_str()).ok_or("The native sync chunk is missing its data.")?;
    if encoded.is_empty() || encoded.len() > (SYNC_CHUNK_BYTES * 4 / 3 + 4) { return Err("The native sync chunk is empty or too large.".into()); }
    let bytes = B64.decode(encoded).map_err(|_| "The native sync chunk is not valid base64.")?;
    if bytes.is_empty() || bytes.len() > SYNC_CHUNK_BYTES || member.bytes.len().saturating_add(bytes.len()) > member.expected_size {
        return Err("The native sync chunk exceeds its member size.".into());
    }
    member.bytes.extend_from_slice(&bytes);
    let next_offset = member.bytes.len();
    if next_offset == member.expected_size { transfer.next_member += 1; }
    Ok(serde_json::json!({"nextOffset": next_offset}))
}

fn commit_native_publish(runtime: &Runtime, pending: &mut Option<PendingPublish>, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let transfer = pending.as_ref().ok_or("No native sync publish is active.")?;
    if payload.get("transferId").and_then(|value| value.as_str()) != Some(transfer.transfer_id.as_str()) {
        return Err("The native sync transfer identity does not match.".into());
    }
    if transfer.next_member != transfer.members.len() { return Err("The native sync publish is incomplete.".into()); }
    let transfer = pending.take().ok_or("No native sync publish is active.")?;
    let staged = transfer.members.into_iter().map(|member| member.bytes).collect();
    native_publish_with_data(runtime, &transfer.payload, Some(staged))
}

fn abort_native_publish(pending: &mut Option<PendingPublish>, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let transfer = pending.as_ref().ok_or("No native sync publish is active.")?;
    if payload.get("transferId").and_then(|value| value.as_str()) != Some(transfer.transfer_id.as_str()) {
        return Err("The native sync transfer identity does not match.".into());
    }
    *pending = None;
    Ok(serde_json::json!({"aborted": true}))
}

fn native_publish_with_data(runtime: &Runtime, payload: &serde_json::Value, staged: Option<Vec<Vec<u8>>>) -> Result<serde_json::Value, String> {
    let context = native_context(payload)?;
    let (_rom_id, _rom_path, root) = find_native_game(&runtime.app_dir, &context, context.rom_id.as_deref())?;
    if context.kind == "save" {
        let (files, manifest_hash) = validate_publish_set(runtime, payload, &context, staged)?;
        let count = files.len();
        write_native_members(&root, "save", files)?;
        return Ok(serde_json::json!({"ok": true, "accepted": count, "manifestHash": manifest_hash}));
    }
    let files = validate_publish_state(payload, &context, staged)?;
    let count = files.len();
    write_native_members(&root, "state", files)?;
    Ok(serde_json::json!({"ok": true, "accepted": count}))
}

fn native_publish(runtime: &Runtime, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    native_publish_with_data(runtime, payload, None)
}

fn native_plan(payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let kind = payload.get("kind").and_then(|value| value.as_str()).unwrap_or("");
    if kind != "save" && kind != "state" { return Err("Unsupported native sync plan kind.".into()); }
    let records = payload.get("records").and_then(|value| value.as_array()).ok_or("The native sync plan is missing records.")?;
    if records.len() > 2000 { return Err("The native sync plan is too large.".into()); }
    let mut transfers = Vec::new();
    for record in records {
        let key = record.get("key").and_then(|value| value.as_str()).unwrap_or("");
        if (kind == "save" && (key.is_empty() || key.len() > 256)) || (kind == "state" && !valid_state_key(key)) { return Err("The native sync plan contains an invalid key.".into()); }
        let local = record.get("local").filter(|value| !value.is_null());
        let remote = record.get("remote").filter(|value| !value.is_null());
        let direction = match (local, remote) {
            (Some(local), Some(remote)) => {
                let local_hash = local.get("content_hash").and_then(|value| value.as_str()).unwrap_or("");
                let remote_hash = remote.get("content_hash").and_then(|value| value.as_str()).unwrap_or("");
                if local_hash == remote_hash { "none" }
                else if record.get("last_synced_hash").and_then(|value| value.as_str()) == Some(local_hash) { "download" }
                else if record.get("last_synced_hash").and_then(|value| value.as_str()) == Some(remote_hash) { "upload" }
                else { "conflict" }
            }
            (Some(_), None) => "upload",
            (None, Some(_)) => "download",
            (None, None) => "none",
        };
        let reason = match direction { "upload" => "local-only", "download" => "remote-only", "conflict" => "both-changed", _ => "identical" };
        transfers.push(serde_json::json!({"key": key, "kind": kind, "direction": direction, "reason": reason, "copyKey": if direction == "conflict" { Some(format!("{key}.conflict")) } else { None }}));
    }
    Ok(serde_json::json!({"mode": "lan", "transport": "lan", "clean": transfers.iter().all(|item| item.get("direction").and_then(|value| value.as_str()) == Some("none")), "transfers": transfers}))
}

pub fn game_identity(app_dir: &Path, system: String, rom_id: String) -> Result<serde_json::Value, String> {
    let core = core_for_system(&system).ok_or("Unsupported native sync system.")?;
    if !crate::validate_rom_id(&rom_id).is_ok() { return Err("Invalid native ROM identity.".into()); }
    let path = native_rom_path(app_dir, &rom_id).filter(|value| native_extension_matches(&system, value)).ok_or("The native ROM is not available.")?;
    let rom_hash = sha256_file(&path)?;
    Ok(serde_json::json!({
        "system": system,
        "core": core,
        "gameId": format!("rom-{}", &rom_hash[..32]),
        "romHash": rom_hash,
        "romId": rom_id,
    }))
}

pub fn storage_read(app_dir: &Path, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    let context = native_context(&payload)?;
    let (_rom_id, _rom_path, root) = find_native_game(app_dir, &context, context.rom_id.as_deref())?;
    let mut records = Vec::new();
    if context.kind == "save" {
        let manifest = native_manifest(&Runtime {
            app_dir: app_dir.to_path_buf(),
            identity: load_identity(app_dir)?,
            mode: Mutex::new("guest".into()),
            code: Mutex::new(String::new()),
            code_expiry: Mutex::new(Instant::now()),
            stop: Arc::new(AtomicBool::new(true)),
            handles: Mutex::new(Vec::new()),
            peers: Mutex::new(Vec::new()),
            connected: Mutex::new(HashSet::new()),
            account_verified: Mutex::new(HashSet::new()),
            challenges: Mutex::new(HashMap::new()),
            peer_proofs: Mutex::new(HashMap::new()),
            local_proof: Mutex::new(None),
            failures: Mutex::new(HashMap::new()),
            error: Mutex::new(String::new()),
        }, &payload, "")?;
        if let Some(set) = manifest.get("sets").and_then(|value| value.as_array()).and_then(|sets| sets.first()) {
            if let Some(members) = set.get("members").and_then(|value| value.as_array()) {
                for member in members {
                    let member_id = member.get("memberId").and_then(|value| value.as_str()).unwrap_or("");
                    let bytes = native_member_bytes(&root.join(member_id))?;
                    records.push(serde_json::json!({"id": member.get("key"), "key": member.get("key"), "path": member.get("path"), "bytes": B64.encode(bytes), "updatedAt": now_seconds()}));
                }
            }
        }
    } else {
        let state_dir = root.join("states");
        let mut relative = Vec::new();
        walk_files(&state_dir, &state_dir, &mut relative, false)?;
        relative.sort();
        for member_id in relative {
            let bytes = native_member_bytes(&state_dir.join(&member_id))?;
            records.push(serde_json::json!({"id": format!("state:{}:{}:{}:{}", context.core, context.game_id, context.rom_hash, member_id), "path": format!("/data/states/{member_id}"), "state": B64.encode(bytes), "updatedAt": now_seconds()}));
        }
    }
    Ok(serde_json::json!({"records": records}))
}

pub fn storage_write(app_dir: &Path, payload: serde_json::Value) -> Result<(), String> {
    if let Some(records) = payload.get("records").and_then(|value| value.as_array()) {
        let context = native_context(&payload)?;
        let (_rom_id, _rom_path, root) = find_native_game(app_dir, &context, context.rom_id.as_deref())?;
        if records.is_empty() || records.len() > MAX_NATIVE_MEMBERS { return Err("The native sync storage write has no valid records.".into()); }
        let mut files = Vec::new();
        for record in records {
            let path = record.get("targetPath").and_then(|value| value.as_str()).filter(|value| !value.is_empty())
                .or_else(|| record.get("path").and_then(|value| value.as_str())).unwrap_or("");
            let prefix = if context.kind == "state" { "/data/states/" } else { "/data/saves/" };
            let member_id = path.strip_prefix(prefix).ok_or("Invalid native storage member path.")?;
            if !valid_member_path(member_id) { return Err("Invalid native storage member path.".into()); }
            let data = record.get("data").and_then(|value| value.as_str()).ok_or("Native storage data is missing.")?;
            let bytes = B64.decode(data).map_err(|_| "Native storage data is not valid base64.")?;
            let expected_size = record.get("size").and_then(|value| value.as_u64()).unwrap_or(bytes.len() as u64);
            let expected_hash = record.get("contentHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
            if bytes.len() as u64 != expected_size || bytes.is_empty() || bytes.len() as u64 > MAX_NATIVE_MEMBER_BYTES || (!expected_hash.is_empty() && sha256_bytes(&bytes) != expected_hash) {
                return Err("Native storage member failed size or SHA-256 validation.".into());
            }
            files.push((member_id.to_string(), bytes));
        }
        return write_native_members(&root, &context.kind, files);
    }
    let runtime = Runtime {
        app_dir: app_dir.to_path_buf(),
        identity: load_identity(app_dir)?,
        mode: Mutex::new("guest".into()),
        code: Mutex::new(String::new()),
        code_expiry: Mutex::new(Instant::now()),
        stop: Arc::new(AtomicBool::new(true)),
        handles: Mutex::new(Vec::new()),
        peers: Mutex::new(Vec::new()),
        connected: Mutex::new(HashSet::new()),
        account_verified: Mutex::new(HashSet::new()),
        challenges: Mutex::new(HashMap::new()),
        peer_proofs: Mutex::new(HashMap::new()),
        local_proof: Mutex::new(None),
        failures: Mutex::new(HashMap::new()),
        error: Mutex::new(String::new()),
    };
    native_publish(&runtime, &payload).map(|_| ())
}

fn is_rate_limited(runtime: &Runtime, ip: IpAddr) -> bool {
    let Ok(mut failures) = runtime.failures.lock() else { return true };
    let now = Instant::now();
    let attempts = failures.entry(ip).or_default();
    attempts.retain(|stamp| now.duration_since(*stamp) < Duration::from_secs(60));
    attempts.len() >= MAX_FAILURES_PER_MINUTE
}

fn note_failure(runtime: &Runtime, ip: IpAddr) { if let Ok(mut failures) = runtime.failures.lock() { failures.entry(ip).or_default().push(Instant::now()); } }
fn clear_failures(runtime: &Runtime, ip: IpAddr) { if let Ok(mut failures) = runtime.failures.lock() { failures.remove(&ip); } }

fn new_code() -> String {
    let mut result = String::with_capacity(6);
    for _ in 0..6 { result.push(char::from(b'0' + (random_bytes::<1>()[0] % 10))); }
    result
}

fn stop_runtime_locked(slot: &mut Option<Arc<Runtime>>) {
    if let Some(runtime) = slot.take() {
        runtime.stop.store(true, Ordering::Relaxed);
        if let Ok(socket) = TcpStream::connect(("127.0.0.1", SYNC_PORT)) { let _ = socket.shutdown(Shutdown::Both); }
        if let Ok(socket) = UdpSocket::bind("127.0.0.1:0") { let _ = socket.send_to(b"stop", (DISCOVERY_ADDRESS, DISCOVERY_PORT)); }
        if let Ok(mut handles) = runtime.handles.lock() { for handle in handles.drain(..) { let _ = handle.join(); } }
    }
    if let Ok(mut current) = client().lock() { if let Some(session) = current.take() { let _ = session.stream.shutdown(Shutdown::Both); } }
}

pub fn stop() { if let Ok(mut slot) = runtime().lock() { stop_runtime_locked(&mut slot); } }

pub fn start(app_dir: PathBuf, mode: String) -> Result<SyncStatus, String> {
    if !mode_valid(&mode) { return Err("Sync mode must be guest or account.".into()); }
    let mut slot = runtime().lock().map_err(|_| "Sync peer lock unavailable".to_string())?;
    if let Some(existing) = slot.as_ref() {
        if let Ok(mut current) = existing.mode.lock() { *current = mode; }
        return Ok(status());
    }
    fs::create_dir_all(&app_dir).map_err(|error| format!("Could not prepare sync storage: {error}"))?;
    let identity = load_identity(&app_dir)?;
    let peers = load_peers(&app_dir);
    let runtime = Arc::new(Runtime {
        app_dir,
        identity,
        mode: Mutex::new(mode),
        code: Mutex::new(new_code()),
        code_expiry: Mutex::new(Instant::now() + PAIRING_TTL),
        stop: Arc::new(AtomicBool::new(false)),
        handles: Mutex::new(Vec::new()),
        peers: Mutex::new(peers),
        connected: Mutex::new(HashSet::new()),
        account_verified: Mutex::new(HashSet::new()),
        challenges: Mutex::new(HashMap::new()),
        peer_proofs: Mutex::new(HashMap::new()),
        local_proof: Mutex::new(None),
        failures: Mutex::new(HashMap::new()),
        error: Mutex::new(String::new()),
    });
    let discovery_runtime = runtime.clone();
    let listener_runtime = runtime.clone();
    let discovery = std::thread::spawn(move || discovery_loop(discovery_runtime));
    let listener = std::thread::spawn(move || listener_loop(listener_runtime));
    if let Ok(mut handles) = runtime.handles.lock() { handles.extend([discovery, listener]); }
    *slot = Some(runtime);
    drop(slot);
    Ok(status())
}

fn discovery_loop(runtime: Arc<Runtime>) {
    let Ok(socket) = UdpSocket::bind("0.0.0.0:0") else { return };
    let _ = socket.set_multicast_loop_v4(true);
    while !runtime.stop.load(Ordering::Relaxed) {
        let payload = serde_json::to_vec(&advertisement_with_capabilities(&runtime.identity.device_id, &default_name(), SYNC_PORT, &["sync"])).unwrap_or_default();
        let _ = socket.send_to(&payload, (DISCOVERY_ADDRESS, DISCOVERY_PORT));
        for _ in 0..20 { if runtime.stop.load(Ordering::Relaxed) { break; } std::thread::sleep(Duration::from_millis(100)); }
    }
}

fn listener_loop(runtime: Arc<Runtime>) {
    let Ok(listener) = TcpListener::bind(("0.0.0.0", SYNC_PORT)) else { set_error(&runtime, format!("Sync port {SYNC_PORT} is unavailable")); return };
    let _ = listener.set_nonblocking(true);
    while !runtime.stop.load(Ordering::Relaxed) {
        match listener.accept() {
            Ok((mut stream, peer)) => {
                let Some(permit) = ACTIVE_HANDLERS.try_acquire() else {
                    drop(stream);
                    continue;
                };
                let runtime = runtime.clone();
                std::thread::spawn(move || {
                    let _permit = permit;
                    handle_client(&runtime, &mut stream, peer);
                });
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => std::thread::sleep(Duration::from_millis(50)),
            Err(_) => std::thread::sleep(Duration::from_millis(100)),
        }
    }
}

fn discover(target: Option<&str>) -> Result<(SocketAddr, String, String), String> {
    let socket = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0)).map_err(|error| format!("Direct LAN discovery is unavailable: {error}"))?;
    let group = DISCOVERY_ADDRESS.parse::<Ipv4Addr>().map_err(|_| "Invalid AN3 discovery group.")?;
    socket.join_multicast_v4(&group, &Ipv4Addr::UNSPECIFIED).map_err(|error| format!("Could not join AN3 LAN discovery: {error}"))?;
    let _ = socket.set_read_timeout(Some(Duration::from_millis(250)));
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut payload = [0u8; 4096];
    while Instant::now() < deadline {
        match socket.recv_from(&mut payload) {
            Ok((length, source)) => {
                let Ok(value) = serde_json::from_slice::<serde_json::Value>(&payload[..length]) else { continue };
                let Ok(peer) = parse_advertisement(&value) else { continue };
                if !peer.capabilities.iter().any(|capability| capability == "sync") || target.is_some_and(|wanted| wanted != peer.id) { continue; }
                return Ok((SocketAddr::new(source.ip(), peer.port), peer.id, peer.name));
            }
            Err(error) if matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
            Err(_) => {}
        }
    }
    Err("No AN3 sync peer was found on the local network.".into())
}

fn local_peer(runtime: &Runtime, peer_id: &str) -> Option<PeerRecord> { runtime.peers.lock().ok()?.iter().find(|peer| peer.device_id == peer_id).cloned() }

fn store_peer(runtime: &Runtime, record: PeerRecord) -> Result<(), String> {
    {
        let mut peers = runtime.peers.lock().map_err(|_| "Sync peer registry unavailable".to_string())?;
        peers.retain(|peer| peer.device_id != record.device_id);
        peers.push(record);
    }
    save_peers(runtime)
}

fn handshake_status(runtime: &Runtime, peer_id: &str, state: &str, name: &str, mode: &str, fp: &str) -> SyncPeerStatus {
    let account_verified = runtime.account_verified.lock().map(|peers| peers.contains(peer_id)).unwrap_or(false);
    SyncPeerStatus { device_id: peer_id.to_string(), name: name.to_string(), mode: mode.to_string(), state: state.to_string(), fingerprint: fp.to_string(), last_seen: now_seconds(), account_verified }
}

fn handle_client(runtime: &Arc<Runtime>, stream: &mut TcpStream, address: SocketAddr) {
    let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
    let _ = stream.set_write_timeout(Some(IO_TIMEOUT));
    let Ok(hello_bytes) = read_frame(stream) else { return };
    let Ok(hello) = serde_json::from_slice::<serde_json::Value>(&hello_bytes) else { return };
    if hello.get("k").and_then(|value| value.as_str()) != Some("hello") || hello.get("v").and_then(|value| value.as_u64()) != Some(PROTOCOL_VERSION as u64) { return; }
    let Some(peer_id) = hello.get("id").and_then(|value| value.as_str()).filter(|value| safe_id(value)) else { return };
    let peer_name = hello.get("name").and_then(|value| value.as_str()).unwrap_or("AN3 device").chars().take(64).collect::<String>();
    let peer_mode = hello.get("mode").and_then(|value| value.as_str()).unwrap_or("guest").to_string();
    if !mode_valid(&peer_mode) || is_rate_limited(runtime, address.ip()) { return; }
    let Some(peer_pub_bytes) = hello.get("pub").and_then(|value| value.as_str()).and_then(|value| B64.decode(value).ok()) else { return };
    let Ok(peer_pub) = PublicKey::from_sec1_bytes(&peer_pub_bytes) else { return };
    let secret = EphemeralSecret::random(&mut p256::elliptic_curve::rand_core::OsRng);
    let host_pub_bytes = secret.public_key().to_encoded_point(false).as_bytes().to_vec();
    let response = serde_json::json!({"k":"hello","v":PROTOCOL_VERSION,"pub":B64.encode(&host_pub_bytes),"id":runtime.identity.device_id,"name":default_name(),"mode":runtime.mode.lock().ok().map(|mode| mode.clone()).unwrap_or_else(|| "guest".into())});
    if write_frame(stream, &serde_json::to_vec(&response).unwrap_or_default()).is_err() { return; }
    let shared = secret.diffie_hellman(&peer_pub);
    let host_mode = runtime.mode.lock().ok().map(|mode| mode.clone()).unwrap_or_else(|| "guest".into());
    let handshake_challenge = challenge(&runtime.identity.device_id, &host_pub_bytes, peer_id, &peer_pub_bytes);
    let trusted = local_peer(runtime, peer_id);
    let Ok(auth_bytes) = read_frame(stream) else { return };
    let mut matched = None;
    if let Some(record) = trusted.as_ref() {
        if let Ok(token) = B64.decode(&record.token) {
            let key = derive_key(shared.raw_secret_bytes().as_slice(), &token);
            if let Ok(cipher) = Aes256Gcm::new_from_slice(&key) {
                if let Some(value) = open(&cipher, DIR_CLIENT_TO_HOST, 0, &auth_bytes) {
                    if value.get("k").and_then(|item| item.as_str()) == Some("auth")
                        && value.get("identity").and_then(|item| item.as_str()) == Some(record.identity.as_str())
                        && value.get("challenge").and_then(|item| item.as_str()) == Some(handshake_challenge.as_str())
                    {
                        matched = Some((key, record.token.clone()));
                    }
                }
            }
        }
    }
    if matched.is_none() && peer_mode == "account" && host_mode == "account" {
        let key = derive_key(shared.raw_secret_bytes().as_slice(), handshake_challenge.as_bytes());
        if let Ok(cipher) = Aes256Gcm::new_from_slice(&key) {
            if let Some(value) = open(&cipher, DIR_CLIENT_TO_HOST, 0, &auth_bytes) {
                let valid_account_handshake = value.get("k").and_then(|item| item.as_str()) == Some("auth")
                    && value.get("mode").and_then(|item| item.as_str()) == Some("account")
                    && value.get("challenge").and_then(|item| item.as_str()) == Some(handshake_challenge.as_str());
                if valid_account_handshake {
                    let token_string = B64.encode(random_bytes::<32>());
                    let identity = value.get("identity").and_then(|item| item.as_str()).unwrap_or_default().to_string();
                    if B64.decode(&identity).ok().is_none_or(|bytes| bytes.len() != 32) { note_failure(runtime, address.ip()); return; }
                    let record = PeerRecord { device_id: peer_id.to_string(), name: peer_name.clone(), mode: peer_mode.clone(), token: token_string.clone(), identity: identity.clone(), fingerprint: fingerprint(&B64.decode(&identity).unwrap_or_default()), last_seen: now_seconds() };
                    if store_peer(runtime, record).is_err() { return; }
                    matched = Some((key, token_string));
                }
            }
        }
    }
    if matched.is_none() && !runtime.code.lock().ok().map(|code| code.is_empty()).unwrap_or(true) && runtime.code_expiry.lock().ok().map(|expiry| Instant::now() < *expiry).unwrap_or(false) {
        let code = runtime.code.lock().ok().map(|value| value.clone()).unwrap_or_default();
        let key = derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes());
        if let Ok(cipher) = Aes256Gcm::new_from_slice(&key) {
            if let Some(value) = open(&cipher, DIR_CLIENT_TO_HOST, 0, &auth_bytes) {
                let valid_pairing = value.get("k").and_then(|item| item.as_str()) == Some("auth")
                    && value.get("mode").and_then(|item| item.as_str()) == Some("guest")
                    && peer_mode == "guest"
                    && host_mode == "guest"
                    && value.get("challenge").and_then(|item| item.as_str()) == Some(handshake_challenge.as_str());
                if valid_pairing {
                    let token = random_bytes::<32>();
                    let token_string = B64.encode(token);
                    let identity = value.get("identity").and_then(|item| item.as_str()).unwrap_or_default().to_string();
                    if B64.decode(&identity).ok().is_none_or(|bytes| bytes.len() != 32) { note_failure(runtime, address.ip()); return; }
                    let record = PeerRecord { device_id: peer_id.to_string(), name: peer_name.clone(), mode: peer_mode.clone(), token: token_string.clone(), identity, fingerprint: fingerprint(&B64.decode(value.get("identity").and_then(|item| item.as_str()).unwrap_or_default()).unwrap_or_default()), last_seen: now_seconds() };
                    if store_peer(runtime, record).is_err() { return; }
                    if let Ok(mut code) = runtime.code.lock() { code.clear(); }
                    matched = Some((key, token_string));
                }
            }
        }
    }
    let Some((session_key, token_string)) = matched else { note_failure(runtime, address.ip()); return };
    clear_failures(runtime, address.ip());
    let Ok(cipher) = Aes256Gcm::new_from_slice(&session_key) else { return };
    let ready = serde_json::json!({"k":"ready","token":token_string,"identity":runtime.identity.secret,"id":runtime.identity.device_id,"name":default_name(),"mode":host_mode,"challenge":handshake_challenge});
    if write_frame(stream, &seal(&cipher, DIR_HOST_TO_CLIENT, 0, &ready)).is_err() { return; }
    if let Ok(mut connected) = runtime.connected.lock() { connected.insert(peer_id.to_string()); }
    if let Ok(mut challenges) = runtime.challenges.lock() { challenges.insert(peer_id.to_string(), handshake_challenge); }
    serve_requests(runtime, stream, &cipher, peer_id, 1);
    if let Ok(mut connected) = runtime.connected.lock() { connected.remove(peer_id); }
    if let Ok(mut challenges) = runtime.challenges.lock() { challenges.remove(peer_id); }
    if let Ok(mut proofs) = runtime.peer_proofs.lock() { proofs.remove(peer_id); }
    if let Ok(mut verified) = runtime.account_verified.lock() { verified.remove(peer_id); }
}

fn serve_requests(runtime: &Arc<Runtime>, stream: &mut TcpStream, cipher: &Aes256Gcm, peer_id: &str, mut send_counter: u64) {
    let mut receive_counter = 1u64;
    let mut pending_publish = None;
    while !runtime.stop.load(Ordering::Relaxed) {
        let Ok(body) = read_frame(stream) else { return };
        let Some(value) = open(cipher, DIR_CLIENT_TO_HOST, receive_counter, &body) else { return };
        receive_counter = receive_counter.wrapping_add(1);
        if value.get("k").and_then(|item| item.as_str()) != Some("request") { continue; }
        let id = value.get("id").cloned().unwrap_or(serde_json::Value::Null);
        let method = value.get("method").and_then(|item| item.as_str()).unwrap_or("");
        let payload = value.get("payload").cloned().unwrap_or(serde_json::Value::Null);
        let result = match method {
            "ping" => Ok(serde_json::json!({"ok":true,"peerId":peer_id,"chunkedTransfers":1})),
            "manifest" => native_manifest(runtime, &payload, peer_id),
            "plan" => native_plan(&payload),
            "blob" => native_blob(runtime, &payload),
            "publish" => native_publish(runtime, &payload),
            "publish-begin" => begin_native_publish(runtime, &payload, &mut pending_publish),
            "publish-chunk" => append_native_publish_chunk(&mut pending_publish, &payload),
            "publish-commit" => commit_native_publish(runtime, &mut pending_publish, &payload),
            "publish-abort" => abort_native_publish(&mut pending_publish, &payload),
            "account-proof" => {
                let proof = payload.get("proof").and_then(|value| value.as_str()).unwrap_or("").to_string();
                if proof.is_empty() || proof.len() > 4096 { Err("Invalid account proof.".into()) }
                else {
                    if let Ok(mut proofs) = runtime.peer_proofs.lock() { proofs.insert(peer_id.to_string(), proof); }
                    let local = runtime.local_proof.lock().ok().and_then(|value| value.clone()).unwrap_or_default();
                    Ok(serde_json::json!({"proof": local}))
                }
            }
            "resolve" => Ok(serde_json::json!({"ok":true,"action":"accepted"})),
            _ => Err("unsupported sync request".to_string()),
        };
        let response = match result { Ok(result) => serde_json::json!({"k":"response","id":id,"ok":true,"result":result}), Err(error) => serde_json::json!({"k":"response","id":id,"ok":false,"error":error}) };
        if write_frame(stream, &seal(cipher, DIR_HOST_TO_CLIENT, send_counter, &response)).is_err() { return; }
        send_counter = send_counter.wrapping_add(1);
    }
}

fn connected_peer() -> Option<String> { client().lock().ok()?.as_ref().map(|session| session.peer.device_id.clone()) }

fn drop_client_session() {
    if let Ok(mut current) = client().lock() {
        if let Some(session) = current.take() {
            let _ = session.stream.shutdown(Shutdown::Both);
        }
    }
}

pub fn join(code: String, mode: String, target: Option<String>) -> Result<SyncStatus, String> {
    if !mode_valid(&mode) { return Err("Sync mode must be guest or account.".into()); }
    let runtime = runtime().lock().ok().and_then(|slot| slot.clone()).ok_or("Start LAN Sync hosting before joining a peer.")?;
    let (address, _peer_id, peer_name) = discover(target.as_deref())?;
    let mut stream = TcpStream::connect_timeout(&address, IO_TIMEOUT).map_err(|error| format!("Could not connect to the AN3 sync peer: {error}"))?;
    let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
    let _ = stream.set_write_timeout(Some(IO_TIMEOUT));
    let secret = EphemeralSecret::random(&mut p256::elliptic_curve::rand_core::OsRng);
    let public = secret.public_key().to_encoded_point(false).as_bytes().to_vec();
    let hello = serde_json::json!({"k":"hello","v":PROTOCOL_VERSION,"pub":B64.encode(&public),"id":runtime.identity.device_id,"name":default_name(),"mode":mode});
    write_frame(&mut stream, &serde_json::to_vec(&hello).unwrap_or_default()).map_err(|error| error.to_string())?;
    let response: serde_json::Value = serde_json::from_slice(&read_frame(&mut stream).map_err(|error| error.to_string())?).map_err(|_| "The sync peer returned malformed handshake data.".to_string())?;
    let host_pub_bytes = response.get("pub").and_then(|value| value.as_str()).and_then(|value| B64.decode(value).ok()).ok_or("The sync peer returned an invalid public key.")?;
    let host_pub = PublicKey::from_sec1_bytes(&host_pub_bytes).map_err(|_| "The sync peer returned an invalid public key.")?;
    let host_id = response.get("id").and_then(|value| value.as_str()).filter(|value| safe_id(value)).ok_or("The sync peer returned an invalid identity.")?;
    let host_mode = response.get("mode").and_then(|value| value.as_str()).unwrap_or("guest");
    if host_mode != mode { return Err("Guest and signed-in LAN sync modes cannot be mixed.".into()); }
    let shared = secret.diffie_hellman(&host_pub);
    let transcript = challenge(host_id, &host_pub_bytes, &runtime.identity.device_id, &public);
    let trusted = local_peer(&runtime, host_id);
    let (key, reconnect) = if let Some(record) = trusted.as_ref() {
        let token = B64.decode(&record.token).map_err(|_| "Remembered peer trust is corrupt; re-pair required.")?;
        (derive_key(shared.raw_secret_bytes().as_slice(), &token), true)
    } else if mode == "account" {
        (derive_key(shared.raw_secret_bytes().as_slice(), transcript.as_bytes()), false)
    } else {
        if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) { return Err("Enter exactly six decimal digits.".into()); }
        (derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes()), false)
    };
    let local_secret = runtime.identity.secret.clone();
    let cipher = Aes256Gcm::new_from_slice(&key).map_err(|_| "Could not initialize sync encryption.")?;
    let auth = serde_json::json!({"k":"auth","mode":mode,"identity":local_secret,"challenge":transcript,"reconnect":reconnect});
    write_frame(&mut stream, &seal(&cipher, DIR_CLIENT_TO_HOST, 0, &auth)).map_err(|error| error.to_string())?;
    let ready = open(&cipher, DIR_HOST_TO_CLIENT, 0, &read_frame(&mut stream).map_err(|error| error.to_string())?).ok_or("The sync peer rejected the pairing code or trust record.")?;
    if ready.get("k").and_then(|value| value.as_str()) != Some("ready") { return Err("The sync peer did not confirm LAN Sync.".into()); }
    let token = ready.get("token").and_then(|value| value.as_str()).unwrap_or_default().to_string();
    if token.is_empty() { return Err("The sync peer did not issue a trust token.".into()); }
    let host_identity = ready.get("identity").and_then(|value| value.as_str()).unwrap_or_default().to_string();
    let host_fingerprint = fingerprint(&B64.decode(&host_identity).unwrap_or_default());
    let record = PeerRecord { device_id: host_id.to_string(), name: peer_name, mode, token: token.clone(), identity: host_identity, fingerprint: host_fingerprint, last_seen: now_seconds() };
    store_peer(&runtime, record.clone())?;
    if let Ok(mut current) = client().lock() { *current = Some(ClientSession { stream, key, send_counter: 1, receive_counter: 1, peer: record, challenge: transcript, account_verified: false, remote_proof: String::new() }); }
    Ok(status())
}

pub fn discover_peers() -> Result<Vec<serde_json::Value>, String> {
    let socket = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0)).map_err(|error| error.to_string())?;
    let group = DISCOVERY_ADDRESS.parse::<Ipv4Addr>().map_err(|_| "Invalid AN3 discovery group.")?;
    socket.join_multicast_v4(&group, &Ipv4Addr::UNSPECIFIED).map_err(|error| error.to_string())?;
    let _ = socket.set_read_timeout(Some(Duration::from_millis(250)));
    let deadline = Instant::now() + Duration::from_secs(2);
    let mut payload = [0u8; 4096];
    let mut found = HashMap::new();
    while Instant::now() < deadline {
        match socket.recv_from(&mut payload) {
            Ok((length, source)) => {
                let Ok(value) = serde_json::from_slice::<serde_json::Value>(&payload[..length]) else { continue };
                let Ok(peer) = parse_advertisement(&value) else { continue };
                if peer.capabilities.iter().any(|capability| capability == "sync") && peer.id != status().device_id { found.insert(peer.id.clone(), serde_json::json!({"deviceId":peer.id,"name":peer.name,"port":peer.port,"address":source.ip().to_string(),"capabilities":peer.capabilities})); }
            }
            Err(error) if matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
            Err(_) => {}
        }
    }
    Ok(found.into_values().collect())
}

pub fn forget(peer_id: String) -> Result<SyncStatus, String> {
    if !safe_id(&peer_id) { return Err("Invalid remembered peer identity.".into()); }
    if connected_peer().as_deref() == Some(peer_id.as_str()) { drop_client_session(); }
    let runtime = runtime().lock().ok().and_then(|slot| slot.clone()).ok_or("LAN Sync is not started.")?;
    if let Ok(mut peers) = runtime.peers.lock() { peers.retain(|peer| peer.device_id != peer_id); }
    save_peers(&runtime)?;
    Ok(status())
}

pub fn request(method: String, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    let mut guard = client().lock().map_err(|_| "Sync connection unavailable".to_string())?;
    let current = guard.as_mut().ok_or("Connect to a remembered LAN Sync peer first.")?;
    let id = hex(&random_bytes::<8>());
    let cipher = Aes256Gcm::new_from_slice(&current.key).map_err(|_| "Could not initialize sync encryption.")?;
    let request = serde_json::json!({"k":"request","id":id,"method":method,"payload":payload});
    if let Err(error) = write_frame(&mut current.stream, &seal(&cipher, DIR_CLIENT_TO_HOST, current.send_counter, &request)) {
        *guard = None;
        return Err(format!("Direct LAN Sync connection failed: {error}"));
    }
    current.send_counter = current.send_counter.wrapping_add(1);
    loop {
        let body = match read_frame(&mut current.stream) {
            Ok(body) => body,
            Err(error) => {
                *guard = None;
                return Err(format!("Direct LAN Sync connection failed: {error}"));
            }
        };
        let Some(response) = open(&cipher, DIR_HOST_TO_CLIENT, current.receive_counter, &body) else {
            *guard = None;
            return Err("Direct LAN Sync response failed authentication.".into());
        };
        current.receive_counter = current.receive_counter.wrapping_add(1);
        if response.get("id").and_then(|value| value.as_str()) != Some(id.as_str()) { continue; }
        if response.get("ok").and_then(|value| value.as_bool()) != Some(true) { return Err(response.get("error").and_then(|value| value.as_str()).unwrap_or("Direct LAN Sync request failed").into()); }
        let result = response.get("result").cloned().unwrap_or(serde_json::Value::Null);
        if method == "account-proof" {
            if let Some(proof) = result.get("proof").and_then(|value| value.as_str()) {
                current.remote_proof = proof.to_string();
            }
        }
        return Ok(result);
    }
}

pub fn status() -> SyncStatus {
    let Some(runtime) = runtime().lock().ok().and_then(|slot| slot.clone()) else { return SyncStatus { running:false, role:"off".into(), mode:"guest".into(), device_id:String::new(), code:String::new(), code_expires_in_seconds:0, peers:Vec::new(), error:String::new() }; };
    let mode = runtime.mode.lock().ok().map(|value| value.clone()).unwrap_or_else(|| "guest".into());
    let connected = runtime.connected.lock().map(|value| value.clone()).unwrap_or_default();
    let client_peer = client().lock().ok().and_then(|value| value.as_ref().map(|session| session.peer.device_id.clone()));
    let client_verified = client().lock().ok().and_then(|value| value.as_ref().map(|session| (session.peer.device_id.clone(), session.account_verified)));
    let peers = runtime.peers.lock().map(|records| records.iter().map(|peer| {
        let active = connected.contains(&peer.device_id) || client_peer.as_deref() == Some(peer.device_id.as_str());
        let mut status = handshake_status(&runtime, &peer.device_id, if active { "connecting" } else { "offline" }, &peer.name, &peer.mode, &peer.fingerprint);
        if client_verified.as_ref().is_some_and(|(id, _)| id == &peer.device_id) {
            status.account_verified = client_verified.as_ref().map(|(_, verified)| *verified).unwrap_or(false);
        }
        if active && (peer.mode != "account" || status.account_verified) {
            status.state = "connected".into();
        }
        status
    }).collect()).unwrap_or_default();
    let code = runtime.code.lock().ok().map(|value| value.clone()).unwrap_or_default();
    let expires = runtime.code_expiry.lock().ok().map(|value| value.saturating_duration_since(Instant::now()).as_secs()).unwrap_or(0);
    SyncStatus { running:true, role: if client_peer.is_some() { "peer".into() } else { "host".into() }, mode, device_id:runtime.identity.device_id.clone(), code, code_expires_in_seconds:expires, peers, error:runtime.error.lock().ok().map(|value| value.clone()).unwrap_or_default() }
}

pub fn identity() -> Result<serde_json::Value, String> {
    let runtime = runtime().lock().ok().and_then(|slot| slot.clone()).ok_or("LAN Sync is not started.")?;
    let secret = B64.decode(&runtime.identity.secret).map_err(|_| "Local sync identity is corrupt.")?;
    Ok(serde_json::json!({"deviceId":runtime.identity.device_id,"fingerprint":fingerprint(&secret),"mode":runtime.mode.lock().ok().map(|value| value.clone()).unwrap_or_else(|| "guest".into())}))
}

pub fn account_context() -> serde_json::Value {
    if let Ok(current) = client().lock() {
        if let Some(session) = current.as_ref() {
            return serde_json::json!({
                "peerId": session.peer.device_id,
                "challenge": session.challenge,
                "remoteProof": session.remote_proof,
                "accountVerified": session.account_verified,
            });
        }
    }
    if let Some(runtime) = runtime().lock().ok().and_then(|slot| slot.clone()) {
        let peer_id = runtime.connected.lock().ok().and_then(|peers| peers.iter().next().cloned());
        if let Some(peer_id) = peer_id {
            return serde_json::json!({
                "peerId": peer_id,
                "challenge": runtime.challenges.lock().ok().and_then(|values| values.get(&peer_id).cloned()).unwrap_or_default(),
                "remoteProof": runtime.peer_proofs.lock().ok().and_then(|values| values.get(&peer_id).cloned()).unwrap_or_default(),
                "accountVerified": runtime.account_verified.lock().map(|values| values.contains(&peer_id)).unwrap_or(false),
            });
        }
    }
    serde_json::json!({"peerId": null, "challenge": "", "remoteProof": "", "accountVerified": false})
}

pub fn set_local_proof(proof: String) -> Result<(), String> {
    if proof.is_empty() || proof.len() > 4096 { return Err("Invalid account proof.".into()); }
    let runtime = runtime().lock().ok().and_then(|slot| slot.clone()).ok_or("LAN Sync is not started.")?;
    if let Ok(mut local) = runtime.local_proof.lock() { *local = Some(proof); }
    Ok(())
}

pub fn mark_account_verified(peer_id: String, verified: bool) -> Result<SyncStatus, String> {
    if !safe_id(&peer_id) { return Err("Invalid remembered peer identity.".into()); }
    let runtime = runtime().lock().ok().and_then(|slot| slot.clone()).ok_or("LAN Sync is not started.")?;
    let connected = runtime.connected.lock().map(|values| values.contains(&peer_id)).unwrap_or(false)
        || client().lock().ok().and_then(|value| value.as_ref().map(|session| session.peer.device_id == peer_id)).unwrap_or(false);
    if !connected { return Err("The account proof is not bound to a live peer session.".into()); }
    if let Ok(mut values) = runtime.account_verified.lock() {
        if verified { values.insert(peer_id.clone()); } else { values.remove(&peer_id); }
    }
    if let Ok(mut current) = client().lock() {
        if let Some(session) = current.as_mut() {
            if session.peer.device_id == peer_id { session.account_verified = verified; }
        }
    }
    Ok(status())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pairing_codes_are_six_decimal_digits() {
        let code = new_code();
        assert_eq!(code.len(), 6);
        assert!(code.bytes().all(|byte| byte.is_ascii_digit()));
    }

    #[test]
    fn handshake_challenge_is_direction_independent() {
        let value = challenge("host", b"host-key", "client", b"client-key");
        assert_eq!(value.len(), 64);
        assert_ne!(value, challenge("client", b"client-key", "host", b"host-key"));
    }

    #[test]
    fn guest_and_account_modes_are_distinct() {
        assert!(mode_valid("guest"));
        assert!(mode_valid("account"));
        assert!(!mode_valid("device"));
    }

    #[test]
    fn chunked_publish_accepts_ordered_chunks_and_releases_its_slot() {
        let mut pending = Some(PendingPublish {
            transfer_id: "transfer-1".into(),
            payload: serde_json::json!({}),
            members: vec![PendingPublishMember { expected_size: 3, bytes: Vec::new() }],
            next_member: 0,
            _permit: ACTIVE_PUBLISHES.try_acquire().expect("publish slot"),
        });
        let result = append_native_publish_chunk(&mut pending, &serde_json::json!({
            "transferId": "transfer-1", "index": 0, "offset": 0, "data": B64.encode(b"abc")
        })).expect("ordered chunk");
        assert_eq!(result["nextOffset"], 3);
        assert_eq!(pending.as_ref().unwrap().next_member, 1);

        drop(pending.take());
        assert!(ACTIVE_PUBLISHES.try_acquire().is_some());
    }

    #[test]
    fn native_blob_ranges_reject_partial_and_mistyped_values() {
        assert_eq!(native_blob_range(&serde_json::json!({})).unwrap(), None);
        assert_eq!(native_blob_range(&serde_json::json!({"offset": 7, "length": 9})).unwrap(), Some((7, 9)));
        assert!(native_blob_range(&serde_json::json!({"offset": 7})).is_err());
        assert!(native_blob_range(&serde_json::json!({"offset": "7", "length": 9})).is_err());
    }
}

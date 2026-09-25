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
    sync::{atomic::{AtomicBool, AtomicU16, Ordering}, Arc, Mutex, OnceLock},
    thread::JoinHandle,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use aes_gcm::{aead::{Aead, KeyInit}, Aes256Gcm, Nonce};
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use hkdf::Hkdf;
use p256::{ecdh::EphemeralSecret, elliptic_curve::sec1::ToEncodedPoint, PublicKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::lan_peer::{advertisement_with_capabilities, discovery_socket, local_lan_ipv4, parse_advertisement, DISCOVERY_ADDRESS, DISCOVERY_BROADCAST, DISCOVERY_PORT, PROTOCOL_VERSION, SYNC_PORT};

const PAIRING_TTL: Duration = Duration::from_secs(120);
// Sync pairing is interactive too. A short, explicit bound keeps a vanished
// peer from making the UI look hung while still allowing a LAN handshake.
const IO_TIMEOUT: Duration = Duration::from_secs(8);
const MAX_FRAME_BYTES: usize = 8 * 1024 * 1024;
const MAX_FAILURES_PER_MINUTE: usize = 6;
const MAX_NATIVE_MEMBERS: usize = 64;
const MAX_NATIVE_SET_BYTES: u64 = 64 * 1024 * 1024;
const MAX_NATIVE_MEMBER_BYTES: u64 = 16 * 1024 * 1024;
const MAX_LIBRARY_ITEMS: usize = 2000;
const MAX_LIBRARY_FILE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const LIBRARY_CHUNK_BYTES: usize = 2 * 1024 * 1024;
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
    pub state: String,
    pub device_id: String,
    pub code: String,
    pub code_expires_in_seconds: u64,
    pub peers: Vec<SyncPeerStatus>,
    pub error: String,
}

struct Runtime {
    app_dir: PathBuf,
    identity: IdentityRecord,
    bind_port: u16,
    discovery_enabled: bool,
    bound_port: AtomicU16,
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
    connecting: AtomicBool,
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

/// The Android emulator cannot receive the Mac's LAN multicast advertisement.
/// Debug instrumentation may therefore pass a private, literal endpoint using
/// `direct:<ip>:<port>`.  The endpoint still goes through the normal encrypted
/// handshake and pairing/trust checks; release builds reject this test bridge.
fn parse_debug_direct_target(value: &str) -> Result<Option<SocketAddr>, String> {
    let Some(endpoint) = value.strip_prefix("direct:") else { return Ok(None); };
    if !cfg!(debug_assertions) {
        return Err("Direct Sync endpoints are available only in debug instrumentation builds.".into());
    }
    let address = endpoint.parse::<SocketAddr>().map_err(|_| "The debug Sync endpoint must be a literal IP address and port.".to_string())?;
    let private = match address.ip() {
        IpAddr::V4(ip) => ip.is_loopback() || ip.is_private() || ip.is_link_local(),
        IpAddr::V6(ip) => ip.is_loopback() || ip.is_unicast_link_local(),
    };
    if !private || address.port() == 0 {
        return Err("The debug Sync endpoint must use a private or loopback address.".into());
    }
    Ok(Some(address))
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

#[derive(Serialize)]
struct CanonicalLibraryItem {
    #[serde(rename = "romId")]
    rom_id: String,
    extension: String,
    system: String,
    size: u64,
    #[serde(rename = "contentHash")]
    content_hash: String,
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

/// A verified content hash for one immutable imported file. The installed app
/// owns ROM files and replaces them atomically on import, so a size + mtime
/// match means the bytes are unchanged. This is only an identity cache: the
/// transfer layer still verifies every byte it moves, so end-to-end integrity
/// is never weakened.
#[derive(Clone, Serialize, Deserialize)]
struct ContentIdentity {
    size: u64,
    mtime: u64,
    sha256: String,
}

fn content_cache() -> &'static Mutex<HashMap<String, ContentIdentity>> {
    static CACHE: OnceLock<Mutex<HashMap<String, ContentIdentity>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn identity_cache_file(app_dir: &Path) -> PathBuf {
    app_dir.join("an3-roms").join(".an3-identity-cache.json")
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum NativeStorageLayout {
    Generic,
    Android,
    Mac,
}

fn current_native_storage_layout() -> NativeStorageLayout {
    #[cfg(target_os = "android")]
    { return NativeStorageLayout::Android; }
    #[cfg(target_os = "macos")]
    { return NativeStorageLayout::Mac; }
    #[allow(unreachable_code)]
    NativeStorageLayout::Generic
}

/// Android's `app_data_dir` resolves to the package data directory, while the
/// native game activity keeps its save/state tree below `files/`. Other
/// libretro platforms use a per-game tree under app data. macOS's AzaharHost
/// predates that layout and owns `<core>/saves/<rom-id>.srm` plus
/// `<core>/saves/states/<rom-id>.*.state`; Sync must address those live files
/// rather than a parallel, empty `native-states-v1` tree.
fn native_state_root(app_dir: &Path, layout: NativeStorageLayout) -> PathBuf {
    let root = app_dir.join("native-states-v1");
    if layout == NativeStorageLayout::Android { app_dir.join("files").join("native-states-v1") } else { root }
}

fn native_save_component(system: &str) -> Option<&'static str> {
    match system {
        "gba" => Some("mgba"),
        "nds" => Some("melondsds"),
        "3ds" => Some("azahar"),
        _ => None,
    }
}

fn normalized_absolute_path(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().map_err(|error| error.to_string())?.join(path)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => { normalized.pop(); }
            _ => normalized.push(component.as_os_str()),
        }
    }
    Ok(normalized)
}

/// Keep in lockstep with NativeCoreHost::stable_rom_id. The Android save root
/// is already isolated by imported ROM UUID, but the core's on-disk basename
/// also includes this path-derived suffix for compatibility with existing
/// saves and slots.
fn android_core_rom_id(rom_path: &Path) -> Result<String, String> {
    let mut name = rom_path.file_stem().and_then(|value| value.to_str()).unwrap_or("game")
        .chars().map(|value| if value.is_ascii_alphanumeric() || matches!(value, '-' | '_') { value } else { '_' })
        .collect::<String>();
    if name.is_empty() { name = "game".into(); }
    name.truncate(80);
    let identity = normalized_absolute_path(rom_path)?.to_string_lossy().into_owned();
    let mut hash = 1_469_598_103_934_665_603_u64;
    for byte in identity.bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(1_099_511_628_211);
    }
    Ok(format!("{name}-{hash:x}"))
}

#[derive(Clone)]
struct NativeGameStorage {
    root: PathBuf,
    layout: NativeStorageLayout,
    runtime_rom_id: String,
}

impl NativeGameStorage {
    fn for_layout(app_dir: &Path, system: &str, rom_id: &str, rom_path: &Path, layout: NativeStorageLayout) -> Result<Self, String> {
        let root = match layout {
            NativeStorageLayout::Mac => app_dir.join(native_save_component(system).ok_or("Unsupported native sync system.")?).join("saves"),
            NativeStorageLayout::Android => native_state_root(app_dir, layout).join(system).join(rom_id).join("native-libretro"),
            NativeStorageLayout::Generic => native_state_root(app_dir, layout).join(system).join(rom_id).join("native-libretro"),
        };
        let runtime_rom_id = match layout {
            NativeStorageLayout::Android => android_core_rom_id(rom_path)?,
            _ => rom_id.to_string(),
        };
        Ok(Self { root, layout, runtime_rom_id })
    }

    fn member_path(&self, kind: &str, member_id: &str) -> Result<PathBuf, String> {
        if !valid_member_path(member_id) { return Err("Invalid native sync member path.".into()); }
        if self.layout == NativeStorageLayout::Generic {
            return Ok(if kind == "state" { self.root.join("states").join(member_id) } else { self.root.join(member_id) });
        }
        let (canonical, conflict_hash) = match member_id.split_once(".an3-conflict-") {
            Some((canonical, hash)) if hash.len() == 16 && hash.bytes().all(|byte| byte.is_ascii_hexdigit()) => (canonical, Some(hash)),
            Some(_) => return Err("Invalid native conflict-copy identity.".into()),
            None => (member_id, None),
        };
        let base = if kind == "save" {
            if canonical != "battery.srm" { return Err("Unsupported native battery-save member.".into()); }
            self.root.join(format!("{}.srm", self.runtime_rom_id))
        } else if kind == "state" {
            let valid_slot = (1..=10).any(|slot| canonical == format!("slot{slot}.state"));
            if canonical != "autosave.state" && !valid_slot { return Err("Unsupported native save-state member.".into()); }
            self.root.join("states").join(format!("{}.{}", self.runtime_rom_id, canonical))
        } else {
            return Err("Unsupported native sync artifact kind.".into());
        };
        Ok(match conflict_hash {
            Some(hash) => base.with_file_name(format!("{}.an3-conflict-{hash}", base.file_name().and_then(|value| value.to_str()).unwrap_or("member"))),
            None => base,
        })
    }

    fn members(&self, kind: &str) -> Result<Vec<(String, PathBuf)>, String> {
        if self.layout == NativeStorageLayout::Generic {
            let directory = if kind == "state" { self.root.join("states") } else { self.root.clone() };
            let mut relative = Vec::new();
            walk_files(&directory, &directory, &mut relative, kind != "state")?;
            relative.sort();
            return Ok(relative.into_iter().map(|member| {
                let path = directory.join(&member);
                (member, path)
            }).collect());
        }
        if kind != "save" && kind != "state" { return Err("Unsupported native sync artifact kind.".into()); }
        let member_ids = if kind == "save" {
            vec!["battery.srm".to_string()]
        } else {
            std::iter::once("autosave.state".to_string())
                .chain((1..=10).map(|slot| format!("slot{slot}.state")))
                .collect()
        };
        let mut members = Vec::new();
        for member_id in member_ids {
            let path = self.member_path(kind, &member_id)?;
            match fs::symlink_metadata(&path) {
                Ok(metadata) if metadata.file_type().is_file() => members.push((member_id, path)),
                Ok(_) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => return Err(error.to_string()),
            }
        }
        members.sort_by(|left, right| left.0.cmp(&right.0));
        Ok(members)
    }
}

fn mtime_nanos(metadata: &fs::Metadata) -> u64 {
    metadata.modified().ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map(|duration| duration.as_nanos().min(u64::MAX as u128) as u64)
        .unwrap_or(0)
}

fn merged_content_cache(app_dir: &Path, cache: &HashMap<String, ContentIdentity>) -> HashMap<String, ContentIdentity> {
    let mut merged = read_json::<HashMap<String, ContentIdentity>>(&identity_cache_file(app_dir)).unwrap_or_default();
    for (stored, entry) in cache.iter() { merged.insert(stored.clone(), entry.clone()); }
    merged
}

/// SHA-256 of an imported ROM, reused while size + mtime are unchanged so a
/// multi-gigabyte file is not re-hashed on every Sync operation.
fn cached_sha256_file(app_dir: &Path, path: &Path) -> Result<String, String> {
    let metadata = fs::metadata(path).map_err(|error| error.to_string())?;
    let size = metadata.len();
    let mtime = mtime_nanos(&metadata);
    let key = path.to_string_lossy().to_string();
    if let Ok(cache) = content_cache().lock() {
        if let Some(entry) = cache.get(&key) {
            if entry.size == size && entry.mtime == mtime { return Ok(entry.sha256.clone()); }
        }
    }
    let sha256 = sha256_file(path)?;
    if let Ok(mut cache) = content_cache().lock() {
        let mut merged = merged_content_cache(app_dir, &cache);
        merged.insert(key, ContentIdentity { size, mtime, sha256: sha256.clone() });
        *cache = merged.clone();
        let _ = write_json(&identity_cache_file(app_dir), &merged);
    }
    Ok(sha256)
}

/// Record an already-computed hash (for example from ROM import) so the first
/// Sync operation reuses it instead of hashing the whole file again.
pub fn prime_content_hash(app_dir: &Path, path: &Path, sha256: &str) {
    if sha256.len() != 64 || !sha256.bytes().all(|byte| byte.is_ascii_hexdigit()) { return; }
    let Ok(metadata) = fs::metadata(path) else { return; };
    let entry = ContentIdentity { size: metadata.len(), mtime: mtime_nanos(&metadata), sha256: sha256.to_ascii_lowercase() };
    if let Ok(mut cache) = content_cache().lock() {
        let mut merged = merged_content_cache(app_dir, &cache);
        merged.insert(path.to_string_lossy().to_string(), entry);
        *cache = merged.clone();
        let _ = write_json(&identity_cache_file(app_dir), &merged);
    }
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

fn valid_library_extension(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 10
        && value.bytes().all(|byte| byte.is_ascii_alphanumeric())
        && crate::native_system_from_extension(value).is_some()
}

fn library_filename(rom_id: &str, extension: &str) -> Result<String, String> {
    crate::validate_rom_id(rom_id)?;
    if !valid_library_extension(extension) { return Err("Unsupported native library ROM extension.".into()); }
    Ok(format!("{rom_id}.{}", extension.to_ascii_lowercase()))
}

fn library_path(app_dir: &Path, rom_id: &str, extension: &str) -> Result<PathBuf, String> {
    let filename = library_filename(rom_id, extension)?;
    Ok(app_dir.join("an3-roms").join(filename))
}

fn canonical_library_hash(items: &[CanonicalLibraryItem]) -> Result<String, String> {
    let bytes = serde_json::to_vec(items).map_err(|error| error.to_string())?;
    Ok(sha256_bytes(&bytes))
}

fn native_library_manifest(app_dir: &Path, device_id: &str) -> Result<serde_json::Value, String> {
    if !safe_id(device_id) { return Err("Invalid native library device identity.".into()); }
    let directory = app_dir.join("an3-roms");
    let mut entries = Vec::new();
    if directory.exists() {
        for entry in fs::read_dir(&directory).map_err(|error| error.to_string())?.flatten() {
            if !entry.file_type().map_err(|error| error.to_string())?.is_file() { continue; }
            let filename = entry.file_name().to_string_lossy().to_string();
            let Some((rom_id, extension)) = filename.split_once('.') else { continue };
            if filename != library_filename(rom_id, extension).unwrap_or_default() { continue; }
            let path = entry.path();
            let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
            if metadata.len() == 0 { continue; }
            if metadata.len() > MAX_LIBRARY_FILE_BYTES { return Err("A native library ROM exceeds the direct-sync size limit.".into()); }
            let system = crate::native_system_from_extension(extension).ok_or("Unsupported native library ROM extension.")?;
            let content_hash = cached_sha256_file(app_dir, &path)?;
            entries.push((
                CanonicalLibraryItem {
                    rom_id: rom_id.to_string(),
                    extension: extension.to_ascii_lowercase(),
                    system: system.to_string(),
                    size: metadata.len(),
                    content_hash: content_hash.clone(),
                },
                serde_json::json!({
                    "key": format!("rom:{rom_id}"),
                    "romId": rom_id,
                    "extension": extension.to_ascii_lowercase(),
                    "system": system,
                    "name": filename,
                    "path": format!("/data/roms/{filename}"),
                    "size": metadata.len(),
                    "contentHash": content_hash,
                    "deviceId": device_id,
                }),
            ));
        }
    }
    if entries.len() > MAX_LIBRARY_ITEMS { return Err("The native library manifest is too large.".into()); }
    entries.sort_by(|left, right| left.0.rom_id.cmp(&right.0.rom_id).then(left.0.extension.cmp(&right.0.extension)));
    let canonical: Vec<CanonicalLibraryItem> = entries.iter().map(|entry| CanonicalLibraryItem {
        rom_id: entry.0.rom_id.clone(),
        extension: entry.0.extension.clone(),
        system: entry.0.system.clone(),
        size: entry.0.size,
        content_hash: entry.0.content_hash.clone(),
    }).collect();
    let total_size = canonical.iter().map(|item| item.size).sum::<u64>();
    let manifest_hash = canonical_library_hash(&canonical)?;
    Ok(serde_json::json!({
        "version": 1,
        "deviceId": device_id,
        "items": entries.into_iter().map(|entry| entry.1).collect::<Vec<_>>(),
        "totalSize": total_size,
        "manifestHash": manifest_hash,
    }))
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

fn find_native_game(app_dir: &Path, context: &NativeContext, requested_rom_id: Option<&str>) -> Result<(String, PathBuf, NativeGameStorage), String> {
    let layout = current_native_storage_layout();
    let expected = context.rom_hash.clone();
    if let Some(rom_id) = requested_rom_id {
        if let Some(path) = native_rom_path(app_dir, rom_id).filter(|path| native_extension_matches(&context.system, path)) {
            if cached_sha256_file(app_dir, &path)? == expected {
                let storage = NativeGameStorage::for_layout(app_dir, &context.system, rom_id, &path, layout)?;
                return Ok((rom_id.to_string(), path, storage));
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
        if cached_sha256_file(app_dir, &path)? == expected {
            let storage = NativeGameStorage::for_layout(app_dir, &context.system, rom_id, &path, layout)?;
            return Ok((rom_id.to_string(), path, storage));
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

fn native_manifest(runtime: &Runtime, payload: &serde_json::Value, _peer_id: &str) -> Result<serde_json::Value, String> {
    let context = native_context(payload)?;
    let Some((rom_id, _rom_path, storage)) = find_native_game(&runtime.app_dir, &context, context.rom_id.as_deref()).ok() else {
        return Ok(serde_json::json!({"items": [], "sets": []}));
    };
    if context.kind == "save" {
        let files = storage.members("save")?;
        if files.len() > MAX_NATIVE_MEMBERS { return Err("The native save set contains too many members.".into()); }
        let set_id = native_set_id(&context);
        let mut members = Vec::new();
        let mut total_size = 0_u64;
        for (member_id, path) in files {
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
    let files = storage.members("state")?;
    if files.len() > MAX_NATIVE_MEMBERS { return Err("The native state collection contains too many members.".into()); }
    let prefix = format!("state:{}:{}:{}:", context.core, context.game_id, context.rom_hash);
    let mut items = Vec::new();
    let mut total_size = 0_u64;
    for (member_id, path) in files {
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

struct LibraryTransferSpec {
    rom_id: String,
    extension: String,
    size: u64,
    content_hash: String,
    offset: u64,
}

fn library_transfer_spec(payload: &serde_json::Value) -> Result<LibraryTransferSpec, String> {
    let rom_id = payload.get("romId").and_then(|value| value.as_str()).unwrap_or("");
    let extension = payload.get("extension").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
    let size = payload.get("size").and_then(|value| value.as_u64()).ok_or("The library transfer is missing its size.")?;
    let content_hash = payload.get("contentHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
    let offset = payload.get("offset").and_then(|value| value.as_u64()).unwrap_or(0);
    crate::validate_rom_id(rom_id)?;
    if !valid_library_extension(&extension) { return Err("Unsupported native library ROM extension.".into()); }
    if size == 0 || size > MAX_LIBRARY_FILE_BYTES { return Err("The native library ROM size is unsafe.".into()); }
    if content_hash.len() != 64 || !content_hash.bytes().all(|byte| byte.is_ascii_hexdigit()) { return Err("The library transfer hash is invalid.".into()); }
    if offset > size { return Err("The library transfer offset is out of range.".into()); }
    Ok(LibraryTransferSpec { rom_id: rom_id.to_string(), extension, size, content_hash, offset })
}

fn library_transfer_paths(app_dir: &Path, spec: &LibraryTransferSpec) -> Result<(PathBuf, PathBuf, PathBuf), String> {
    let filename = library_filename(&spec.rom_id, &spec.extension)?;
    let directory = app_dir.join("an3-roms");
    Ok((
        directory.join(&filename),
        directory.join(format!(".{filename}.an3-library.part")),
        directory.join(format!(".{filename}.an3-library.meta")),
    ))
}

fn checked_library_source(app_dir: &Path, spec: &LibraryTransferSpec) -> Result<PathBuf, String> {
    let path = library_path(app_dir, &spec.rom_id, &spec.extension)?;
    let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
    if !metadata.is_file() || metadata.len() != spec.size { return Err("The native library ROM changed during sync.".into()); }
    if cached_sha256_file(app_dir, &path)? != spec.content_hash { return Err("The native library ROM hash changed during sync.".into()); }
    Ok(path)
}

fn native_library_blob(app_dir: &Path, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let spec = library_transfer_spec(payload)?;
    let path = checked_library_source(app_dir, &spec)?;
    let length = payload.get("length").and_then(|value| value.as_u64()).unwrap_or(LIBRARY_CHUNK_BYTES as u64);
    if length == 0 || length > LIBRARY_CHUNK_BYTES as u64 || spec.offset.saturating_add(length) > spec.size {
        return Err("The library transfer chunk is invalid.".into());
    }
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    file.seek(SeekFrom::Start(spec.offset)).map_err(|error| error.to_string())?;
    let mut bytes = vec![0_u8; length as usize];
    file.read_exact(&mut bytes).map_err(|error| error.to_string())?;
    Ok(serde_json::json!({
        "romId": spec.rom_id,
        "extension": spec.extension,
        "offset": spec.offset,
        "size": spec.size,
        "contentHash": spec.content_hash,
        "data": B64.encode(bytes),
    }))
}

#[derive(Serialize, Deserialize)]
struct LibraryUploadMeta {
    version: u8,
    rom_id: String,
    extension: String,
    size: u64,
    content_hash: String,
    next_offset: u64,
}

fn write_library_meta(path: &Path, meta: &LibraryUploadMeta) -> Result<(), String> {
    let temporary = path.with_extension("tmp");
    let bytes = serde_json::to_vec(meta).map_err(|error| error.to_string())?;
    let mut output = File::create(&temporary).map_err(|error| error.to_string())?;
    output.write_all(&bytes).map_err(|error| error.to_string())?;
    output.sync_all().map_err(|error| error.to_string())?;
    drop(output);
    fs::rename(temporary, path).map_err(|error| error.to_string())
}

fn read_library_meta(path: &Path) -> Option<LibraryUploadMeta> { read_json(path) }

fn library_final_state(app_dir: &Path, spec: &LibraryTransferSpec, final_path: &Path) -> Result<Option<bool>, String> {
    if !final_path.exists() { return Ok(None); }
    let metadata = fs::metadata(final_path).map_err(|error| error.to_string())?;
    if !metadata.is_file() || metadata.len() != spec.size { return Err("A different ROM already uses this library identity.".into()); }
    let actual = cached_sha256_file(app_dir, final_path)?;
    if actual != spec.content_hash { return Err("A different ROM already uses this library identity.".into()); }
    Ok(Some(true))
}

fn native_library_upload_status(app_dir: &Path, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let spec = library_transfer_spec(payload)?;
    let (final_path, part_path, meta_path) = library_transfer_paths(app_dir, &spec)?;
    if library_final_state(app_dir, &spec, &final_path)?.is_some() {
        return Ok(serde_json::json!({"complete": true, "nextOffset": spec.size}));
    }
    let next_offset = read_library_meta(&meta_path)
        .filter(|meta| meta.version == 1 && meta.rom_id == spec.rom_id && meta.extension == spec.extension && meta.size == spec.size && meta.content_hash == spec.content_hash && part_path.exists())
        .map(|meta| meta.next_offset)
        .unwrap_or(0);
    Ok(serde_json::json!({"complete": false, "nextOffset": next_offset}))
}

fn native_library_write_chunk(app_dir: &Path, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let spec = library_transfer_spec(payload)?;
    let data = payload.get("data").and_then(|value| value.as_str()).ok_or("The library transfer chunk has no data.")?;
    let bytes = B64.decode(data).map_err(|_| "The library transfer chunk is not valid base64.")?;
    if bytes.is_empty() || bytes.len() > LIBRARY_CHUNK_BYTES || spec.offset.saturating_add(bytes.len() as u64) > spec.size {
        return Err("The library transfer chunk is invalid.".into());
    }
    let (final_path, part_path, meta_path) = library_transfer_paths(app_dir, &spec)?;
    if library_final_state(app_dir, &spec, &final_path)?.is_some() {
        return Ok(serde_json::json!({"complete": true, "nextOffset": spec.size}));
    }
    if let Some(existing) = read_library_meta(&meta_path) {
        if existing.version != 1 || existing.rom_id != spec.rom_id || existing.extension != spec.extension || existing.size != spec.size || existing.content_hash != spec.content_hash {
            if spec.offset != 0 { return Err("The resumable library transfer metadata does not match.".into()); }
        }
    }
    let mut next_offset = read_library_meta(&meta_path)
        .filter(|meta| meta.version == 1 && meta.rom_id == spec.rom_id && meta.extension == spec.extension && meta.size == spec.size && meta.content_hash == spec.content_hash && part_path.exists())
        .map(|meta| meta.next_offset)
        .unwrap_or(0);
    if spec.offset > next_offset { return Err("The library transfer has a missing chunk.".into()); }
    fs::create_dir_all(app_dir.join("an3-roms")).map_err(|error| error.to_string())?;
    let mut file = OpenOptions::new().create(true).read(true).write(true).open(&part_path).map_err(|error| error.to_string())?;
    if next_offset == 0 && spec.offset == 0 { file.set_len(spec.size).map_err(|error| error.to_string())?; }
    file.seek(SeekFrom::Start(spec.offset)).map_err(|error| error.to_string())?;
    file.write_all(&bytes).map_err(|error| error.to_string())?;
    file.sync_all().map_err(|error| error.to_string())?;
    next_offset = next_offset.max(spec.offset.saturating_add(bytes.len() as u64));
    write_library_meta(&meta_path, &LibraryUploadMeta { version: 1, rom_id: spec.rom_id.clone(), extension: spec.extension.clone(), size: spec.size, content_hash: spec.content_hash.clone(), next_offset })?;
    if next_offset < spec.size { return Ok(serde_json::json!({"complete": false, "nextOffset": next_offset})); }
    if sha256_file(&part_path)? != spec.content_hash || fs::metadata(&part_path).map_err(|error| error.to_string())?.len() != spec.size {
        return Err("The finalized library ROM failed SHA-256 verification.".into());
    }
    if let Some(existing) = library_final_state(app_dir, &spec, &final_path)? {
        if existing { let _ = fs::remove_file(&part_path); let _ = fs::remove_file(&meta_path); return Ok(serde_json::json!({"complete": true, "nextOffset": spec.size})); }
    }
    fs::rename(&part_path, &final_path).map_err(|error| error.to_string())?;
    let _ = fs::remove_file(&meta_path);
    prime_content_hash(app_dir, &final_path, &spec.content_hash);
    Ok(serde_json::json!({"complete": true, "nextOffset": spec.size}))
}

fn native_blob(runtime: &Runtime, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let context = native_context(payload)?;
    let (_rom_id, _rom_path, storage) = find_native_game(&runtime.app_dir, &context, context.rom_id.as_deref())?;
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
    let path = storage.member_path(&context.kind, relative)?;
    let bytes = native_member_bytes(&path)?;
    let expected_size = item.get("size").and_then(|value| value.as_u64()).ok_or("The sync blob request is missing its size.")?;
    let expected_hash = item.get("contentHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
    if expected_size != bytes.len() as u64 || expected_hash != sha256_bytes(&bytes) { return Err("Native sync blob verification failed.".into()); }
    Ok(serde_json::json!({"data": B64.encode(bytes), "size": expected_size, "contentHash": expected_hash}))
}

fn write_native_members(storage: &NativeGameStorage, kind: &str, files: Vec<(String, Vec<u8>)>) -> Result<(), String> {
    if files.is_empty() || files.len() > MAX_NATIVE_MEMBERS { return Err("The sync operation contains no valid members.".into()); }
    if kind != "save" && kind != "state" { return Err("Unsupported native sync artifact kind.".into()); }
    let mut total = 0_u64;
    let mut prepared = Vec::new();
    let mut seen = HashSet::new();
    for (member_id, bytes) in files {
        if !valid_member_path(&member_id) || !seen.insert(member_id.clone()) || bytes.is_empty() || bytes.len() as u64 > MAX_NATIVE_MEMBER_BYTES {
            return Err("The native sync member list is invalid.".into());
        }
        total = total.saturating_add(bytes.len() as u64);
        if total > MAX_NATIVE_SET_BYTES { return Err("The native sync payload is too large.".into()); }
        let target = storage.member_path(kind, &member_id)?;
        let previous = match fs::symlink_metadata(&target) {
            Ok(metadata) if metadata.file_type().is_file() => Some(fs::read(&target).map_err(|error| error.to_string())?),
            Ok(_) => return Err("Native sync destination is not a regular file.".into()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
            Err(error) => return Err(error.to_string()),
        };
        if member_id.contains(".an3-conflict-") && previous.as_deref().is_some_and(|old| old != bytes.as_slice()) {
            return Err("An existing conflict copy differs; it was preserved without overwrite.".into());
        }
        prepared.push((target, bytes, previous));
    }
    fs::create_dir_all(&storage.root).map_err(|error| error.to_string())?;
    let mut snapshots = Vec::new();
    let mut temporary = Vec::new();
    for (target, bytes, previous) in &prepared {
        if let Some(parent) = target.parent() { fs::create_dir_all(parent).map_err(|error| error.to_string())?; }
        let name = target.file_name().and_then(|value| value.to_str()).unwrap_or("member");
        let part = target.with_file_name(format!(".{name}.an3-sync-{}.part", hex(&random_bytes::<8>())));
        let mut output = File::create(&part).map_err(|error| error.to_string())?;
        output.write_all(bytes).map_err(|error| error.to_string())?;
        output.sync_all().map_err(|error| error.to_string())?;
        snapshots.push((target.clone(), previous.clone()));
        temporary.push(part);
    }
    for (index, (target, _, _)) in prepared.iter().enumerate() {
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

fn validate_publish_set(runtime: &Runtime, payload: &serde_json::Value, context: &NativeContext) -> Result<(Vec<(String, Vec<u8>)>, String), String> {
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
    for item in items {
        let key = item.get("key").and_then(|value| value.as_str()).unwrap_or("").to_string();
        if by_key.insert(key.clone(), item).is_some() { return Err("The save-set publish contains a duplicate member.".into()); }
    }
    let mut files = Vec::new();
    for member in &canonical {
        let key = format!("{set_id}:{}", member.member_id);
        let item = by_key.remove(&key).ok_or("The save-set publish is missing a member.")?;
        let data = item.get("data").and_then(|value| value.as_str()).ok_or("The save-set member has no data.")?;
        let bytes = B64.decode(data).map_err(|_| "The save-set member data is not valid base64.")?;
        if bytes.len() as u64 != member.size || sha256_bytes(&bytes) != member.content_hash { return Err("The save-set member failed size or SHA-256 validation.".into()); }
        files.push((if set_id.ends_with(".conflict") { format!("{}.an3-conflict-{}", member.member_id, &manifest_hash[..16]) } else { member.member_id.clone() }, bytes));
    }
    if !by_key.is_empty() { return Err("The save-set publish contains unexpected members.".into()); }
    let _ = runtime;
    Ok((files, manifest_hash))
}

fn validate_publish_state(payload: &serde_json::Value, context: &NativeContext) -> Result<Vec<(String, Vec<u8>)>, String> {
    let items = payload.get("items").and_then(|value| value.as_array()).ok_or("The save-state publish is missing member data.")?;
    if items.is_empty() || items.len() > MAX_NATIVE_MEMBERS { return Err("The save-state member list is invalid.".into()); }
    let prefix = format!("state:{}:{}:{}:", context.core, context.game_id, context.rom_hash);
    let mut seen = HashSet::new();
    let mut files = Vec::new();
    let mut total = 0_u64;
    for item in items {
        let key = item.get("key").and_then(|value| value.as_str()).unwrap_or("");
        let path = item.get("path").and_then(|value| value.as_str()).unwrap_or("");
        let member_id = path.strip_prefix("/data/states/").ok_or("Invalid native save-state path.")?;
        let size = item.get("size").and_then(|value| value.as_u64()).unwrap_or(0);
        let hash = item.get("contentHash").and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
        if !key.starts_with(&prefix) || !valid_state_key(key) || !valid_member_path(member_id) || !seen.insert(member_id.to_string()) || size == 0 || size > MAX_NATIVE_MEMBER_BYTES || hash.len() != 64 || !hash.chars().all(|ch| ch.is_ascii_hexdigit()) {
            return Err("The save-state member manifest is invalid.".into());
        }
        let data = item.get("data").and_then(|value| value.as_str()).ok_or("The save-state member has no data.")?;
        let bytes = B64.decode(data).map_err(|_| "The save-state member data is not valid base64.")?;
        if bytes.len() as u64 != size || sha256_bytes(&bytes) != hash { return Err("The save-state member failed size or SHA-256 validation.".into()); }
        total = total.saturating_add(size);
        if total > MAX_NATIVE_SET_BYTES { return Err("The save-state payload is too large.".into()); }
        files.push((member_id.to_string(), bytes));
    }
    Ok(files)
}

fn native_publish(runtime: &Runtime, payload: &serde_json::Value) -> Result<serde_json::Value, String> {
    let context = native_context(payload)?;
    let (_rom_id, _rom_path, storage) = find_native_game(&runtime.app_dir, &context, context.rom_id.as_deref())?;
    if context.kind == "save" {
        let (files, manifest_hash) = validate_publish_set(runtime, payload, &context)?;
        let count = files.len();
        write_native_members(&storage, "save", files)?;
        return Ok(serde_json::json!({"ok": true, "accepted": count, "manifestHash": manifest_hash}));
    }
    let files = validate_publish_state(payload, &context)?;
    let count = files.len();
    write_native_members(&storage, "state", files)?;
    Ok(serde_json::json!({"ok": true, "accepted": count}))
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

pub fn library_manifest(app_dir: &Path) -> Result<serde_json::Value, String> {
    let identity = load_identity(app_dir)?;
    native_library_manifest(app_dir, &identity.device_id)
}

pub fn library_read_chunk(app_dir: &Path, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    native_library_blob(app_dir, &payload)
}

pub fn library_upload_status(app_dir: &Path, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    native_library_upload_status(app_dir, &payload)
}

pub fn library_write_chunk(app_dir: &Path, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    native_library_write_chunk(app_dir, &payload)
}

pub fn game_identity(app_dir: &Path, system: String, rom_id: String) -> Result<serde_json::Value, String> {
    let core = core_for_system(&system).ok_or("Unsupported native sync system.")?;
    if !crate::validate_rom_id(&rom_id).is_ok() { return Err("Invalid native ROM identity.".into()); }
    let path = native_rom_path(app_dir, &rom_id).filter(|value| native_extension_matches(&system, value)).ok_or("The native ROM is not available.")?;
    let rom_hash = cached_sha256_file(app_dir, &path)?;
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
    let (_rom_id, _rom_path, storage) = find_native_game(app_dir, &context, context.rom_id.as_deref())?;
    let mut records = Vec::new();
    if context.kind == "save" {
        let manifest = native_manifest(&Runtime {
            app_dir: app_dir.to_path_buf(),
            identity: load_identity(app_dir)?,
            bind_port: SYNC_PORT,
            discovery_enabled: false,
            bound_port: AtomicU16::new(0),
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
            connecting: AtomicBool::new(false),
        }, &payload, "")?;
        if let Some(set) = manifest.get("sets").and_then(|value| value.as_array()).and_then(|sets| sets.first()) {
            if let Some(members) = set.get("members").and_then(|value| value.as_array()) {
                for member in members {
                    let member_id = member.get("memberId").and_then(|value| value.as_str()).unwrap_or("");
                    let bytes = native_member_bytes(&storage.member_path("save", member_id)?)?;
                    records.push(serde_json::json!({"id": member.get("key"), "key": member.get("key"), "path": member.get("path"), "bytes": B64.encode(bytes), "updatedAt": now_seconds()}));
                }
            }
        }
    } else {
        for (member_id, path) in storage.members("state")? {
            let bytes = native_member_bytes(&path)?;
            records.push(serde_json::json!({"id": format!("state:{}:{}:{}:{}", context.core, context.game_id, context.rom_hash, member_id), "path": format!("/data/states/{member_id}"), "state": B64.encode(bytes), "updatedAt": now_seconds()}));
        }
    }
    Ok(serde_json::json!({"records": records}))
}

pub fn storage_write(app_dir: &Path, payload: serde_json::Value) -> Result<(), String> {
    if let Some(records) = payload.get("records").and_then(|value| value.as_array()) {
        let context = native_context(&payload)?;
        let (_rom_id, _rom_path, storage) = find_native_game(app_dir, &context, context.rom_id.as_deref())?;
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
        return write_native_members(&storage, &context.kind, files);
    }
    let runtime = Runtime {
        app_dir: app_dir.to_path_buf(),
        identity: load_identity(app_dir)?,
        bind_port: SYNC_PORT,
        discovery_enabled: false,
        bound_port: AtomicU16::new(0),
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
        connecting: AtomicBool::new(false),
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
        runtime.connecting.store(false, Ordering::Relaxed);
        let port = runtime.bound_port.load(Ordering::Acquire);
        if port != 0 {
            if let Ok(socket) = TcpStream::connect(("127.0.0.1", port)) { let _ = socket.shutdown(Shutdown::Both); }
        }
        if let Ok(socket) = UdpSocket::bind("127.0.0.1:0") { let _ = socket.send_to(b"stop", (DISCOVERY_ADDRESS, DISCOVERY_PORT)); }
        if let Ok(mut handles) = runtime.handles.lock() { for handle in handles.drain(..) { let _ = handle.join(); } }
    }
    if let Ok(mut current) = client().lock() { if let Some(session) = current.take() { let _ = session.stream.shutdown(Shutdown::Both); } }
}

pub fn stop() { if let Ok(mut slot) = runtime().lock() { stop_runtime_locked(&mut slot); } }

pub fn start(app_dir: PathBuf, mode: String) -> Result<SyncStatus, String> {
    start_with_listener(app_dir, mode, SYNC_PORT, true)
}

fn start_with_listener(app_dir: PathBuf, mode: String, bind_port: u16, discovery_enabled: bool) -> Result<SyncStatus, String> {
    if !mode_valid(&mode) { return Err("Sync mode must be guest or account.".into()); }
    let mut slot = runtime().lock().map_err(|_| "Sync peer lock unavailable".to_string())?;
    if let Some(existing) = slot.as_ref() {
        if existing.bind_port != bind_port || existing.discovery_enabled != discovery_enabled {
            return Err("Sync runtime is already running with a different listener configuration.".into());
        }
        if let Ok(mut current) = existing.mode.lock() { *current = mode; }
        // `start` is called by the installed shell on every foreground load.
        // Do not call `status()` while holding the global runtime lock: that
        // re-enters this mutex and used to leave the Android UI waiting
        // forever when Start Hosting was pressed after init().  Refresh the
        // short-lived host code as part of an explicit start/restart request,
        // then release the lock before taking a status snapshot.
        if let Ok(mut code) = existing.code.lock() { *code = new_code(); }
        if let Ok(mut expiry) = existing.code_expiry.lock() { *expiry = Instant::now() + PAIRING_TTL; }
        if let Ok(mut error) = existing.error.lock() { error.clear(); }
        drop(slot);
        return Ok(status());
    }
    fs::create_dir_all(&app_dir).map_err(|error| format!("Could not prepare sync storage: {error}"))?;
    let identity = load_identity(&app_dir)?;
    let peers = load_peers(&app_dir);
    let runtime = Arc::new(Runtime {
        app_dir,
        identity,
        bind_port,
        discovery_enabled,
        bound_port: AtomicU16::new(0),
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
        connecting: AtomicBool::new(false),
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

#[cfg(test)]
fn start_for_test(app_dir: PathBuf, mode: String) -> Result<(SyncStatus, u16), String> {
    let status = start_with_listener(app_dir, mode, 0, false)?;
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let active = runtime().lock().map_err(|_| "Sync peer lock unavailable".to_string())?
            .as_ref().cloned().ok_or_else(|| "Sync test runtime stopped before binding.".to_string())?;
        let port = active.bound_port.load(Ordering::Acquire);
        if port != 0 { return Ok((status, port)); }
        if let Ok(error) = active.error.lock() {
            if !error.is_empty() { return Err(error.clone()); }
        }
        if Instant::now() >= deadline { return Err("Sync test listener did not bind an ephemeral port.".into()); }
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn discovery_loop(runtime: Arc<Runtime>) {
    if !runtime.discovery_enabled { return; }
    let local = local_lan_ipv4().unwrap_or(Ipv4Addr::UNSPECIFIED);
    let Ok(socket) = UdpSocket::bind((local, 0)) else { return };
    let _ = socket.set_multicast_loop_v4(true);
    let _ = socket.set_broadcast(true);
    while !runtime.stop.load(Ordering::Relaxed) {
        let payload = serde_json::to_vec(&advertisement_with_capabilities(&runtime.identity.device_id, &default_name(), runtime.bind_port, &["sync"])).unwrap_or_default();
        let _ = socket.send_to(&payload, (DISCOVERY_ADDRESS, DISCOVERY_PORT));
        let _ = socket.send_to(&payload, (DISCOVERY_BROADCAST, DISCOVERY_PORT));
        for _ in 0..20 { if runtime.stop.load(Ordering::Relaxed) { break; } std::thread::sleep(Duration::from_millis(100)); }
    }
}

fn listener_loop(runtime: Arc<Runtime>) {
    let address = if runtime.discovery_enabled { Ipv4Addr::UNSPECIFIED } else { Ipv4Addr::LOCALHOST };
    let Ok(listener) = TcpListener::bind((address, runtime.bind_port)) else { set_error(&runtime, format!("Sync port {} is unavailable", runtime.bind_port)); return };
    let Ok(bound_port) = listener.local_addr().map(|address| address.port()) else { set_error(&runtime, "Could not inspect the Sync listener port"); return };
    runtime.bound_port.store(bound_port, Ordering::Release);
    let _ = listener.set_nonblocking(true);
    while !runtime.stop.load(Ordering::Relaxed) {
        match listener.accept() {
            Ok((mut stream, peer)) => {
                // Accepted sockets can inherit the listener's non-blocking
                // mode on Unix. The bounded handshake reader is blocking;
                // restore that mode before handing the socket to the worker.
                let _ = stream.set_nonblocking(false);
                let runtime = runtime.clone();
                std::thread::spawn(move || handle_client(&runtime, &mut stream, peer));
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => std::thread::sleep(Duration::from_millis(50)),
            Err(_) => std::thread::sleep(Duration::from_millis(100)),
        }
    }
}

fn discover(target: Option<&str>, local_id: &str) -> Result<(SocketAddr, String, String), String> {
    let socket = discovery_socket(DISCOVERY_PORT).map_err(|error| format!("Direct LAN discovery is unavailable: {error}"))?;
    let group = DISCOVERY_ADDRESS.parse::<Ipv4Addr>().map_err(|_| "Invalid AN3 discovery group.")?;
    let interface = local_lan_ipv4().unwrap_or(Ipv4Addr::UNSPECIFIED);
    socket.join_multicast_v4(&group, &interface).map_err(|error| format!("Could not join AN3 LAN discovery: {error}"))?;
    let _ = socket.set_read_timeout(Some(Duration::from_millis(250)));
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut payload = [0u8; 4096];
    while Instant::now() < deadline {
        match socket.recv_from(&mut payload) {
            Ok((length, source)) => {
                let Ok(value) = serde_json::from_slice::<serde_json::Value>(&payload[..length]) else { continue };
                let Ok(peer) = parse_advertisement(&value) else { continue };
                if peer.id == local_id || !peer.capabilities.iter().any(|capability| capability == "sync") || target.is_some_and(|wanted| wanted != peer.id) { continue; }
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
    // Pairing/authentication is bounded, but an established sync session may
    // legitimately be idle while the user is in a menu.  Keep the UI and
    // remembered peer alive until the session is explicitly closed.
    let _ = stream.set_read_timeout(None);
    let _ = stream.set_write_timeout(None);
    // A later successful pairing supersedes a transient error from an earlier
    // discovery/handshake attempt.  Clear it before publishing the connected
    // peer so the UI cannot report Error while an authenticated session is
    // actually active.
    if let Ok(mut error) = runtime.error.lock() { error.clear(); }
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
    while !runtime.stop.load(Ordering::Relaxed) {
        let Ok(body) = read_frame(stream) else { return };
        let Some(value) = open(cipher, DIR_CLIENT_TO_HOST, receive_counter, &body) else { return };
        receive_counter = receive_counter.wrapping_add(1);
        if value.get("k").and_then(|item| item.as_str()) != Some("request") { continue; }
        let id = value.get("id").cloned().unwrap_or(serde_json::Value::Null);
        let method = value.get("method").and_then(|item| item.as_str()).unwrap_or("");
        let payload = value.get("payload").cloned().unwrap_or(serde_json::Value::Null);
        let result = match method {
            "ping" => Ok(serde_json::json!({"ok":true,"peerId":peer_id})),
            "manifest" => native_manifest(runtime, &payload, peer_id),
            "plan" => native_plan(&payload),
            "blob" => native_blob(runtime, &payload),
            "publish" => native_publish(runtime, &payload),
            "library-manifest" => native_library_manifest(&runtime.app_dir, &runtime.identity.device_id),
            "library-blob" => native_library_blob(&runtime.app_dir, &payload),
            "library-upload-status" => native_library_upload_status(&runtime.app_dir, &payload),
            "library-publish-chunk" => native_library_write_chunk(&runtime.app_dir, &payload),
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

fn join_blocking(code: String, mode: String, target: Option<String>, direct_address: Option<SocketAddr>, peer_runtime: Arc<Runtime>) -> Result<SyncStatus, String> {
    if !mode_valid(&mode) { return Err("Sync mode must be guest or account.".into()); }
    let (address, peer_name) = if let Some(address) = direct_address {
        (address, "AN3 direct peer".to_string())
    } else {
        let (address, _peer_id, peer_name) = discover(target.as_deref(), &peer_runtime.identity.device_id)?;
        (address, peer_name)
    };
    let mut stream = TcpStream::connect_timeout(&address, IO_TIMEOUT).map_err(|error| format!("Could not connect to the AN3 sync peer: {error}"))?;
    let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
    let _ = stream.set_write_timeout(Some(IO_TIMEOUT));
    let secret = EphemeralSecret::random(&mut p256::elliptic_curve::rand_core::OsRng);
    let public = secret.public_key().to_encoded_point(false).as_bytes().to_vec();
    let hello = serde_json::json!({"k":"hello","v":PROTOCOL_VERSION,"pub":B64.encode(&public),"id":peer_runtime.identity.device_id,"name":default_name(),"mode":mode});
    write_frame(&mut stream, &serde_json::to_vec(&hello).unwrap_or_default()).map_err(|error| error.to_string())?;
    let response: serde_json::Value = serde_json::from_slice(&read_frame(&mut stream).map_err(|error| error.to_string())?).map_err(|_| "The sync peer returned malformed handshake data.".to_string())?;
    let host_pub_bytes = response.get("pub").and_then(|value| value.as_str()).and_then(|value| B64.decode(value).ok()).ok_or("The sync peer returned an invalid public key.")?;
    let host_pub = PublicKey::from_sec1_bytes(&host_pub_bytes).map_err(|_| "The sync peer returned an invalid public key.")?;
    let host_id = response.get("id").and_then(|value| value.as_str()).filter(|value| safe_id(value)).ok_or("The sync peer returned an invalid identity.")?;
    let host_mode = response.get("mode").and_then(|value| value.as_str()).unwrap_or("guest");
    if host_mode != mode { return Err("Guest and signed-in LAN sync modes cannot be mixed.".into()); }
    let shared = secret.diffie_hellman(&host_pub);
    let transcript = challenge(host_id, &host_pub_bytes, &peer_runtime.identity.device_id, &public);
    let trusted = local_peer(&peer_runtime, host_id);
    let (key, reconnect) = if let Some(record) = trusted.as_ref() {
        let token = B64.decode(&record.token).map_err(|_| "Remembered peer trust is corrupt; re-pair required.")?;
        (derive_key(shared.raw_secret_bytes().as_slice(), &token), true)
    } else if mode == "account" {
        (derive_key(shared.raw_secret_bytes().as_slice(), transcript.as_bytes()), false)
    } else {
        if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) { return Err("Enter exactly six decimal digits.".into()); }
        (derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes()), false)
    };
    let local_secret = peer_runtime.identity.secret.clone();
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
    let current_runtime = runtime().lock().ok().and_then(|slot| slot.clone()).is_some_and(|current| Arc::ptr_eq(&current, &peer_runtime));
    if !current_runtime || peer_runtime.stop.load(Ordering::Relaxed) || !peer_runtime.connecting.load(Ordering::Relaxed) {
        let _ = stream.shutdown(Shutdown::Both);
        return Err("Direct LAN Sync pairing was canceled.".into());
    }
    store_peer(&peer_runtime, record.clone())?;
    // The handshake timeout must not become an idle-session timeout after
    // the peer has authenticated.  Save requests can be separated by long
    // periods while the user plays or remains in a menu.
    let _ = stream.set_read_timeout(None);
    let _ = stream.set_write_timeout(None);
    if let Ok(mut error) = peer_runtime.error.lock() { error.clear(); }
    if let Ok(mut current) = client().lock() { *current = Some(ClientSession { stream, key, send_counter: 1, receive_counter: 1, peer: record, challenge: transcript, account_verified: false, remote_proof: String::new() }); }
    Ok(status())
}

/// Start discovery and pairing in a bounded background worker. The UI observes
/// `SyncStatus.state` instead of waiting for multicast/TCP handshakes.
pub fn join_async(code: String, mode: String, target: Option<String>) -> Result<SyncStatus, String> {
    if !mode_valid(&mode) { return Err("Sync mode must be guest or account.".into()); }
    if mode == "guest" && target.is_none() && (code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit())) {
        return Err("Enter exactly six decimal digits.".into());
    }
    let direct_address = match target.as_deref() {
        Some(value) => parse_debug_direct_target(value)?,
        None => None,
    };
    let discovery_target = if direct_address.is_some() { None } else { target };
    let peer_runtime = runtime().lock().ok().and_then(|slot| slot.clone()).ok_or("Start LAN Sync hosting before joining a peer.")?;
    if peer_runtime.connecting.swap(true, Ordering::Relaxed) {
        return Ok(status());
    }
    if let Ok(mut error) = peer_runtime.error.lock() { error.clear(); }
    drop_client_session();
    let worker_runtime = peer_runtime.clone();
    std::thread::spawn(move || {
        let result = join_blocking(code, mode, discovery_target, direct_address, worker_runtime.clone());
        if runtime().lock().ok().and_then(|slot| slot.clone()).is_some_and(|current| Arc::ptr_eq(&current, &worker_runtime)) {
            if let Err(error) = result { set_error(&worker_runtime, error); }
            worker_runtime.connecting.store(false, Ordering::Relaxed);
        }
    });
    Ok(status())
}

pub fn discover_peers() -> Result<Vec<serde_json::Value>, String> {
    let socket = discovery_socket(DISCOVERY_PORT).map_err(|error| error.to_string())?;
    let group = DISCOVERY_ADDRESS.parse::<Ipv4Addr>().map_err(|_| "Invalid AN3 discovery group.")?;
    let interface = local_lan_ipv4().unwrap_or(Ipv4Addr::UNSPECIFIED);
    socket.join_multicast_v4(&group, &interface).map_err(|error| error.to_string())?;
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
    drop(runtime);
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
    let Some(runtime) = runtime().lock().ok().and_then(|slot| slot.clone()) else { return SyncStatus { running:false, role:"off".into(), mode:"guest".into(), state:"idle".into(), device_id:String::new(), code:String::new(), code_expires_in_seconds:0, peers:Vec::new(), error:String::new() }; };
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
    let error = runtime.error.lock().ok().map(|value| value.clone()).unwrap_or_default();
    SyncStatus { running:true, role: if client_peer.is_some() { "peer".into() } else { "host".into() }, mode, state: if runtime.connecting.load(Ordering::Relaxed) { "connecting".into() } else if !error.is_empty() { "error".into() } else { "ready".into() }, device_id:runtime.identity.device_id.clone(), code, code_expires_in_seconds:expires, peers, error }
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
    drop(runtime);
    Ok(status())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The native host runtime is a process-global singleton, so tests that
    /// start it must not run concurrently.
    static SERIAL: Mutex<()> = Mutex::new(());

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

    #[cfg(debug_assertions)]
    #[test]
    fn debug_direct_target_accepts_private_endpoints_only() {
        assert_eq!(
            parse_debug_direct_target("direct:10.0.2.2:47833").unwrap(),
            Some(SocketAddr::from(([10, 0, 2, 2], 47833))),
        );
        assert!(parse_debug_direct_target("direct:8.8.8.8:47833").is_err());
        assert!(parse_debug_direct_target("direct:10.0.2.2:0").is_err());
        assert_eq!(parse_debug_direct_target("an3-peer-1234").unwrap(), None);
    }

    #[test]
    fn android_runtime_id_matches_the_native_host_filename_contract() {
        let path = Path::new("/data/user/0/space.an3tocom.offline/an3-roms/11111111-1111-1111-1111-111111111111.gba");
        assert_eq!(
            android_core_rom_id(path).unwrap(),
            "11111111-1111-1111-1111-111111111111-b39f48cd5ae8ebe5",
        );
    }

    #[test]
    fn mac_and_android_storage_share_game_scoped_logical_members() {
        let root = std::env::temp_dir().join(format!("an3-sync-layout-{}-{:?}", std::process::id(), Instant::now()));
        let rom_id = "11111111-1111-1111-1111-111111111111";
        let rom_path = root.join("an3-roms").join(format!("{rom_id}.gba"));
        std::fs::create_dir_all(rom_path.parent().unwrap()).unwrap();
        std::fs::write(&rom_path, b"fixture ROM").unwrap();
        let mac = NativeGameStorage::for_layout(&root, "gba", rom_id, &rom_path, NativeStorageLayout::Mac).unwrap();
        let android = NativeGameStorage::for_layout(&root, "gba", rom_id, &rom_path, NativeStorageLayout::Android).unwrap();

        let mac_save = mac.member_path("save", "battery.srm").unwrap();
        let android_save = android.member_path("save", "battery.srm").unwrap();
        assert_ne!(mac_save, android_save, "each runtime keeps its established physical path");
        assert_eq!(mac_save.file_name().unwrap().to_str().unwrap(), format!("{rom_id}.srm"));
        assert_eq!(android_save.file_name().unwrap().to_str().unwrap(), format!("{}.srm", android.runtime_rom_id));
        std::fs::create_dir_all(mac_save.parent().unwrap()).unwrap();
        std::fs::create_dir_all(android_save.parent().unwrap()).unwrap();
        std::fs::write(&mac_save, b"same battery bytes").unwrap();
        std::fs::write(&android_save, b"same battery bytes").unwrap();

        let mac_slot = mac.member_path("state", "slot1.state").unwrap();
        let android_slot = android.member_path("state", "slot1.state").unwrap();
        std::fs::create_dir_all(mac_slot.parent().unwrap()).unwrap();
        std::fs::create_dir_all(android_slot.parent().unwrap()).unwrap();
        std::fs::write(&mac_slot, b"same state bytes").unwrap();
        std::fs::write(&android_slot, b"same state bytes").unwrap();
        let another_game = mac.root.join(format!("22222222-2222-2222-2222-222222222222.srm"));
        std::fs::write(&another_game, b"unrelated game save").unwrap();

        let mac_save_members = mac.members("save").unwrap();
        let android_save_members = android.members("save").unwrap();
        assert_eq!(mac_save_members.iter().map(|(id, _)| id.as_str()).collect::<Vec<_>>(), ["battery.srm"]);
        assert_eq!(android_save_members.iter().map(|(id, _)| id.as_str()).collect::<Vec<_>>(), ["battery.srm"]);
        let mac_state_members = mac.members("state").unwrap();
        let android_state_members = android.members("state").unwrap();
        assert_eq!(mac_state_members.iter().map(|(id, _)| id.as_str()).collect::<Vec<_>>(), ["slot1.state"]);
        assert_eq!(android_state_members.iter().map(|(id, _)| id.as_str()).collect::<Vec<_>>(), ["slot1.state"]);

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn existing_keep_both_conflict_copy_is_never_overwritten() {
        let root = std::env::temp_dir().join(format!("an3-sync-copy-{}-{:?}", std::process::id(), Instant::now()));
        let rom_id = "11111111-1111-1111-1111-111111111111";
        let rom_path = root.join("an3-roms").join(format!("{rom_id}.gba"));
        std::fs::create_dir_all(rom_path.parent().unwrap()).unwrap();
        std::fs::write(&rom_path, b"fixture ROM").unwrap();
        let storage = NativeGameStorage::for_layout(&root, "gba", rom_id, &rom_path, NativeStorageLayout::Mac).unwrap();
        let member = "battery.srm.an3-conflict-0123456789abcdef";
        let path = storage.member_path("save", member).unwrap();
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, b"existing conflict copy").unwrap();

        let result = write_native_members(&storage, "save", vec![(member.to_string(), b"different incoming copy".to_vec())]);
        assert!(result.unwrap_err().contains("preserved without overwrite"));
        assert_eq!(std::fs::read(path).unwrap(), b"existing conflict copy");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn content_identity_cache_reuses_a_primed_hash_for_unchanged_files() {
        let root = std::env::temp_dir().join(format!("an3-sync-cache-{}-{:?}", std::process::id(), Instant::now()));
        let roms = root.join("an3-roms");
        std::fs::create_dir_all(&roms).unwrap();
        let file = roms.join("11111111-1111-1111-1111-111111111111.gba");
        std::fs::write(&file, b"rom-bytes").unwrap();

        let computed = cached_sha256_file(&root, &file).unwrap();
        assert_eq!(computed, sha256_bytes(b"rom-bytes"));

        // A primed identity (as ROM import stores it) is reused while the file
        // size + mtime are unchanged; the transfer layer still verifies bytes.
        let primed = "a".repeat(64);
        prime_content_hash(&root, &file, &primed);
        assert_eq!(cached_sha256_file(&root, &file).unwrap(), primed);

        // An invalid prime is ignored rather than poisoning the cache.
        let invalid = root.join("an3-roms").join("22222222-2222-2222-2222-222222222222.gba");
        std::fs::write(&invalid, b"other").unwrap();
        prime_content_hash(&root, &invalid, "not-a-hash");
        assert_eq!(cached_sha256_file(&root, &invalid).unwrap(), sha256_bytes(b"other"));

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn native_library_chunks_resume_atomically_and_refuse_conflicts() {
        let root = std::env::temp_dir().join(format!("an3-library-e2e-{}-{:?}", std::process::id(), Instant::now()));
        let source = root.join("source");
        let destination = root.join("destination");
        let conflict = root.join("conflict");
        let rom_id = "11111111-1111-1111-1111-111111111111";
        let bytes: Vec<u8> = (0..(LIBRARY_CHUNK_BYTES + 17)).map(|index| (index % 251) as u8).collect();
        std::fs::create_dir_all(source.join("an3-roms")).unwrap();
        std::fs::write(source.join("an3-roms").join(format!("{rom_id}.gba")), &bytes).unwrap();

        let manifest = library_manifest(&source).unwrap();
        let item = manifest.get("items").and_then(|value| value.as_array()).and_then(|items| items.first()).unwrap();
        assert_eq!(item.get("key").and_then(|value| value.as_str()), Some("rom:11111111-1111-1111-1111-111111111111"));
        assert_eq!(item.get("size").and_then(|value| value.as_u64()), Some(bytes.len() as u64));
        let spec = serde_json::json!({
            "romId": rom_id,
            "extension": "gba",
            "size": bytes.len(),
            "contentHash": sha256_bytes(&bytes),
        });
        let first = native_library_blob(&source, &serde_json::json!({"romId":rom_id,"extension":"gba","size":bytes.len(),"contentHash":sha256_bytes(&bytes),"offset":0,"length":LIBRARY_CHUNK_BYTES})).unwrap();
        let first_bytes = B64.decode(first.get("data").and_then(|value| value.as_str()).unwrap()).unwrap();
        assert_eq!(first_bytes, bytes[..LIBRARY_CHUNK_BYTES]);

        let first_write = native_library_write_chunk(&destination, &serde_json::json!({
            "romId": rom_id, "extension": "gba", "size": bytes.len(), "contentHash": sha256_bytes(&bytes), "offset": 0, "data": B64.encode(&bytes[..LIBRARY_CHUNK_BYTES]),
        })).unwrap();
        assert_eq!(first_write.get("complete").and_then(|value| value.as_bool()), Some(false));
        assert_eq!(first_write.get("nextOffset").and_then(|value| value.as_u64()), Some(LIBRARY_CHUNK_BYTES as u64));
        let status = native_library_upload_status(&destination, &spec).unwrap();
        assert_eq!(status.get("nextOffset").and_then(|value| value.as_u64()), Some(LIBRARY_CHUNK_BYTES as u64));
        let final_write = native_library_write_chunk(&destination, &serde_json::json!({
            "romId": rom_id, "extension": "gba", "size": bytes.len(), "contentHash": sha256_bytes(&bytes), "offset": LIBRARY_CHUNK_BYTES, "data": B64.encode(&bytes[LIBRARY_CHUNK_BYTES..]),
        })).unwrap();
        assert_eq!(final_write.get("complete").and_then(|value| value.as_bool()), Some(true));
        assert_eq!(std::fs::read(destination.join("an3-roms").join(format!("{rom_id}.gba"))).unwrap(), bytes);
        assert!(native_library_upload_status(&destination, &spec).unwrap().get("complete").and_then(|value| value.as_bool()).unwrap());

        std::fs::create_dir_all(conflict.join("an3-roms")).unwrap();
        std::fs::write(conflict.join("an3-roms").join(format!("{rom_id}.gba")), b"user data").unwrap();
        let failure = native_library_write_chunk(&conflict, &serde_json::json!({
            "romId": rom_id, "extension": "gba", "size": bytes.len(), "contentHash": sha256_bytes(&bytes), "offset": 0, "data": B64.encode(&bytes[..LIBRARY_CHUNK_BYTES]),
        })).unwrap_err();
        assert!(failure.contains("different ROM"));
        assert_eq!(std::fs::read(conflict.join("an3-roms").join(format!("{rom_id}.gba"))).unwrap(), b"user data");

        let _ = std::fs::remove_dir_all(&root);
    }

    /// Send one authenticated request and return the host's result, asserting
    /// the response is a successful `response` frame for that request id.
    fn call_request(stream: &mut TcpStream, cipher: &Aes256Gcm, send_counter: &mut u64, receive_counter: &mut u64, id: u64, method: &str, payload: serde_json::Value) -> serde_json::Value {
        let frame = serde_json::json!({"k":"request","id":id,"method":method,"payload":payload});
        write_frame(stream, &seal(cipher, DIR_CLIENT_TO_HOST, *send_counter, &frame)).expect("send request");
        *send_counter += 1;
        let body = read_frame(stream).expect("read response");
        let response = open(cipher, DIR_HOST_TO_CLIENT, *receive_counter, &body).expect("open response");
        *receive_counter += 1;
        assert_eq!(response.get("k").and_then(|v| v.as_str()), Some("response"));
        assert_eq!(response.get("id").and_then(|v| v.as_u64()), Some(id));
        assert_eq!(response.get("ok").and_then(|v| v.as_bool()), Some(true), "request {method} failed: {response}");
        response.get("result").cloned().unwrap_or(serde_json::Value::Null)
    }

    fn connect_guest_for_test(port: u16, code: &str, client_id: &str) -> (TcpStream, Aes256Gcm) {
        let mut stream = TcpStream::connect_timeout(&SocketAddr::from((Ipv4Addr::LOCALHOST, port)), IO_TIMEOUT).expect("connect");
        let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
        let _ = stream.set_write_timeout(Some(IO_TIMEOUT));
        let secret = EphemeralSecret::random(&mut p256::elliptic_curve::rand_core::OsRng);
        let public = secret.public_key().to_encoded_point(false).as_bytes().to_vec();
        let hello = serde_json::json!({"k":"hello","v":PROTOCOL_VERSION,"pub":B64.encode(&public),"id":client_id,"name":"AN3 test client","mode":"guest"});
        write_frame(&mut stream, &serde_json::to_vec(&hello).unwrap()).expect("send hello");
        let response: serde_json::Value = serde_json::from_slice(&read_frame(&mut stream).expect("hello response")).expect("parse hello response");
        let host_pub_bytes = B64.decode(response.get("pub").and_then(|value| value.as_str()).unwrap()).unwrap();
        let host_pub = PublicKey::from_sec1_bytes(&host_pub_bytes).unwrap();
        let host_id = response.get("id").and_then(|value| value.as_str()).unwrap();
        let shared = secret.diffie_hellman(&host_pub);
        let transcript = challenge(host_id, &host_pub_bytes, client_id, &public);
        let key = derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes());
        let cipher = Aes256Gcm::new_from_slice(&key).unwrap();
        let auth = serde_json::json!({"k":"auth","mode":"guest","identity":B64.encode(random_bytes::<32>()),"challenge":transcript,"reconnect":false});
        write_frame(&mut stream, &seal(&cipher, DIR_CLIENT_TO_HOST, 0, &auth)).expect("send auth");
        let ready = open(&cipher, DIR_HOST_TO_CLIENT, 0, &read_frame(&mut stream).expect("ready frame")).expect("open ready");
        assert_eq!(ready.get("k").and_then(|value| value.as_str()), Some("ready"));
        (stream, cipher)
    }

    /// End-to-end over the real native transport: a device with a real ROM and
    /// a real save pairs by code, reads the save manifest and bytes back over
    /// the encrypted LAN session, and publishes modified bytes that the host
    /// verifies and writes atomically. This proves actual save bytes travel in
    /// both directions with SHA-256 integrity, not just that a handshake works.
    #[test]
    fn native_save_round_trips_over_the_lan_transport() {
        let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
        let root = std::env::temp_dir().join(format!("an3-sync-e2e-{}-{:?}", std::process::id(), Instant::now()));
        let rom_id = "11111111-1111-1111-1111-111111111111";
        let roms = root.join("an3-roms");
        std::fs::create_dir_all(&roms).unwrap();
        let rom_path = roms.join(format!("{rom_id}.gba"));
        std::fs::write(&rom_path, b"AN3 homebrew test ROM payload").unwrap();
        let storage = NativeGameStorage::for_layout(&root, "gba", rom_id, &rom_path, current_native_storage_layout()).unwrap();
        let save_path = storage.member_path("save", "battery.srm").unwrap();
        std::fs::create_dir_all(save_path.parent().unwrap()).unwrap();
        let original = b"original save bytes v1".to_vec();
        std::fs::write(&save_path, &original).unwrap();
        let state_path = storage.member_path("state", "slot1.state").unwrap();
        std::fs::create_dir_all(state_path.parent().unwrap()).unwrap();
        let original_state = b"original slot-one state bytes v1".to_vec();
        std::fs::write(&state_path, &original_state).unwrap();

        let (status, listener_port) = start_for_test(root.clone(), "guest".to_string()).expect("start host");
        let code = status.code.clone();
        assert_eq!(code.len(), 6, "host must publish a six-digit pairing code");

        let identity = game_identity(&root, "gba".to_string(), rom_id.to_string()).expect("rom identity");
        let context_value = serde_json::json!({"kind":"save","system":"gba","romId":rom_id,"identity":identity});

        // Pair as a guest using the displayed pairing code.
        let (mut stream, cipher) = connect_guest_for_test(listener_port, &code, "an3-test-client");

        let mut send_counter = 1u64;
        let mut receive_counter = 1u64;

        // 1. The host advertises the real save with its content hash.
        let manifest = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 1, "manifest", context_value.clone());
        let set = manifest.get("sets").and_then(|v| v.as_array()).and_then(|sets| sets.first()).expect("a save set");
        let members = set.get("members").and_then(|v| v.as_array()).expect("members");
        assert_eq!(members.len(), 1);
        let member = &members[0];
        assert_eq!(member.get("size").and_then(|v| v.as_u64()), Some(original.len() as u64));
        assert_eq!(member.get("contentHash").and_then(|v| v.as_str()), Some(sha256_bytes(&original).as_str()));

        // 2. The real save bytes travel back over the encrypted session.
        let blob = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 2, "blob",
            serde_json::json!({"kind":"save","system":"gba","romId":rom_id,"identity":context_value.get("identity").cloned().unwrap(),"item": member}));
        let blob_bytes = B64.decode(blob.get("data").and_then(|v| v.as_str()).unwrap()).unwrap();
        assert_eq!(blob_bytes, original, "the received save bytes must match the host's save");

        // 3. Publish modified bytes in the other direction; the host verifies
        //    size + SHA-256 and writes them atomically.
        let updated = b"updated save bytes v2 - returns".to_vec();
        let context = native_context(&context_value).unwrap();
        let set_id = native_set_id(&context);
        let member_id = member.get("memberId").and_then(|v| v.as_str()).unwrap().to_string();
        let canonical = CanonicalMember { member_id: member_id.clone(), path: format!("/data/saves/{member_id}"), size: updated.len() as u64, content_hash: sha256_bytes(&updated) };
        let manifest_hash = canonical_set_hash(&context, &set_id, std::slice::from_ref(&canonical), updated.len() as u64).unwrap();
        let publish = serde_json::json!({
            "kind":"save","system":"gba","romId":rom_id,"identity":context_value.get("identity").cloned().unwrap(),
            "set":{"setId":set_id,"core":context.core,"gameId":context.game_id,"romHash":context.rom_hash,"memberCount":1,"totalSize":updated.len(),"manifestHash":manifest_hash,
                   "members":[{"key":format!("{set_id}:{member_id}"),"memberId":member_id,"path":format!("/data/saves/{member_id}"),"size":updated.len(),"contentHash":sha256_bytes(&updated)}]},
            "items":[{"key":format!("{set_id}:{member_id}"),"data":B64.encode(&updated)}],
        });
        let published = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 3, "publish", publish);
        assert_eq!(published.get("accepted").and_then(|v| v.as_u64()), Some(1));

        // 4. The host's on-disk save is the published bytes, byte-for-byte.
        let on_disk = std::fs::read(&save_path).expect("host save written");
        assert_eq!(on_disk, updated, "the host must persist the exact published bytes");
        assert_eq!(sha256_bytes(&on_disk), sha256_bytes(&updated));

        // 5. Save states use their own authenticated manifest and blob identity.
        let mut state_context = context_value.clone();
        state_context["kind"] = serde_json::json!("state");
        let state_manifest = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 4, "manifest", state_context.clone());
        let state_items = state_manifest.get("items").and_then(|value| value.as_array()).expect("state items");
        assert_eq!(state_items.len(), 1);
        let state_member = &state_items[0];
        assert_eq!(state_member.get("path").and_then(|value| value.as_str()), Some("/data/states/slot1.state"));
        assert_eq!(state_member.get("size").and_then(|value| value.as_u64()), Some(original_state.len() as u64));
        assert_eq!(state_member.get("contentHash").and_then(|value| value.as_str()), Some(sha256_bytes(&original_state).as_str()));
        let state_blob = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 5, "blob",
            serde_json::json!({"kind":"state","system":"gba","romId":rom_id,"identity":context_value.get("identity").cloned().unwrap(),"item":state_member}));
        let state_blob_bytes = B64.decode(state_blob.get("data").and_then(|value| value.as_str()).unwrap()).unwrap();
        assert_eq!(state_blob_bytes, original_state, "the received save-state bytes must match the host state");

        // 6. Publishing a valid state replaces the selected state atomically.
        let updated_state = b"updated slot-one state bytes v2 - returns".to_vec();
        let state_key = state_member.get("key").and_then(|value| value.as_str()).unwrap().to_string();
        let state_publish = serde_json::json!({
            "kind":"state","system":"gba","romId":rom_id,"identity":context_value.get("identity").cloned().unwrap(),
            "items":[{"key":state_key,"path":"/data/states/slot1.state","size":updated_state.len(),"contentHash":sha256_bytes(&updated_state),"data":B64.encode(&updated_state)}]
        });
        let published_state = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 6, "publish", state_publish);
        assert_eq!(published_state.get("accepted").and_then(|value| value.as_u64()), Some(1));
        let state_on_disk = std::fs::read(&state_path).expect("host save-state written");
        assert_eq!(state_on_disk, updated_state, "the host must persist the exact published state bytes");
        assert_eq!(sha256_bytes(&state_on_disk), sha256_bytes(&updated_state));

        let _ = stream.shutdown(Shutdown::Both);
        stop();
        let _ = std::fs::remove_dir_all(&root);
    }

    /// Exercise both native-library directions over the authenticated,
    /// encrypted LAN protocol. The opaque bytes are transport test data only;
    /// this test does not treat them as bootable ROM fixtures or launch them.
    #[test]
    fn native_library_bytes_round_trip_over_the_encrypted_lan_transport() {
        let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
        let root = std::env::temp_dir().join(format!("an3-library-e2e-{}-{:?}", std::process::id(), Instant::now()));
        let client_root = root.join("client");
        let host_rom_id = "11111111-1111-1111-1111-111111111111";
        let client_rom_id = "22222222-2222-2222-2222-222222222222";
        let host_bytes = b"opaque native-library download payload".to_vec();
        let client_bytes = b"opaque native-library upload payload".to_vec();
        let host_roms = root.join("an3-roms");
        let client_roms = client_root.join("an3-roms");
        std::fs::create_dir_all(&host_roms).unwrap();
        std::fs::create_dir_all(&client_roms).unwrap();
        std::fs::write(host_roms.join(format!("{host_rom_id}.gba")), &host_bytes).unwrap();
        std::fs::write(client_roms.join(format!("{client_rom_id}.gba")), &client_bytes).unwrap();

        let (status, listener_port) = start_for_test(root.clone(), "guest".to_string()).expect("start host");
        let code = status.code.clone();
        let (mut stream, cipher) = connect_guest_for_test(listener_port, &code, "an3-library-test-client");
        let mut send_counter = 1u64;
        let mut receive_counter = 1u64;

        let host_manifest = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 1, "library-manifest", serde_json::Value::Null);
        let host_item = host_manifest.get("items").and_then(|value| value.as_array()).and_then(|items| {
            items.iter().find(|item| item.get("romId").and_then(|value| value.as_str()) == Some(host_rom_id))
        }).expect("host library item");
        assert_eq!(host_item.get("size").and_then(|value| value.as_u64()), Some(host_bytes.len() as u64));
        assert_eq!(host_item.get("contentHash").and_then(|value| value.as_str()), Some(sha256_bytes(&host_bytes).as_str()));

        let host_blob = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 2, "library-blob", serde_json::json!({
            "romId": host_rom_id,
            "extension": "gba",
            "size": host_bytes.len(),
            "contentHash": sha256_bytes(&host_bytes),
            "offset": 0,
            "length": host_bytes.len(),
        }));
        let downloaded = B64.decode(host_blob.get("data").and_then(|value| value.as_str()).unwrap()).unwrap();
        assert_eq!(downloaded, host_bytes, "the encrypted host-to-client bytes must match");
        let received = native_library_write_chunk(&client_root, &serde_json::json!({
            "romId": host_rom_id,
            "extension": "gba",
            "size": host_bytes.len(),
            "contentHash": sha256_bytes(&host_bytes),
            "offset": 0,
            "data": B64.encode(&downloaded),
        })).expect("persist downloaded library bytes");
        assert_eq!(received.get("complete").and_then(|value| value.as_bool()), Some(true));
        assert_eq!(std::fs::read(client_roms.join(format!("{host_rom_id}.gba"))).unwrap(), host_bytes);

        let client_manifest = library_manifest(&client_root).expect("client library manifest");
        let client_item = client_manifest.get("items").and_then(|value| value.as_array()).and_then(|items| {
            items.iter().find(|item| item.get("romId").and_then(|value| value.as_str()) == Some(client_rom_id))
        }).expect("client library item");
        assert_eq!(client_item.get("contentHash").and_then(|value| value.as_str()), Some(sha256_bytes(&client_bytes).as_str()));
        let client_blob = library_read_chunk(&client_root, serde_json::json!({
            "romId": client_rom_id,
            "extension": "gba",
            "size": client_bytes.len(),
            "contentHash": sha256_bytes(&client_bytes),
            "offset": 0,
            "length": client_bytes.len(),
        })).expect("read client library bytes");
        let upload_data = client_blob.get("data").and_then(|value| value.as_str()).unwrap();
        assert_eq!(B64.decode(upload_data).unwrap(), client_bytes);

        let client_spec = serde_json::json!({
            "romId": client_rom_id,
            "extension": "gba",
            "size": client_bytes.len(),
            "contentHash": sha256_bytes(&client_bytes),
        });
        let upload_status = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 3, "library-upload-status", client_spec.clone());
        assert_eq!(upload_status.get("complete").and_then(|value| value.as_bool()), Some(false));
        assert_eq!(upload_status.get("nextOffset").and_then(|value| value.as_u64()), Some(0));
        let mut publish = client_spec;
        publish["offset"] = serde_json::json!(0);
        publish["data"] = serde_json::json!(upload_data);
        let published = call_request(&mut stream, &cipher, &mut send_counter, &mut receive_counter, 4, "library-publish-chunk", publish);
        assert_eq!(published.get("complete").and_then(|value| value.as_bool()), Some(true));
        assert_eq!(published.get("nextOffset").and_then(|value| value.as_u64()), Some(client_bytes.len() as u64));
        assert_eq!(std::fs::read(host_roms.join(format!("{client_rom_id}.gba"))).unwrap(), client_bytes);
        let final_manifest = library_manifest(&root).expect("final host library manifest");
        let final_item = final_manifest.get("items").and_then(|value| value.as_array()).and_then(|items| {
            items.iter().find(|item| item.get("romId").and_then(|value| value.as_str()) == Some(client_rom_id))
        }).expect("uploaded host library item");
        assert_eq!(final_item.get("contentHash").and_then(|value| value.as_str()), Some(sha256_bytes(&client_bytes).as_str()));

        let _ = stream.shutdown(Shutdown::Both);
        stop();
        let _ = std::fs::remove_dir_all(&root);
    }

    /// A publish whose bytes do not match the declared content hash must be
    /// rejected, and the host's existing good save must be left untouched.
    #[test]
    fn native_publish_rejects_bytes_that_do_not_match_the_declared_hash() {
        let _guard = SERIAL.lock().unwrap_or_else(|e| e.into_inner());
        let root = std::env::temp_dir().join(format!("an3-sync-bad-{}-{:?}", std::process::id(), Instant::now()));
        let rom_id = "11111111-1111-1111-1111-111111111111";
        let roms = root.join("an3-roms");
        std::fs::create_dir_all(&roms).unwrap();
        let rom_path = roms.join(format!("{rom_id}.gba"));
        std::fs::write(&rom_path, b"AN3 homebrew test ROM payload").unwrap();
        let storage = NativeGameStorage::for_layout(&root, "gba", rom_id, &rom_path, current_native_storage_layout()).unwrap();
        let save_path = storage.member_path("save", "battery.srm").unwrap();
        std::fs::create_dir_all(save_path.parent().unwrap()).unwrap();
        let original = b"good save that must survive".to_vec();
        std::fs::write(&save_path, &original).unwrap();

        let (status, listener_port) = start_for_test(root.clone(), "guest".to_string()).expect("start host");
        let code = status.code.clone();
        let identity = game_identity(&root, "gba".to_string(), rom_id.to_string()).expect("rom identity");
        let context_value = serde_json::json!({"kind":"save","system":"gba","romId":rom_id,"identity":identity});

        let mut stream = TcpStream::connect_timeout(&SocketAddr::from((Ipv4Addr::LOCALHOST, listener_port)), IO_TIMEOUT).expect("connect");
        let _ = stream.set_read_timeout(Some(IO_TIMEOUT));
        let secret = EphemeralSecret::random(&mut p256::elliptic_curve::rand_core::OsRng);
        let public = secret.public_key().to_encoded_point(false).as_bytes().to_vec();
        let client_id = "an3-test-bad";
        let client_secret = B64.encode(random_bytes::<32>());
        write_frame(&mut stream, &serde_json::to_vec(&serde_json::json!({"k":"hello","v":PROTOCOL_VERSION,"pub":B64.encode(&public),"id":client_id,"name":"Test","mode":"guest"})).unwrap()).unwrap();
        let response: serde_json::Value = serde_json::from_slice(&read_frame(&mut stream).unwrap()).unwrap();
        let host_pub_bytes = B64.decode(response.get("pub").and_then(|v| v.as_str()).unwrap()).unwrap();
        let host_pub = PublicKey::from_sec1_bytes(&host_pub_bytes).unwrap();
        let host_id = response.get("id").and_then(|v| v.as_str()).unwrap().to_string();
        let shared = secret.diffie_hellman(&host_pub);
        let transcript = challenge(&host_id, &host_pub_bytes, client_id, &public);
        let key = derive_key(shared.raw_secret_bytes().as_slice(), code.as_bytes());
        let cipher = Aes256Gcm::new_from_slice(&key).unwrap();
        write_frame(&mut stream, &seal(&cipher, DIR_CLIENT_TO_HOST, 0, &serde_json::json!({"k":"auth","mode":"guest","identity":client_secret,"challenge":transcript,"reconnect":false}))).unwrap();
        let ready = open(&cipher, DIR_HOST_TO_CLIENT, 0, &read_frame(&mut stream).unwrap()).unwrap();
        assert_eq!(ready.get("k").and_then(|v| v.as_str()), Some("ready"));

        let context = native_context(&context_value).unwrap();
        let set_id = native_set_id(&context);
        let bad = b"tampered bytes".to_vec();
        // A consistent manifest (so the manifest hash validates) whose member
        // declares one hash, but whose data is different bytes: the host must
        // reject it at the byte SHA-256 check.
        let declared = sha256_bytes(b"the honest bytes");
        let member_id = "battery.srm";
        let canonical = CanonicalMember { member_id: member_id.to_string(), path: format!("/data/saves/{member_id}"), size: bad.len() as u64, content_hash: declared.clone() };
        let manifest_hash = canonical_set_hash(&context, &set_id, std::slice::from_ref(&canonical), bad.len() as u64).unwrap();
        let publish = serde_json::json!({
            "kind":"save","system":"gba","romId":rom_id,"identity":context_value.get("identity").cloned().unwrap(),
            "set":{"setId":set_id,"core":context.core,"gameId":context.game_id,"romHash":context.rom_hash,"memberCount":1,"totalSize":bad.len(),"manifestHash":manifest_hash,
                   "members":[{"key":format!("{set_id}:{member_id}"),"memberId":member_id,"path":format!("/data/saves/{member_id}"),"size":bad.len(),"contentHash":declared}]},
            "items":[{"key":format!("{set_id}:{member_id}"),"data":B64.encode(&bad)}],
        });
        let frame = serde_json::json!({"k":"request","id":1,"method":"publish","payload":publish});
        write_frame(&mut stream, &seal(&cipher, DIR_CLIENT_TO_HOST, 1, &frame)).unwrap();
        let body = read_frame(&mut stream).unwrap();
        let result = open(&cipher, DIR_HOST_TO_CLIENT, 1, &body).unwrap();
        assert_eq!(result.get("ok").and_then(|v| v.as_bool()), Some(false), "a hash mismatch must be rejected: {result}");

        // The good save must be exactly as it was.
        assert_eq!(std::fs::read(&save_path).unwrap(), original, "the existing save must not be overwritten");

        let _ = stream.shutdown(Shutdown::Both);
        stop();
        let _ = std::fs::remove_dir_all(&root);
    }
}

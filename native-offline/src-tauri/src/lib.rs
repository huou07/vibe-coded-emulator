// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#[cfg(not(mobile))]
use include_dir::{include_dir, Dir};
mod azahar;
mod controller_host;
use azahar::{native_capabilities, set_native_input, start_native_game, stop_native_game};
use serde::Serialize;
use std::{
    fs::{self, File},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
};
#[cfg(not(mobile))]
use std::{
    io::{BufRead, BufReader},
    net::{TcpListener, TcpStream},
    thread,
};
#[cfg(not(mobile))]
use tauri::Url;
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;

const COPY_BUFFER_BYTES: usize = 1024 * 1024;
// The capability policy must name the local renderer's origin exactly.  A fixed
// loopback-only port avoids granting Tauri IPC to arbitrary local web pages.
#[cfg(not(mobile))]
const NATIVE_RUNTIME_PORT: u16 = 38_471;
#[cfg(not(mobile))]
static NATIVE_RUNTIME: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/../dist");

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ImportedNativeRom {
    url: String,
    name: String,
    size: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    system: Option<String>,
}

fn validate_rom_id(rom_id: &str) -> Result<(), String> {
    let valid = rom_id.len() == 36
        && rom_id.bytes().enumerate().all(|(index, byte)| {
            matches!(byte, b'0'..=b'9' | b'a'..=b'f')
                || (byte == b'-' && matches!(index, 8 | 13 | 18 | 23))
        });
    if valid {
        Ok(())
    } else {
        Err("Invalid local ROM identifier".into())
    }
}

fn safe_extension(source: &Path) -> String {
    source
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.to_ascii_lowercase())
        .filter(|value| {
            !value.is_empty()
                && value.len() <= 10
                && value.bytes().all(|byte| byte.is_ascii_alphanumeric())
        })
        .unwrap_or_else(|| "rom".into())
}

fn safe_request_extension(value: &str) -> bool {
    !value.is_empty() && value.len() <= 10 && value.bytes().all(|byte| byte.is_ascii_alphanumeric())
}

// Keep native import recognition aligned with the official Azahar libretro
// core. Archives and CIA installation packages deliberately stay out of this
// list: the embedded player receives one playable local file, not an installer
// or an archive extractor.
pub(crate) const NATIVE_3DS_FILE_EXTENSIONS: &[&str] = &[
    "3ds", "3dsx", "z3dsx", "elf", "axf", "cci", "zcci", "cxi", "zcxi", "app",
];

pub(crate) fn native_system_from_extension(extension: &str) -> Option<&'static str> {
    if extension.eq_ignore_ascii_case("gba") || extension.eq_ignore_ascii_case("raw") {
        Some("gba")
    } else if extension.eq_ignore_ascii_case("nds") {
        Some("nds")
    } else if NATIVE_3DS_FILE_EXTENSIONS
        .iter()
        .any(|known| extension.eq_ignore_ascii_case(known))
    {
        Some("3ds")
    } else {
        None
    }
}

fn canonical_extension_for_system(system: &str) -> Option<&'static str> {
    match system {
        "gba" => Some("gba"),
        "nds" => Some("nds"),
        "3ds" => Some("3ds"),
        _ => None,
    }
}

fn native_system_from_header(source: &Path, file_size: u64) -> Option<&'static str> {
    let mut header = [0_u8; 0x200];
    let mut input = File::open(source).ok()?;
    input.read_exact(&mut header).ok()?;
    if &header[0x100..0x104] == b"NCSD" || &header[0x100..0x104] == b"NCCH" {
        return Some("3ds");
    }
    if header[0xb2] == 0x96 {
        return Some("gba");
    }
    let arm9_offset = u32::from_le_bytes(header[0x20..0x24].try_into().ok()?) as u64;
    let arm9_size = u32::from_le_bytes(header[0x2c..0x30].try_into().ok()?) as u64;
    if arm9_offset >= 0x200
        && arm9_size > 0
        && arm9_offset
            .checked_add(arm9_size)
            .is_some_and(|end| end <= file_size)
    {
        return Some("nds");
    }
    None
}

fn detect_native_system(source: &Path, extension: &str, file_size: u64) -> Option<&'static str> {
    native_system_from_extension(extension)
        .or_else(|| native_system_from_header(source, file_size))
}

fn declared_ncsd_length(source: &Path, file_size: u64) -> u64 {
    let mut header = [0_u8; 0x200];
    let Ok(mut input) = File::open(source) else {
        return file_size;
    };
    if input.read_exact(&mut header).is_err() || &header[0x100..0x104] != b"NCSD" {
        return file_size;
    }
    let mut end = 0_u64;
    for index in 0..8 {
        let offset = u32::from_le_bytes(
            header[0x120 + index * 8..0x124 + index * 8]
                .try_into()
                .unwrap(),
        ) as u64;
        let length = u32::from_le_bytes(
            header[0x124 + index * 8..0x128 + index * 8]
                .try_into()
                .unwrap(),
        ) as u64;
        let Some(partition_end) = offset
            .checked_add(length)
            .and_then(|value| value.checked_mul(0x200))
        else {
            return file_size;
        };
        if length > 0 && partition_end > file_size {
            return file_size;
        }
        end = end.max(partition_end);
    }
    if end > 0 && end < file_size {
        end
    } else {
        file_size
    }
}

fn copy_prefix(source: &Path, destination: &Path, length: u64) -> Result<(), String> {
    let mut input =
        File::open(source).map_err(|error| format!("Cannot open the selected ROM: {error}"))?;
    let mut output = File::create(destination)
        .map_err(|error| format!("Cannot create local ROM storage: {error}"))?;
    let mut buffer = vec![0_u8; COPY_BUFFER_BYTES];
    let mut remaining = length;
    while remaining > 0 {
        let wanted = remaining.min(buffer.len() as u64) as usize;
        let count = input
            .read(&mut buffer[..wanted])
            .map_err(|error| format!("Cannot read the selected ROM: {error}"))?;
        if count == 0 {
            return Err("The selected ROM ended before its declared length".into());
        }
        output
            .write_all(&buffer[..count])
            .map_err(|error| format!("Cannot save the local ROM: {error}"))?;
        remaining -= count as u64;
    }
    output
        .sync_all()
        .map_err(|error| format!("Cannot finish saving the local ROM: {error}"))
}

#[cfg(not(mobile))]
fn runtime_content_type(path: &str) -> &'static str {
    if path.ends_with(".html") {
        "text/html; charset=utf-8"
    } else if path.ends_with(".js") {
        "text/javascript; charset=utf-8"
    } else if path.ends_with(".css") {
        "text/css; charset=utf-8"
    } else if path.ends_with(".json") {
        "application/json; charset=utf-8"
    } else if path.ends_with(".svg") {
        "image/svg+xml"
    } else if path.ends_with(".png") {
        "image/png"
    } else if path.ends_with(".webp") {
        "image/webp"
    } else if path.ends_with(".woff2") {
        "font/woff2"
    } else {
        "application/octet-stream"
    }
}

#[cfg(not(mobile))]
fn write_response_head(
    stream: &mut TcpStream,
    status: &str,
    content_type: &str,
    length: u64,
    cache: &str,
    range: Option<(u64, u64, u64)>,
) -> std::io::Result<()> {
    let content_range = range
        .map(|(start, end, total)| format!("Content-Range: bytes {start}-{end}/{total}\r\n"))
        .unwrap_or_default();
    stream.write_all(format!(
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {length}\r\nCache-Control: {cache}\r\nAccept-Ranges: bytes\r\nCross-Origin-Opener-Policy: same-origin\r\nCross-Origin-Embedder-Policy: require-corp\r\nCross-Origin-Resource-Policy: same-origin\r\nContent-Security-Policy: default-src 'self' blob: data:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob:; connect-src 'self' blob:; worker-src 'self' blob:; media-src 'self' blob: data:; object-src 'none'; base-uri 'self'; form-action 'self'\r\nX-Content-Type-Options: nosniff\r\n{content_range}Connection: close\r\n\r\n"
    ).as_bytes())
}

#[cfg(not(mobile))]
fn parse_range(value: Option<&str>, size: u64) -> Result<Option<(u64, u64)>, ()> {
    let Some(value) = value else {
        return Ok(None);
    };
    let Some(specification) = value.strip_prefix("bytes=") else {
        return Err(());
    };
    if specification.contains(',') {
        return Err(());
    }
    let Some((start, end)) = specification.split_once('-') else {
        return Err(());
    };
    if start.is_empty() {
        let suffix = end.parse::<u64>().map_err(|_| ())?;
        if suffix == 0 {
            return Err(());
        }
        return Ok(Some((size.saturating_sub(suffix), size.saturating_sub(1))));
    }
    let start = start.parse::<u64>().map_err(|_| ())?;
    if start >= size {
        return Err(());
    }
    let end = if end.is_empty() {
        size - 1
    } else {
        end.parse::<u64>().map_err(|_| ())?.min(size - 1)
    };
    if end < start {
        return Err(());
    }
    Ok(Some((start, end)))
}

#[cfg(not(mobile))]
fn read_request(stream: &mut TcpStream) -> std::io::Result<(String, String, Option<String>)> {
    let mut reader = BufReader::new(stream);
    let mut request = String::new();
    reader.read_line(&mut request)?;
    let mut parts = request.split_whitespace();
    let method = parts.next().unwrap_or_default().to_string();
    let path = parts
        .next()
        .unwrap_or_default()
        .split('?')
        .next()
        .unwrap_or_default()
        .to_string();
    let mut range = None;
    loop {
        let mut line = String::new();
        reader.read_line(&mut line)?;
        if line == "\r\n" || line.is_empty() {
            break;
        }
        if let Some((name, value)) = line.split_once(':') {
            if name.eq_ignore_ascii_case("range") {
                range = Some(value.trim().to_string());
            }
        }
    }
    drop(reader);
    Ok((method, path, range))
}

#[cfg(not(mobile))]
fn valid_runtime_path(path: &str) -> Option<&str> {
    let path = path.strip_prefix('/').unwrap_or(path);
    let path = if path.is_empty() { "index.html" } else { path };
    if path
        .split('/')
        .any(|part| part.is_empty() || part == "." || part == ".." || part.contains('\\'))
    {
        None
    } else {
        Some(path)
    }
}

#[cfg(not(mobile))]
fn native_rom_request_parts(request: &str) -> Option<(&str, Option<&str>)> {
    // Keep the original ROM suffix in the URL.  EmulatorJS uses that suffix
    // while choosing the content filename handed to a libretro core; a UUID
    // path with no extension can otherwise create a core that is technically
    // started but never loads the selected game.
    let (rom_id, extension) = match request.len() {
        36 => (request, None),
        length if length > 37 && request.as_bytes().get(36) == Some(&b'.') => {
            (&request[..36], Some(&request[37..]))
        }
        _ => return None,
    };
    validate_rom_id(rom_id).ok()?;
    if extension.is_some_and(|value| !safe_request_extension(value)) {
        return None;
    }
    Some((rom_id, extension))
}

#[cfg(not(mobile))]
fn native_rom_path(
    directory: &Path,
    rom_id: &str,
    requested_extension: Option<&str>,
) -> Option<PathBuf> {
    validate_rom_id(rom_id).ok()?;
    let prefix = format!("{rom_id}.");
    fs::read_dir(directory).ok()?.flatten().find_map(|entry| {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        let valid_name = name.starts_with(&prefix)
            && requested_extension.map_or(true, |extension| {
                name.strip_prefix(&prefix)
                    .is_some_and(|actual| actual.eq_ignore_ascii_case(extension))
            });
        entry
            .file_type()
            .ok()
            .filter(|type_| type_.is_file() && valid_name)
            .map(|_| entry.path())
    })
}

#[cfg(not(mobile))]
fn send_runtime_asset(
    stream: &mut TcpStream,
    method: &str,
    path: &str,
    range: Option<String>,
) -> std::io::Result<()> {
    let Some(path) = valid_runtime_path(path) else {
        return write_response_head(
            stream,
            "404 Not Found",
            "text/plain; charset=utf-8",
            0,
            "no-store",
            None,
        );
    };
    let Some(asset) = NATIVE_RUNTIME.get_file(path) else {
        return write_response_head(
            stream,
            "404 Not Found",
            "text/plain; charset=utf-8",
            0,
            "no-store",
            None,
        );
    };
    let bytes = asset.contents();
    let size = bytes.len() as u64;
    let selected = parse_range(range.as_deref(), size);
    let Ok(selected) = selected else {
        return write_response_head(
            stream,
            "416 Range Not Satisfiable",
            "text/plain; charset=utf-8",
            0,
            "no-store",
            None,
        );
    };
    let (start, end, status) = selected
        .map(|(start, end)| (start, end, "206 Partial Content"))
        .unwrap_or((0, size.saturating_sub(1), "200 OK"));
    let length = if size == 0 { 0 } else { end - start + 1 };
    write_response_head(
        stream,
        status,
        runtime_content_type(path),
        length,
        // The app shell has fixed local URLs while each Tauri release embeds
        // new HTML/JS/CSS. Never let WebKit keep a previous player UI for a
        // year; large emulator core assets remain immutable under
        // `emulatorjs/`.
        if path == "index.html" || path == "native-bootstrap.js" || path.starts_with("static/") {
            "no-cache"
        } else {
            "public,max-age=31536000,immutable"
        },
        selected.map(|_| (start, end, size)),
    )?;
    if method == "GET" && length > 0 {
        stream.write_all(&bytes[start as usize..=end as usize])?;
    }
    Ok(())
}

#[cfg(not(mobile))]
fn send_native_rom(
    stream: &mut TcpStream,
    method: &str,
    directory: &Path,
    request: &str,
    range: Option<String>,
) -> std::io::Result<()> {
    let Some((rom_id, requested_extension)) = native_rom_request_parts(request) else {
        return write_response_head(
            stream,
            "404 Not Found",
            "text/plain; charset=utf-8",
            0,
            "no-store",
            None,
        );
    };
    let Some(path) = native_rom_path(directory, rom_id, requested_extension) else {
        return write_response_head(
            stream,
            "404 Not Found",
            "text/plain; charset=utf-8",
            0,
            "no-store",
            None,
        );
    };
    let mut file = File::open(path)?;
    let size = file.metadata()?.len();
    let selected = parse_range(range.as_deref(), size);
    let Ok(selected) = selected else {
        return write_response_head(
            stream,
            "416 Range Not Satisfiable",
            "text/plain; charset=utf-8",
            0,
            "no-store",
            None,
        );
    };
    let (start, end, status) = selected
        .map(|(start, end)| (start, end, "206 Partial Content"))
        .unwrap_or((0, size.saturating_sub(1), "200 OK"));
    let length = if size == 0 { 0 } else { end - start + 1 };
    write_response_head(
        stream,
        status,
        "application/octet-stream",
        length,
        "no-store",
        selected.map(|_| (start, end, size)),
    )?;
    if method == "GET" && length > 0 {
        file.seek(SeekFrom::Start(start))?;
        let mut remaining = length;
        let mut buffer = vec![0_u8; COPY_BUFFER_BYTES];
        while remaining > 0 {
            let chunk_length = remaining.min(buffer.len() as u64) as usize;
            let count = file.read(&mut buffer[..chunk_length])?;
            if count == 0 {
                break;
            }
            stream.write_all(&buffer[..count])?;
            remaining -= count as u64;
        }
    }
    Ok(())
}

#[cfg(not(mobile))]
fn serve_runtime_connection(mut stream: TcpStream, rom_directory: &Path) {
    let Ok((method, path, range)) = read_request(&mut stream) else {
        return;
    };
    if !matches!(method.as_str(), "GET" | "HEAD") {
        let _ = write_response_head(
            &mut stream,
            "405 Method Not Allowed",
            "text/plain; charset=utf-8",
            0,
            "no-store",
            None,
        );
        return;
    }
    if let Some(rom_request) = path.strip_prefix("/_an3/rom/") {
        let _ = send_native_rom(&mut stream, &method, rom_directory, rom_request, range);
    } else {
        let _ = send_runtime_asset(&mut stream, &method, &path, range);
    }
}

#[cfg(not(mobile))]
fn start_runtime_server(app: &AppHandle) -> Result<Url, String> {
    let rom_directory = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot find native app storage: {error}"))?
        .join("an3-roms");
    let listener = TcpListener::bind(("127.0.0.1", NATIVE_RUNTIME_PORT)).map_err(|error| {
        format!("Cannot start the local game runtime on port {NATIVE_RUNTIME_PORT}: {error}")
    })?;
    thread::Builder::new()
        .name("an3-local-runtime".into())
        .spawn(move || {
            for connection in listener.incoming().flatten() {
                serve_runtime_connection(connection, &rom_directory);
            }
        })
        .map_err(|error| format!("Cannot run the local game runtime: {error}"))?;
    Url::parse(&format!("http://127.0.0.1:{NATIVE_RUNTIME_PORT}/"))
        .map_err(|error| format!("Cannot prepare the local game runtime: {error}"))
}

fn import_native_rom(
    app: &AppHandle,
    rom_id: &str,
    source: PathBuf,
) -> Result<ImportedNativeRom, String> {
    validate_rom_id(rom_id)?;
    let source = source
        .canonicalize()
        .map_err(|error| format!("Cannot resolve the selected ROM: {error}"))?;
    let metadata = fs::metadata(&source)
        .map_err(|error| format!("Cannot inspect the selected ROM: {error}"))?;
    if !metadata.is_file() || metadata.len() == 0 {
        return Err("Choose a non-empty ROM file".into());
    }
    let source_extension = safe_extension(&source);
    if source_extension.eq_ignore_ascii_case("zip") || source_extension.eq_ignore_ascii_case("cia") {
        return Err("Choose an extracted, decrypted GBA, NDS, or 3DS ROM. ZIP archives and CIA install packages are not playable in the in-app native player.".into());
    }
    let system = detect_native_system(&source, &source_extension, metadata.len()).ok_or_else(|| {
        "Choose a supported GBA, NDS, or decrypted 3DS ROM file for the in-app player.".to_string()
    })?;
    let directory = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot find native app storage: {error}"))?
        .join("an3-roms");
    fs::create_dir_all(&directory)
        .map_err(|error| format!("Cannot prepare native ROM storage: {error}"))?;
    // A file with an arbitrary suffix can still be a valid GBA/NDS/3DS ROM.
    // Once its header identifies it, give EmulatorJS a conventional content
    // suffix; otherwise it may boot the core but decline to load the ROM.
    let extension = if system == "gba" && source_extension.eq_ignore_ascii_case("raw") {
        // mGBA receives the full byte buffer, but preserve its conventional
        // content suffix for core-side identification and save naming.
        "gba".to_string()
    } else if native_system_from_extension(&source_extension).is_some() {
        source_extension
    } else {
        canonical_extension_for_system(system)
            .map(str::to_owned)
            .unwrap_or(source_extension)
    };
    let filename = format!("{rom_id}.{extension}");
    let destination = directory.join(filename);
    let temporary = directory.join(format!(".{rom_id}.part"));
    let playable_size = declared_ncsd_length(&source, metadata.len());
    if let Err(error) = copy_prefix(&source, &temporary, playable_size) {
        let _ = fs::remove_file(&temporary);
        return Err(error);
    }
    fs::rename(&temporary, &destination)
        .map_err(|error| format!("Cannot finalize local ROM storage: {error}"))?;
    let name = source
        .file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "The selected ROM has no usable filename".to_string())?
        .to_string();
    Ok(ImportedNativeRom {
        url: format!("/_an3/rom/{rom_id}.{extension}"),
        name,
        size: playable_size,
        system: Some(system.to_owned()),
    })
}

#[tauri::command]
async fn pick_and_import_native_rom(
    app: AppHandle,
    rom_id: String,
) -> Result<Option<ImportedNativeRom>, String> {
    validate_rom_id(&rom_id)?;
    let dialog_app = app.clone();
    let selected = tauri::async_runtime::spawn_blocking(move || {
        dialog_app
            .dialog()
            .file()
            .set_title("Choose a local ROM")
            .blocking_pick_file()
    })
    .await
    .map_err(|error| format!("Native ROM picker failed: {error}"))?;
    let Some(selected) = selected else {
        return Ok(None);
    };
    let source = selected
        .into_path()
        .map_err(|error| format!("The selected ROM is not a local file path: {error}"))?;
    let import_app = app.clone();
    let imported = tauri::async_runtime::spawn_blocking(move || {
        import_native_rom(&import_app, &rom_id, source)
    })
    .await
    .map_err(|error| format!("Native ROM import failed: {error}"))?;
    Ok(Some(imported?))
}

#[tauri::command]
async fn native_controller_start(base_url: Option<String>) -> Result<controller_host::ControllerSession, String> {
    tauri::async_runtime::spawn_blocking(move || controller_host::start(base_url.unwrap_or_default()))
        .await
        .map_err(|error| error.to_string())?
}

#[tauri::command]
fn native_controller_stop() {
    controller_host::stop();
}

#[tauri::command]
fn native_controller_status() -> controller_host::ControllerStatus {
    controller_host::status()
}

#[tauri::command]
async fn remove_native_rom(app: AppHandle, rom_id: String) -> Result<(), String> {
    validate_rom_id(&rom_id)?;
    let directory = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot find native app storage: {error}"))?
        .join("an3-roms");
    let prefix = format!("{rom_id}.");
    tauri::async_runtime::spawn_blocking(move || {
        let entries = match fs::read_dir(&directory) {
            Ok(entries) => entries,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(format!("Cannot inspect native ROM storage: {error}")),
        };
        for entry in entries {
            let entry =
                entry.map_err(|error| format!("Cannot inspect native ROM storage: {error}"))?;
            let filename = entry.file_name();
            if filename.to_string_lossy().starts_with(&prefix)
                && entry
                    .file_type()
                    .map_err(|error| format!("Cannot inspect native ROM storage: {error}"))?
                    .is_file()
            {
                fs::remove_file(entry.path())
                    .map_err(|error| format!("Cannot remove local ROM: {error}"))?;
            }
        }
        Ok(())
    })
    .await
    .map_err(|error| format!("Native ROM removal failed: {error}"))?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                controller_host::stop();
            }
            #[cfg(any(target_os = "windows", target_os = "linux"))]
            if matches!(event, tauri::WindowEvent::Destroyed) && window.label() == "main" {
                let _ = stop_native_game(window.app_handle().clone());
            }
            #[cfg(not(any(target_os = "windows", target_os = "linux")))]
            let _ = (window, event);
        })
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            pick_and_import_native_rom,
            remove_native_rom,
            native_capabilities,
            start_native_game,
            stop_native_game,
            set_native_input,
            native_controller_start,
            native_controller_stop,
            native_controller_status
        ])
        .setup(|_app| {
            // Desktop uses the Rust loopback server to stream private ROMs
            // directly from disk instead of copying multi-gigabyte files into
            // browser storage.
            #[cfg(not(mobile))]
            {
                let runtime =
                    start_runtime_server(&_app.handle()).map_err(std::io::Error::other)?;
                _app.get_webview_window("main")
                    .ok_or_else(|| {
                        std::io::Error::new(
                            std::io::ErrorKind::NotFound,
                            "Native window is unavailable",
                        )
                    })?
                    .navigate(runtime)?;
            }
            #[cfg(mobile)]
            {
                // Android keeps its regular library UI at WebViewAssetLoader's
                // HTTPS origin. Its 3DS bridge delegates the selected file to
                // the native companion through a read-only content URI, so no
                // loopback service or WebView copy of a multi-gigabyte ROM is
                // created on mobile. The Activity owns the initial navigation.
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running VibeCodedEmulator");
}

#[cfg(test)]
mod tests {
    use super::{
        canonical_extension_for_system, native_rom_request_parts, native_system_from_extension,
    };

    const ROM_ID: &str = "01234567-89ab-cdef-0123-456789abcdef";

    #[test]
    fn native_rom_request_keeps_a_safe_content_extension() {
        assert_eq!(
            native_rom_request_parts(&format!("{ROM_ID}.gba")),
            Some((ROM_ID, Some("gba")))
        );
        assert_eq!(native_rom_request_parts(ROM_ID), Some((ROM_ID, None)));
    }

    #[test]
    fn native_rom_request_rejects_untrusted_suffixes() {
        assert_eq!(
            native_rom_request_parts(&format!("{ROM_ID}.gba/../nds")),
            None
        );
        assert_eq!(native_rom_request_parts(&format!("{ROM_ID}.")), None);
        assert_eq!(native_rom_request_parts("not-a-rom"), None);
    }

    #[test]
    fn native_rom_system_detection_covers_gba_nds_and_3ds_file_types() {
        assert_eq!(native_system_from_extension("GBA"), Some("gba"));
        assert_eq!(native_system_from_extension("nds"), Some("nds"));
        assert_eq!(native_system_from_extension("cia"), None);
        assert_eq!(native_system_from_extension("3dsx"), Some("3ds"));
        assert_eq!(native_system_from_extension("z3dsx"), Some("3ds"));
        assert_eq!(canonical_extension_for_system("gba"), Some("gba"));
        assert_eq!(canonical_extension_for_system("nds"), Some("nds"));
        assert_eq!(canonical_extension_for_system("3ds"), Some("3ds"));
    }
}

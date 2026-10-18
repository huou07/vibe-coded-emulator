// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Local native-ROM catalog support for the installed player.

use std::{
    collections::HashMap,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::{Mutex, OnceLock},
    time::{SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

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

fn read_cache(path: &Path) -> HashMap<String, ContentIdentity> {
    let mut input = String::new();
    File::open(path)
        .and_then(|mut file| file.read_to_string(&mut input))
        .ok()
        .and_then(|_| serde_json::from_str(&input).ok())
        .unwrap_or_default()
}

fn write_cache(path: &Path, value: &HashMap<String, ContentIdentity>) {
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return;
        }
    }
    let temporary = path.with_extension("part");
    let Ok(bytes) = serde_json::to_vec_pretty(value) else {
        return;
    };
    let mut options = OpenOptions::new();
    options.create(true).truncate(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let Ok(mut output) = options.open(&temporary) else {
        return;
    };
    if output.write_all(&bytes).is_err() || output.flush().is_err() {
        return;
    }
    drop(output);
    let _ = fs::rename(temporary, path);
}

fn mtime_nanos(metadata: &fs::Metadata) -> u64 {
    metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map(|duration| duration.as_nanos().min(u64::MAX as u128) as u64)
        .unwrap_or(0)
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut input = File::open(path).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = input.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn cached_sha256_file(app_dir: &Path, path: &Path) -> Result<String, String> {
    let metadata = fs::metadata(path).map_err(|error| error.to_string())?;
    let size = metadata.len();
    let mtime = mtime_nanos(&metadata);
    let key = path.to_string_lossy().to_string();
    if let Ok(cache) = content_cache().lock() {
        if let Some(entry) = cache.get(&key) {
            if entry.size == size && entry.mtime == mtime {
                return Ok(entry.sha256.clone());
            }
        }
    }

    let cache_path = identity_cache_file(app_dir);
    let mut merged = read_cache(&cache_path);
    if let Some(entry) = merged.get(&key) {
        if entry.size == size && entry.mtime == mtime {
            if let Ok(mut cache) = content_cache().lock() {
                cache.insert(key, entry.clone());
            }
            return Ok(entry.sha256.clone());
        }
    }

    let sha256 = sha256_file(path)?;
    let entry = ContentIdentity {
        size,
        mtime,
        sha256: sha256.clone(),
    };
    merged.insert(key.clone(), entry.clone());
    if let Ok(mut cache) = content_cache().lock() {
        cache.insert(key, entry);
    }
    write_cache(&cache_path, &merged);
    Ok(sha256)
}

pub fn prime_content_hash(app_dir: &Path, path: &Path, sha256: &str) {
    if sha256.len() != 64 || !sha256.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return;
    }
    let Ok(metadata) = fs::metadata(path) else {
        return;
    };
    let key = path.to_string_lossy().to_string();
    let entry = ContentIdentity {
        size: metadata.len(),
        mtime: mtime_nanos(&metadata),
        sha256: sha256.to_ascii_lowercase(),
    };
    let cache_path = identity_cache_file(app_dir);
    let mut merged = read_cache(&cache_path);
    merged.insert(key.clone(), entry.clone());
    if let Ok(mut cache) = content_cache().lock() {
        cache.insert(key, entry);
    }
    write_cache(&cache_path, &merged);
}

pub fn manifest(app_dir: &Path) -> Result<serde_json::Value, String> {
    let directory = app_dir.join("an3-roms");
    let mut items = Vec::new();
    if directory.exists() {
        for entry in fs::read_dir(&directory)
            .map_err(|error| error.to_string())?
            .flatten()
        {
            if !entry
                .file_type()
                .map_err(|error| error.to_string())?
                .is_file()
            {
                continue;
            }
            let filename = entry.file_name().to_string_lossy().to_string();
            let Some((rom_id, extension)) = filename.split_once('.') else {
                continue;
            };
            if crate::validate_rom_id(rom_id).is_err()
                || extension.is_empty()
                || filename != format!("{rom_id}.{}", extension.to_ascii_lowercase())
            {
                continue;
            }
            let Some(system) = crate::native_system_from_extension(extension) else {
                continue;
            };
            let path = entry.path();
            let size = fs::metadata(&path)
                .map_err(|error| error.to_string())?
                .len();
            if size == 0 {
                continue;
            }
            let content_hash = cached_sha256_file(app_dir, &path)?;
            items.push(serde_json::json!({
                "romId": rom_id,
                "extension": extension,
                "system": system,
                "name": filename,
                "size": size,
                "contentHash": content_hash,
            }));
        }
    }
    items.sort_by(|left, right| {
        left.get("romId")
            .and_then(|value| value.as_str())
            .cmp(&right.get("romId").and_then(|value| value.as_str()))
    });
    Ok(serde_json::json!({ "items": items }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_directory() -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!(
            "an3-native-rom-library-{}-{unique}",
            std::process::id()
        ))
    }

    #[test]
    fn local_manifest_lists_supported_roms_and_caches_their_hash() {
        let root = temporary_directory();
        let roms = root.join("an3-roms");
        fs::create_dir_all(&roms).unwrap();
        let rom = roms.join("11111111-1111-1111-1111-111111111111.gba");
        fs::write(&rom, b"local gba fixture").unwrap();
        fs::write(roms.join("notes.txt"), b"not a ROM").unwrap();

        let manifest = manifest(&root).unwrap();
        let items = manifest["items"].as_array().unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0]["system"], "gba");
        assert_eq!(items[0]["name"], "11111111-1111-1111-1111-111111111111.gba");
        assert_eq!(
            items[0]["contentHash"],
            format!("{:x}", Sha256::digest(b"local gba fixture"))
        );
        assert!(identity_cache_file(&root).is_file());

        fs::remove_dir_all(root).unwrap();
    }
}

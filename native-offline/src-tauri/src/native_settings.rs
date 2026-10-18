// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
use serde_json::{json, Map, Value};
use std::{collections::BTreeMap, fs, path::Path};

const MODEL: &str = include_str!("../../shared/native-settings-model.json");

fn model() -> Result<Value, String> {
    serde_json::from_str(MODEL).map_err(|error| format!("Invalid native settings model: {error}"))
}

fn definitions(model: &Value) -> BTreeMap<String, Value> {
    let mut result = BTreeMap::new();
    let Some(systems) = model["systems"].as_array() else {
        return result;
    };
    for definition in model["global"].as_array().into_iter().flatten() {
        if definition["external"] == true {
            let key = definition["storageKey"]
                .as_str()
                .unwrap_or_else(|| definition["id"].as_str().unwrap_or(""));
            if !key.is_empty() {
                result.insert(key.to_string(), definition.clone());
            }
        }
    }
    for system in systems.iter().filter_map(Value::as_str) {
        for definition in model["graphics"][system]
            .as_array()
            .into_iter()
            .flatten()
            .chain(model["emulation"][system].as_array().into_iter().flatten())
        {
            if definition["external"] != true {
                continue;
            }
            let key = definition["storageKey"]
                .as_str()
                .map(str::to_owned)
                .unwrap_or_else(|| format!("{}-{system}", definition["id"].as_str().unwrap_or("")));
            if !key.ends_with('-') {
                result.insert(key, definition.clone());
            }
        }
    }
    result
}

fn fallback(definition: &Value) -> Value {
    if !definition["default"].is_null() {
        return definition["default"].clone();
    }
    definition["values"]
        .as_array()
        .and_then(|values| values.first())
        .cloned()
        .unwrap_or(Value::Null)
}

fn valid(definition: &Value, value: &Value) -> Option<Value> {
    let text = value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string());
    match definition["type"].as_str()? {
        "enum"
            if definition["values"]
                .as_array()?
                .iter()
                .any(|entry| entry.as_str() == Some(text.as_str())) =>
        {
            Some(Value::String(text))
        }
        "bool" if text == "true" || text == "false" => Some(Value::String(text)),
        "int" => {
            let number = text.parse::<i64>().ok()?;
            let min = definition["min"].as_i64()?;
            let max = definition["max"].as_i64()?;
            (number >= min && number <= max).then(|| Value::String(number.to_string()))
        }
        "string" => Some(Value::String(text)),
        _ => None,
    }
}

fn read_store(path: &Path) -> Result<Map<String, Value>, String> {
    match fs::read(path) {
        Ok(bytes) => serde_json::from_slice(&bytes)
            .map_err(|error| format!("Cannot read native settings: {error}")),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(Map::new()),
        Err(error) => Err(format!("Cannot read native settings: {error}")),
    }
}

fn write_store(path: &Path, store: &Map<String, Value>) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or("Native settings path has no parent directory")?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("Cannot create native settings directory: {error}"))?;
    let temporary = path.with_extension("json.tmp");
    let bytes = serde_json::to_vec_pretty(store).map_err(|error| error.to_string())?;
    fs::write(&temporary, bytes)
        .map_err(|error| format!("Cannot write native settings: {error}"))?;
    fs::rename(&temporary, path).map_err(|error| format!("Cannot save native settings: {error}"))
}

fn read_action(
    path: &Path,
    model: &Value,
    defs: &BTreeMap<String, Value>,
) -> Result<Value, String> {
    let stored = read_store(path)?;
    let mut global = Map::new();
    for definition in model["global"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|d| d["external"] == true)
    {
        let key = definition["storageKey"]
            .as_str()
            .unwrap_or_else(|| definition["id"].as_str().unwrap_or(""));
        let value = stored
            .get(key)
            .and_then(|value| valid(definition, value))
            .unwrap_or_else(|| fallback(definition));
        if !key.is_empty() {
            global.insert(definition["id"].as_str().unwrap_or(key).into(), value);
        }
    }
    let mut systems = Map::new();
    for system in model["systems"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
    {
        let mut values = Map::new();
        for definition in model["graphics"][system]
            .as_array()
            .into_iter()
            .flatten()
            .chain(model["emulation"][system].as_array().into_iter().flatten())
            .filter(|d| d["external"] == true)
        {
            let key = definition["storageKey"]
                .as_str()
                .map(str::to_owned)
                .unwrap_or_else(|| format!("{}-{system}", definition["id"].as_str().unwrap_or("")));
            if let Some(known) = defs.get(&key) {
                let value = stored
                    .get(&key)
                    .and_then(|value| valid(known, value))
                    .unwrap_or_else(|| fallback(known));
                values.insert(definition["id"].as_str().unwrap_or(&key).into(), value);
            }
        }
        systems.insert(system.into(), Value::Object(values));
    }
    Ok(json!({"global": global, "systems": systems, "unavailable": {}}))
}

pub(crate) fn execute(
    path: &Path,
    action: &str,
    system: Option<&str>,
    edits: Option<Map<String, Value>>,
) -> Result<Value, String> {
    let model = model()?;
    let defs = definitions(&model);
    match action {
        "all" => read_action(path, &model, &defs),
        "save" => {
            let mut store = read_store(path)?;
            let mut saved = Vec::new();
            let mut rejected = Vec::new();
            for (key, value) in edits.unwrap_or_default() {
                match defs
                    .get(&key)
                    .filter(|definition| definition["editable"] != false)
                    .and_then(|definition| valid(definition, &value))
                {
                    Some(value) => {
                        store.insert(key.clone(), value);
                        saved.push(Value::String(key));
                    }
                    None => rejected.push(Value::String(key)),
                }
            }
            write_store(path, &store)?;
            Ok(json!({"ok": rejected.is_empty(), "saved": saved, "rejected": rejected}))
        }
        "reset-graphics" => {
            let system = system.ok_or("System is required")?;
            if !model["systems"]
                .as_array()
                .is_some_and(|systems| systems.iter().any(|value| value == system))
            {
                return Err("Unknown system".into());
            }
            let mut store = read_store(path)?;
            let mut saved = Vec::new();
            for definition in model["graphics"][system]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|d| d["external"] == true)
            {
                let key = definition["storageKey"]
                    .as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| {
                        format!("{}-{system}", definition["id"].as_str().unwrap_or(""))
                    });
                store.insert(key.clone(), fallback(definition));
                saved.push(Value::String(key));
            }
            write_store(path, &store)?;
            Ok(json!({"ok": true, "saved": saved}))
        }
        _ => Err("Unknown native settings action".into()),
    }
}

fn saved_launch_values(path: &Path, system: &str) -> Result<Vec<(String, String)>, String> {
    let model = model()?;
    if !model["systems"]
        .as_array()
        .is_some_and(|systems| systems.iter().any(|value| value == system))
    {
        return Err("Unknown system".into());
    }
    let stored = read_store(path)?;
    let mut values = Vec::new();
    for definition in model["graphics"][system]
        .as_array()
        .into_iter()
        .flatten()
        .chain(model["emulation"][system].as_array().into_iter().flatten())
        .filter(|definition| definition["external"] == true && definition["editable"] != false)
    {
        let id = definition["id"].as_str().unwrap_or("");
        if id.is_empty() {
            continue;
        }
        let key = definition["storageKey"]
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| format!("{id}-{system}"));
        let Some(value) = stored.get(&key).and_then(|value| valid(definition, value)) else {
            continue;
        };
        let value = value
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| value.to_string());
        values.push((id.into(), value));
    }
    Ok(values)
}

/// Return only explicitly saved, editable launch settings for the selected
/// system. Reading a launch snapshot must not replace host defaults with model
/// fallbacks, and pinned options must remain owned by the runtime adapter.
pub(crate) fn launch_arguments(path: &Path, system: &str) -> Result<Vec<String>, String> {
    let mut args = Vec::new();
    for (id, value) in saved_launch_values(path, system)? {
        match id.as_str() {
            "renderer" => args.extend(["--renderer".into(), value]),
            "screen-layout" => args.extend(["--layout".into(), value]),
            _ => args.extend(["--core-option".into(), format!("{id}={value}")]),
        }
    }
    Ok(args)
}

pub(crate) fn launch_core_options(
    path: &Path,
    system: &str,
) -> Result<Vec<(String, String)>, String> {
    Ok(saved_launch_values(path, system)?
        .into_iter()
        .filter(|(id, _)| id != "renderer" && id != "screen-layout")
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_path() -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "an3-settings-{}-{}.json",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn settings_are_validated_scoped_and_persistent() {
        let path = temp_path();
        let mut edits = Map::new();
        edits.insert("renderer-gba".into(), Value::String("opengl".into()));
        edits.insert("renderer-nds".into(), Value::String("vulkan".into()));
        edits.insert("volume".into(), Value::String("75".into()));
        edits.insert("volume".into(), Value::String("101".into()));
        edits.insert(
            "core-3ds-citra_graphics_api".into(),
            Value::String("invalid".into()),
        );
        let saved = execute(&path, "save", None, Some(edits)).unwrap();
        assert_eq!(saved["ok"], false);
        assert!(saved["rejected"].as_array().unwrap().len() >= 2);
        let all = execute(&path, "all", None, None).unwrap();
        assert_eq!(all["systems"]["gba"]["renderer"], "opengl");
        assert_eq!(all["systems"]["nds"]["renderer"], "vulkan");
        assert_eq!(all["global"]["volume"], "100");
        let _ = fs::remove_file(path);
    }

    #[test]
    fn reset_graphics_changes_only_the_selected_system() {
        let path = temp_path();
        let mut edits = Map::new();
        edits.insert("renderer-gba".into(), Value::String("opengl".into()));
        edits.insert("renderer-nds".into(), Value::String("vulkan".into()));
        execute(&path, "save", None, Some(edits)).unwrap();
        execute(&path, "reset-graphics", Some("gba"), None).unwrap();
        let all = execute(&path, "all", None, None).unwrap();
        assert_eq!(all["systems"]["gba"]["renderer"], "auto");
        assert_eq!(all["systems"]["nds"]["renderer"], "vulkan");
        let _ = fs::remove_file(path);
    }

    #[test]
    fn launch_arguments_include_only_saved_editable_settings_for_one_system() {
        let path = temp_path();
        execute(
            &path,
            "save",
            None,
            Some(
                serde_json::from_value(json!({
                    "renderer-gba": "opengl",
                    "core-gba-mgba_frameskip": "auto",
                    "renderer-nds": "vulkan",
                    "core-nds-melonds_audio_bitdepth": "16bit",
                    "screen-layout-nds": "bottom-top",
                    "core-nds-melonds_render_mode": "opengl"
                }))
                .unwrap(),
            ),
        )
        .unwrap();
        assert_eq!(
            launch_arguments(&path, "gba").unwrap(),
            vec![
                "--renderer".to_string(),
                "opengl".to_string(),
                "--core-option".to_string(),
                "mgba_frameskip=auto".to_string()
            ]
        );
        assert_eq!(
            launch_arguments(&path, "nds").unwrap(),
            vec![
                "--renderer".to_string(),
                "vulkan".to_string(),
                "--layout".to_string(),
                "bottom-top".to_string(),
                "--core-option".to_string(),
                "melonds_audio_bitdepth=16bit".to_string()
            ]
        );
        assert_eq!(
            launch_core_options(&path, "gba").unwrap(),
            vec![("mgba_frameskip".into(), "auto".into())]
        );
        let _ = fs::remove_file(path);
    }
}

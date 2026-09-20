// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Shared direct-LAN peer protocol constants and discovery validation.
//!
//! This module deliberately contains no product-server URL, account address,
//! access token, or filesystem behavior.  Installed AN3 peers advertise only
//! enough information to find a local listener; the authenticated session
//! decides whether the peer is allowed to use a capability.

use serde::Deserialize;

pub const SERVICE: &str = "an3-peer";
pub const PROTOCOL_VERSION: u32 = 1;
pub const DISCOVERY_ADDRESS: &str = "239.255.43.3";
pub const DISCOVERY_PORT: u16 = 47831;
pub const CONTROL_PORT: u16 = 47832;
pub const CAPABILITIES: [&str; 2] = ["controller", "sync"];

#[derive(Debug, Deserialize, PartialEq, Eq)]
pub struct Advertisement {
    pub service: String,
    #[serde(rename = "v")]
    pub version: u32,
    pub id: String,
    pub name: String,
    pub port: u16,
    pub capabilities: Vec<String>,
}

pub fn advertisement(id: &str, name: &str, port: u16) -> serde_json::Value {
    advertisement_with_capabilities(id, name, port, &CAPABILITIES)
}

pub fn advertisement_with_capabilities(
    id: &str,
    name: &str,
    port: u16,
    capabilities: &[&str],
) -> serde_json::Value {
    serde_json::json!({
        "an3": "peer",
        "service": SERVICE,
        "v": PROTOCOL_VERSION,
        "id": id,
        "name": name,
        "port": port,
        "capabilities": capabilities,
    })
}

/// Validate only the public, non-sensitive discovery envelope.  Account
/// compatibility is intentionally a direct-session handshake concern, never a
/// multicast field.
pub fn parse_advertisement(value: &serde_json::Value) -> Result<Advertisement, &'static str> {
    if value.get("an3").and_then(|item| item.as_str()) != Some("peer") {
        return Err("not an AN3 peer advertisement");
    }
    let advertisement: Advertisement = serde_json::from_value(value.clone())
        .map_err(|_| "malformed AN3 peer advertisement")?;
    if advertisement.service != SERVICE || advertisement.version != PROTOCOL_VERSION {
        return Err("incompatible AN3 peer protocol");
    }
    if advertisement.id.is_empty()
        || advertisement.id.len() > 128
        || advertisement.name.len() > 64
        || advertisement.port == 0
        || advertisement.capabilities.iter().any(|capability| {
            !CAPABILITIES.contains(&capability.as_str())
        })
    {
        return Err("invalid AN3 peer advertisement");
    }
    Ok(advertisement)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discovery_envelope_has_no_account_or_credential_fields() {
        let value = advertisement("device-1", "Desktop", CONTROL_PORT);
        let object = value.as_object().unwrap();
        assert!(!object.keys().any(|key| {
            matches!(key.as_str(), "account" | "email" | "token" | "accessToken")
        }));
        assert_eq!(parse_advertisement(&value).unwrap().service, SERVICE);
    }

    #[test]
    fn incompatible_or_unknown_capabilities_are_rejected() {
        let mut value = advertisement("device-1", "Desktop", CONTROL_PORT);
        value["v"] = serde_json::json!(99);
        assert!(parse_advertisement(&value).is_err());
        value["v"] = serde_json::json!(PROTOCOL_VERSION);
        value["capabilities"] = serde_json::json!(["unknown"]);
        assert!(parse_advertisement(&value).is_err());
    }

    #[test]
    fn a_host_advertises_only_the_capabilities_it_serves() {
        let value = advertisement_with_capabilities("device-1", "Desktop", CONTROL_PORT, &["controller"]);
        assert_eq!(value["capabilities"], serde_json::json!(["controller"]));
        assert_eq!(parse_advertisement(&value).unwrap().capabilities, vec!["controller"]);
    }
}

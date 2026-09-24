// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Shared direct-LAN peer protocol constants and discovery validation.
//!
//! This module deliberately contains no product-server URL, account address,
//! access token, or filesystem behavior.  Installed AN3 peers advertise only
//! enough information to find a local listener; the authenticated session
//! decides whether the peer is allowed to use a capability.

use std::net::{Ipv4Addr, SocketAddr, UdpSocket};

use serde::Deserialize;
use socket2::{Domain, Protocol, Socket, Type};

pub const SERVICE: &str = "an3-peer";
pub const PROTOCOL_VERSION: u32 = 1;
pub const DISCOVERY_ADDRESS: &str = "239.255.43.3";
pub const DISCOVERY_BROADCAST: &str = "255.255.255.255";
pub const DISCOVERY_PORT: u16 = 47831;
pub const CONTROL_PORT: u16 = 47832;
pub const SYNC_PORT: u16 = 47833;
pub const CAPABILITIES: [&str; 2] = ["controller", "sync"];

/// Create a multicast discovery socket with the reuse flags required by
/// macOS and Android. Binding the discovery port (instead of an ephemeral
/// port) is intentional: those platforms deliver LAN multicast reliably only
/// when the receiver is bound to the advertised discovery port. Reuse keeps
/// Sync and Controller discovery from claiming the shared envelope.
pub fn discovery_socket(port: u16) -> std::io::Result<UdpSocket> {
    let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    socket.set_reuse_address(true)?;
    #[cfg(unix)]
    socket.set_reuse_port(true)?;
    socket.bind(&SocketAddr::from((Ipv4Addr::UNSPECIFIED, port)).into())?;
    Ok(socket.into())
}

/// Ask the OS which IPv4 interface it would use for the local discovery
/// group. This is a route lookup only; no packet is sent and no fixed LAN
/// address is assumed. Binding discovery sockets to this address prevents a
/// down cellular/virtual interface from silently winning on Android or a
/// multi-interface desktop.
pub fn local_lan_ipv4() -> Option<std::net::Ipv4Addr> {
    let socket = std::net::UdpSocket::bind((std::net::Ipv4Addr::UNSPECIFIED, 0)).ok()?;
    socket.connect((DISCOVERY_ADDRESS, DISCOVERY_PORT)).ok()?;
    match socket.local_addr().ok()?.ip() {
        std::net::IpAddr::V4(address) if !address.is_loopback() => Some(address),
        _ => None,
    }
}

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

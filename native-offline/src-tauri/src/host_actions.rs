// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Canonical, authenticated Phone Controller host actions.
//!
//! Gameplay snapshots and one-shot host operations share the encrypted
//! controller frame, but they do not have the same semantics.  This module is
//! the small boundary between the transport adapters and the native player:
//! it normalizes the action name, validates the optional save slot, and keeps a
//! bounded command-id replay window.  A command is considered delivered only
//! when the platform sink reports that it actually performed the operation.

use std::collections::HashSet;

use serde_json::Value;

pub(crate) const FIRST_SAVE_SLOT: u8 = 1;
pub(crate) const LAST_SAVE_SLOT: u8 = 10;
const MAX_COMMAND_ID_BYTES: usize = 128;
const MAX_SEEN_COMMANDS: usize = 64;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct HostAction {
    pub action: String,
    pub command_id: String,
    pub slot: u8,
    /// The legacy numeric sequence is retained for the staging acknowledgement
    /// API. Direct LAN peers use `command_id` as the replay identity.
    pub sequence: i64,
}

impl HostAction {
    fn from_entry(entry: &Value) -> Option<Self> {
        let object = entry.as_object()?;
        let action = object
            .get("action")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_ascii_uppercase();
        if action.len() > MAX_COMMAND_ID_BYTES {
            return None;
        }
        let sequence = object
            .get("sequence")
            .and_then(Value::as_i64)
            .unwrap_or(0);
        let command_id = object
            .get("command_id")
            .or_else(|| object.get("commandId"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| {
                if sequence > 0 {
                    format!("legacy:{sequence}")
                } else {
                    String::new()
                }
            });
        if command_id.len() > MAX_COMMAND_ID_BYTES || !command_id.is_ascii() {
            return None;
        }
        let slot = match object.get("slot") {
            None => FIRST_SAVE_SLOT,
            Some(value) => value
                .as_u64()
                .and_then(|value| u8::try_from(value).ok())
                .or_else(|| value.as_str().and_then(|value| value.parse::<u8>().ok()))
                .filter(|value| (FIRST_SAVE_SLOT..=LAST_SAVE_SLOT).contains(value))?,
        };
        Some(Self { action, command_id, slot, sequence })
    }

}

#[derive(Debug, Default)]
pub(crate) struct ReplayGuard {
    last_legacy_sequence: i64,
    seen_command_ids: HashSet<String>,
}

impl ReplayGuard {
    pub(crate) fn reset(&mut self) {
        self.last_legacy_sequence = 0;
        self.seen_command_ids.clear();
    }

    fn accept(&mut self, command: &HostAction) -> bool {
        // Old staging clients do not send command_id. Preserve their strictly
        // increasing sequence semantics while making the new direct-LAN path
        // idempotent by the explicit command identity.
        if command.command_id.starts_with("legacy:") {
            if command.sequence <= 0 || command.sequence <= self.last_legacy_sequence {
                return false;
            }
            self.last_legacy_sequence = command.sequence;
            return true;
        }
        if command.command_id.is_empty() || !self.seen_command_ids.insert(command.command_id.clone()) {
            return false;
        }
        self.last_legacy_sequence = self.last_legacy_sequence.max(command.sequence);
        if self.seen_command_ids.len() > MAX_SEEN_COMMANDS {
            // Command IDs are session-scoped. Keeping the most recent bounded
            // window is enough to reject retransmits without allowing an
            // authenticated peer to grow host memory indefinitely.
            if let Some(oldest) = self.seen_command_ids.iter().next().cloned() {
                self.seen_command_ids.remove(&oldest);
            }
        }
        true
    }
}

pub(crate) fn dispatch(
    payload: &Value,
    replay: &mut ReplayGuard,
    sink: &dyn Fn(&HostAction) -> bool,
) -> i64 {
    let mut executed = 0_i64;
    for key in ["utilities", "u"] {
        let Some(entries) = payload.get(key).and_then(Value::as_array) else {
            continue;
        };
        for entry in entries {
            let Some(command) = HostAction::from_entry(entry) else {
                continue;
            };
            if !replay.accept(&command) {
                continue;
            }
            if sink(&command) {
                executed = executed.max(command.sequence);
            }
        }
    }
    executed
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_slot_and_command_id_without_accepting_out_of_range_slots() {
        let value = serde_json::json!({
            "action": "quick_save",
            "command_id": "phone-session-7",
            "sequence": 7,
            "slot": 10
        });
        let action = HostAction::from_entry(&value).expect("valid action");
        assert_eq!(action.action, "QUICK_SAVE");
        assert_eq!(action.command_id, "phone-session-7");
        assert_eq!(action.slot, 10);
        assert!(HostAction::from_entry(&serde_json::json!({
            "action": "QUICK_LOAD", "command_id": "bad", "slot": 11
        })).is_none());
    }

    #[test]
    fn command_id_replay_is_exact_and_bounded() {
        let mut replay = ReplayGuard::default();
        let command = HostAction::from_entry(&serde_json::json!({
            "action": "OPEN_MENU", "command_id": "same", "sequence": 1
        })).unwrap();
        assert!(replay.accept(&command));
        assert!(!replay.accept(&command));
        let different = HostAction::from_entry(&serde_json::json!({
            "action": "OPEN_MENU", "command_id": "different", "sequence": 1
        })).unwrap();
        assert!(replay.accept(&different));
    }
}

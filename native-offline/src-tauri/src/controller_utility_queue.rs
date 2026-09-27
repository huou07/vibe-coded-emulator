// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded bridge for discrete controller actions consumed by the native frame
//! owner. Normal controller state never enters this queue.

use std::{
    collections::VecDeque,
    ffi::CStr,
    os::raw::{c_char, c_int},
    ptr,
    sync::{Condvar, Mutex, OnceLock},
};

pub(crate) const MAX_PENDING_CONTROLLER_UTILITIES: usize = 16;
const MAX_COMPLETED_CONTROLLER_UTILITIES: usize = 64;
const MAX_COMMAND_ID_BYTES: usize = 128;
const MAX_RESULT_MESSAGE_CHARS: usize = 256;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct ControllerUtility {
    pub(crate) action: u32,
    pub(crate) slot: u32,
    pub(crate) command_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ControllerUtilityResult {
    pub(crate) command_id: String,
    pub(crate) action: String,
    pub(crate) slot: u8,
    pub(crate) success: bool,
    pub(crate) message: String,
}

#[derive(Default)]
struct Queue {
    accepting: bool,
    waiting_producers: usize,
    items: VecDeque<ControllerUtility>,
}

fn shared() -> &'static (Mutex<Queue>, Condvar) {
    static QUEUE: OnceLock<(Mutex<Queue>, Condvar)> = OnceLock::new();
    QUEUE.get_or_init(|| (Mutex::new(Queue::default()), Condvar::new()))
}

fn encode_action(action: &str, slot: u8, command_id: &str) -> Result<ControllerUtility, String> {
    if command_id.is_empty()
        || command_id.len() > MAX_COMMAND_ID_BYTES
        || !command_id.bytes().all(|byte| (0x20..=0x7e).contains(&byte))
    {
        return Err("The controller utility command ID is invalid.".into());
    }
    let action = match action {
        "QUICK_SAVE" if (1..=10).contains(&slot) => 1,
        "QUICK_LOAD" if (1..=10).contains(&slot) => 2,
        "SPEED_UP" => 3,
        "SPEED_DOWN" => 4,
        "OPEN_MENU" => 5,
        "QUICK_SAVE" | "QUICK_LOAD" => {
            return Err("Save-state slot must be between 1 and 10.".into())
        }
        _ => return Err(format!("Unsupported controller utility action '{action}'.")),
    };
    Ok(ControllerUtility {
        action,
        slot: slot as u32,
        command_id: command_id.to_string(),
    })
}

pub(crate) fn enqueue(action: &str, slot: u8, command_id: &str) -> Result<(), String> {
    let item = encode_action(action, slot, command_id)?;
    let (lock, available) = shared();
    let mut queue = lock
        .lock()
        .map_err(|_| "Controller utility queue is unavailable.".to_string())?;
    while queue.accepting && queue.items.len() >= MAX_PENDING_CONTROLLER_UTILITIES {
        queue.waiting_producers += 1;
        queue = available
            .wait(queue)
            .map_err(|_| "Controller utility queue is unavailable.".to_string())?;
        queue.waiting_producers -= 1;
    }
    if !queue.accepting {
        return Err("The native game is stopping; the controller utility was not accepted.".into());
    }
    queue.items.push_back(item);
    Ok(())
}

fn set_accepting(accepting: bool) {
    let (lock, available) = shared();
    if let Ok(mut queue) = lock.lock() {
        queue.accepting = accepting;
        available.notify_all();
    }
}

fn take() -> Option<ControllerUtility> {
    let (lock, available) = shared();
    let mut queue = lock.lock().ok()?;
    let item = queue.items.pop_front();
    if item.is_some() {
        available.notify_one();
    }
    item
}

fn completed_shared() -> &'static Mutex<VecDeque<ControllerUtilityResult>> {
    static COMPLETED: OnceLock<Mutex<VecDeque<ControllerUtilityResult>>> = OnceLock::new();
    COMPLETED.get_or_init(|| Mutex::new(VecDeque::new()))
}

fn action_name(action: u32) -> Option<&'static str> {
    match action {
        1 => Some("QUICK_SAVE"),
        2 => Some("QUICK_LOAD"),
        3 => Some("SPEED_UP"),
        4 => Some("SPEED_DOWN"),
        5 => Some("OPEN_MENU"),
        _ => None,
    }
}

fn action_code(action: &str) -> Option<u32> {
    match action {
        "QUICK_SAVE" => Some(1),
        "QUICK_LOAD" => Some(2),
        "SPEED_UP" => Some(3),
        "SPEED_DOWN" => Some(4),
        "OPEN_MENU" => Some(5),
        _ => None,
    }
}

pub(crate) fn record_completed(
    command_id: &str,
    action: u32,
    slot: u32,
    success: bool,
    message: &str,
) {
    let Some(action) = action_name(action) else {
        return;
    };
    if command_id.is_empty()
        || command_id.len() > MAX_COMMAND_ID_BYTES
        || !command_id.bytes().all(|byte| (0x20..=0x7e).contains(&byte))
    {
        return;
    }
    let result = ControllerUtilityResult {
        command_id: command_id.to_string(),
        action: action.to_string(),
        slot: slot.min(u8::MAX as u32) as u8,
        success,
        message: message.chars().take(MAX_RESULT_MESSAGE_CHARS).collect(),
    };
    if let Ok(mut completed) = completed_shared().lock() {
        if completed.len() == MAX_COMPLETED_CONTROLLER_UTILITIES {
            completed.pop_front();
        }
        completed.push_back(result);
    }
}

pub(crate) fn record_rejected(command_id: &str, action: &str, slot: u8, message: &str) {
    if let Some(code) = action_code(action) {
        record_completed(command_id, code, slot as u32, false, message);
    }
}

pub(crate) fn take_completed() -> Vec<ControllerUtilityResult> {
    completed_shared()
        .lock()
        .map(|mut completed| completed.drain(..).collect())
        .unwrap_or_default()
}

/// Called by the native host after it has crossed a game lifecycle boundary.
#[no_mangle]
pub extern "C" fn an3_native_controller_utilities_accepting(accepting: c_int) {
    set_accepting(accepting != 0);
}

/// Called only while the native host owns its render/core boundary.
#[no_mangle]
pub extern "C" fn an3_native_take_controller_utility(
    action: *mut u32,
    slot: *mut u32,
    command_id: *mut c_char,
    command_id_capacity: usize,
) -> c_int {
    if action.is_null()
        || slot.is_null()
        || command_id.is_null()
        || command_id_capacity < MAX_COMMAND_ID_BYTES + 1
    {
        return -1;
    }
    let Some(item) = take() else { return 0 };
    // The native caller supplies valid pointers according to the C ABI.
    unsafe {
        *action = item.action;
        *slot = item.slot;
        let length = item.command_id.len();
        ptr::copy_nonoverlapping(item.command_id.as_ptr(), command_id.cast::<u8>(), length);
        *command_id.add(length) = 0;
    }
    1
}

/// Called only after the native frame owner or save worker has completed the
/// requested operation, including durable completion for asynchronous saves.
#[no_mangle]
pub extern "C" fn an3_native_controller_utility_completed(
    command_id: *const c_char,
    action: u32,
    slot: u32,
    success: c_int,
    message: *const c_char,
) {
    if command_id.is_null() {
        return;
    }
    let command_id = unsafe { CStr::from_ptr(command_id) }.to_string_lossy();
    let message = if message.is_null() {
        String::new()
    } else {
        unsafe { CStr::from_ptr(message) }
            .to_string_lossy()
            .into_owned()
    };
    record_completed(&command_id, action, slot, success != 0, &message);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        sync::{mpsc, MutexGuard},
        thread,
        time::{Duration, Instant},
    };

    static TEST_LOCK: Mutex<()> = Mutex::new(());

    fn reset() -> MutexGuard<'static, ()> {
        let guard = TEST_LOCK.lock().unwrap();
        let (lock, available) = shared();
        let mut queue = lock.lock().unwrap();
        queue.items.clear();
        queue.accepting = true;
        available.notify_all();
        drop(queue);
        completed_shared().lock().unwrap().clear();
        guard
    }

    #[test]
    fn discrete_utilities_remain_fifo_and_slots_are_preserved() {
        let _guard = reset();
        enqueue("QUICK_SAVE", 3, "save-3").unwrap();
        enqueue("OPEN_MENU", 1, "menu-1").unwrap();
        enqueue("QUICK_LOAD", 9, "load-9").unwrap();
        assert_eq!(
            take(),
            Some(ControllerUtility {
                action: 1,
                slot: 3,
                command_id: "save-3".into()
            })
        );
        assert_eq!(
            take(),
            Some(ControllerUtility {
                action: 5,
                slot: 1,
                command_id: "menu-1".into()
            })
        );
        assert_eq!(
            take(),
            Some(ControllerUtility {
                action: 2,
                slot: 9,
                command_id: "load-9".into()
            })
        );
        assert_eq!(take(), None);
    }

    #[test]
    fn queue_capacity_is_bounded_and_stop_releases_waiting_producers() {
        let _guard = reset();
        for index in 0..MAX_PENDING_CONTROLLER_UTILITIES {
            enqueue("SPEED_UP", 1, &format!("speed-{index}")).unwrap();
        }
        let (started, wait_started) = mpsc::channel();
        let producer = thread::spawn(move || {
            started.send(()).unwrap();
            enqueue("QUICK_SAVE", 1, "blocked-save")
        });
        wait_started.recv_timeout(Duration::from_secs(2)).unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        while shared().0.lock().unwrap().waiting_producers == 0 {
            assert!(
                Instant::now() < deadline,
                "producer should wait at the bounded queue limit"
            );
            thread::yield_now();
        }
        assert_eq!(
            shared().0.lock().unwrap().items.len(),
            MAX_PENDING_CONTROLLER_UTILITIES
        );
        an3_native_controller_utilities_accepting(0);
        assert!(enqueue("QUICK_SAVE", 1, "stopped-save").is_err());
        assert_eq!(
            shared().0.lock().unwrap().items.len(),
            MAX_PENDING_CONTROLLER_UTILITIES
        );
        assert!(producer.join().unwrap().is_err());
        let (lock, available) = shared();
        let mut queue = lock.lock().unwrap();
        queue.items.clear();
        available.notify_all();
    }

    #[test]
    fn action_and_slot_validation_happens_before_queueing() {
        let _guard = reset();
        assert!(enqueue("QUICK_SAVE", 0, "slot-zero").is_err());
        assert!(enqueue("QUICK_LOAD", 11, "slot-eleven").is_err());
        assert!(enqueue("NOT_A_COMMAND", 1, "unknown").is_err());
        assert!(enqueue("OPEN_MENU", 1, "").is_err());
        assert!(enqueue("OPEN_MENU", 1, "bad\0id").is_err());
        assert_eq!(shared().0.lock().unwrap().items.len(), 0);
    }

    #[test]
    fn c_abi_take_rejects_small_id_buffers_without_dequeueing() {
        let _guard = reset();
        enqueue("OPEN_MENU", 1, "phone-1").unwrap();
        let mut action = 0;
        let mut slot = 0;
        let mut command_id = [0; MAX_COMMAND_ID_BYTES];
        assert_eq!(
            an3_native_take_controller_utility(
                &mut action,
                &mut slot,
                command_id.as_mut_ptr(),
                command_id.len(),
            ),
            -1
        );
        assert_eq!(take().unwrap().command_id, "phone-1");

        enqueue("OPEN_MENU", 1, "phone-1").unwrap();
        let mut command_id = [0; MAX_COMMAND_ID_BYTES + 1];
        assert_eq!(
            an3_native_take_controller_utility(
                &mut action,
                &mut slot,
                command_id.as_mut_ptr(),
                command_id.len(),
            ),
            1
        );
        assert_eq!(
            unsafe { std::ffi::CStr::from_ptr(command_id.as_ptr()) }
                .to_str()
                .unwrap(),
            "phone-1"
        );
    }

    #[test]
    fn completion_results_preserve_identity_and_have_a_bounded_window() {
        let _guard = reset();
        record_completed("phone-7", 1, 3, true, "Quick save complete.");
        let first = take_completed();
        assert_eq!(first.len(), 1);
        assert_eq!(first[0].command_id, "phone-7");
        assert_eq!(first[0].action, "QUICK_SAVE");
        assert_eq!(first[0].slot, 3);
        assert!(first[0].success);
        assert_eq!(first[0].message, "Quick save complete.");

        for index in 0..=MAX_COMPLETED_CONTROLLER_UTILITIES {
            record_completed(&format!("phone-{index}"), 2, 10, false, "slot empty");
        }
        let recent = take_completed();
        assert_eq!(recent.len(), MAX_COMPLETED_CONTROLLER_UTILITIES);
        assert_eq!(recent.first().unwrap().command_id, "phone-1");
        assert_eq!(recent.last().unwrap().command_id, "phone-64");

        record_rejected("phone-rejected", "QUICK_LOAD", 10, "No native game is running.");
        let rejected = take_completed();
        assert_eq!(rejected.len(), 1);
        assert_eq!(rejected[0].command_id, "phone-rejected");
        assert_eq!(rejected[0].action, "QUICK_LOAD");
        assert_eq!(rejected[0].slot, 10);
        assert!(!rejected[0].success);
    }
}

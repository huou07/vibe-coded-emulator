// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounds handler threads created for accepted LAN connections.

use std::sync::atomic::{AtomicUsize, Ordering};

pub(crate) struct ConnectionLimit {
    max_active: usize,
    active: AtomicUsize,
}

impl ConnectionLimit {
    pub(crate) const fn new(max_active: usize) -> Self {
        Self {
            max_active,
            active: AtomicUsize::new(0),
        }
    }

    pub(crate) fn try_acquire(&self) -> Option<ConnectionPermit<'_>> {
        self.active
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |active| {
                (active < self.max_active).then_some(active + 1)
            })
            .ok()
            .map(|_| ConnectionPermit(self))
    }
}

pub(crate) struct ConnectionPermit<'a>(&'a ConnectionLimit);

impl Drop for ConnectionPermit<'_> {
    fn drop(&mut self) {
        self.0.active.fetch_sub(1, Ordering::Release);
    }
}

#[cfg(test)]
mod tests {
    use super::ConnectionLimit;

    #[test]
    fn active_handlers_are_bounded_and_capacity_returns_on_drop() {
        let limit = ConnectionLimit::new(2);
        let first = limit.try_acquire().expect("first slot");
        let second = limit.try_acquire().expect("second slot");
        assert!(limit.try_acquire().is_none());

        drop(first);
        let replacement = limit.try_acquire().expect("released slot");
        assert!(limit.try_acquire().is_none());

        drop(replacement);
        drop(second);
        let final_permit = limit.try_acquire().expect("all capacity is released");
        let second_final_permit = limit.try_acquire().expect("second slot is released");
        assert!(limit.try_acquire().is_none());
        drop(final_permit);
        drop(second_final_permit);
    }
}

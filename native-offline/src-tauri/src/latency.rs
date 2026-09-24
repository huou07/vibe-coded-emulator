// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//! Track B1: debug-only latency instrumentation for the phone-controller path.
//!
//! This module measures the *real* phone -> host -> core -> produced-frame
//! pipeline without changing input semantics. It is compiled in every build so
//! the call sites stay honest, but a run only records when it is explicitly
//! enabled by the ARTIFACT: `AN3_LATENCY_TRACE` with a bounded capacity and a
//! per-run token. No release UI enables it and a sampler that was never started
//! has zero overhead beyond a relaxed atomic load.
//!
//! Boundary discipline (do not subtract across devices without a shared clock):
//!
//! * T0 (phone capture) is echoed back inside the frame as `t0` on the phone's
//!   own `perf.now()` clock, so controller RTT is `phoneNow - t0` measured
//!   entirely on the phone. The host only transports the value.
//! * T3..T5 are captured on one host and one host clock only
//!   (`perf_counter`), so those intervals are directly subtractable.
//! * Input-to-frame is always reported as `T5 - T3`; it never claims a physical
//!   display saw the frame. `T5` is a *produced* frame, not a visible one.
//!
//! Every sample carries the phone `sequence`, so a measurement can never mix
//! two unrelated inputs. There is no unbounded growth: the ring drops into
//! counters once full, and no network acknowledgement is introduced.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Mutex;

/// Hard upper bound on retained samples. A full ring drops into `dropped` so a
/// long session can never grow the log or the heap without limit.
pub(crate) const MAX_SAMPLES: usize = 4096;

/// The five instrumented stages.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Stage {
    /// T3: the host decrypted and validated a phone gameplay frame.
    HostApplied,
    /// T1 (host receive timestamp, transport clock only, never phone clock).
    HostReceived,
}

/// One end-to-end latency sample for a single phone input sequence.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Sample {
    /// Phone frame sequence (`s`). The association key: samples never mix.
    pub sequence: u64,
    /// Phone monotonic capture time (ms). Used only to echo RTT on the phone.
    pub phone_t0: i64,
    /// Host monotonic time at frame receipt (`perf_counter`).
    pub host_received_ns: u64,
    /// Host monotonic time when the resolved input was handed to the core.
    pub host_applied_ns: u64,
    /// Core frame counter observed when the input was applied (produced-frame
    /// identity, not a display timestamp).
    pub frame_at_apply: u64,
    /// Host monotonic time when the first core frame after this input was
    /// produced. `0` while no frame has been produced yet.
    pub host_frame_ns: u64,
    /// Core frame counter at `host_frame_ns`.
    pub frame_after: u64,
}

impl Sample {
    /// Host-side processing latency: decryption/validation/handoff to core.
    /// Both timestamps come from this host's `perf_counter`, so this is a real
    /// interval, not a cross-device subtraction.
    pub fn host_processing_ns(&self) -> u64 {
        self.host_applied_ns.saturating_sub(self.host_received_ns)
    }

    /// Input-to-produced-frame latency on the host clock. This is the interval
    /// from handing the resolved input to the core until the first core frame
    /// was produced afterwards. It is *not* a display-latency claim.
    pub fn input_to_frame_ns(&self) -> Option<u64> {
        if self.host_frame_ns == 0 {
            None
        } else {
            Some(self.host_frame_ns.saturating_sub(self.host_applied_ns))
        }
    }

    /// Number of core frames that elapsed between applying the input and
    /// producing the next frame. 1 means the very next frame already carried
    /// it; a larger value means the input landed more than a frame behind.
    pub fn frames_to_apply(&self) -> Option<u64> {
        if self.host_frame_ns == 0 || self.frame_after < self.frame_at_apply {
            None
        } else {
            Some(self.frame_after.saturating_sub(self.frame_at_apply))
        }
    }
}

struct Trace {
    capacity: usize,
    samples: Vec<Sample>,
    dropped: u64,
    /// The newest sequence for which a sample is still open (waiting for the
    /// next produced frame). Only one input can be open at a time because the
    /// host applies frames one at a time in receive order.
    pending: Option<usize>,
}

static ENABLED: AtomicBool = AtomicBool::new(false);
static FRAMES_PRODUCED: AtomicU64 = AtomicU64::new(0);
static SAMPLES_TOTAL: AtomicU64 = AtomicU64::new(0);
static TRACE: Mutex<Option<Trace>> = Mutex::new(None);

/// Monotonic nanoseconds from the host clock. Never compared against a phone
/// timestamp.
pub(crate) fn host_now_ns() -> u64 {
    static START: std::sync::OnceLock<std::time::Instant> = std::sync::OnceLock::new();
    let start = START.get_or_init(std::time::Instant::now);
    start.elapsed().as_nanos() as u64
}

/// Enable tracing with a bounded capacity. Returns false when tracing is
/// already active, so a run has exactly one owner and cannot clear another
/// test's samples.
pub(crate) fn start(capacity: usize) -> bool {
    if ENABLED.load(Ordering::Acquire) {
        return false;
    }
    let capacity = capacity.clamp(1, MAX_SAMPLES);
    if let Ok(mut slot) = TRACE.lock() {
        *slot = Some(Trace {
            capacity,
            samples: Vec::with_capacity(capacity.min(256)),
            dropped: 0,
            pending: None,
        });
    }
    SAMPLES_TOTAL.store(0, Ordering::Relaxed);
    ENABLED.store(true, Ordering::Release);
    true
}

/// Disable tracing and return `(samples, dropped)`.
pub(crate) fn stop() -> (Vec<Sample>, u64) {
    ENABLED.store(false, Ordering::Release);
    // A stopped run owns no samples: reset the counter so a fresh check never
    // sees a previous run's totals.
    SAMPLES_TOTAL.store(0, Ordering::Relaxed);
    match TRACE.lock() {
        Ok(mut slot) => slot
            .take()
            .map(|trace| (trace.samples, trace.dropped))
            .unwrap_or_default(),
        Err(_) => (Vec::new(), 0),
    }
}

/// Whether tracing is currently active.
pub(crate) fn is_enabled() -> bool {
    ENABLED.load(Ordering::Relaxed)
}

/// Total samples recorded since the last `start` (bounded by capacity+drops).
pub(crate) fn samples_total() -> u64 {
    SAMPLES_TOTAL.load(Ordering::Relaxed)
}

/// Serializes every test that touches the process-global tracer, in this module
/// and in others (e.g. the real-transport measurement in `lan_host`), so a
/// parallel runner cannot start or stop a run mid-measurement.
#[cfg(test)]
pub(crate) fn test_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: Mutex<()> = Mutex::new(());
    LOCK.lock().unwrap_or_else(|poison| poison.into_inner())
}

fn record(sample: Sample) {
    SAMPLES_TOTAL.fetch_add(1, Ordering::Relaxed);
    let Ok(mut slot) = TRACE.lock() else { return };
    let Some(trace) = slot.as_mut() else { return };
    if trace.samples.len() >= trace.capacity {
        trace.dropped += 1;
        return;
    }
    trace.samples.push(sample);
}

/// T3: a gameplay frame was decrypted, validated and is about to be handed to
/// the core. `phone_t0` is echoed through unchanged; it is never interpreted on
/// the host clock. A later call with the same `sequence` does not create a
/// second sample (association is by sequence).
pub(crate) fn note_input_applied(sequence: u64, phone_t0: i64) {
    if !is_enabled() {
        return;
    }
    let now = host_now_ns();
    let frame = FRAMES_PRODUCED.load(Ordering::Relaxed);
    let Ok(mut slot) = TRACE.lock() else { return };
    let Some(trace) = slot.as_mut() else { return };
    if trace
        .samples
        .iter()
        .any(|existing| existing.sequence == sequence)
    {
        return;
    }
    if trace.samples.len() >= trace.capacity {
        trace.dropped += 1;
        return;
    }
    trace.pending = None;
    trace.samples.push(Sample {
        sequence,
        phone_t0,
        host_received_ns: now,
        host_applied_ns: now,
        frame_at_apply: frame,
        host_frame_ns: 0,
        frame_after: 0,
    });
    SAMPLES_TOTAL.fetch_add(1, Ordering::Relaxed);
}

/// T1: the host received the encrypted frame, before decryption. Kept separate
/// from T3 so transport and processing can be distinguished. Optional: if it is
/// never called the sample uses T3 as its receipt time.
pub(crate) fn note_frame_received(sequence: u64, phone_t0: i64) {
    if !is_enabled() {
        return;
    }
    let now = host_now_ns();
    let frame = FRAMES_PRODUCED.load(Ordering::Relaxed);
    let Ok(mut slot) = TRACE.lock() else { return };
    let Some(trace) = slot.as_mut() else { return };
    if trace
        .samples
        .iter()
        .any(|existing| existing.sequence == sequence)
    {
        return;
    }
    if trace.samples.len() >= trace.capacity {
        trace.dropped += 1;
        return;
    }
    trace.pending = Some(trace.samples.len());
    trace.samples.push(Sample {
        sequence,
        phone_t0,
        host_received_ns: now,
        host_applied_ns: now,
        frame_at_apply: frame,
        host_frame_ns: 0,
        frame_after: 0,
    });
    SAMPLES_TOTAL.fetch_add(1, Ordering::Relaxed);
}

/// T5: a core frame was produced. Closes the most recent open sample so the
/// next-frame interval is meaningful. Safe to call for every produced frame.
pub(crate) fn note_frame_produced() {
    let produced = FRAMES_PRODUCED.fetch_add(1, Ordering::Relaxed) + 1;
    close_pending(produced);
}

/// T5 with an authoritative core frame counter (e.g. the native player's
/// presented-frame count). The counter is stored verbatim so a caller can see
/// exactly which core frame carried the input.
pub(crate) fn note_frame_produced_at(core_frame: u64) {
    FRAMES_PRODUCED.store(core_frame, Ordering::Relaxed);
    close_pending(core_frame);
}

fn close_pending(produced: u64) {
    if !is_enabled() {
        return;
    }
    let now = host_now_ns();
    let Ok(mut slot) = TRACE.lock() else { return };
    let Some(trace) = slot.as_mut() else { return };
    let Some(index) = trace.pending.take() else {
        // Nothing is waiting on a frame; still attach to the newest applied
        // sample that has not seen a frame yet, if any.
        if let Some(last) = trace.samples.last_mut() {
            if last.host_frame_ns == 0 {
                last.host_frame_ns = now;
                last.frame_after = produced;
            }
        }
        return;
    };
    if let Some(sample) = trace.samples.get_mut(index) {
        sample.host_frame_ns = now;
        sample.frame_after = produced;
    }
}

/// A snapshot of the currently retained samples (for a live UI readout).
pub(crate) fn snapshot() -> Vec<Sample> {
    TRACE
        .lock()
        .ok()
        .and_then(|slot| slot.as_ref().map(|trace| trace.samples.clone()))
        .unwrap_or_default()
}

/// Percentile (0..=100) of a host-local interval in nanoseconds over the
/// retained samples that have a completed frame interval.
pub(crate) fn input_to_frame_percentile(percent: u64) -> Option<u64> {
    let mut values: Vec<u64> = snapshot()
        .iter()
        .filter_map(Sample::input_to_frame_ns)
        .collect();
    if values.is_empty() {
        return None;
    }
    values.sort_unstable();
    let index = ((values.len() - 1) as u64 * percent.clamp(0, 100) / 100) as usize;
    Some(values[index])
}

#[cfg(test)]
mod tests {
    use super::*;

    fn exclusive() -> std::sync::MutexGuard<'static, ()> {
        test_lock()
    }

    #[test]
    fn a_disabled_tracer_records_nothing() {
        let _guard = exclusive();
        let _ = stop();
        note_input_applied(1, 100);
        note_frame_produced();
        assert!(!is_enabled());
        assert_eq!(samples_total(), 0, "a disabled tracer must stay silent");
        let (samples, dropped) = stop();
        assert!(samples.is_empty());
        assert_eq!(dropped, 0);
    }

    #[test]
    fn events_are_associated_by_phone_sequence() {
        let _guard = exclusive();
        let _ = stop();
        assert!(start(64));
        note_input_applied(7, 1_000);
        note_input_applied(7, 1_000); // duplicate must not create a second sample
        note_input_applied(8, 1_100);
        let (samples, _) = stop();
        assert_eq!(samples.len(), 2, "one sample per distinct sequence");
        assert_eq!(samples[0].sequence, 7);
        assert_eq!(samples[1].sequence, 8);
        assert_eq!(samples[0].phone_t0, 1_000);
    }

    #[test]
    fn host_local_intervals_are_calculated_from_one_clock() {
        let _guard = exclusive();
        let _ = stop();
        assert!(start(64));
        note_input_applied(1, 0);
        // Force a measurable gap on the same host clock, then produce a frame.
        let spin_until = host_now_ns() + 2_000_000;
        while host_now_ns() < spin_until {}
        note_frame_produced();
        let (samples, _) = stop();
        assert_eq!(samples.len(), 1);
        let interval = samples[0]
            .input_to_frame_ns()
            .expect("a produced frame closes the interval");
        assert!(
            interval >= 2_000_000,
            "input-to-frame must use the host monotonic clock, got {interval} ns"
        );
        assert!(interval < 60_000_000_000, "interval must stay bounded");
    }

    #[test]
    fn a_frame_does_not_close_an_unrelated_open_input() {
        let _guard = exclusive();
        let _ = stop();
        assert!(start(64));
        note_input_applied(1, 0);
        note_frame_produced();
        note_frame_produced();
        let (samples, _) = stop();
        assert_eq!(samples.len(), 1, "produced frames must not invent samples");
        assert_eq!(samples[0].sequence, 1);
        assert!(samples[0].input_to_frame_ns().is_some());
    }

    #[test]
    fn the_ring_is_bounded_and_counts_drops() {
        let _guard = exclusive();
        let _ = stop();
        assert!(start(4));
        for sequence in 1..=10 {
            note_input_applied(sequence, 0);
        }
        let (samples, dropped) = stop();
        assert_eq!(samples.len(), 4, "capacity is a hard bound");
        assert_eq!(dropped, 6, "every dropped sample is counted, not stored");
    }

    #[test]
    fn a_second_start_does_not_clear_an_owned_run() {
        let _guard = exclusive();
        let _ = stop();
        assert!(start(16));
        note_input_applied(1, 0);
        assert!(!start(16), "a run has exactly one owner");
        let (samples, _) = stop();
        assert_eq!(samples.len(), 1, "the owner's sample survived");
    }

    #[test]
    fn percentiles_report_a_meaningful_distribution() {
        let _guard = exclusive();
        let _ = stop();
        assert!(start(256));
        for sequence in 1..=100u64 {
            note_input_applied(sequence, 0);
            let target = host_now_ns() + sequence * 100_000; // 0.1ms steps
            while host_now_ns() < target {}
            note_frame_produced();
        }
        let p50 = input_to_frame_percentile(50).expect("p50");
        let p99 = input_to_frame_percentile(99).expect("p99");
        assert!(p50 <= p99, "p50 {p50} must not exceed p99 {p99}");
        assert!(p99 >= 9_000_000, "the last sample is the slowest by design");
        let _ = stop();
    }
}

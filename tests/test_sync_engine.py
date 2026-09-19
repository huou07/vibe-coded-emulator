# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import dataclasses
import unittest

import sync_engine as se


def item(hash_, **kwargs):
    return se.ItemVersion(content_hash=hash_, **kwargs)


class ModeAndTransportTests(unittest.TestCase):
    def test_parse_defaults_unknown_to_off(self):
        self.assertEqual(se.parse_sync_mode("drive"), se.SyncMode.DRIVE)
        self.assertEqual(se.parse_sync_mode("lan_drive"), se.SyncMode.LAN_DRIVE)
        self.assertEqual(se.parse_sync_mode("nonsense"), se.SyncMode.OFF)
        self.assertEqual(se.parse_sync_mode(None), se.SyncMode.OFF)

    def test_lan_is_preferred_when_available(self):
        self.assertEqual(se.select_transport(se.SyncMode.LAN_DRIVE, same_lan=True), se.Transport.LAN)
        self.assertEqual(se.select_transport(se.SyncMode.LAN_DRIVE, same_lan=False), se.Transport.DRIVE)
        self.assertEqual(se.select_transport(se.SyncMode.LAN, same_lan=True), se.Transport.LAN)
        self.assertIsNone(se.select_transport(se.SyncMode.LAN, same_lan=False))
        self.assertIsNone(se.select_transport(se.SyncMode.OFF, same_lan=True))

    def test_automatic_prefers_lan_then_drive(self):
        self.assertEqual(se.parse_sync_mode("automatic"), se.SyncMode.AUTO)
        self.assertEqual(se.parse_sync_mode("auto"), se.SyncMode.AUTO)
        self.assertEqual(se.select_transport(se.SyncMode.AUTO, same_lan=True), se.Transport.LAN)
        self.assertEqual(se.select_transport(se.SyncMode.AUTO, same_lan=False), se.Transport.DRIVE)
        # No credentials means Automatic stays local instead of failing.
        self.assertIsNone(se.select_transport(se.SyncMode.AUTO, same_lan=False, drive_available=False))
        self.assertFalse(se.SyncMode.AUTO.requires_drive)
        self.assertTrue(se.SyncMode.AUTO.lan_enabled)
        self.assertTrue(se.SyncMode.AUTO.drive_enabled)

    def test_off_never_plans_transfers(self):
        entry = se.SyncEntry(kind=se.ItemKind.SAVE, key="a", local=item("1"))
        plan = se.build_plan(se.SyncMode.OFF, [entry], same_lan=True)
        self.assertEqual(plan.transfers, [])
        self.assertEqual(se.summarize(plan)["actions"], 0)


class PlanEntryTests(unittest.TestCase):
    def test_identical_content_is_a_noop_loop_guard(self):
        entry = se.SyncEntry(
            kind=se.ItemKind.SAVE, key="save", local=item("h"), remote=item("h"), last_synced_hash="h"
        )
        plan = se.plan_entry(entry)
        self.assertEqual(plan.direction, se.Direction.NONE)
        self.assertEqual(plan.reason, "identical")

    def test_local_only_uploads(self):
        entry = se.SyncEntry(kind=se.ItemKind.ROM, key="rom", local=item("h1"))
        self.assertEqual(se.plan_entry(entry).direction, se.Direction.UPLOAD)

    def test_remote_only_downloads(self):
        entry = se.SyncEntry(kind=se.ItemKind.ROM, key="rom", remote=item("h1"))
        self.assertEqual(se.plan_entry(entry).direction, se.Direction.DOWNLOAD)

    def test_one_sided_change_is_applied(self):
        entry = se.SyncEntry(
            kind=se.ItemKind.SAVE, key="save", local=item("new"), remote=item("old"), last_synced_hash="old"
        )
        self.assertEqual(se.plan_entry(entry).direction, se.Direction.UPLOAD)
        entry = se.SyncEntry(
            kind=se.ItemKind.SAVE, key="save", local=item("old"), remote=item("new"), last_synced_hash="old"
        )
        self.assertEqual(se.plan_entry(entry).direction, se.Direction.DOWNLOAD)

    def test_both_sides_changed_is_a_conflict(self):
        entry = se.SyncEntry(
            kind=se.ItemKind.STATE, key="state", local=item("local-new"), remote=item("remote-new"),
            last_synced_hash="base",
        )
        plan = se.plan_entry(entry)
        self.assertEqual(plan.direction, se.Direction.CONFLICT)
        self.assertEqual(plan.reason, "both-changed")

    def test_missing_index_with_divergent_hashes_is_a_conflict_not_a_guess(self):
        entry = se.SyncEntry(kind=se.ItemKind.SAVE, key="save", local=item("l"), remote=item("r"))
        self.assertEqual(se.plan_entry(entry).direction, se.Direction.CONFLICT)

    def test_deletions_propagate_only_when_the_other_side_is_unchanged(self):
        remote_deleted = se.SyncEntry(
            kind=se.ItemKind.ROM, key="rom", local=item("h"), last_synced_hash="h"
        )
        self.assertEqual(se.plan_entry(remote_deleted).direction, se.Direction.DELETE_LOCAL)
        local_edited = se.SyncEntry(
            kind=se.ItemKind.ROM, key="rom", local=item("edited"), last_synced_hash="h"
        )
        self.assertEqual(se.plan_entry(local_edited).direction, se.Direction.UPLOAD)

    def test_firmware_and_keys_are_never_synced(self):
        for kind in (se.ItemKind.FIRMWARE, se.ItemKind.KEYS):
            entry = se.SyncEntry(kind=kind, key="secret", local=item("h"))
            plan = se.plan_entry(entry)
            self.assertEqual(plan.direction, se.Direction.NONE)
            self.assertEqual(plan.reason, "not-eligible")


class ConflictResolutionTests(unittest.TestCase):
    def _conflict(self):
        entry = se.SyncEntry(
            kind=se.ItemKind.STATE, key="state", local=item("l"), remote=item("r"), last_synced_hash="base"
        )
        return se.plan_entry(entry)

    def test_keep_local_uploads(self):
        plan = se.resolve_conflict(self._conflict(), "local", local_hash="l", remote_hash="r")
        self.assertEqual(plan.direction, se.Direction.UPLOAD)
        self.assertEqual(plan.reason, "conflict-keep-local")

    def test_keep_remote_downloads(self):
        plan = se.resolve_conflict(self._conflict(), "remote", local_hash="l", remote_hash="r")
        self.assertEqual(plan.direction, se.Direction.DOWNLOAD)

    def test_keep_both_preserves_the_losing_copy(self):
        plan = se.resolve_conflict(self._conflict(), "both", local_hash="l", remote_hash="r")
        self.assertEqual(plan.direction, se.Direction.UPLOAD)
        self.assertEqual(plan.copy_key, "state.conflict")

    def test_invalid_resolution_is_rejected(self):
        with self.assertRaises(se.SyncError):
            se.resolve_conflict(self._conflict(), "overwrite", local_hash="l", remote_hash="r")


class LoopPreventionTests(unittest.TestCase):
    def test_applying_a_result_stops_the_next_pass_from_conflicting(self):
        entry = se.SyncEntry(
            kind=se.ItemKind.SAVE, key="save", local=item("new"), remote=item("old"), last_synced_hash="old"
        )
        self.assertEqual(se.plan_entry(entry).direction, se.Direction.UPLOAD)
        synced = se.apply_result(entry, content_hash="new")
        synced = dataclasses.replace(synced, local=item("new"), remote=item("new"))
        self.assertEqual(se.plan_entry(synced).direction, se.Direction.NONE)


class EntriesFromRecordsTests(unittest.TestCase):
    def test_records_map_to_entries_and_require_a_key(self):
        entries = se.entries_from_records(
            [
                {
                    "key": "roms/x.gba",
                    "local": {"content_hash": "h1", "size": 10, "device_id": "dev-a"},
                    "remote": {"content_hash": "h2", "content_id": "drive-1"},
                    "last_synced_hash": "h1",
                }
            ],
            kind=se.ItemKind.ROM,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].kind, se.ItemKind.ROM)
        self.assertEqual(entries[0].remote.content_id, "drive-1")
        with self.assertRaises(se.SyncError):
            se.entries_from_records([{"local": {}}], kind=se.ItemKind.ROM)


class SummaryTests(unittest.TestCase):
    def test_summary_counts_conflicts_and_actions(self):
        entries = [
            se.SyncEntry(kind=se.ItemKind.SAVE, key="a", local=item("x"), remote=item("y"), last_synced_hash="b"),
            se.SyncEntry(kind=se.ItemKind.SAVE, key="b", local=item("same"), remote=item("same")),
            se.SyncEntry(kind=se.ItemKind.ROM, key="c", local=item("only")),
        ]
        plan = se.build_plan(se.SyncMode.DRIVE, entries, same_lan=False)
        summary = se.summarize(plan)
        self.assertEqual(summary["conflicts"], 1)
        self.assertEqual(summary["actions"], 2)
        self.assertEqual(summary["total"], 3)


if __name__ == "__main__":
    unittest.main()

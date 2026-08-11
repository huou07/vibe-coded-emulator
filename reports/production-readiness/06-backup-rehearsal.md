# Backup rehearsal

Status: PASS for local rehearsal; production backup remains unverified.

The copied workspace database (`data/arcade.db`) was backed up to a temporary file using Python `sqlite3.Connection.backup()`, matching the consistent-backup method in `deploy.sh`. The temporary backup returned `PRAGMA integrity_check = ok`, retained `journal_mode = wal`, and matched the source size at 135,168 bytes. The temporary file was removed after verification.

This proves the local backup procedure, not production backup availability or restore authorization. No production database was opened or modified.

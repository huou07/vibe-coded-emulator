# Local build storage guard

Local package builds check free space before downloading dependencies or generating build output. By default they warn below 40 GiB and stop below a 25 GiB reserve. The guard never deletes files; use CI or remove only known disposable build output when space is low.

The POSIX helper is `tools/disk-preflight.sh`; Windows uses `tools/disk-preflight.ps1`. Override thresholds with `AN3_DISK_WARNING_GIB` and `AN3_DISK_RESERVE_GIB` when a builder has a documented different reserve.

The preflight runs before macOS, Windows, Linux DEB/Flatpak, and Android package or companion builds. The Windows helper still requires execution on a Windows builder for runtime verification.

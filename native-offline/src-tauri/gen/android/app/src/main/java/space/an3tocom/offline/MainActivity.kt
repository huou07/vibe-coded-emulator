// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.webkit.JavascriptInterface
import android.webkit.WebView
import androidx.activity.enableEdgeToEdge
import java.io.BufferedInputStream
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.util.Locale
import java.util.zip.ZipInputStream
import org.apache.commons.compress.archivers.sevenz.SevenZFile
import org.json.JSONObject

class MainActivity : TauriActivity() {
  private companion object {
    const val OFFLINE_ORIGIN = "https://appassets.androidplatform.net/index.html"
    const val ROM_IMPORT_REQUEST = 0xA31
    const val STATE_EXPORT_REQUEST = 0xA32
    const val COPY_BUFFER_BYTES = 1024 * 1024
    const val MAX_NATIVE_ROM_BYTES = 512L * 1024 * 1024
    const val MAX_ARCHIVE_BYTES = 512L * 1024 * 1024
    const val MAX_ARCHIVE_ENTRIES = 256
  }

  private var pendingRomId: String? = null
  private var contentWebView: WebView? = null
  private var pendingState: ByteArray? = null

  private class AndroidNativeRomBridge(private val activity: MainActivity) {
    @JavascriptInterface
    fun pickAndImportRom(romId: String) = activity.pickAndImportRom(romId)

    @JavascriptInterface
    fun removeRom(romId: String) = activity.removeRom(romId)

    @JavascriptInterface
    fun launchNative(romId: String, system: String): String = activity.launchNative(romId, system, -1L)

    // Size-aware launch keeps older library assets working while allowing the
    // current one to recover a ROM whose stored id no longer matches its file.
    @JavascriptInterface
    fun launchNativeSized(romId: String, system: String, expectedSize: Long): String =
      activity.launchNative(romId, system, expectedSize)

    @JavascriptInterface
    fun exportState(encoded: String) = activity.exportState(encoded)
  }

  // Library Settings -> Phone Controller. It shares the one app-scoped host
  // with in-game play, so a session started before a game keeps working when a
  // game launches. Returns the current status as JSON; never the raw token.
  private class AndroidNativeControllerBridge {
    @JavascriptInterface
    fun start(baseUrl: String): String {
      An3ControllerHost.start(baseUrl)
      return An3ControllerHost.statusJson()
    }

    @JavascriptInterface
    fun stop(): String {
      An3ControllerHost.stop()
      return An3ControllerHost.statusJson()
    }

    @JavascriptInterface
    fun status(): String = An3ControllerHost.statusJson()
  }

  // Canonical settings surface for the offline shell. MainActivity is a
  // separate process from NativeGameActivity, so `all()` re-reads the shared
  // preferences; a renderer that crashes the game process can never trap the
  // library UI, which edits the same persisted values directly.
  private class AndroidNativeSettingsBridge(private val activity: MainActivity) {
    @JavascriptInterface
    fun all(): String = NativeSettings.all(activity).toString()

    @JavascriptInterface
    fun save(edits: String): String = try {
      NativeSettings.save(activity, JSONObject(edits)).toString()
    } catch (error: Exception) {
      JSONObject().put("ok", false).put("error", error.message ?: "Invalid settings payload").toString()
    }

    @JavascriptInterface
    fun resetGraphics(system: String): String =
      if (system in NativeSettingsSchema.systems) NativeSettings.resetGraphics(activity, system).toString()
      else JSONObject().put("ok", false).put("error", "Unknown system").toString()
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    // Keep Chrome DevTools available for local debug builds only.  A staging
    // release must not expose its private-ROM WebView inspector to another
    // device on the same network.
    WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
  }

  override fun onWebViewCreate(webView: WebView) {
    super.onWebViewCreate(webView)
    contentWebView = webView
    webView.addJavascriptInterface(AndroidNativeRomBridge(this), "AN3AndroidNative")
    webView.addJavascriptInterface(AndroidNativeControllerBridge(), "AN3AndroidNativeController")
    webView.addJavascriptInterface(AndroidNativeSettingsBridge(this), "AN3AndroidSettings")
    // Tauri creates its WebView at `tauri.localhost`; Android does not make
    // that origin cross-origin isolated. Tauri attaches its stock client
    // immediately after this callback, so replace it on the next event-loop
    // turn, then move to the packaged AssetLoader origin.
    webView.postDelayed({
      webView.webViewClient = An3SecureWebViewClient(webView as RustWebView)
      webView.loadUrl(OFFLINE_ORIGIN)
    }, 250)
  }

  private fun isValidRomId(romId: String): Boolean =
    Regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$").matches(romId)

  private fun launchNative(romId: String, system: String, expectedSize: Long): String {
    if (!isValidRomId(romId) || system !in listOf("gba", "nds", "3ds")) return "Unsupported native game"
    val rom = nativeRomFile(romId, system, expectedSize) ?: return "Native ROM is unavailable"
    runOnUiThread {
      startActivity(Intent(this, NativeGameActivity::class.java)
        .putExtra("romId", romId).putExtra("system", system).putExtra("romFilename", rom.name))
    }
    return ""
  }

  // Keep a supported ROM's suffix: libretro cores use it to distinguish
  // containers such as .3dsx from NCSD cards. The resolver also accepts old
  // UUID.system records from before suffix preservation was introduced.
  //
  // When a record's own id no longer matches its copied file (for example a
  // WebView store that was restored while the private file was not), recover
  // by exact byte size: only one ROM of that system can match the recorded
  // size, so this never launches a different game.
  private fun nativeRomFile(romId: String, system: String, expectedSize: Long = -1L): File? {
    val candidates = File(dataDir, "an3-roms").listFiles()
      ?.filter { file -> file.isFile && extensionSystem(safeExtension(file.name)) == system }
      ?: return null
    candidates.firstOrNull { file -> file.name.startsWith("$romId.") }?.let { return it }
    if (expectedSize > 0) {
      val sized = candidates.filter { file -> file.length() == expectedSize }
      if (sized.size == 1) return sized.first()
    }
    return null
  }

  private fun pickAndImportRom(romId: String) {
    if (!isValidRomId(romId) || pendingRomId != null) {
      sendImportResult(JSONObject().put("ok", false).put("error", "Invalid or busy ROM import request."))
      return
    }
    pendingRomId = romId
    val chooser = Intent(Intent.ACTION_OPEN_DOCUMENT)
      .addCategory(Intent.CATEGORY_OPENABLE)
      // Android DocumentsUI assigns different vendor MIME types to GBA and
      // NDS files. Filtering as application/octet-stream can make valid
      // files appear disabled on some devices.
      .setType("*/*")
      .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
      .addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
    try {
      startActivityForResult(chooser, ROM_IMPORT_REQUEST)
    } catch (error: Exception) {
      pendingRomId = null
      sendImportResult(JSONObject().put("ok", false).put("error", error.message ?: "Could not open the ROM picker."))
    }
  }

  @Deprecated("Activity result callback required for the native document picker")
  override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
    super.onActivityResult(requestCode, resultCode, data)
    if (requestCode == STATE_EXPORT_REQUEST) {
      val bytes = pendingState
      pendingState = null
      val destination = data?.data
      if (resultCode != Activity.RESULT_OK || bytes == null || destination == null) {
        stateExportResult("Export cancelled")
        return
      }
      Thread {
        try {
          contentResolver.openOutputStream(destination, "wt")?.use { it.write(bytes) }
            ?: throw IllegalStateException("Destination unavailable")
          stateExportResult("State exported")
        } catch (_: Exception) { stateExportResult("State export failed") }
      }.start()
      return
    }
    if (requestCode != ROM_IMPORT_REQUEST) return
    val romId = pendingRomId
    pendingRomId = null
    if (romId == null) return
    val uri = data?.data
    if (resultCode != Activity.RESULT_OK || uri == null) {
      sendImportResult(JSONObject().put("ok", false).put("id", romId).put("error", "No ROM selected."))
      return
    }
    val permissions = data.flags and (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
    try { contentResolver.takePersistableUriPermission(uri, permissions and Intent.FLAG_GRANT_READ_URI_PERMISSION) } catch (_: SecurityException) {}
    Thread {
      try {
        val imported = importRom(uri, romId)
        sendImportResult(
          JSONObject()
            .put("ok", true)
            .put("id", romId)
            .put("name", imported.name)
            .put("size", imported.size)
            .put("system", imported.system)
            .put("path", "/native-rom/${imported.filename}"),
        )
      } catch (ambiguous: AmbiguousArchiveException) {
        showArchiveChoice(uri, romId, ambiguous.candidates)
      } catch (error: Exception) {
        sendImportResult(
          JSONObject()
            .put("ok", false)
            .put("id", romId)
            .put("error", error.message ?: "Could not import the ROM."),
        )
      }
    }.start()
  }

  private data class ImportedRom(val name: String, val filename: String, val size: Long, val system: String)
  private data class ArchiveCandidate(val entryName: String, val system: String)
  private class AmbiguousArchiveException(val candidates: List<ArchiveCandidate>) : IllegalArgumentException("Choose a ROM from this archive.")

  private fun exportState(encoded: String) {
    if (encoded.length > 90_000_000) { stateExportResult("State is too large"); return }
    val bytes = try { android.util.Base64.decode(encoded, android.util.Base64.NO_WRAP) }
      catch (_: IllegalArgumentException) { stateExportResult("Invalid state"); return }
    if (bytes.isEmpty() || bytes.size > 64 * 1024 * 1024) { stateExportResult("Invalid state size"); return }
    runOnUiThread {
      if (pendingState != null) { stateExportResult("An export is already open"); return@runOnUiThread }
      pendingState = bytes
      try {
        startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT)
          .addCategory(Intent.CATEGORY_OPENABLE).setType("application/octet-stream")
          .putExtra(Intent.EXTRA_TITLE, "vibecodedemulator-${System.currentTimeMillis()}.state"), STATE_EXPORT_REQUEST)
      } catch (_: Exception) { pendingState = null; stateExportResult("State export unavailable") }
    }
  }

  private fun stateExportResult(message: String) {
    runOnUiThread { contentWebView?.evaluateJavascript("window.__AN3StateExportResult?.(${JSONObject.quote(message)})", null) }
  }

  private fun importRom(uri: Uri, romId: String, requestedArchiveEntry: String? = null): ImportedRom {
    val name = displayName(uri)
    val extension = safeExtension(name)
    val destinationDirectory = File(dataDir, "an3-roms")
    if (!destinationDirectory.exists() && !destinationDirectory.mkdirs()) {
      throw IllegalStateException("Could not create private ROM storage.")
    }
    val temporary = File(destinationDirectory, ".$romId.part")
    try {
      if (extension == "zip") {
        val candidates = inspectZip(uri)
        val selected = requestedArchiveEntry?.let { selected -> candidates.firstOrNull { it.entryName == selected } }
          ?: candidates.singleOrNull()
          ?: throw AmbiguousArchiveException(candidates)
        val destinationName = "$romId.${storageExtension(selected.entryName, selected.system)}"
        val destination = File(destinationDirectory, destinationName)
        copyZipEntry(uri, selected.entryName, temporary)
        if (destination.exists() && !destination.delete()) throw IllegalStateException("Could not replace the prior ROM.")
        if (!temporary.renameTo(destination)) throw IllegalStateException("Could not finalize the imported ROM.")
        return ImportedRom(name, destinationName, destination.length(), selected.system)
      }
      if (extension == "7z") {
        verifySevenZipHeader(uri)
        // SevenZFile needs random access. Copy only the user-selected archive
        // into app-private temporary storage, with a hard compressed-size
        // limit; it is deleted regardless of selection or extraction result.
        val archive = File(destinationDirectory, ".$romId.7z.part")
        try {
          copyUriWithLimit(uri, archive, MAX_ARCHIVE_BYTES)
          val candidates = inspectSevenZip(archive)
          val selected = requestedArchiveEntry?.let { requested -> candidates.firstOrNull { it.entryName == requested } }
            ?: candidates.singleOrNull()
            ?: throw AmbiguousArchiveException(candidates)
          val destinationName = "$romId.${storageExtension(selected.entryName, selected.system)}"
          val destination = File(destinationDirectory, destinationName)
          copySevenZipEntry(archive, selected.entryName, temporary)
          if (destination.exists() && !destination.delete()) throw IllegalStateException("Could not replace the prior ROM.")
          if (!temporary.renameTo(destination)) throw IllegalStateException("Could not finalize the imported ROM.")
          return ImportedRom(name, destinationName, destination.length(), selected.system)
        } finally {
          archive.delete()
        }
      }
      val sourceSize = contentResolver.openAssetFileDescriptor(uri, "r")?.use { it.length }?.takeIf { it > 0 }
      val system = detectDirectSystem(uri, extension, sourceSize)
        ?: throw IllegalArgumentException("Could not identify a supported GBA, NDS, or decrypted 3DS ROM.")
      val destinationName = "$romId.${storageExtension(name, system)}"
      val destination = File(destinationDirectory, destinationName)
      val playableSize = declaredNcsdLength(uri, sourceSize)
      copyUriPrefix(uri, temporary, playableSize)
      if (destination.exists() && !destination.delete()) throw IllegalStateException("Could not replace the prior ROM.")
      if (!temporary.renameTo(destination)) throw IllegalStateException("Could not finalize the imported ROM.")
      return ImportedRom(name, destinationName, destination.length(), system)
    } catch (error: Exception) {
      temporary.delete()
      throw error
    }
  }

  private fun showArchiveChoice(uri: Uri, romId: String, candidates: List<ArchiveCandidate>) {
    runOnUiThread {
      val unique = candidates.distinctBy { it.entryName }
      AlertDialog.Builder(this)
        .setTitle("Choose a ROM from archive")
        .setItems(unique.map { "${it.entryName} (${it.system.uppercase(Locale.ROOT)})" }.toTypedArray()) { _, index ->
          Thread {
            try {
              val imported = importRom(uri, romId, unique[index].entryName)
              sendImportResult(JSONObject().put("ok", true).put("id", romId).put("name", imported.name).put("size", imported.size).put("system", imported.system).put("path", "/native-rom/${imported.filename}"))
            } catch (error: Exception) {
              sendImportResult(JSONObject().put("ok", false).put("id", romId).put("error", error.message ?: "Could not import archive ROM."))
            }
          }.start()
        }
        .setNegativeButton("Cancel") { _, _ -> sendImportResult(JSONObject().put("ok", false).put("id", romId).put("error", "Archive import cancelled.")) }
        .show()
    }
  }

  private fun displayName(uri: Uri): String {
    val fallback = "game.rom"
    val name = contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
      if (cursor.moveToFirst()) cursor.getString(cursor.getColumnIndexOrThrow(OpenableColumns.DISPLAY_NAME)) else null
    }
    return name?.takeIf { it.isNotBlank() } ?: fallback
  }

  private fun safeExtension(name: String): String {
    val candidate = name.substringAfterLast('.', "rom").lowercase(Locale.ROOT)
    return candidate.takeIf { it.matches(Regex("[a-z0-9]{1,12}")) } ?: "rom"
  }

  private fun storageExtension(name: String, system: String): String {
    val extension = safeExtension(name)
    return extension.takeIf { extensionSystem(it) == system } ?: system
  }

  private fun isSafeArchivePath(path: String): Boolean {
    if (path.isBlank() || path.length > 240 || path.startsWith("/") || path.startsWith("\\") || path.contains('\\')) return false
    return path.split('/').all { it.isNotEmpty() && it != "." && it != ".." }
  }

  private fun extensionSystem(extension: String): String? = when (extension.lowercase(Locale.ROOT)) {
    "gba", "raw" -> "gba"
    "nds", "dsi" -> "nds"
    "3ds", "3dsx", "cci", "cxi", "app" -> "3ds"
    else -> null
  }

  private fun systemFromHeader(header: ByteArray, fileSize: Long?): String? {
    if (header.size >= 0x104 && String(header, 0x100, 4, Charsets.US_ASCII) in setOf("NCSD", "NCCH")) return "3ds"
    // The GBA fixed value at 0xb2 can occur coincidentally in an NDS title.
    // Prefer the NDS's internally bounded ARM9 header before accepting that
    // one-byte GBA marker; extension fallbacks must not overturn this result.
    if (header.size >= 0x30) {
      val arm9Offset = littleEndianUInt(header, 0x20)
      val arm9Size = littleEndianUInt(header, 0x2c)
      if (arm9Offset >= 0x200 && arm9Size > 0 && (fileSize == null || arm9Offset + arm9Size <= fileSize)) return "nds"
    }
    if (header.size > 0xb2 && (header[0xb2].toInt() and 0xff) == 0x96) return "gba"
    return null
  }

  private fun readPrefix(input: InputStream, count: Int = 0x200): ByteArray {
    val bytes = ByteArray(count); var offset = 0
    while (offset < bytes.size) { val read = input.read(bytes, offset, bytes.size - offset); if (read < 0) break; offset += read }
    return bytes.copyOf(offset)
  }

  private fun detectDirectSystem(uri: Uri, extension: String, sourceSize: Long?): String? {
    val header = contentResolver.openInputStream(uri)?.use { readPrefix(BufferedInputStream(it)) } ?: return null
    return systemFromHeader(header, sourceSize).orElse { extensionSystem(extension) }
  }

  private fun String?.orElse(fallback: () -> String?): String? = this ?: fallback()

  private fun inspectZip(uri: Uri): List<ArchiveCandidate> {
    val candidates = mutableListOf<ArchiveCandidate>(); val names = mutableSetOf<String>(); var entries = 0
    contentResolver.openInputStream(uri)?.use { raw -> ZipInputStream(BufferedInputStream(raw, COPY_BUFFER_BYTES)).use { zip ->
      while (true) {
        val entry = zip.nextEntry ?: break
        if (++entries > MAX_ARCHIVE_ENTRIES) throw IllegalArgumentException("Archive has too many entries.")
        if (!isSafeArchivePath(entry.name)) throw IllegalArgumentException("Archive contains an unsafe path.")
        if (!names.add(entry.name)) throw IllegalArgumentException("Archive contains duplicate entry names.")
        if (!entry.isDirectory) {
          if (entry.size > MAX_NATIVE_ROM_BYTES) throw IllegalArgumentException("Archive ROM exceeds the 512 MiB safety limit.")
          val header = readPrefix(zip)
          val extension = safeExtension(entry.name)
          val system = systemFromHeader(header, entry.size.takeIf { it >= 0 }) ?: extensionSystem(extension)
          if (system != null) candidates += ArchiveCandidate(entry.name, system)
        }
        zip.closeEntry()
      }
    }} ?: throw IllegalStateException("Could not inspect the selected archive.")
    if (candidates.isEmpty()) throw IllegalArgumentException("Archive contains no supported GBA, NDS, or decrypted 3DS ROM.")
    return candidates
  }

  private fun copyZipEntry(uri: Uri, selectedName: String, destination: File) {
    contentResolver.openInputStream(uri)?.use { raw -> ZipInputStream(BufferedInputStream(raw, COPY_BUFFER_BYTES)).use { zip ->
      while (true) {
        val entry = zip.nextEntry ?: break
        if (!isSafeArchivePath(entry.name)) throw IllegalArgumentException("Archive contains an unsafe path.")
        if (!entry.isDirectory && entry.name == selectedName) {
          FileOutputStream(destination, false).use { output ->
            val buffer = ByteArray(COPY_BUFFER_BYTES); var total = 0L
            while (true) { val count = zip.read(buffer); if (count < 0) break; total += count; if (total > MAX_NATIVE_ROM_BYTES) throw IllegalArgumentException("Archive ROM exceeds the 512 MiB safety limit."); output.write(buffer, 0, count) }
            output.fd.sync()
          }
          if (destination.length() == 0L) throw IllegalArgumentException("Archive ROM is empty.")
          return
        }
        zip.closeEntry()
      }
    }} ?: throw IllegalStateException("Could not read the selected archive.")
    throw IllegalArgumentException("The selected archive entry is unavailable.")
  }

  private fun inspectSevenZip(archive: File): List<ArchiveCandidate> {
    val candidates = mutableListOf<ArchiveCandidate>(); val names = mutableSetOf<String>(); var entries = 0
    SevenZFile(archive).use { sevenZip ->
      while (true) {
        val entry = sevenZip.nextEntry ?: break
        if (++entries > MAX_ARCHIVE_ENTRIES) throw IllegalArgumentException("Archive has too many entries.")
        if (!isSafeArchivePath(entry.name)) throw IllegalArgumentException("Archive contains an unsafe path.")
        if (!names.add(entry.name)) throw IllegalArgumentException("Archive contains duplicate entry names.")
        if (!entry.isDirectory) {
          if (entry.size < 0L || entry.size > MAX_NATIVE_ROM_BYTES) throw IllegalArgumentException("Archive ROM exceeds the 512 MiB safety limit.")
          val header = readSevenZipPrefix(sevenZip)
          val system = systemFromHeader(header, entry.size) ?: extensionSystem(safeExtension(entry.name))
          if (system != null) candidates += ArchiveCandidate(entry.name, system)
        }
      }
    }
    if (candidates.isEmpty()) throw IllegalArgumentException("Archive contains no supported GBA, NDS, or decrypted 3DS ROM.")
    return candidates
  }

  private fun readSevenZipPrefix(archive: SevenZFile, count: Int = 0x200): ByteArray {
    val bytes = ByteArray(count); var offset = 0
    while (offset < bytes.size) {
      val read = archive.read(bytes, offset, bytes.size - offset)
      if (read < 0) break
      offset += read
    }
    return bytes.copyOf(offset)
  }

  private fun copySevenZipEntry(archive: File, selectedName: String, destination: File) {
    SevenZFile(archive).use { sevenZip ->
      while (true) {
        val entry = sevenZip.nextEntry ?: break
        if (!isSafeArchivePath(entry.name)) throw IllegalArgumentException("Archive contains an unsafe path.")
        if (!entry.isDirectory && entry.name == selectedName) {
          if (entry.size < 0L || entry.size > MAX_NATIVE_ROM_BYTES) throw IllegalArgumentException("Archive ROM exceeds the 512 MiB safety limit.")
          FileOutputStream(destination, false).use { output ->
            val buffer = ByteArray(COPY_BUFFER_BYTES); var total = 0L
            while (true) {
              val count = sevenZip.read(buffer)
              if (count < 0) break
              total += count
              if (total > MAX_NATIVE_ROM_BYTES) throw IllegalArgumentException("Archive ROM exceeds the 512 MiB safety limit.")
              output.write(buffer, 0, count)
            }
            output.fd.sync()
          }
          if (destination.length() == 0L) throw IllegalArgumentException("Archive ROM is empty.")
          return
        }
      }
    }
    throw IllegalArgumentException("The selected archive entry is unavailable.")
  }

  private fun verifySevenZipHeader(uri: Uri) {
    val header = contentResolver.openInputStream(uri)?.use { readPrefix(BufferedInputStream(it), 6) } ?: throw IllegalStateException("Could not inspect the selected 7z archive.")
    if (header.size != 6 || !header.contentEquals(byteArrayOf(0x37, 0x7a, 0xbc.toByte(), 0xaf.toByte(), 0x27, 0x1c))) throw IllegalArgumentException("Invalid 7z archive header.")
  }

  private fun declaredNcsdLength(uri: Uri, sourceSize: Long?): Long? {
    if (sourceSize == null || sourceSize < 2_147_483_648L) return sourceSize
    val header = ByteArray(0x200)
    val bytesRead = contentResolver.openInputStream(uri)?.use { input ->
      BufferedInputStream(input).read(header)
    } ?: return sourceSize
    if (bytesRead < 0x160 || String(header, 0x100, 4, Charsets.US_ASCII) != "NCSD") return sourceSize
    var payloadEnd = 0L
    for (index in 0 until 8) {
      val offset = littleEndianUInt(header, 0x120 + index * 8)
      val length = littleEndianUInt(header, 0x124 + index * 8)
      if (length == 0L) continue
      val end = (offset + length) * 0x200L
      if (end <= 0L || end > sourceSize) return sourceSize
      payloadEnd = maxOf(payloadEnd, end)
    }
    return payloadEnd.takeIf { it in 1 until sourceSize } ?: sourceSize
  }

  private fun littleEndianUInt(bytes: ByteArray, offset: Int): Long =
    (bytes[offset].toLong() and 0xffL) or
      ((bytes[offset + 1].toLong() and 0xffL) shl 8) or
      ((bytes[offset + 2].toLong() and 0xffL) shl 16) or
      ((bytes[offset + 3].toLong() and 0xffL) shl 24)

  private fun copyUriPrefix(uri: Uri, destination: File, expectedSize: Long?) {
    contentResolver.openInputStream(uri)?.use { source ->
      BufferedInputStream(source, COPY_BUFFER_BYTES).use { input ->
        FileOutputStream(destination, false).use { output ->
          val buffer = ByteArray(COPY_BUFFER_BYTES)
          var remaining = expectedSize
          while (remaining == null || remaining > 0L) {
            val request = if (remaining == null) buffer.size else minOf(buffer.size.toLong(), remaining).toInt()
            val count = input.read(buffer, 0, request)
            if (count < 0) break
            output.write(buffer, 0, count)
            if (remaining != null) remaining -= count.toLong()
          }
          output.fd.sync()
        }
      }
    } ?: throw IllegalStateException("Could not read the selected ROM.")
    if (destination.length() == 0L) throw IllegalStateException("The selected ROM is empty.")
  }

  private fun copyUriWithLimit(uri: Uri, destination: File, limit: Long) {
    contentResolver.openInputStream(uri)?.use { source ->
      BufferedInputStream(source, COPY_BUFFER_BYTES).use { input ->
        FileOutputStream(destination, false).use { output ->
          val buffer = ByteArray(COPY_BUFFER_BYTES); var total = 0L
          while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            total += count
            if (total > limit) throw IllegalArgumentException("Archive exceeds the 512 MiB safety limit.")
            output.write(buffer, 0, count)
          }
          output.fd.sync()
        }
      }
    } ?: throw IllegalStateException("Could not read the selected archive.")
    if (destination.length() == 0L) throw IllegalArgumentException("Archive is empty.")
  }

  private fun sendImportResult(result: JSONObject) {
    val script = "window.__AN3NativeRomImportResult && window.__AN3NativeRomImportResult(JSON.parse(${JSONObject.quote(result.toString())}));"
    runOnUiThread { contentWebView?.evaluateJavascript(script, null) }
  }

  private fun removeRom(romId: String) {
    if (!isValidRomId(romId)) return
    val directory = File(dataDir, "an3-roms")
    directory.listFiles()?.filter { it.isFile && it.name.startsWith("$romId.") }?.forEach { it.delete() }
  }

}

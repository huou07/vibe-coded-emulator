// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.app.Activity
import android.content.ComponentCallbacks2
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.Toast
import java.io.File

/** The WebView owns the library only. This activity owns native gameplay. */
class NativeGameActivity : Activity(), SurfaceHolder.Callback {
    companion object { init { System.loadLibrary("an3_runtime") } }
    private external fun nativeStart(surface: Surface, core: String, rom: String, saves: String, backend: String, layout: String, system: String, autoSaveMode: String, resume: Boolean)
    private external fun nativeStop(suspend: Boolean)
    private external fun nativeButton(button: Int, pressed: Boolean)
    private external fun nativePointer(x: Int, y: Int, pressed: Boolean)
    private external fun nativeAnalog(x: Int, y: Int)
    private external fun nativeCancelPointer()
    private external fun nativeCommand(command: String, value: String)
    private external fun nativeDiagnostics(): String
    private external fun nativeOptions(): String
    private lateinit var overlay: NativeGameOverlay
    private var mouseX = 128f
    private var mouseY = 96f
    private lateinit var surface: SurfaceView
    private val handler = Handler(Looper.getMainLooper())
    private val preferences by lazy { getSharedPreferences("an3-native-game", MODE_PRIVATE) }
    private var active = false
    private var surfaceStarted = false
    private val pendingCommands = mutableListOf<Pair<String, String>>()
    private fun commandWhenReady(command: String, value: String) {
        if (active) nativeCommand(command, value) else if (pendingCommands.size < 128) pendingCommands.add(command to value)
    }
    private var pointerId = -1
    private var layout = "left-right"
    private var backend = "auto"
    private var system = ""
    private var romId = ""
    private var rom: File? = null
    private val tick = object : Runnable {
        override fun run() {
            if (active) overlay.updateDiagnostics(nativeDiagnostics())
            handler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        romId = intent.getStringExtra("romId") ?: ""
        system = intent.getStringExtra("system") ?: ""
        if (!Regex("^[0-9a-f-]{36}$").matches(romId) || system !in listOf("gba", "nds", "3ds")) { finish(); return }
        val romFilename = intent.getStringExtra("romFilename") ?: ""
        if (!Regex("^$romId\\.[a-z0-9]{1,12}$").matches(romFilename)) { finish(); return }
        rom = File(dataDir, "an3-roms/$romFilename").takeIf { it.isFile }
        if (rom == null) { finish(); return }
        val storedLayout = preferences.getString("screen-layout-$system", preferences.getString("nds-layout", "left-right"))
        layout = NativeLayoutModel.normalize(this, system, storedLayout)
        backend = preferences.getString("renderer", "auto") ?: "auto"
        val root = FrameLayout(this).apply { setBackgroundColor(0xff07060c.toInt()) }
        surface = SurfaceView(this)
        surface.holder.addCallback(this)
        surface.setOnTouchListener { _, event -> if (overlay.isMenuOpen()) false else touch(event) }
        surface.setOnCapturedPointerListener { _, event ->
            if (system != "nds" || !active || overlay.isMenuOpen()) return@setOnCapturedPointerListener true
            mouseX = (mouseX + event.x).coerceIn(0f,255f); mouseY = (mouseY + event.y).coerceIn(0f,191f)
            sendDsPointer(mouseX,mouseY,event.buttonState and MotionEvent.BUTTON_PRIMARY != 0)
            true
        }
        root.addView(surface, FrameLayout.LayoutParams(-1,-1))
        overlay = NativeGameOverlay(this,system,preferences,File(filesDir,"native-states-v1/$system/$romId"),
            {command,value -> commandWhenReady(command,value)},
            {id,pressed -> if(active) nativeButton(id,pressed)},
            {exporting -> openStatePicker(exporting)},
            {if(active) nativeOptions() else "[]"},
            {toggleFullscreen()},
            {if(surface.hasPointerCapture()) surface.releasePointerCapture() else {surface.requestFocus();surface.requestPointerCapture()}},
            {value -> applyLayout(value)},
            {x,y -> setVirtualDirectionalInput(x,y)},
            {applySavedSettings()})
        root.addView(overlay,FrameLayout.LayoutParams(-1,-1))
        setContentView(root)
        if (!preferences.getBoolean("start-fullscreen",true)) window.decorView.systemUiVisibility=View.SYSTEM_UI_FLAG_VISIBLE
        handler.post(tick)
    }
    private fun Int.dp() = (this * resources.displayMetrics.density).toInt()

    override fun surfaceCreated(holder: SurfaceHolder) {
        val core = when (system) {
            "gba" -> "libmgba_libretro_android.so"
            "nds" -> "libmelondsds_libretro_android.so"
            else -> "libazahar_libretro_android.so"
        }
        val saves = File(filesDir, "native-states-v1/$system/$romId").apply { mkdirs() }
        nativeStart(holder.surface, File(applicationInfo.nativeLibraryDir, core).path, rom!!.path, saves.path, backend, layout, system, NativeAutoSave.resolve(preferences), surfaceStarted)
        active = true
        surfaceStarted = true
        for ((command, value) in pendingCommands) nativeCommand(command, value)
        pendingCommands.clear()
        applySavedSettings()
    }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) { releasePointer() }
    override fun surfaceDestroyed(holder: SurfaceHolder) { releasePointer(); if (active) nativeStop(!isFinishing); active = false }
    override fun onPause() { if (active) nativeCommand("pause", "1"); releasePointer(); super.onPause() }
    override fun onResume() { super.onResume(); if (active) nativeCommand("pause", "0") }
    // Under memory pressure preserve progress instead of letting the system
    // kill the process and lose the session.
    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        if (active && level >= ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW) commandWhenReady("save", "auto")
    }
    override fun onLowMemory() { super.onLowMemory(); if (active) commandWhenReady("save", "auto") }
    override fun onDestroy() { handler.removeCallbacks(tick); stopController(); if (active) nativeStop(false); active = false; super.onDestroy() }

    private fun stopController() { try { overlay.stopController() } catch (_: Exception) {} }

    private fun releasePointer(cancel: Boolean = true) { if (active) {if(cancel)nativeCancelPointer() else nativePointer(0,0,false)}; pointerId = -1 }
    private fun touch(event: MotionEvent): Boolean {
        // The in-game menu owns pointer input while it is open; a menu tap must
        // never leak into the emulated NDS/3DS touchscreen.
        if (overlay.isMenuOpen()) { releasePointer(); return true }
        if (!active || system !in listOf("nds", "3ds")) return true
        if (event.actionMasked == MotionEvent.ACTION_DOWN) pointerId = event.getPointerId(event.actionIndex)
        if (pointerId < 0) return true
        if (event.actionMasked == MotionEvent.ACTION_CANCEL || event.actionMasked == MotionEvent.ACTION_UP ||
            (event.actionMasked == MotionEvent.ACTION_POINTER_UP && event.getPointerId(event.actionIndex) == pointerId)) { releasePointer(event.actionMasked == MotionEvent.ACTION_CANCEL); return true }
        val index = event.findPointerIndex(pointerId)
        if (index < 0) { releasePointer(); return true }
        if (system == "3ds") return touch3ds(event, index)
        val wide = layout == "left-right"
        val frameWidth = if (wide) 512f else 256f
        val frameHeight = if (wide) 192f else 384f
        val scale = minOf(surface.width / frameWidth, surface.height / frameHeight)
        if (scale <= 0) return true
        val x = (event.getX(index) - (surface.width - frameWidth * scale) / 2) / scale - if (wide) 256 else 0
        val y = (event.getY(index) - (surface.height - frameHeight * scale) / 2) / scale - if (wide) 0 else 192
        if (x < 0 || x >= 256 || y < 0 || y >= 192) { nativeCancelPointer(); return true }
        // Hit-test in 256x192 DS touch space above. melonDS DS's libretro
        // pointer ABI then expects the composite framebuffer coordinates;
        // its bottomScreenMatrixInverse performs the final DS-local mapping.
        sendDsPointer(x,y,true)
        return true
    }

    // Azahar at the pinned 1x resolution uses the same composite frame
    // rectangles as the macOS reference: 400×480 (vertical) or 720×240
    // (side-by-side). Normalize the complete composite after hit-testing the
    // lower screen; the core owns the final lower-screen transform.
    private fun touch3ds(event: MotionEvent, index: Int): Boolean {
        val wide = layout == "left-right"
        val frameWidth = if (wide) 720f else 400f
        val frameHeight = if (wide) 240f else 480f
        val scale = minOf(surface.width / frameWidth, surface.height / frameHeight)
        if (scale <= 0) return true
        val x = (event.getX(index) - (surface.width - frameWidth * scale) / 2) / scale
        val y = (event.getY(index) - (surface.height - frameHeight * scale) / 2) / scale
        val left = if (wide) 400f else 40f
        val right = if (wide) 720f else 360f
        val top = if (wide) 0f else 240f
        val bottom = if (wide) 240f else 480f
        if (x < left || x >= right || y < top || y >= bottom) { nativeCancelPointer(); return true }
        nativePointer((x / frameWidth * 65534 - 32767).toInt(), (y / frameHeight * 65534 - 32767).toInt(), true)
        return true
    }

    private fun sendDsPointer(x:Float,y:Float,pressed:Boolean) {
        val wide=layout=="left-right"
        val compositeX=x+if(wide)256f else 0f
        val compositeY=y+if(wide)0f else 192f
        nativePointer((compositeX/(if(wide)512f else 256f)*65534-32767).toInt(),(compositeY/(if(wide)192f else 384f)*65534-32767).toInt(),pressed)
    }
    private fun applyLayout(value: String) {
        if (system !in listOf("nds", "3ds")) return
        layout = NativeLayoutModel.normalize(this, system, value)
        commandWhenReady("layout", layout)
        overlay.onActiveLayoutChanged()
    }
    private fun setVirtualDirectionalInput(x: Float, y: Float) {
        // Input is event-driven; the native core samples this stable state on
        // its own scheduler tick. This must never depend on SurfaceView FPS.
        if (system == "3ds") {
            nativeAnalog((x * 32767).toInt(), (y * 32767).toInt())
            return
        }
        val deadZone = .35f
        nativeButton(6, x < -deadZone); nativeButton(7, x > deadZone)
        nativeButton(4, y < -deadZone); nativeButton(5, y > deadZone)
    }
    private fun toggleFullscreen() {
        val hidden = window.decorView.systemUiVisibility and View.SYSTEM_UI_FLAG_FULLSCREEN != 0
        window.decorView.systemUiVisibility = if(hidden) View.SYSTEM_UI_FLAG_VISIBLE else View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
    }
    private fun applySavedSettings() {
        commandWhenReady("volume",preferences.getInt("volume",100).toString())
        commandWhenReady("mute",if(preferences.getBoolean("mute",false)) "1" else "0")
        commandWhenReady("latency",preferences.getInt("latency",64).toString())
        commandWhenReady("quality",preferences.getString("quality","medium") ?: "medium")
        commandWhenReady("autosave-mode",NativeAutoSave.resolve(preferences))
        for((key,value) in preferences.all) if(key.startsWith("core-$system-")) commandWhenReady("option",key.removePrefix("core-$system-")+"\t"+value.toString())
        overlay.refreshPreferences()
    }
    private fun openStatePicker(exporting: Boolean) {
        releasePointer()
        startActivityForResult(Intent(if(exporting) Intent.ACTION_CREATE_DOCUMENT else Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE).setType("application/octet-stream")
            .putExtra(Intent.EXTRA_TITLE,"native-$system.state"),if(exporting)701 else 702)
    }
    @Deprecated("Native document picker callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (resultCode != RESULT_OK || data?.data == null || requestCode !in listOf(701, 702)) return
        val uri = data.data!!
        val file = try { File.createTempFile("native-state-", ".state", cacheDir) }
        catch (_: Exception) {
            Toast.makeText(this, "Native state storage unavailable", Toast.LENGTH_LONG).show()
            return
        }
        if (requestCode == 701) {
            file.delete()
            commandWhenReady("export", file.path)
            val deadline = System.currentTimeMillis() + 30_000
            val poll = object : Runnable {
                override fun run() {
                    if (file.isFile) {
                        Thread {
                            try {
                                contentResolver.openOutputStream(uri, "wt")?.use { output -> file.inputStream().use { it.copyTo(output) } }
                                    ?: throw IllegalStateException("Destination unavailable")
                                runOnUiThread { Toast.makeText(this@NativeGameActivity, "Native state exported", Toast.LENGTH_LONG).show() }
                            } catch (_: Exception) { runOnUiThread { Toast.makeText(this@NativeGameActivity, "Native state export failed", Toast.LENGTH_LONG).show() } }
                            finally { file.delete() }
                        }.start()
                    } else if (System.currentTimeMillis() < deadline && !isDestroyed) handler.postDelayed(this, 100)
                    else Toast.makeText(this@NativeGameActivity, "Native state export unavailable", Toast.LENGTH_LONG).show()
                }
            }
            handler.post(poll)
        } else Thread {
            try {
                contentResolver.openInputStream(uri)?.use { input ->
                    file.outputStream().use { output ->
                        val buffer = ByteArray(65536); var total = 0L
                        while (true) {
                            val count = input.read(buffer); if (count < 0) break
                            total += count; if (total > 64L * 1024 * 1024) throw IllegalStateException("State too large")
                            output.write(buffer, 0, count)
                        }
                        if (total == 0L) throw IllegalStateException("Empty state")
                    }
                } ?: throw IllegalStateException("Source unavailable")
                runOnUiThread { commandWhenReady("import", file.path) }
            } catch (_: Exception) { file.delete(); runOnUiThread { Toast.makeText(this@NativeGameActivity, "Native state import failed", Toast.LENGTH_LONG).show() } }
        }.start()
    }
    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        if (active && !overlay.isMenuOpen() && event.source and android.view.InputDevice.SOURCE_JOYSTICK == android.view.InputDevice.SOURCE_JOYSTICK) {
            val x=event.getAxisValue(MotionEvent.AXIS_HAT_X).takeIf{it!=0f}?:event.getAxisValue(MotionEvent.AXIS_X)
            val y=event.getAxisValue(MotionEvent.AXIS_HAT_Y).takeIf{it!=0f}?:event.getAxisValue(MotionEvent.AXIS_Y)
            nativeButton(6,x<-.5f);nativeButton(7,x>.5f);nativeButton(4,y<-.5f);nativeButton(5,y>.5f)
            return true
        }
        return super.onGenericMotionEvent(event)
    }
    private fun keyButton(code: Int): Int? = overlay.mappedKey(code) ?: when (code) {
        KeyEvent.KEYCODE_DPAD_UP -> 4; KeyEvent.KEYCODE_DPAD_DOWN -> 5; KeyEvent.KEYCODE_DPAD_LEFT -> 6; KeyEvent.KEYCODE_DPAD_RIGHT -> 7
        KeyEvent.KEYCODE_BUTTON_A, KeyEvent.KEYCODE_X -> 8; KeyEvent.KEYCODE_BUTTON_B, KeyEvent.KEYCODE_Z -> 0
        KeyEvent.KEYCODE_BUTTON_X, KeyEvent.KEYCODE_S -> 9; KeyEvent.KEYCODE_BUTTON_Y, KeyEvent.KEYCODE_A -> 1
        KeyEvent.KEYCODE_BUTTON_L1, KeyEvent.KEYCODE_L -> 10; KeyEvent.KEYCODE_BUTTON_R1, KeyEvent.KEYCODE_J -> 11
        KeyEvent.KEYCODE_BUTTON_START, KeyEvent.KEYCODE_ENTER -> 3; KeyEvent.KEYCODE_BUTTON_SELECT, KeyEvent.KEYCODE_SPACE -> 2
        else -> null
    }
    override fun onKeyDown(code: Int, event: KeyEvent): Boolean { if(code==KeyEvent.KEYCODE_ESCAPE){if(overlay.isMenuOpen()){overlay.handleEscape();return true};if(surface.hasPointerCapture()){surface.releasePointerCapture();releasePointer()}else finish();return true}; val id = keyButton(code); if (id != null && active) { nativeButton(id, true); return true }; return super.onKeyDown(code, event) }
    override fun onKeyUp(code: Int, event: KeyEvent): Boolean { val id = keyButton(code); if (id != null && active) { nativeButton(id, false); return true }; return super.onKeyUp(code, event) }
}

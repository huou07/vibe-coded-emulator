// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.app.Activity
import android.app.AlertDialog
import android.app.Dialog
import android.content.SharedPreferences
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject

/** Native counterpart of AN3NativeGameView's DMG controls and nine-tab menu. */
class NativeGameOverlay(
    private val activity: Activity,
    private val system: String,
    private val prefs: SharedPreferences,
    private val saveDirectory: java.io.File,
    private val send: (String, String) -> Unit,
    private val input: (Int, Boolean) -> Unit,
    private val statePicker: (Boolean) -> Unit,
    private val coreOptions: () -> String,
    private val fullscreen: () -> Unit,
    private val lockCursor: () -> Unit,
    private val previewLayout: (String) -> Unit,
    private val directionalInput: (Float, Float) -> Unit,
    private val settingsSaved: () -> Unit
) : FrameLayout(activity) {
    private val pad = mutableListOf<View>()
    private var menu: Dialog? = null
    private var diagnostics = "Starting native runtime…"
    private var diagnosticsView: TextView? = null
    private var stateStatus: TextView? = null
    private var autoSaveStatus: TextView? = null
    private var captureKey: Int? = null
    private var keyDraft = JSONObject()
    private var keyStatus: TextView? = null
    private var fastSpeed = 2
    private val fps = TextView(activity)
    private val actions = listOf("B", "Y", "Select", "Start", "Up", "Down", "Left", "Right", "A", "X", "L", "R")
    private fun Int.dp() = (this * resources.displayMetrics.density).toInt()
    private fun shape(circle: Boolean = false) = GradientDrawable().apply {
        setColor(0xd91b1730.toInt()); cornerRadius = (if (circle) 28 else 8).dp().toFloat()
        setStroke(1.dp(), 0xff3a3254.toInt())
    }
    private fun button(label: String, circle: Boolean = false, action: (() -> Unit)? = null) = Button(activity).apply {
        text = label; isAllCaps = false; textSize = if (circle) 15f else 12f
        setTextColor(Color.WHITE); typeface = Typeface.DEFAULT_BOLD
        minWidth = 0; minimumWidth = 0; minHeight = 0; minimumHeight = 0
        setPadding(2.dp(), 0, 2.dp(), 0); background = android.graphics.drawable.StateListDrawable().apply {
            addState(intArrayOf(android.R.attr.state_pressed),shape(circle).apply{setColor(0xff8b5cf6.toInt())})
            addState(intArrayOf(),shape(circle))
        }
        contentDescription = label
        if (action != null) setOnClickListener { action() }
    }
    private fun choiceAdapter(values: List<String>) = object : ArrayAdapter<String>(activity, android.R.layout.simple_spinner_dropdown_item, values) {
        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View = super.getView(position,convertView,parent).apply {
            (this as? TextView)?.setTextColor(Color.WHITE)
        }
    }
    private val menuButton = button(NativePlayerUi.MENU_LABEL) { showMenu() }
    private val padButton = button(NativePlayerUi.PAD_LABEL) {
        val show = pad.firstOrNull()?.visibility != View.VISIBLE
        pad.forEach { it.visibility = if (show) View.VISIBLE else View.GONE }
        if (show) applyDirectionalMode() else releaseVirtualDirections()
    }
    private val layoutButton = button(NativePlayerUi.LAYOUT_LABEL) { showLayoutChooser() }
    private val saveButton = button(NativePlayerUi.SAVE_LABEL) { showSaveMenu() }
    private val slow = button(NativePlayerUi.speedLabels[0]) { setSpeed("0.5") }
    private val normal = button(NativePlayerUi.speedLabels[1]) { setSpeed("1") }
    private val fast = button(NativePlayerUi.speedLabels[2]) { setSpeed(fastSpeed.toString()); fastSpeed = if (fastSpeed == 8) 2 else fastSpeed * 2 }
    private val cursor = button(NativePlayerUi.CURSOR_LOCK_LABEL) { lockCursor() }
    private val keys = mutableMapOf<Int, Button>()
    private val joystick = NativeAnalogStick(activity, directionalInput)
    private val circular = NativeCircularDpad(activity) { ids -> applyCircularDirections(ids) }
    private var circularPressed: Set<Int> = emptySet()
    private var currentSpeed = "1"
    // The controller host lives in the main process (library Settings). This
    // game process binds to it through a Messenger bridge; the raw host token
    // never crosses the boundary. The bridge is set by NativeGameActivity.
    interface ControllerBridge {
        fun isRunning(): Boolean
        fun start()
        fun stop()
        fun statusText(): String
    }
    var controllerBridge: ControllerBridge? = null
    private val controllerStatusTick = object : Runnable {
        override fun run() {
            controllerStatus?.text = controllerStatusText()
            postDelayed(this, 700)
        }
    }
    private var controllerStatus: TextView? = null
    private var directionalMode = prefs.getString("directional-control-$system", "dpad") ?: "dpad"
    private var controlScale = prefs.getInt("virtual-control-scale-$system", 100).coerceIn(70, 140)
    private var controlOpacity = prefs.getInt("virtual-control-opacity-$system", 85).coerceIn(30, 100)
    private var controlPositionX = prefs.getInt("virtual-control-position-x-$system", 0).coerceIn(-40, 40)
    private var controlPositionY = prefs.getInt("virtual-control-position-y-$system", 0).coerceIn(-40, 40)

    init {
        // Empty overlay areas stay available to SurfaceView touch input.
        isClickable = false; isFocusable = false
        listOf(menuButton, padButton, slow, normal, fast, saveButton).forEach { addView(it) }
        if (system in listOf("nds", "3ds")) addView(layoutButton)
        if (system == "nds") addView(cursor)
        val labels = mapOf(4 to "▲", 5 to "▼", 6 to "◀", 7 to "▶", 8 to "A", 0 to "B", 9 to "X", 1 to "Y", 10 to "L", 11 to "R", 3 to "Start", 2 to "Select")
        for ((id, label) in labels) {
            val key = button(label, id !in listOf(2, 3, 10, 11))
            key.setOnTouchListener { _, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { key.isPressed = true; input(id, true) }
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> { key.isPressed = false; input(id, false) }
                }; true
            }
            keys[id] = key; pad.add(key); addView(key)
        }
        pad.add(joystick); addView(joystick)
        pad.add(circular); addView(circular)
        fps.textSize = 11f; fps.setTextColor(Color.WHITE); fps.setBackgroundColor(0xb8000000.toInt())
        // The FPS badge is display-only: it must never intercept a tap meant for
        // the game surface or a control beneath it.
        fps.isClickable = false; fps.isFocusable = false; fps.isLongClickable = false
        fps.setOnTouchListener { _, _ -> false }
        fps.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        fps.gravity = Gravity.CENTER; addView(fps); refreshPreferences()
    }

    private fun releaseVirtualDirections() {
        joystick.release()
        circular.release()
        listOf(4, 5, 6, 7).forEach { input(it, false) }
        directionalInput(0f, 0f)
    }
    private fun applyCircularDirections(next: Set<Int>) {
        // A diagonal is two cardinals pressed together; never a synthetic button.
        for (id in circularPressed) if (id !in next) input(id, false)
        for (id in next) if (id !in circularPressed) input(id, true)
        circularPressed = next
    }
    private fun applyDirectionalMode() {
        val joystickMode = directionalMode == "joystick"
        val circularMode = directionalMode == "circular"
        listOf(4, 5, 6, 7).forEach { id -> keys[id]?.visibility = if (joystickMode || circularMode) View.GONE else View.VISIBLE }
        joystick.visibility = if (joystickMode) View.VISIBLE else View.GONE
        circular.visibility = if (circularMode) View.VISIBLE else View.GONE
        if (!joystickMode) joystick.release()
        if (!circularMode) circular.release()
    }
    private fun applyVirtualControlStyle() {
        pad.forEach { it.alpha = controlOpacity / 100f }
        applyDirectionalMode()
        requestLayout()
    }

    // Exposes every layout the active core supports instead of only cycling.
    private fun showLayoutChooser() {
        val layouts = NativeLayoutModel.layouts(activity, system)
        if (layouts.isEmpty()) return
        val current = NativeLayoutModel.normalize(activity, system,
            prefs.getString("screen-layout-$system", prefs.getString("nds-layout", "left-right")))
        AlertDialog.Builder(activity)
            .setTitle(NativePlayerUi.LAYOUT_LABEL)
            .setSingleChoiceItems(layouts.map { it.label }.toTypedArray(), layouts.indexOfFirst { it.id == current }) { dialog, which ->
                val id = layouts[which].id
                previewLayout(id)
                prefs.edit().apply {
                    putString("screen-layout-$system", id)
                    if (system == "nds") putString("nds-layout", id)
                }.apply()
                dialog.dismiss()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // The toolbar Save control mirrors the Save States tab's quick actions.
    // Quick Save / Quick Load expose all ten quick slots, matching the Save
    // States tab, so a save or load never needs the full menu.
    private fun chooseQuickSlot(save: Boolean) {
        val slots = (1..10).map { "Slot $it" }.toTypedArray()
        AlertDialog.Builder(activity)
            .setTitle(if (save) NativePlayerUi.QUICK_SAVE_LABEL else NativePlayerUi.QUICK_LOAD_LABEL)
            .setItems(slots) { _, which ->
                val slot = which + 1
                if (save) prefs.edit().putInt("quick-save-slot", slot).commit()
                send(if (save) "save" else "load", slot.toString())
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /** Canonical utility actions (one-shot; never held gameplay bits). */
    fun utility(action: String, slot: Int = quickSaveSlot()) {
        when (action) {
            "QUICK_SAVE" -> {
                val selected = slot.coerceIn(1, 10)
                prefs.edit().putInt("quick-save-slot", selected).apply()
                send("save", selected.toString())
            }
            "QUICK_LOAD" -> send("load", slot.coerceIn(1, 10).toString())
            "SPEED_UP" -> setSpeed(stepSpeed(1))
            "SPEED_DOWN" -> setSpeed(stepSpeed(-1))
            "OPEN_MENU" -> if (!isMenuOpen()) showMenu()
        }
    }

    private fun quickSaveSlot(): Int = prefs.getInt("quick-save-slot", 1).coerceIn(1, 10)

    private fun stepSpeed(direction: Int): String {
        val speeds = NativeInputActions.speeds
        val index = speeds.indexOf(currentSpeed).takeIf { it >= 0 } ?: 1
        return speeds[(index + direction).coerceIn(0, speeds.lastIndex)]
    }

    private fun showSaveMenu() {
        val items = arrayOf(NativePlayerUi.QUICK_SAVE_LABEL + "…", NativePlayerUi.QUICK_LOAD_LABEL + "…", "Auto Save now", "Load Auto Save")
        AlertDialog.Builder(activity)
            .setTitle(NativePlayerUi.SAVE_LABEL)
            .setItems(items) { _, which ->
                when (which) {
                    0 -> chooseQuickSlot(true)
                    1 -> chooseQuickSlot(false)
                    2 -> send("save", "auto")
                    else -> send("load", "auto")
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun controllerStatusText(): String = controllerBridge?.statusText() ?: "Off"

    private fun controllerRunning(): Boolean = controllerBridge?.isRunning() == true

    private fun toggleController() {
        val bridge = controllerBridge
        if (bridge == null) {
            controllerStatus?.text = "Controller unavailable"
            return
        }
        if (bridge.isRunning()) {
            bridge.stop()
            controllerStatus?.text = "Off"
            return
        }
        bridge.start()
        controllerStatus?.text = "Starting…"
        removeCallbacks(controllerStatusTick)
        post(controllerStatusTick)
    }

    /** Apply one remote (phone) button through the same path as the on-screen pad. */
    fun applyRemoteButton(index: Int, pressed: Boolean) {
        if (isMenuOpen()) {
            val keyCode = when (index) {
                4 -> KeyEvent.KEYCODE_DPAD_UP
                5 -> KeyEvent.KEYCODE_DPAD_DOWN
                6 -> KeyEvent.KEYCODE_DPAD_LEFT
                7 -> KeyEvent.KEYCODE_DPAD_RIGHT
                8, 3 -> KeyEvent.KEYCODE_ENTER
                0 -> {
                    if (pressed) handleEscape()
                    return
                }
                else -> return
            }
            menu?.window?.decorView?.dispatchKeyEvent(KeyEvent(if (pressed) KeyEvent.ACTION_DOWN else KeyEvent.ACTION_UP, keyCode))
            return
        }
        input(index, pressed)
    }

    fun applyRemoteAnalog(x: Float, y: Float) {
        if (isMenuOpen()) { directionalInput(0f, 0f); return }
        directionalInput(x, y)
    }

    /** Release every remote-held control; used when the menu opens or the game ends. */
    fun releaseRemoteInput() {
        circular.release()
        for (index in 0..11) input(index, false)
        directionalInput(0f, 0f)
    }

    /** Detach this game from the controller bridge. The pairing session stays alive. */
    fun stopController() {
        releaseRemoteInput()
        removeCallbacks(controllerStatusTick)
    }

    private fun setSpeed(value: String) {
        currentSpeed = value
        send("speed", value)
        slow.alpha = if (value == "0.5") 1f else .7f; normal.alpha = if (value == "1") 1f else .7f
        fast.alpha = if (value !in listOf("0.5", "1")) 1f else .7f
        if (value !in listOf("0.5", "1")) fast.text = "x$value"
    }
    private fun place(view: View, x: Int, y: Int, w: Int, h: Int) {
        val old=view.layoutParams as? LayoutParams
        if(old==null || old.width!=w || old.height!=h || old.leftMargin!=x || old.topMargin!=y)
            view.layoutParams = LayoutParams(w, h).apply { leftMargin = x; topMargin = y }
    }
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w=MeasureSpec.getSize(widthMeasureSpec); val h=MeasureSpec.getSize(heightMeasureSpec)
        val edge = 18.dp(); val top = 16.dp(); val scale = controlScale / 100f
        val key = (minOf(52.dp(), (w - 32.dp()) / 7) * scale).toInt().coerceAtLeast(32.dp())
        val dx = (w * controlPositionX / 100f).toInt(); val dy = (h * controlPositionY / 100f).toInt()
        val compact = w < 600.dp(); val sw = if (compact) 48.dp() else 64.dp()
        if (compact) {
            // A phone-width top bar needs all four NDS actions in one row.
            // These fixed narrow cells leave a deliberate gap before Pad;
            // the previous desktop coordinates overlapped Next Layout and
            // Lock cursor at 320px wide.
            place(menuButton, 8.dp(), top, 52.dp(), 32.dp())
            place(padButton, w-8.dp()-62.dp(), top, 62.dp(), 32.dp())
            if (system in listOf("nds", "3ds")) place(layoutButton, 148.dp(), top, 84.dp(), 32.dp())
            if (system == "nds") place(cursor, 64.dp(), top, 80.dp(), 32.dp())
        } else {
            place(menuButton, edge, top, 64.dp(), 32.dp()); place(padButton, w-edge-64.dp(), top, 64.dp(), 32.dp())
            if (system in listOf("nds", "3ds")) place(layoutButton, w-edge-112.dp(), top, 96.dp(), 32.dp())
            if (system == "nds") place(cursor, 90.dp(), top, 102.dp(), 32.dp())
        }
        val sx = (w - sw * 3 - 10.dp()) / 2; val sy = if (compact) 52.dp() else top
        place(slow, sx, sy, sw, 28.dp()); place(normal, sx+sw+5.dp(), sy, sw, 28.dp()); place(fast, sx+sw*2+10.dp(), sy, sw, 28.dp())
        // Save sits beside the speed row so it never competes with the top actions.
        place(saveButton, sx + sw * 3 + 16.dp(), sy, 64.dp(), 28.dp())
        val bottom = h - 70.dp() + dy; val left = 18.dp() + dx; val right = w - 18.dp() - key*3 + dx
        place(keys.getValue(4), left+key, bottom-key*3, key, key)
        place(keys.getValue(5), left+key, bottom-key, key, key)
        place(keys.getValue(6), left, bottom-key*2, key, key)
        place(keys.getValue(7), left+key*2, bottom-key*2, key, key)
        place(joystick, left, bottom-key*3, key*3, key*3)
        place(circular, left, bottom-key*3, key*3, key*3)
        place(keys.getValue(8), right+key*2, bottom-key*2, key, key)
        place(keys.getValue(0), right+key, bottom-key, key, key)
        place(keys.getValue(9), right+key, bottom-key*3, key, key)
        place(keys.getValue(1), right, bottom-key*2, key, key)
        place(keys.getValue(10), edge+dx, 90.dp()+dy, (58.dp()*scale).toInt(), (34.dp()*scale).toInt()); place(keys.getValue(11), w-edge-58.dp()+dx, 90.dp()+dy, (58.dp()*scale).toInt(), (34.dp()*scale).toInt())
        place(keys.getValue(2), w/2-100.dp()+dx, h-48.dp()+dy, (86.dp()*scale).toInt(), (30.dp()*scale).toInt()); place(keys.getValue(3), w/2+14.dp()+dx, h-48.dp()+dy, (86.dp()*scale).toInt(), (30.dp()*scale).toInt())
        place(fps, (w-230.dp())/2, if (compact) 130.dp() else 54.dp(), 230.dp(), 24.dp())
        super.onMeasure(widthMeasureSpec,heightMeasureSpec)
    }
    // The auto-save path is deterministic; never walk the save tree on the UI
    // thread. Azahar's shader cache grows across a long session, so the old
    // per-second recursive scan stalled the main thread and could ANR.
    private val autoSaveFile by lazy { java.io.File(saveDirectory, "native-libretro/states/${saveDirectory.name}.autosave.state") }
    private var autoSaveLabelAt = 0L
    fun updateDiagnostics(value: String) {
        diagnostics = value; diagnosticsView?.text = value
        val message=value.lineSequence().lastOrNull().orEmpty()
        if(message.contains("completed") || message.contains("failed") || message.contains("Auto Save")) stateStatus?.text=message
        autoSaveStatus?.let { label ->
            val now = System.currentTimeMillis()
            if (message.contains("Auto Save") || now - autoSaveLabelAt > 15000) {
                val stamp = if (autoSaveFile.isFile) java.text.DateFormat.getDateTimeInstance().format(java.util.Date(autoSaveFile.lastModified())) else "—"
                label.text = "Last Auto Save: $stamp"
                autoSaveLabelAt = now
            }
        }
        val summary = value.lineSequence().firstOrNull { it.contains("FPS core=") }
        fps.text = summary?.substringBefore(" ring=") ?: value.lineSequence().firstOrNull()
        fps.visibility = if (prefs.getBoolean("show-fps", false) || value.contains("failed", true)) View.VISIBLE else View.GONE
    }
    fun refreshPreferences() {
        directionalMode = prefs.getString("directional-control-$system", "dpad") ?: "dpad"
        controlScale = prefs.getInt("virtual-control-scale-$system", 100).coerceIn(70, 140)
        controlOpacity = prefs.getInt("virtual-control-opacity-$system", 85).coerceIn(30, 100)
        controlPositionX = prefs.getInt("virtual-control-position-x-$system", 0).coerceIn(-40, 40)
        controlPositionY = prefs.getInt("virtual-control-position-y-$system", 0).coerceIn(-40, 40)
        fps.visibility = if (prefs.getBoolean("show-fps", false)) View.VISIBLE else View.GONE
        applyVirtualControlStyle()
    }
    fun onActiveLayoutChanged() { requestLayout() }
    fun mappedKey(code: Int): Int? = try { JSONObject(prefs.getString("key-map", "{}")!!).optInt(code.toString(), -1).takeIf { it >= 0 } } catch (_: Exception) { null }
    fun isMenuOpen() = menu?.isShowing == true
    fun handleEscape(): Boolean {
        if (!isMenuOpen()) return false
        if (captureKey != null) {
            captureKey = null
            keyStatus?.text = "Key capture cancelled."
        } else {
            menu?.dismiss()
        }
        return true
    }
    private fun text(label: String) = TextView(activity).apply { this.text = label; textSize = 13f; setTextColor(Color.WHITE); setPadding(0, 6.dp(), 0, 6.dp()) }

    fun showMenu() {
        if (isMenuOpen()) { menu?.dismiss(); return }
        (0..11).forEach { input(it, false) }; releaseVirtualDirections()
        send("clear-input", "")
        val draft = mutableMapOf(
            "renderer" to NativeSettings.renderer(prefs, system),
            "nds-layout" to NativeLayoutModel.normalize(activity, system, NativeSettings.layout(prefs, system) ?: prefs.getString("screen-layout-$system", prefs.getString("nds-layout", "left-right"))),
            "volume" to prefs.getInt("volume", 100).toString(), "latency" to prefs.getInt("latency", 64).toString(),
            "quality" to (prefs.getString("quality", "medium") ?: "medium"),
            "autosave-mode" to NativeAutoSave.resolve(prefs)
        )
        val flags = mutableMapOf("show-fps" to prefs.getBoolean("show-fps", false), "mute" to prefs.getBoolean("mute", false), "start-fullscreen" to prefs.getBoolean("start-fullscreen", true))
        val optionDraft = mutableMapOf<String, String>()
        val controlDraft = mutableMapOf(
            "directional" to directionalMode,
            "scale" to controlScale.toString(), "opacity" to controlOpacity.toString(),
            "position-x" to controlPositionX.toString(), "position-y" to controlPositionY.toString()
        )
        keyDraft = JSONObject(prefs.getString("key-map", "{}") ?: "{}")
        val dialog = Dialog(activity); menu = dialog
        val root = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(14.dp(), 12.dp(), 14.dp(), 12.dp()); background = shape() }
        val tabs = LinearLayout(activity)
        val tabScroll = HorizontalScrollView(activity).apply { addView(tabs); isHorizontalScrollBarEnabled = false }
        val previousTabs = button("◀").apply { contentDescription = "Previous tabs"; textSize = 18f }
        val nextTabs = button("▶").apply { contentDescription = "Next tabs"; textSize = 18f }
        // Edge indicators show only when tabs exist outside the visible region,
        // so they never look misleading when every tab already fits.
        fun updateTabArrows() {
            previousTabs.visibility = if (tabScroll.canScrollHorizontally(-1)) View.VISIBLE else View.GONE
            nextTabs.visibility = if (tabScroll.canScrollHorizontally(1)) View.VISIBLE else View.GONE
        }
        fun scrollToNextTab(direction: Int) {
            if (tabScroll.width <= 0) return
            val visibleLeft = tabScroll.scrollX
            val visibleRight = visibleLeft + tabScroll.width
            var target = -1
            for (index in 0 until tabs.childCount) {
                val child = tabs.getChildAt(index) ?: continue
                if (direction > 0 && child.right > visibleRight + 1) { target = child.left; break }
                if (direction < 0 && child.left < visibleLeft - 1) target = child.left
            }
            if (target < 0) return
            val maximum = maxOf(0, tabs.width - tabScroll.width)
            tabScroll.smoothScrollTo(target.coerceIn(0, maximum), 0)
        }
        fun ensureTabVisible(tab: String) {
            for (index in 0 until tabs.childCount) {
                val child = tabs.getChildAt(index) ?: continue
                if ((child as? Button)?.text?.toString() != tab) continue
                tabScroll.post {
                    val maximum = maxOf(0, tabs.width - tabScroll.width)
                    val visibleLeft = tabScroll.scrollX
                    val visibleRight = visibleLeft + tabScroll.width
                    when {
                        child.left < visibleLeft -> tabScroll.smoothScrollTo(child.left.coerceIn(0, maximum), 0)
                        child.right > visibleRight -> tabScroll.smoothScrollTo((child.right - tabScroll.width).coerceIn(0, maximum), 0)
                    }
                    updateTabArrows()
                }
                break
            }
        }
        previousTabs.setOnClickListener { scrollToNextTab(-1); tabScroll.post { updateTabArrows() } }
        nextTabs.setOnClickListener { scrollToNextTab(1); tabScroll.post { updateTabArrows() } }
        tabScroll.setOnScrollChangeListener { _, _, _, _, _ -> updateTabArrows() }
        tabs.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> updateTabArrows() }
        root.addView(LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            addView(previousTabs, LinearLayout.LayoutParams(38.dp(), 38.dp()))
            addView(tabScroll, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))
            addView(nextTabs, LinearLayout.LayoutParams(38.dp(), 38.dp()))
        }, LinearLayout.LayoutParams(-1, 44.dp()))
        val content = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(8.dp(), 8.dp(), 8.dp(), 8.dp()) }
        root.addView(ScrollView(activity).apply { addView(content) }, LinearLayout.LayoutParams(-1, 0, 1f))
        val saved = text("Save and Exit keeps your changes on this device; Exit discards them.")
        root.addView(saved)

        // Persist the draft through the canonical settings service, then apply
        // the values that can take effect immediately. Returns false (menu stays
        // open) if anything could not be written, so a failed save never closes
        // the menu with the changes lost.
        fun persistDraft(): Boolean {
            val edits = JSONObject()
            edits.put("renderer-$system", draft.getValue("renderer"))
            if (system in listOf("nds", "3ds")) edits.put("screen-layout-$system", draft.getValue("nds-layout"))
            edits.put("volume", draft.getValue("volume"))
            edits.put("latency", draft.getValue("latency"))
            edits.put("quality", draft.getValue("quality"))
            edits.put("autosave-mode", draft.getValue("autosave-mode"))
            flags.forEach { (key, value) -> edits.put(key, value) }
            edits.put("key-map", keyDraft.toString())
            val result = NativeSettings.save(activity, edits)
            if (!result.optBoolean("ok")) return false
            // Core options come from the live core and persist under the canonical
            // per-system keys the external Game Settings read. Virtual-control
            // presentation keeps its existing per-system preferences.
            val edit = prefs.edit()
            optionDraft.forEach { (key, value) -> edit.putString("core-$system-$key", value) }
            edit.putString("directional-control-$system", controlDraft.getValue("directional"))
            edit.putInt("virtual-control-scale-$system", controlDraft.getValue("scale").toInt())
            edit.putInt("virtual-control-opacity-$system", controlDraft.getValue("opacity").toInt())
            edit.putInt("virtual-control-position-x-$system", controlDraft.getValue("position-x").toInt())
            edit.putInt("virtual-control-position-y-$system", controlDraft.getValue("position-y").toInt())
            if (!edit.commit()) return false
            if (system in listOf("nds", "3ds")) previewLayout(draft.getValue("nds-layout"))
            optionDraft.forEach { (key, value) -> send("option", "$key\t$value") }
            settingsSaved()
            refreshPreferences()
            return true
        }

        val footer = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL }
        fun footerButton(label: String, block: () -> Unit) = button(label, action = block).apply {
            textSize = 11f; setSingleLine(false); maxLines = 2; gravity = Gravity.CENTER
        }
        val saveAndExit = footerButton("Save and Exit") {
            if (persistDraft()) {
                saved.text = "Settings saved. Layout is applied now; renderer applies on next launch."
                dialog.dismiss()
            } else {
                saved.text = "Could not save settings. The menu stays open so nothing is lost."
            }
        }
        val exitButton = footerButton("Exit") { dialog.dismiss() }
        val returnButton = footerButton("Return to Library") { dialog.dismiss(); activity.finish() }
        listOf(saveAndExit, exitButton, returnButton).forEachIndexed { index, item ->
            footer.addView(item, LinearLayout.LayoutParams(0, 46.dp(), 1f).apply { if (index < 2) rightMargin = 6.dp() })
        }
        root.addView(footer, LinearLayout.LayoutParams(-1, -2))

        fun checkbox(label: String, key: String) { content.addView(CheckBox(activity).apply { text=label; setTextColor(Color.WHITE); buttonTintList=android.content.res.ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked),intArrayOf()),intArrayOf(0xffc4b5fd.toInt(),0xff6f6885.toInt())); isChecked=flags[key] == true; setOnCheckedChangeListener { _, checked -> flags[key]=checked } }) }
        fun choice(label: String, key: String, labels: List<String>, values: List<String> = labels) {
            content.addView(text(label))
            content.addView(Spinner(activity).apply {
                adapter = choiceAdapter(labels)
                setSelection(values.indexOf(draft[key]).coerceAtLeast(0))
                onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                    override fun onNothingSelected(parent: AdapterView<*>?) {}
                    override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) { draft[key]=values[position] }
                }
            })
        }
        fun layoutChoice() {
            val layouts = NativeLayoutModel.layouts(activity, system)
            val labels = layouts.map { it.label }
            val values = layouts.map { it.id }
            content.addView(text("Screen layout · applies immediately"))
            content.addView(Spinner(activity).apply {
                adapter = choiceAdapter(labels)
                setSelection(values.indexOf(draft["nds-layout"]).coerceAtLeast(0))
                onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                    override fun onNothingSelected(parent: AdapterView<*>?) {}
                    override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                        val layout = values[position]
                        draft["nds-layout"] = layout
                        previewLayout(layout)
                    }
                }
            })
        }
        fun previewControls() {
            directionalMode = controlDraft.getValue("directional")
            controlScale = controlDraft.getValue("scale").toInt().coerceIn(70, 140)
            controlOpacity = controlDraft.getValue("opacity").toInt().coerceIn(30, 100)
            controlPositionX = controlDraft.getValue("position-x").toInt().coerceIn(-40, 40)
            controlPositionY = controlDraft.getValue("position-y").toInt().coerceIn(-40, 40)
            applyVirtualControlStyle()
        }
        fun controlChoice(label: String, key: String, labels: List<String>, values: List<String>) {
            content.addView(text(label)); content.addView(Spinner(activity).apply {
                adapter=choiceAdapter(labels); setSelection(values.indexOf(controlDraft[key]).coerceAtLeast(0))
                onItemSelectedListener=object:AdapterView.OnItemSelectedListener {
                    override fun onNothingSelected(parent: AdapterView<*>?) {}
                    override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) { controlDraft[key]=values[position]; previewControls() }
                }
            })
        }
        fun controlRange(label: String, key: String, min: Int, max: Int) {
            val value=text("$label ${controlDraft[key]}"); content.addView(value)
            content.addView(SeekBar(activity).apply { this.max=max-min; progress=controlDraft.getValue(key).toInt()-min; setOnSeekBarChangeListener(object:SeekBar.OnSeekBarChangeListener {
                override fun onStartTrackingTouch(s:SeekBar?) {}; override fun onStopTrackingTouch(s:SeekBar?) {}
                override fun onProgressChanged(s:SeekBar?, p:Int, user:Boolean) { if(user){controlDraft[key]=(p+min).toString();value.text="$label ${p+min}";previewControls()} }
            }) })
        }
        fun action(label: String, block: () -> Unit) { content.addView(button(label, action=block), LinearLayout.LayoutParams(-1, 42.dp()).apply { bottomMargin=6.dp() }) }
        fun render(tab: String) {
            for(i in 0 until tabs.childCount) {
                val item=tabs.getChildAt(i) as Button
                item.isSelected=item.text.toString()==tab
                item.backgroundTintList=android.content.res.ColorStateList.valueOf(if(item.isSelected)0xff8b5cf6.toInt() else 0xff1b1730.toInt())
            }
            diagnosticsView=null; keyStatus=null; stateStatus=null;autoSaveStatus=null; content.removeAllViews()
            when (tab) {
                "General" -> {
                    content.addView(text("VibeCodedEmulator · ${if(system=="gba") "mGBA" else if(system=="nds") "melonDS DS" else "Azahar 3DS"} native").apply { textSize=16f; typeface=Typeface.DEFAULT_BOLD })
                    content.addView(text("Keyboard: arrows, Z/X, A/S, L/J, Return and Space.\nMenu and Pad control native gameplay. Ten quick-save slots remain separate from Auto Save."))
                    checkbox("Start fullscreen on launch", "start-fullscreen"); action("Enter fullscreen now") { fullscreen() }
                    content.addView(text("Phone Controller").apply { setPadding(0, 12.dp(), 0, 0) })
                    content.addView(text("Use a phone on the same network as a controller for this game. The phone never receives the game or its saves.").apply { textSize=12f })
                    controllerStatus = text(controllerStatusText())
                    content.addView(controllerStatus)
                    action(if (controllerRunning()) "Stop controller session" else "Start controller session") { toggleController() }
                }
                "Graphics" -> {
                    choice("Renderer · applies on next launch", "renderer", listOf("Auto", "Vulkan", "OpenGL ES"), listOf("auto", "vulkan", "opengl"))
                    checkbox("Show FPS", "show-fps")
                    if(system in listOf("nds", "3ds")) layoutChoice()
                    action("Reset Graphics to Defaults") {
                        NativeSettings.resetGraphics(activity, system)
                        draft["renderer"] = NativeSettings.renderer(prefs, system)
                        draft["nds-layout"] = NativeLayoutModel.normalize(activity, system,
                            NativeSettings.layout(prefs, system) ?: prefs.getString("screen-layout-$system", "left-right"))
                        if (system in listOf("nds", "3ds")) previewLayout(draft.getValue("nds-layout"))
                        refreshPreferences()
                        saved.text = "Graphics defaults restored for $system only."
                        render("Graphics")
                    }
                }
                "Audio" -> {
                    val volumeLabel=text("Volume ${draft["volume"]}%"); content.addView(volumeLabel)
                    content.addView(SeekBar(activity).apply { max=100; progress=draft.getValue("volume").toInt(); setOnSeekBarChangeListener(object:SeekBar.OnSeekBarChangeListener {
                        override fun onStartTrackingTouch(s:SeekBar?) {}; override fun onStopTrackingTouch(s:SeekBar?) {}
                        override fun onProgressChanged(s:SeekBar?, p:Int, user:Boolean) { if(user){draft["volume"]=p.toString();volumeLabel.text="Volume $p%"} }
                    }) })
                    checkbox("Mute", "mute"); choice("Audio latency", "latency", listOf("32 ms", "64 ms", "96 ms", "128 ms"), listOf("32","64","96","128"))
                    choice("Resampler quality", "quality", listOf("Low", "Medium", "High"), listOf("low","medium","high"))
                }
                "Keyboard" -> {
                    var selected=0
                    content.addView(Spinner(activity).apply { adapter=choiceAdapter(actions); onItemSelectedListener=object:AdapterView.OnItemSelectedListener {
                        override fun onNothingSelected(p:AdapterView<*>?) {}; override fun onItemSelected(p:AdapterView<*>?,v:View?,position:Int,id:Long){selected=position}
                    } })
                    action("Map selected key") { captureKey=selected; keyStatus?.text="Press a physical key for ${actions[selected]}." }
                    action("Reset custom keyboard map") { keyDraft=JSONObject();keyStatus?.text="Custom map cleared in this draft." }
                    keyStatus=text("Choose an action, then capture one physical key.");content.addView(keyStatus)
                }
                "Controller" -> {
                    content.addView(text("Controller support: native Android gamepad buttons and directional input. Keyboard and gamepad mappings remain independent of virtual controls."))
                    controlChoice("Directional control", "directional",
                        NativeInputActions.directionalControls.map { NativeInputActions.directionalControlLabels[it] ?: it },
                        NativeInputActions.directionalControls)
                    controlRange("Virtual control scale", "scale", 70, 140)
                    controlRange("Virtual control opacity", "opacity", 30, 100)
                    controlRange("Virtual control horizontal position", "position-x", -40, 40)
                    controlRange("Virtual control vertical position", "position-y", -40, 40)
                    action("Reset virtual controls") {
                        controlDraft["directional"]="dpad";controlDraft["scale"]="100";controlDraft["opacity"]="85";controlDraft["position-x"]="0";controlDraft["position-y"]="0";previewControls();render("Controller")
                    }
                    content.addView(text("Changes preview live. Save Settings persists this device's $system controls; Escape/close discards the preview."))
                }
                "Emulation" -> {
                    content.addView(text("Core Options announced by the active libretro core"))
                    val options=try { JSONArray(coreOptions()) } catch(_:Exception){JSONArray()}
                    if(options.length()==0) content.addView(text("The core has not announced any options."))
                    for(i in 0 until options.length()) {
                        val option=options.getJSONObject(i); val key=option.getString("key")
                        // Core options the runtime intentionally pins must not be
                        // shown as if the user could override them.
                        if(key in NativeSettingsSchema.pinned(system)) continue
                        val values=option.getJSONArray("values"); val names=(0 until values.length()).map{values.getString(it)}
                        if(names.isEmpty()) continue
                        content.addView(text(option.optString("title",key)))
                        content.addView(Spinner(activity).apply { adapter=choiceAdapter(names); setSelection(names.indexOf(optionDraft[key]?:option.getString("current")).coerceAtLeast(0)); onItemSelectedListener=object:AdapterView.OnItemSelectedListener {
                            override fun onNothingSelected(p:AdapterView<*>?) {}; override fun onItemSelected(p:AdapterView<*>?,v:View?,position:Int,id:Long){optionDraft[key]=names[position]}
                        } })
                    }
                    content.addView(text("Some core options require restarting the game."))
                }
                "Save States" -> {
                    choice(NativePlayerUi.AUTO_SAVE_LABEL, "autosave-mode", NativePlayerUi.autoSaveTitles, NativePlayerUi.autoSaveTokens)
                    autoSaveStatus=text("Last Auto Save: —");content.addView(autoSaveStatus)
                    action("Load Auto Save") {send("load","auto")}
                    for(slot in 1..10) {
                        val row=LinearLayout(activity)
                        row.addView(button("Quick save $slot"){send("save",slot.toString())},LinearLayout.LayoutParams(0,40.dp(),1f).apply{rightMargin=4.dp()})
                        row.addView(button("Quick load $slot"){send("load",slot.toString())},LinearLayout.LayoutParams(0,40.dp(),1f))
                        content.addView(row,LinearLayout.LayoutParams(-1,44.dp()))
                    }
                    stateStatus=text("Quick saves use native core state bytes.");content.addView(stateStatus)
                    action("Export Save State…"){statePicker(true)};action("Import Save State…"){statePicker(false)}
                }
                "Diagnostics" -> { diagnosticsView=text(diagnostics);content.addView(diagnosticsView) }
                "About" -> {
                    content.addView(text("VibeCodedEmulator 0.4.5 · Android staging\nGBA · NDS native cores\nVulkan / OpenGL ES · AAudio"))
                    action("About VibeCodedEmulator…") { content.addView(text("Core licenses are bundled with this APK. mGBA: MPL 2.0 · melonDS DS: GPL 3.0 or later · libretro header: MIT.")) }
                    action("Resume") {dialog.dismiss()};action("Return to library") {dialog.dismiss();activity.finish()}
                }
            }
            ensureTabVisible(tab)
        }
        for(tab in NativePlayerUi.tabs) tabs.addView(button(tab){render(tab)},LinearLayout.LayoutParams(-2,36.dp()).apply{rightMargin=5.dp()})
        dialog.setContentView(root)
        dialog.setOnKeyListener { _,code,event ->
            if (code == KeyEvent.KEYCODE_ESCAPE && event.action == KeyEvent.ACTION_DOWN) return@setOnKeyListener handleEscape()
            val target=captureKey
            if(target!=null && event.action==KeyEvent.ACTION_DOWN){keyDraft.put(code.toString(),target);keyStatus?.text="${KeyEvent.keyCodeToString(code)} → ${actions[target]} (draft)";captureKey=null;true}
            else false
        }
        dialog.setOnDismissListener {
            // Layout and virtual-control edits preview while the menu is open.
            // Reloading their persisted values here gives close/Escape the same
            // discard semantics as the rest of this draft.
            if (system in listOf("nds", "3ds")) {
                previewLayout(NativeLayoutModel.normalize(activity, system,
                    prefs.getString("screen-layout-$system", prefs.getString("nds-layout", "left-right"))))
            }
            menu=null;captureKey=null;diagnosticsView=null;keyStatus=null;refreshPreferences()
        }
        dialog.window?.setBackgroundDrawableResource(android.R.color.transparent)
        dialog.show();dialog.window?.setLayout(minOf(NativePlayerUi.PANEL_WIDTH.dp(),width-24.dp()),minOf(NativePlayerUi.PANEL_HEIGHT.dp(),height-24.dp()))
        render("General")
        tabScroll.post { updateTabArrows() }
    }
}

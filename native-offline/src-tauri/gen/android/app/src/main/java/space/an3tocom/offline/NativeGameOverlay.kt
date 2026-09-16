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

// The Android app is offline-first and has no origin of its own, so the
// staging-only phone-controller service is configured explicitly. The default
// matches the isolated staging host.
private const val DEFAULT_CONTROLLER_SERVER = "http://192.0.2.8:8092"

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
    // Staging-only phone controller host. The raw host token stays in
    // ControllerClient and is never shown or persisted.
    private var controller: ControllerClient? = null
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
        listOf(4, 5, 6, 7).forEach { input(it, false) }
        directionalInput(0f, 0f)
    }
    private fun applyDirectionalMode() {
        val joystickMode = directionalMode == "joystick"
        listOf(4, 5, 6, 7).forEach { id -> keys[id]?.visibility = if (joystickMode) View.GONE else View.VISIBLE }
        joystick.visibility = if (joystickMode) View.VISIBLE else View.GONE
        if (!joystickMode) joystick.release()
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
            .setItems(slots) { _, which -> send(if (save) "save" else "load", (which + 1).toString()) }
            .setNegativeButton("Cancel", null)
            .show()
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

    // Phone controller (staging-only). The native app is the pairing host: it
    // creates the session, shows the code, polls the host state and pushes the
    // phone's frame through the same input path as the on-screen pad.
    private fun controllerServer(): String =
        (prefs.getString("controller-server", DEFAULT_CONTROLLER_SERVER) ?: DEFAULT_CONTROLLER_SERVER).trim()

    private fun toggleController() {
        val existing = controller
        if (existing != null && existing.running) {
            existing.stop()
            controller = null
            controllerStatus?.text = "Phone controller stopped."
            return
        }
        val server = controllerServer()
        if (!server.startsWith("http://") && !server.startsWith("https://")) {
            controllerStatus?.text = "Set the controller server URL (http://…)."
            return
        }
        val client = ControllerClient(
            server,
            onStatus = { message -> activity.runOnUiThread { controllerStatus?.text = message } },
            shouldApply = { !isMenuOpen() },
            onButton = { index, pressed -> input(index, pressed) },
            onAnalog = { x, y -> directionalInput(x, y) },
        )
        controller = client
        controllerStatus?.text = "Starting…"
        client.start()
    }

    fun stopController() {
        controller?.stop()
        controller = null
    }

    private fun setSpeed(value: String) {
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
            "renderer" to (prefs.getString("renderer", "auto") ?: "auto"),
            "nds-layout" to NativeLayoutModel.normalize(activity, system, prefs.getString("screen-layout-$system", prefs.getString("nds-layout", "left-right"))),
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
        root.addView(HorizontalScrollView(activity).apply { addView(tabs); isHorizontalScrollBarEnabled = false }, LinearLayout.LayoutParams(-1, 44.dp()))
        val content = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(8.dp(), 8.dp(), 8.dp(), 8.dp()) }
        root.addView(ScrollView(activity).apply { addView(content) }, LinearLayout.LayoutParams(-1, 0, 1f))
        val saved = text("Changes are saved only when you choose Save Settings.")
        root.addView(saved)
        root.addView(button("Save Settings") {
            val edit = prefs.edit()
            draft.forEach { (k,v) ->
                if (k in listOf("volume", "latency")) edit.putInt(k,v.toInt())
                else if (k == "nds-layout") {
                    edit.putString("screen-layout-$system", v)
                    if (system == "nds") edit.putString("nds-layout", v)
                } else edit.putString(k,v)
            }
            flags.forEach { (k,v) -> edit.putBoolean(k,v) }
            edit.putString("key-map", keyDraft.toString())
            optionDraft.forEach { (k,v) -> edit.putString("core-$system-$k", v); send("option", "$k\t$v") }
            edit.putString("directional-control-$system", controlDraft.getValue("directional"))
            edit.putInt("virtual-control-scale-$system", controlDraft.getValue("scale").toInt())
            edit.putInt("virtual-control-opacity-$system", controlDraft.getValue("opacity").toInt())
            edit.putInt("virtual-control-position-x-$system", controlDraft.getValue("position-x").toInt())
            edit.putInt("virtual-control-position-y-$system", controlDraft.getValue("position-y").toInt())
            edit.apply()
            if (system in listOf("nds", "3ds")) previewLayout(draft.getValue("nds-layout"))
            settingsSaved()
            refreshPreferences()
            saved.text = "Settings saved. Layout is applied now; renderer applies on next launch."
        }, LinearLayout.LayoutParams(-1, 40.dp()))

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
                    content.addView(text("Phone controller · staging").apply { setPadding(0, 12.dp(), 0, 0) })
                    content.addView(text("A phone on the same LAN pairs with a code and drives this game. The controller server is the isolated staging host.").apply { textSize=12f })
                    val serverField = EditText(activity).apply {
                        setText(controllerServer()); setTextColor(Color.WHITE); textSize = 13f
                        setHint("Controller server URL"); setSingleLine(true)
                    }
                    content.addView(serverField, LinearLayout.LayoutParams(-1, -2))
                    serverField.setOnFocusChangeListener { _, focused ->
                        if (!focused) prefs.edit().putString("controller-server", serverField.text.toString().trim()).apply()
                    }
                    controllerStatus = text(if (controller?.running == true) "Running" else "Stopped")
                    content.addView(controllerStatus)
                    action(if (controller?.running == true) "Stop phone controller" else "Start phone controller") { toggleController() }
                }
                "Graphics" -> {
                    choice("Renderer · applies on next launch", "renderer", listOf("Auto", "Vulkan", "OpenGL ES"), listOf("auto", "vulkan", "opengl"))
                    checkbox("Show FPS", "show-fps")
                    if(system in listOf("nds", "3ds")) layoutChoice()
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
                    controlChoice("Directional control", "directional", listOf("D-Pad", "Analog Joystick"), listOf("dpad", "joystick"))
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
                        if(key in listOf("melonds_render_mode", "melonds_screen_layout1", "melonds_number_of_screen_layouts", "melonds_touch_mode")) continue
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
    }
}

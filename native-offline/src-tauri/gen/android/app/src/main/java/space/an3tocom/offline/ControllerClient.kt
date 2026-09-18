// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/** Snapshot of the phone-controller host. Never carries the raw host token. */
data class ControllerStatus(
    val running: Boolean,
    val paired: Boolean,
    val code: String,
    val inputActive: Boolean,
    val lastSequence: Int,
    val ackSequence: Int,
    val input: String,
    val error: String,
) {
    fun toJson(): String = JSONObject()
        .put("running", running)
        .put("paired", paired)
        .put("code", code)
        .put("inputActive", inputActive)
        .put("lastSequence", lastSequence)
        .put("ackSequence", ackSequence)
        .put("input", input)
        .put("error", error)
        .toString()
}

/**
 * Staging-only phone-controller host for native gameplay.
 *
 * The native app is the pairing host: it creates a short-lived controller
 * session on the configured staging server, shows the phone the pairing code,
 * polls the host-state endpoint, feeds the phone's latest frame into the same
 * input path the on-screen pad uses, and acknowledges frames that were really
 * applied. The raw host token never leaves this process and is never logged.
 */
class ControllerClient(
    private val baseUrl: String,
    private val onStatus: (ControllerStatus) -> Unit,
    private val shouldApply: () -> Boolean,
    private val onButton: (Int, Boolean) -> Unit,
    private val onAnalog: (Float, Float) -> Unit,
    private val systemProvider: () -> String? = { null },
    private val onTouch: (Float, Float, Boolean) -> Unit = { _, _, _ -> },
    private val onUtility: (String) -> Unit = {},
) {
    companion object {
        // Same libretro joypad indices the web player and phone page use.
        val BUTTONS = mapOf(
            "b" to 0, "y" to 1, "select" to 2, "start" to 3,
            "up" to 4, "down" to 5, "left" to 6, "right" to 7,
            "a" to 8, "x" to 9, "l" to 10, "r" to 11,
        )
        private const val POLL_MILLIS = 250L
        private const val AXIS_THRESHOLD = 0.35f
        private val EMPTY = ControllerStatus(false, false, "", false, 0, 0, "", "")
    }

    private val scheduler = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "an3-controller").apply { isDaemon = true }
    }
    @Volatile private var poll: ScheduledFuture<*>? = null
    @Volatile private var code = ""
    @Volatile private var hostToken = ""
    @Volatile private var applied = setOf<String>()
    @Volatile private var axesEngaged = false
    @Volatile private var touchPressed = false
    @Volatile private var lastAck = 0
    @Volatile private var lastUtility = 0

    val running: Boolean get() = poll != null

    fun start() {
        if (running) return
        onStatus(EMPTY.copy(error = ""))
        scheduler.execute {
            try {
                val session = request(
                    "POST",
                    "/api/controller/session",
                    JSONObject()
                        .put("deviceId", "android-native")
                        .put("name", "Android device")
                        .put("ttlSeconds", 3600),
                )
                code = session.optString("code")
                hostToken = session.optString("hostToken")
                if (code.isEmpty() || hostToken.isEmpty()) throw IllegalStateException("Invalid session response")
                lastAck = 0
                onStatus(ControllerStatus(true, false, code, false, 0, 0, "", ""))
                poll = scheduler.scheduleWithFixedDelay({ pollOnce() }, 0, POLL_MILLIS, TimeUnit.MILLISECONDS)
            } catch (error: Exception) {
                release()
                code = ""
                hostToken = ""
                onStatus(EMPTY.copy(error = "Controller unavailable: ${error.message}"))
            }
        }
    }

    fun stop() {
        poll?.cancel(false)
        poll = null
        code = ""
        hostToken = ""
        lastAck = 0
        lastUtility = 0
        release()
        onStatus(EMPTY.copy(error = ""))
    }

    private fun pollOnce() {
        if (code.isEmpty() || hostToken.isEmpty()) return
        try {
            val payload = request(
                "GET",
                "/api/controller/state?code=${encodeURIComponent(code)}&hostToken=${encodeURIComponent(hostToken)}",
                null,
            )
            val lastSequence = payload.optInt("lastSequence", 0)
            val ackSequence = payload.optInt("ackSequence", 0)
            if (shouldApply()) {
                apply(payload)
                dispatchUtilities(payload)
                if (lastSequence > lastAck && lastSequence > 0) {
                    ack(lastSequence)
                }
            } else {
                release()
            }
            onStatus(
                ControllerStatus(
                    running = true,
                    paired = payload.optBoolean("paired"),
                    code = code,
                    inputActive = shouldApply() && payload.optBoolean("inputActive"),
                    lastSequence = lastSequence,
                    ackSequence = maxOf(ackSequence, lastAck),
                    input = describe(payload),
                    error = "",
                ),
            )
        } catch (error: Exception) {
            // A 403/404 means the session ended or expired.
            stop()
            onStatus(EMPTY.copy(error = "Controller session ended"))
        }
    }

    private fun ack(sequence: Int) {
        val body = JSONObject()
            .put("code", code)
            .put("hostToken", hostToken)
            .put("sequence", sequence)
            .put("utilitySequence", lastUtility)
        systemProvider()?.let { system -> if (system.isNotBlank()) body.put("system", system) }
        request("POST", "/api/controller/ack", body)
        lastAck = sequence
    }

    /**
     * Dispatch each pending utility action at most once. The server resends the
     * pending list until it is acknowledged, so the host — not the network —
     * enforces "once per deliberate press".
     */
    private fun dispatchUtilities(payload: JSONObject) {
        val utilities = payload.optJSONArray("utilities") ?: return
        for (index in 0 until utilities.length()) {
            val entry = utilities.optJSONObject(index) ?: continue
            val sequence = entry.optInt("sequence", 0)
            if (sequence <= lastUtility) continue
            lastUtility = sequence
            val action = entry.optString("action")
            if (action.isNotEmpty()) onUtility(action)
        }
    }

    private fun apply(payload: JSONObject) {
        val state = payload.optJSONObject("state")
        val pressed = mutableSetOf<String>()
        state?.optJSONArray("b")?.let { array ->
            for (index in 0 until array.length()) {
                val name = array.optString(index)
                if (BUTTONS.containsKey(name)) pressed.add(name)
            }
        }
        for (name in applied) if (!pressed.contains(name)) BUTTONS[name]?.let { onButton(it, false) }
        for (name in pressed) if (!applied.contains(name)) BUTTONS[name]?.let { onButton(it, true) }
        applied = pressed
        val axes = state?.optJSONArray("a")
        val leftX = axes?.optDouble(0, 0.0)?.toFloat() ?: 0f
        val leftY = axes?.optDouble(1, 0.0)?.toFloat() ?: 0f
        val engaged = kotlin.math.abs(leftX) > AXIS_THRESHOLD || kotlin.math.abs(leftY) > AXIS_THRESHOLD
        if (engaged) { onAnalog(leftX, leftY); axesEngaged = true }
        else if (axesEngaged) { onAnalog(0f, 0f); axesEngaged = false }
        // Normalized 0..1 stylus position for the host's NDS/3DS touch screen.
        val touch = state?.optJSONArray("t")
        if (touch != null && touch.length() == 2) {
            onTouch(touch.optDouble(0, 0.0).toFloat(), touch.optDouble(1, 0.0).toFloat(), true)
            touchPressed = true
        } else if (touchPressed) {
            onTouch(0f, 0f, false)
            touchPressed = false
        }
    }

    private fun release() {
        for (name in applied) BUTTONS[name]?.let { onButton(it, false) }
        applied = emptySet()
        if (axesEngaged) { onAnalog(0f, 0f); axesEngaged = false }
        if (touchPressed) { onTouch(0f, 0f, false); touchPressed = false }
    }

    /** Release any input this session is holding, without ending the session. */
    fun releaseInput() {
        release()
    }

    private fun describe(payload: JSONObject): String {
        val array = payload.optJSONObject("state")?.optJSONArray("b") ?: return ""
        return (0 until array.length()).joinToString(",") { array.optString(it) }
    }

    private fun encodeURIComponent(value: String): String =
        java.net.URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    private fun request(method: String, path: String, body: JSONObject?): JSONObject {
        val connection = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 4000
            readTimeout = 4000
            setRequestProperty("Accept", "application/json")
        }
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        }
        return try {
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            if (status !in 200..299) throw IllegalStateException("HTTP $status")
            JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }
}

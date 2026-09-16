// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Staging-only phone-controller host for native gameplay.
 *
 * The native app is the pairing host: it creates a short-lived controller
 * session on the configured staging server, shows the phone the pairing code,
 * polls the host-state endpoint, and feeds the phone's latest frame into the
 * same input path the on-screen pad uses. The raw host token never leaves this
 * process and is never logged.
 */
class ControllerClient(
    private val baseUrl: String,
    private val onStatus: (String) -> Unit,
    private val shouldApply: () -> Boolean,
    private val onButton: (Int, Boolean) -> Unit,
    private val onAnalog: (Float, Float) -> Unit,
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
    }

    private val scheduler = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "an3-controller").apply { isDaemon = true }
    }
    @Volatile private var poll: ScheduledFuture<*>? = null
    @Volatile private var code = ""
    @Volatile private var hostToken = ""
    @Volatile private var applied = setOf<String>()
    @Volatile private var axesEngaged = false

    val running: Boolean get() = poll != null

    fun start() {
        if (running) return
        onStatus("Creating session…")
        scheduler.execute {
            try {
                val session = request(
                    "POST",
                    "/api/controller/session",
                    JSONObject().put("deviceId", "android-native").put("ttlSeconds", 3600),
                )
                code = session.optString("code")
                hostToken = session.optString("hostToken")
                if (code.isEmpty() || hostToken.isEmpty()) throw IllegalStateException("Invalid session response")
                val link = session.optString("joinPath")
                onStatus("Pairing code $code · $baseUrl$link")
                poll = scheduler.scheduleWithFixedDelay({ pollOnce() }, 0, POLL_MILLIS, TimeUnit.MILLISECONDS)
            } catch (error: Exception) {
                onStatus("Controller unavailable: ${error.message}")
                release()
            }
        }
    }

    fun stop() {
        poll?.cancel(false)
        poll = null
        code = ""
        hostToken = ""
        release()
    }

    private fun pollOnce() {
        if (code.isEmpty() || hostToken.isEmpty()) return
        try {
            val payload = request(
                "GET",
                "/api/controller/state?code=${encodeURIComponent(code)}&hostToken=${encodeURIComponent(hostToken)}",
                null,
            )
            if (shouldApply()) apply(payload) else release()
            val state = payload.optJSONObject("state")
            if (!payload.optBoolean("paired")) {
                // Keep the pairing code visible: it is the only way the phone's
                // user can join before a device is paired.
                onStatus("Pairing code $code · waiting for a phone · ${payload.optInt("expiresInSeconds")}s")
            } else {
                val names = state?.optJSONArray("b")?.let { array -> (0 until array.length()).map { array.optString(it) } } ?: emptyList()
                onStatus("Phone connected · ${names.joinToString(",").ifEmpty { "no input" }} · ${payload.optInt("expiresInSeconds")}s")
            }
        } catch (error: Exception) {
            // A 403/404 means the session ended or expired.
            onStatus("Controller session ended")
            stop()
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
    }

    private fun release() {
        for (name in applied) BUTTONS[name]?.let { onButton(it, false) }
        applied = emptySet()
        if (axesEngaged) { onAnalog(0f, 0f); axesEngaged = false }
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

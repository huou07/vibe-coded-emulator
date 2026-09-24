// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.app.Service
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Message
import android.os.Messenger
import android.os.RemoteException

/**
 * Bridges the app-scoped phone-controller host (the library Settings card,
 * running in the main process) to the isolated native game process.
 *
 * [NativeGameActivity] runs in `:game`, so it cannot share [An3ControllerHost]
 * directly. It binds here, attaches a reply [Messenger], and receives the
 * phone's buttons/axes as they are applied. The raw host token never crosses
 * this boundary; only resolved input and a short status string do.
 */
class ControllerHostService : Service() {
    companion object {
        const val MSG_ATTACH = 1
        const val MSG_DETACH = 2
        const val MSG_MENU = 3
        const val MSG_START = 4
        const val MSG_STOP = 5
        const val MSG_STATUS = 6
        const val MSG_INPUT = 10
        const val KEY_KIND = "kind"
        const val KEY_BUTTON = "button"
        const val KEY_PRESSED = "pressed"
        const val KEY_ACTION = "action"
        const val KEY_SLOT = "slot"
        const val KEY_X = "x"
        const val KEY_Y = "y"
        const val KEY_MENU = "menu"
        const val KEY_SYSTEM = "system"
        const val KEY_RUNNING = "running"
        const val KEY_STATUS = "status"
    }

    private var game: Messenger? = null
    private var menuOpen = false
    private var activeSystem: String? = null

    private val sink = object : An3ControllerHost.Sink {
        // Menu navigation is also delivered through the game process; the
        // overlay consumes those button events while it is open.
        override fun canApply(): Boolean = game != null
        override fun button(index: Int, pressed: Boolean) = forward(
            Bundle().apply { putString(KEY_KIND, "button"); putInt(KEY_BUTTON, index); putBoolean(KEY_PRESSED, pressed) },
        )
        override fun analog(x: Float, y: Float) = forward(
            Bundle().apply { putString(KEY_KIND, "analog"); putFloat(KEY_X, x); putFloat(KEY_Y, y) },
        )
        override fun touch(x: Float, y: Float, pressed: Boolean) = forward(
            Bundle().apply { putString(KEY_KIND, "touch"); putFloat(KEY_X, x); putFloat(KEY_Y, y); putBoolean(KEY_PRESSED, pressed) },
        )
        override fun utility(action: String, slot: Int) = forward(
            Bundle().apply { putString(KEY_KIND, "utility"); putString(KEY_ACTION, action); putInt(KEY_SLOT, slot) },
        )
        override fun system(): String? = if (game != null) activeSystem else null
    }

    private fun forward(bundle: Bundle) {
        val target = game ?: return
        try {
            target.send(Message.obtain(null, MSG_INPUT).apply { data = bundle })
        } catch (_: RemoteException) {
            game = null
        }
    }

    private fun sendStatus() {
        val target = game ?: return
        val status = An3ControllerHost.status()
        val bundle = Bundle().apply {
            putBoolean(KEY_RUNNING, status.running)
            putString(KEY_STATUS, statusText(status))
        }
        try {
            target.send(Message.obtain(null, MSG_STATUS).apply { data = bundle })
        } catch (_: RemoteException) {
            game = null
        }
    }

    private fun statusText(status: ControllerStatus): String = when {
        status.error.isNotEmpty() -> status.error
        !status.running -> "Off"
        !status.paired -> "Waiting for device"
        status.inputActive -> "Connected"
        else -> "Connected — input unavailable"
    }

    private val handler = Handler(Looper.getMainLooper()) { message ->
        when (message.what) {
            MSG_ATTACH -> {
                game = message.replyTo
                menuOpen = message.data?.getBoolean(KEY_MENU) ?: false
                activeSystem = message.data?.getString(KEY_SYSTEM)
                An3ControllerHost.setSink(sink)
                sendStatus()
            }
            MSG_DETACH -> { game = null; activeSystem = null }
            MSG_MENU -> menuOpen = message.data?.getBoolean(KEY_MENU) ?: false
            MSG_START -> {
                An3ControllerHost.start()
                sendStatus()
            }
            MSG_STOP -> {
                An3ControllerHost.stop()
                sendStatus()
            }
        }
        true
    }

    private val messenger = Messenger(handler)

    private val statusTick = object : Runnable {
        override fun run() {
            if (game != null) sendStatus()
            handler.postDelayed(this, 700)
        }
    }

    override fun onCreate() {
        super.onCreate()
        An3ControllerHost.setSink(sink)
        handler.post(statusTick)
    }

    override fun onDestroy() {
        handler.removeCallbacks(statusTick)
        An3ControllerHost.setSink(null)
        game = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder = messenger.binder
}

// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

/**
 * App-scoped phone-controller host shared by every surface.
 *
 * There is exactly one implementation: the library Settings card, the in-game
 * menu, and [ControllerClient] all use this object. A running game attaches a
 * [Sink] so phone frames reach its input path; when the game exits the sink is
 * cleared and held input is released, but the pairing session keeps running so
 * entering or leaving a game does not drop the phone.
 */
object An3ControllerHost {
    interface Sink {
        /** False while the game cannot accept input (not running, menu open). */
        fun canApply(): Boolean
        fun button(index: Int, pressed: Boolean)
        fun analog(x: Float, y: Float)
        /** Normalized 0..1 stylus position; pressed=false is a release. */
        fun touch(x: Float, y: Float, pressed: Boolean) {}
        /** One-shot canonical utility action (QUICK_SAVE/SPEED_UP/SPEED_DOWN/OPEN_MENU). */
        fun utility(action: String) {}
        /** The running system (gba/nds/3ds) so the phone picks the right layout. */
        fun system(): String? = null
    }

    private val empty = ControllerStatus(false, false, "", false, 0, 0, "", "")

    @Volatile private var sink: Sink? = null
    @Volatile private var client: ControllerClient? = null
    @Volatile private var status: ControllerStatus = empty

    @Synchronized
    fun setSink(value: Sink?) {
        if (value == null) client?.releaseInput()
        sink = value
    }

    @Synchronized
    fun start(baseUrl: String) {
        if (status.running) return
        status = empty
        val created = ControllerClient(
            baseUrl = baseUrl,
            onStatus = { update ->
                status = update
                if (!update.running && update.error.isNotEmpty()) {
                    client = null
                }
            },
            shouldApply = { sink?.canApply() == true },
            onButton = { index, pressed -> sink?.button(index, pressed) },
            onAnalog = { x, y -> sink?.analog(x, y) },
            systemProvider = { sink?.system() },
            onTouch = { x, y, pressed -> sink?.touch(x, y, pressed) },
            onUtility = { action -> sink?.utility(action) },
        )
        client = created
        created.start()
    }

    @Synchronized
    fun stop() {
        val current = client
        client = null
        current?.stop()
        status = empty
    }

    fun status(): ControllerStatus = status

    fun statusJson(): String = status.toJson()
}

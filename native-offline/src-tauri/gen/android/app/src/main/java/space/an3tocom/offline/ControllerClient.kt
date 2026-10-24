// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import org.json.JSONArray
import org.json.JSONObject
import java.io.DataInputStream
import java.io.DataOutputStream
import java.math.BigInteger
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.ServerSocket
import java.net.Socket
import java.nio.ByteBuffer
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** Public controller status; resume credentials never leave this process. */
data class ControllerStatus(
    val running: Boolean,
    val role: String,
    val paired: Boolean,
    val code: String,
    val inputActive: Boolean,
    val lastSequence: Int,
    val ackSequence: Int,
    val input: String,
    val error: String,
    val canReconnect: Boolean = false,
) {
    fun toJson(): String = JSONObject()
        .put("running", running)
        .put("role", role)
        .put("paired", paired)
        .put("code", code)
        .put("inputActive", inputActive)
        .put("lastSequence", lastSequence)
        .put("ackSequence", ackSequence)
        .put("input", input)
        .put("error", error)
        .put("canReconnect", canReconnect)
        .toString()
}

/**
 * Direct LAN peer host for native gameplay.
 *
 * Discovery is a private multicast advertisement containing only public peer
 * metadata. The connection is a direct TCP stream. The six-digit code is used
 * once to derive an ephemeral AES-GCM session key from P-256 ECDH; it is never
 * sent to a server or retained after pairing.
 */
class ControllerClient(
    private val onStatus: (ControllerStatus) -> Unit,
    private val shouldApply: () -> Boolean,
    private val onButton: (Int, Boolean) -> Unit,
    private val onAnalog: (Float, Float) -> Unit,
    private val systemProvider: () -> String? = { null },
    private val onTouch: (Float, Float, Boolean) -> Unit = { _, _, _ -> },
    private val onUtility: (String) -> Unit = {},
) {
    companion object {
        val BUTTONS = mapOf(
            "b" to 0, "y" to 1, "select" to 2, "start" to 3,
            "up" to 4, "down" to 5, "left" to 6, "right" to 7,
            "a" to 8, "x" to 9, "l" to 10, "r" to 11,
        )
        private const val DISCOVERY_ADDRESS = "239.255.43.3"
        private const val DISCOVERY_PORT = 47831
        private const val CONTROL_PORT = 47832
        private const val PROTOCOL_VERSION = 1
        private const val MAX_FRAME_BYTES = 64 * 1024
        private const val PAIRING_TTL_MILLIS = 120_000L
        private const val MAX_FAILURES_PER_MINUTE = 6
        private const val FAILURE_WINDOW_MILLIS = 60_000L
        private const val AXIS_THRESHOLD = 0.35f
        private const val DIR_PHONE_TO_HOST = 1
        private const val DIR_HOST_TO_PHONE = 2
        private val EMPTY = ControllerStatus(false, "off", false, "", false, 0, 0, "", "", false)
        private val RANDOM = SecureRandom()
        private val failureLock = Any()
        private val failedAttempts = mutableMapOf<String, MutableList<Long>>()
    }

    private val executor = Executors.newCachedThreadPool { runnable ->
        Thread(runnable, "an3-lan-peer").apply { isDaemon = true }
    }
    private val stopping = AtomicBoolean(false)
    @Volatile private var server: ServerSocket? = null
    @Volatile private var discovery: DatagramSocket? = null
    @Volatile private var clientSocket: Socket? = null
    @Volatile private var hostSocket: Socket? = null
    @Volatile private var clientKey: ByteArray? = null
    @Volatile private var clientSystem = "auto"
    @Volatile private var clientInputActive = false
    @Volatile private var clientSendCounter = 1L
    @Volatile private var hostResumeToken: ByteArray? = null
    @Volatile private var clientResumeToken: ByteArray? = null
    @Volatile private var clientHostId: String? = null
    @Volatile private var code = ""
    @Volatile private var codeExpiresAt = 0L
    @Volatile private var paired = false
    @Volatile private var lastSequence = 0
    @Volatile private var lastUtility = 0
    @Volatile private var ackSequence = 0
    @Volatile private var input = ""
    @Volatile private var error = ""
    @Volatile private var applied = emptySet<String>()
    @Volatile private var axesEngaged = false
    @Volatile private var touchPressed = false
    private val deviceId = randomHex(16)
    private val pairingLock = Any()

    val running: Boolean get() = (server != null || clientSocket != null || clientResumeToken != null) && !stopping.get()

    private fun failureKey(address: InetAddress): String = address.hostAddress ?: address.toString()

    private fun rateLimited(address: InetAddress): Boolean = synchronized(failureLock) {
        val key = failureKey(address)
        val now = System.currentTimeMillis()
        val attempts = failedAttempts[key] ?: return@synchronized false
        attempts.removeAll { now - it >= FAILURE_WINDOW_MILLIS }
        if (attempts.isEmpty()) failedAttempts.remove(key)
        attempts.size >= MAX_FAILURES_PER_MINUTE
    }

    private fun noteFailure(address: InetAddress) = synchronized(failureLock) {
        val key = failureKey(address)
        val now = System.currentTimeMillis()
        val attempts = failedAttempts.getOrPut(key) { mutableListOf() }
        attempts.removeAll { now - it >= FAILURE_WINDOW_MILLIS }
        attempts.add(now)
    }

    private fun clearFailures(address: InetAddress) = synchronized(failureLock) {
        failedAttempts.remove(failureKey(address))
    }

    @Synchronized
    fun start() {
        if (running) return
        stop()
        stopping.set(false)
        code = newPairingCode()
        codeExpiresAt = System.currentTimeMillis() + PAIRING_TTL_MILLIS
        paired = false
        lastSequence = 0
        lastUtility = 0
        ackSequence = 0
        input = ""
        error = ""
        try {
            server = ServerSocket(CONTROL_PORT, 8, InetAddress.getByName("0.0.0.0"))
        } catch (failure: Exception) {
            error = "Direct LAN controller unavailable: ${failure.message}"
            onStatus(status())
            return
        }
        onStatus(status())
        executor.execute { acceptLoop() }
        executor.execute { advertiseLoop() }
    }

    /** Join a direct controller host discovered on the local multicast LAN. */
    @Synchronized
    fun join(pairCode: String) {
        val normalized = pairCode.trim()
        if (!Regex("^[0-9]{6}$").matches(normalized)) {
            error = "Enter exactly six decimal digits."
            onStatus(status())
            return
        }
        stop()
        stopping.set(false)
        code = ""
        codeExpiresAt = 0L
        clientHostId = null
        paired = false
        lastSequence = 0
        lastUtility = 0
        ackSequence = 0
        clientSystem = "auto"
        clientInputActive = false
        error = ""
        try {
            connectController(normalized.toByteArray(Charsets.UTF_8), pairing = true)
        } catch (failure: Exception) {
            clientSocket = null
            clientKey = null
            clientResumeToken = null
            paired = false
            clientInputActive = false
            error = failure.message ?: "Could not join the direct LAN host."
            onStatus(status())
        }
    }

    /** Resume a previously paired direct session using its host-issued token. */
    @Synchronized
    fun reconnect(): ControllerStatus {
        val token = clientResumeToken
        if (token == null) {
            error = "No saved direct-session token is available. Pair with a new code."
            onStatus(status())
            return status()
        }
        if (clientSocket != null) return status()
        stopping.set(false)
        error = ""
        try {
            connectController(token, pairing = false)
        } catch (failure: Exception) {
            clientSocket = null
            clientKey = null
            paired = false
            clientInputActive = false
            error = failure.message ?: "Could not reconnect to the direct LAN host."
            onStatus(status())
        }
        return status()
    }

    private fun connectController(secretBytes: ByteArray, pairing: Boolean) {
        val peer = discoverController(if (pairing) null else clientHostId)
        val connection = Socket()
        try {
            connection.connect(InetSocketAddress(peer.address, peer.port), 30_000)
            connection.soTimeout = 30_000
            val inputStream = DataInputStream(connection.getInputStream())
            val outputStream = DataOutputStream(connection.getOutputStream())
            val secret = ecKeyPair()
            val hello = JSONObject()
                .put("k", "hello")
                .put("v", PROTOCOL_VERSION)
                .put("pub", encode(publicKeyBytes(secret.public)))
                .put("id", deviceId)
                .put("name", "Android device")
                .put("capability", "controller")
            writeFrame(outputStream, hello.toString().toByteArray(Charsets.UTF_8))
            val response = JSONObject(String(readFrame(inputStream), Charsets.UTF_8))
            require(response.optString("k") == "hello" && response.optInt("v") == PROTOCOL_VERSION) {
                "The direct peer uses an incompatible protocol."
            }
            val hostId = response.optString("id")
            require(hostId.isNotBlank() && (pairing || hostId == clientHostId)) {
                "The discovered host is not the paired device."
            }
            val peerPublic = publicKeyFromRaw(decode(response.optString("pub")))
            val agreement = KeyAgreement.getInstance("ECDH")
            agreement.init(secret.private)
            agreement.doPhase(peerPublic, true)
            val sessionKey = deriveKey(agreement.generateSecret(), secretBytes)
            writeFrame(outputStream, seal(sessionKey, DIR_PHONE_TO_HOST, 0, JSONObject().put("k", "auth")))
            val ready = open(sessionKey, DIR_HOST_TO_PHONE, 0, readFrame(inputStream))
                ?: throw IllegalStateException("The direct peer rejected the pairing code or resume token.")
            require(ready.optString("k") == "ready") { "The direct peer did not confirm the session." }
            val tokenText = ready.optString("token", "")
            val returnedToken = try { decode(tokenText).takeIf { it.size == 32 } } catch (_: Exception) { null }
            if (pairing) {
                clientResumeToken = returnedToken
                clientHostId = hostId
            } else if (returnedToken != null) {
                clientResumeToken = returnedToken
            }
            clientSocket = connection
            clientKey = sessionKey
            clientSendCounter = 1L
            clientSystem = ready.optString("system", "auto")
            paired = true
            onStatus(status())
            executor.execute { clientReadLoop(connection, inputStream, sessionKey) }
        } catch (failure: Exception) {
            try { connection.close() } catch (_: Exception) {}
            throw failure
        }
    }

    @Synchronized
    fun stop() {
        stopping.set(true)
        try { server?.close() } catch (_: Exception) {}
        try { discovery?.close() } catch (_: Exception) {}
        try { clientSocket?.close() } catch (_: Exception) {}
        try { hostSocket?.close() } catch (_: Exception) {}
        server = null
        discovery = null
        clientSocket = null
        hostSocket = null
        clientKey = null
        clientSystem = "auto"
        clientInputActive = false
        clientSendCounter = 1L
        clientResumeToken = null
        clientHostId = null
        hostResumeToken = null
        release()
        code = ""
        codeExpiresAt = 0L
        paired = false
        lastUtility = 0
        input = ""
        error = ""
        onStatus(EMPTY.copy(error = ""))
    }

    fun releaseInput() = release()

    /** Send one complete controller snapshot over the encrypted direct session. */
    @Synchronized
    fun sendState(state: JSONObject): ControllerStatus {
        val connection = clientSocket ?: return status().copy(error = "No direct controller session is active.")
        val key = clientKey ?: return status().copy(error = "The direct controller session is not authenticated.")
        return try {
            state.put("k", "state")
            val output = DataOutputStream(connection.getOutputStream())
            writeFrame(output, seal(key, DIR_PHONE_TO_HOST, clientSendCounter, state))
            clientSendCounter += 1
            status()
        } catch (failure: Exception) {
            setError("Direct controller send failed: ${failure.message ?: "connection closed"}")
            status()
        }
    }

    fun status(): ControllerStatus {
        val client = clientSocket != null
        return ControllerStatus(
            running = running,
            role = if (client || clientResumeToken != null) "controller" else if (server != null) "host" else "off",
            paired = paired,
            code = if (!client && server != null && running && !paired && System.currentTimeMillis() < codeExpiresAt) code else "",
            inputActive = if (client) clientInputActive else hostSocket != null && shouldApply() && paired,
            lastSequence = lastSequence,
            ackSequence = ackSequence,
            input = if (client) "" else input,
            error = error,
            canReconnect = !client && clientResumeToken != null,
        )
    }

    private fun acceptLoop() {
        while (!stopping.get()) {
            try {
                val socket = server?.accept() ?: break
                executor.execute { handle(socket) }
            } catch (_: Exception) {
                if (!stopping.get()) setError("Direct LAN controller stopped unexpectedly")
            }
        }
    }

    private fun advertiseLoop() {
        try {
            val address = InetAddress.getByName(DISCOVERY_ADDRESS)
            val socket = DatagramSocket()
            discovery = socket
            while (!stopping.get()) {
                val advertisement = JSONObject()
                    .put("an3", "peer")
                    .put("service", "an3-peer")
                    .put("v", PROTOCOL_VERSION)
                    .put("id", deviceId)
                    .put("name", "Android device")
                    .put("port", CONTROL_PORT)
                    // Native sync is intentionally not advertised until this
                    // shell has an account-backed peer proof provider.
                    .put("capabilities", JSONArray().put("controller"))
                    .toString()
                    .toByteArray(Charsets.UTF_8)
                socket.send(DatagramPacket(advertisement, advertisement.size, address, DISCOVERY_PORT))
                Thread.sleep(2000)
            }
        } catch (_: Exception) {
            if (!stopping.get()) setError("Direct LAN discovery unavailable")
        }
    }

    private data class DiscoveredPeer(val address: InetAddress, val port: Int, val id: String)

    private fun discoverController(expectedId: String? = null): DiscoveredPeer {
        MulticastSocket(DISCOVERY_PORT).use { socket ->
            val group = InetAddress.getByName(DISCOVERY_ADDRESS)
            socket.joinGroup(group)
            socket.soTimeout = 250
            val deadline = System.currentTimeMillis() + 3_000L
            val buffer = ByteArray(4096)
            while (System.currentTimeMillis() < deadline) {
                try {
                    val packet = DatagramPacket(buffer, buffer.size)
                    socket.receive(packet)
                    val record = JSONObject(String(packet.data, packet.offset, packet.length, Charsets.UTF_8))
                    val sensitive = record.keys().asSequence().any { it.matches(Regex("(?i)account|email|token|accessToken|refreshToken|password|credential|secret|auth")) }
                    val capabilities = record.optJSONArray("capabilities")
                    val controller = capabilities != null && (0 until capabilities.length()).any { capabilities.optString(it) == "controller" }
                    val id = record.optString("id")
                    val name = record.optString("name")
                    val port = record.optInt("port", 0)
                    if (!sensitive && record.optString("an3") == "peer" && record.optString("service") == "an3-peer" && record.optInt("v") == PROTOCOL_VERSION && controller && port in 1..65535 && Regex("^[A-Za-z0-9._-]{8,64}$").matches(id) && name.length in 1..64 && (expectedId == null || id == expectedId)) {
                        return DiscoveredPeer(packet.address, port, id)
                    }
                } catch (_: Exception) {
                    // Keep listening until the bounded discovery window expires.
                }
            }
        }
        if (expectedId != null) throw IllegalStateException("The paired controller host was not found on the local network.")
        throw IllegalStateException("No AN3 controller host was found on the local network.")
    }

    private fun clientReadLoop(connection: Socket, inputStream: DataInputStream, key: ByteArray) {
        var receiveCounter = 1L
        try {
            while (!stopping.get() && !connection.isClosed) {
                val frame = open(key, DIR_HOST_TO_PHONE, receiveCounter, readFrame(inputStream))
                    ?: throw IllegalStateException("The direct controller acknowledgement failed authentication.")
                receiveCounter += 1
                if (frame.optString("k") == "ack") {
                    ackSequence = frame.optLong("s", 0).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
                    clientInputActive = frame.optBoolean("inputActive", false)
                    clientSystem = frame.optString("system", clientSystem)
                    error = ""
                    onStatus(status())
                }
            }
        } catch (failure: Exception) {
            if (!stopping.get()) setError("Direct controller session ended")
        } finally {
            if (clientSocket === connection) {
                clientSocket = null
                clientKey = null
                paired = false
                clientInputActive = false
                if (!stopping.get()) onStatus(status())
            }
            try { connection.close() } catch (_: Exception) {}
        }
    }

    private fun handle(socket: Socket) {
        socket.use { connection ->
            var activated = false
            try {
                val peerAddress = connection.inetAddress
                connection.soTimeout = 30_000
                val inputStream = DataInputStream(connection.getInputStream())
                val outputStream = DataOutputStream(connection.getOutputStream())
                val hello = JSONObject(String(readFrame(inputStream), Charsets.UTF_8))
                val peerId = hello.optString("id")
                if (hello.optString("k") != "hello" || hello.optInt("v") != PROTOCOL_VERSION || hello.optString("capability") != "controller" || !Regex("^[A-Za-z0-9._-]{8,64}$").matches(peerId)) {
                    noteFailure(peerAddress)
                    return
                }
                if (rateLimited(peerAddress)) return
                val peerPublic = publicKeyFromRaw(decode(hello.optString("pub")))
                val keyPair = ecKeyPair()
                val agreement = KeyAgreement.getInstance("ECDH")
                agreement.init(keyPair.private)
                agreement.doPhase(peerPublic, true)
                val shared = agreement.generateSecret()
                val response = JSONObject()
                    .put("k", "hello")
                    .put("v", PROTOCOL_VERSION)
                    .put("pub", encode(publicKeyBytes(keyPair.public)))
                    .put("id", deviceId)
                    .put("name", "Android device")
                writeFrame(outputStream, response.toString().toByteArray(Charsets.UTF_8))

                val sealedAuth = readFrame(inputStream)
                var sessionKey: ByteArray? = null
                var usedCode = false
                val tokenCandidate = hostResumeToken
                if (tokenCandidate != null) {
                    val candidate = deriveKey(shared, tokenCandidate)
                    if (open(candidate, DIR_PHONE_TO_HOST, 0, sealedAuth)?.optString("k") == "auth") {
                        sessionKey = candidate
                    }
                }
                if (sessionKey == null && !paired && System.currentTimeMillis() < codeExpiresAt) {
                    val candidate = deriveKey(shared, code.toByteArray(Charsets.UTF_8))
                    if (open(candidate, DIR_PHONE_TO_HOST, 0, sealedAuth)?.optString("k") == "auth") {
                        sessionKey = candidate
                        usedCode = true
                    }
                }
                // Pairing is one-shot even when two peers race to use the
                // displayed code; token-authenticated sessions can reconnect.
                val authenticatedKey = sessionKey ?: run {
                    noteFailure(peerAddress)
                    return
                }
                if (usedCode) synchronized(pairingLock) {
                    if (paired || System.currentTimeMillis() >= codeExpiresAt) {
                        noteFailure(peerAddress)
                        return
                    }
                    paired = true
                    code = ""
                    codeExpiresAt = 0L
                    val token = ByteArray(32).also { RANDOM.nextBytes(it) }
                    hostResumeToken = token
                }
                clearFailures(peerAddress)
                val previous = synchronized(pairingLock) {
                    // State sequences belong to this authenticated transport. A
                    // resumed controller may have reloaded its WebView and
                    // restarted its local counters at zero.
                    lastSequence = 0
                    lastUtility = 0
                    ackSequence = 0
                    hostSocket.also { hostSocket = connection }
                }
                activated = true
                if (previous != null && previous !== connection) {
                    try { previous.close() } catch (_: Exception) {}
                }
                val ready = JSONObject()
                    .put("k", "ready")
                    .put("token", if (usedCode) encode(hostResumeToken ?: ByteArray(0)) else JSONObject.NULL)
                    .put("system", systemProvider() ?: "auto")
                writeFrame(outputStream, seal(authenticatedKey, DIR_HOST_TO_PHONE, 0, ready))
                readFrames(inputStream, outputStream, authenticatedKey)
            } catch (failure: Exception) {
                if (!stopping.get() && (!activated || hostSocket === connection)) {
                    setError("Direct LAN controller session ended")
                }
            } finally {
                if (activated) synchronized(pairingLock) {
                    if (hostSocket === connection) {
                        hostSocket = null
                        release()
                        onStatus(status())
                    }
                }
            }
        }
    }

    private fun readFrames(inputStream: DataInputStream, outputStream: DataOutputStream, key: ByteArray) {
        var receiveCounter = 1L
        var sendCounter = 1L
        while (!stopping.get()) {
            val frame = open(key, DIR_PHONE_TO_HOST, receiveCounter, readFrame(inputStream)) ?: return
            receiveCounter += 1
            if (frame.optString("k") != "state") continue
            val sequence = frame.optLong("s", 0).coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
            if (sequence <= lastSequence) continue
            lastSequence = sequence
            if (shouldApply()) {
                apply(frame)
                error = ""
            } else {
                release()
            }
            val ack = JSONObject()
                .put("k", "ack")
                .put("s", lastSequence)
                .put("utilitySequence", lastUtility)
                .put("inputActive", shouldApply() && paired)
                .put("system", systemProvider() ?: "auto")
            writeFrame(outputStream, seal(key, DIR_HOST_TO_PHONE, sendCounter, ack))
            sendCounter += 1
            ackSequence = lastSequence
            onStatus(status())
        }
    }

    private fun apply(frame: JSONObject) {
        val state = frame.optJSONArray("b")
        val pressed = mutableSetOf<String>()
        if (state != null) for (index in 0 until state.length()) {
            val name = state.optString(index)
            if (BUTTONS.containsKey(name)) pressed.add(name)
        }
        for (name in applied) if (!pressed.contains(name)) BUTTONS[name]?.let { onButton(it, false) }
        for (name in pressed) if (!applied.contains(name)) BUTTONS[name]?.let { onButton(it, true) }
        applied = pressed
        val axes = frame.optJSONArray("a")
        val leftX = axes?.optDouble(0, 0.0)?.toFloat() ?: 0f
        val leftY = axes?.optDouble(1, 0.0)?.toFloat() ?: 0f
        val engaged = kotlin.math.abs(leftX) > AXIS_THRESHOLD || kotlin.math.abs(leftY) > AXIS_THRESHOLD
        if (engaged) { onAnalog(leftX, leftY); axesEngaged = true }
        else if (axesEngaged) { onAnalog(0f, 0f); axesEngaged = false }
        val touch = frame.optJSONArray("t")
        if (touch != null && touch.length() == 2) {
            onTouch(touch.optDouble(0, 0.0).toFloat(), touch.optDouble(1, 0.0).toFloat(), true)
            touchPressed = true
        } else if (touchPressed) {
            onTouch(0f, 0f, false)
            touchPressed = false
        }
        dispatchUtilities(frame)
        input = pressed.sorted().joinToString(",")
    }

    /** Apply each one-shot utility action once, even when a state frame is retried. */
    private fun dispatchUtilities(frame: JSONObject) {
        frame.optJSONArray("u")?.let { utilities ->
            for (index in 0 until utilities.length()) {
                val item = utilities.optJSONObject(index) ?: continue
                val sequence = item.optInt("sequence", 0)
                if (sequence <= lastUtility) continue
                lastUtility = sequence
                val action = item.optString("action")
                if (action.isNotEmpty()) onUtility(action)
            }
        }
    }

    private fun release() {
        for (name in applied) BUTTONS[name]?.let { onButton(it, false) }
        applied = emptySet()
        if (axesEngaged) { onAnalog(0f, 0f); axesEngaged = false }
        if (touchPressed) { onTouch(0f, 0f, false); touchPressed = false }
    }

    private fun setError(message: String) {
        error = message
        onStatus(status())
    }

    private fun newPairingCode(): String = buildString {
        repeat(6) { append(('0'.code + RANDOM.nextInt(10)).toChar()) }
    }

    private fun randomHex(bytes: Int): String {
        val value = ByteArray(bytes)
        RANDOM.nextBytes(value)
        return value.joinToString("") { "%02x".format(it) }
    }

    private fun ecKeyPair() = KeyPairGenerator.getInstance("EC").apply {
        initialize(ECGenParameterSpec("secp256r1"), RANDOM)
    }.generateKeyPair()

    private fun publicKeyBytes(key: java.security.PublicKey): ByteArray {
        val point = (key as ECPublicKey).w
        val xBytes = point.affineX.toByteArray()
        val yBytes = point.affineY.toByteArray()
        val x = xBytes.copyOfRange(maxOf(0, xBytes.size - 32), xBytes.size)
        val y = yBytes.copyOfRange(maxOf(0, yBytes.size - 32), yBytes.size)
        return byteArrayOf(4) + ByteArray(32 - x.size) + x + ByteArray(32 - y.size) + y
    }

    private fun publicKeyFromRaw(raw: ByteArray): java.security.PublicKey {
        require(raw.size == 65 && raw[0].toInt() == 4)
        val parameters = AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }
            .getParameterSpec(ECParameterSpec::class.java)
        val point = ECPoint(BigInteger(1, raw.copyOfRange(1, 33)), BigInteger(1, raw.copyOfRange(33, 65)))
        return KeyFactory.getInstance("EC").generatePublic(ECPublicKeySpec(point, parameters))
    }

    private fun deriveKey(shared: ByteArray, secret: ByteArray): ByteArray {
        val salt = MessageDigest.getInstance("SHA-256").digest("an3-ctrl-v1|".toByteArray() + secret)
        val prk = hmac(salt, shared)
        val info = "an3-ctrl|v1|session".toByteArray()
        var previous = ByteArray(0)
        val output = ByteArray(32)
        var offset = 0
        for (counter in 1..2) {
            previous = hmac(prk, previous + info + byteArrayOf(counter.toByte()))
            val count = minOf(previous.size, output.size - offset)
            previous.copyInto(output, offset, 0, count)
            offset += count
        }
        return output
    }

    private fun hmac(key: ByteArray, data: ByteArray): ByteArray = Mac.getInstance("HmacSHA256").run {
        init(SecretKeySpec(key, "HmacSHA256")); doFinal(data)
    }

    private fun nonce(direction: Int, counter: Long): ByteArray = ByteBuffer.allocate(12).putInt(direction).putLong(counter).array()

    private fun seal(key: ByteArray, direction: Int, counter: Long, value: JSONObject): ByteArray {
        val nonce = nonce(direction, counter)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
        return nonce + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
    }

    private fun open(key: ByteArray, direction: Int, counter: Long, body: ByteArray): JSONObject? {
        if (body.size < 28 || !body.copyOfRange(0, 12).contentEquals(nonce(direction, counter))) return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, body.copyOfRange(0, 12)))
            JSONObject(String(cipher.doFinal(body.copyOfRange(12, body.size)), Charsets.UTF_8))
        } catch (_: Exception) { null }
    }

    private fun readFrame(input: DataInputStream): ByteArray {
        val length = input.readInt()
        require(length in 1..MAX_FRAME_BYTES)
        return ByteArray(length).also { input.readFully(it) }
    }

    private fun writeFrame(output: DataOutputStream, body: ByteArray) {
        require(body.isNotEmpty() && body.size <= MAX_FRAME_BYTES)
        output.writeInt(body.size); output.write(body); output.flush()
    }

    private fun encode(bytes: ByteArray): String = android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
    private fun decode(value: String): ByteArray = android.util.Base64.decode(value, android.util.Base64.DEFAULT)
}

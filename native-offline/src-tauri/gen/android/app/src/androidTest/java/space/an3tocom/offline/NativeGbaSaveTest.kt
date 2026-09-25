// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.app.Activity
import android.webkit.WebView
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.web.assertion.WebViewAssertions.webMatches
import androidx.test.espresso.web.sugar.Web.onWebView
import androidx.test.espresso.web.webdriver.DriverAtoms.findElement
import androidx.test.espresso.web.webdriver.DriverAtoms.getText
import androidx.test.espresso.web.webdriver.DriverAtoms.webClick
import androidx.test.espresso.web.webdriver.Locator
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.LargeTest
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * T1b: prove the GBA battery save (SRAM) round-trips through the native runtime.
 *
 * The fixture (tools/testrom/gba_homebrew_test.py) reads and writes SRAM with
 * 8-bit accesses, which is what makes mGBA resolve the save type to SRAM, and
 * writes an "AN3B" signature plus a boot counter byte at SRAM[4] that increments
 * on every boot. The native host owns SRAM persistence: it flushes the core's
 * RETRO_MEMORY_SAVE_RAM to `<save dir>/<rom id>.srm` on stop and loads it back
 * before the first frame.
 *
 * The test therefore asserts real state, not a file's mere existence:
 *  1. run 1 (fresh): a 32 KiB .srm appears with the "AN3B" signature;
 *  2. run 2 (reload): the signature is still present AND the counter advanced,
 *     which is only possible if run 2 read back what run 1 persisted.
 *
 * Prerequisite (documented, done by the runner, not the test): the fixture is
 * pushed to the device's public Downloads:
 *   python3 tools/testrom/gba_homebrew_test.py /tmp/an3-homebrew-test-visible-20260923.gba
 *   adb push /tmp/an3-homebrew-test-visible-20260923.gba /sdcard/Download/an3-homebrew-test-visible-20260923.gba
 *
 * One MainActivity launch per instrumentation process (Tauri shell limitation):
 * run this class in its own invocation.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativeGbaSaveTest {

    @Test
    fun persistsAndRestoresSramAcrossRuns() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val device = UiDevice.getInstance(instrumentation)
        val appFiles = instrumentation.targetContext.filesDir

        // A previous test run may have left a save for a deduplicated ROM id;
        // remove it so run 1 starts genuinely fresh.
        deleteExistingSaves(appFiles)

        ActivityScenario.launch(MainActivity::class.java).use {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='quick-library']"))
                .perform(webClick())

            awaitElement("[data-testid='choose-rom']")
            onWebView()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='choose-rom']"))
                .perform(webClick())
            selectFixtureInPicker(device)

            try {
                awaitElement("[data-testid='game-launch']", 30_000)
            } catch (error: Throwable) {
                val visible = device.findObjects(By.pkg("space.an3tocom.offline"))
                    .mapNotNull { it.text }.filter { it.isNotBlank() }.take(30)
                throw AssertionError("game-launch did not appear after import. App text: $visible", error)
            }

            // ----- run 1: fresh boot creates the save -----
            launchGame(device)
            awaitCoreRunning(device)
            stopGame(device)
            val first = awaitSaveFile(appFiles, 20_000)
            val firstBytes = first.readBytes()
            assertEquals("GBA SRAM save must be 32 KiB", GBA_SRAM_BYTES, firstBytes.size)
            assertEquals(
                "the save must contain the fixture's AN3B signature",
                SIGNATURE,
                String(firstBytes, 0, SIGNATURE.length, Charsets.US_ASCII),
            )
            val firstCounter = firstBytes[COUNTER_OFFSET].toInt() and 0xFF

            // ----- run 2: reloading restores the saved state -----
            launchGame(device)
            awaitCoreRunning(device)
            stopGame(device)
            val second = awaitSaveFile(appFiles, 20_000)
            val secondBytes = second.readBytes()
            assertEquals(
                "the restored save must keep the AN3B signature",
                SIGNATURE,
                String(secondBytes, 0, SIGNATURE.length, Charsets.US_ASCII),
            )
            val secondCounter = secondBytes[COUNTER_OFFSET].toInt() and 0xFF
            assertEquals(
                "the boot counter must advance, proving run 2 read run 1's persisted SRAM",
                (firstCounter + 1) and 0xFF,
                secondCounter,
            )
        }
    }

    /** Clicks Play and waits for the native overlay, which proves the core booted. */
    private fun launchGame(device: UiDevice) {
        onWebView()
            .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='game-launch']"))
            .perform(webClick())
        assertTrue(
            "the native game overlay did not appear after Play",
            device.wait(Until.hasObject(By.text("Menu")), 30_000),
        )
    }

    /** Waits for the emulated core process and a short, bounded boot window. */
    private fun awaitCoreRunning(device: UiDevice) {
        val deadline = System.currentTimeMillis() + 15_000
        while (System.currentTimeMillis() < deadline) {
            if (device.executeShellCommand("pidof space.an3tocom.offline:game").trim().isNotEmpty()) break
            Thread.sleep(200)
        }
        // The fixture writes SRAM in its first frames; give the core frames and
        // the 60 Hz scheduler a bounded window, not an arbitrary long sleep.
        Thread.sleep(BOOT_WINDOW_MILLIS)
    }

    /** Leaves the game so the native host flushes and the session stops. */
    private fun stopGame(device: UiDevice) {
        device.pressBack()
        device.waitForIdle()
        assertTrue(
            "the app did not return to the library after leaving the game",
            awaitActivity("MainActivity", 20_000),
        )
        // Wait for the separate :game process to finish its native shutdown (the
        // SRAM flush happens there). Ending the instrumentation while it is still
        // tearing down races the shell/UI-process exit.
        val deadline = System.currentTimeMillis() + 20_000
        while (System.currentTimeMillis() < deadline) {
            if (device.executeShellCommand("pidof space.an3tocom.offline:game").trim().isEmpty()) break
            Thread.sleep(200)
        }
        Thread.sleep(SETTLE_MILLIS)
    }

    private fun awaitSaveFile(appFiles: File, timeoutMillis: Long): File {
        val deadline = System.currentTimeMillis() + timeoutMillis
        var found: File? = null
        var lastCount = 0
        while (System.currentTimeMillis() < deadline) {
            val saves = saveFiles(appFiles)
            lastCount = saves.size
            if (saves.isNotEmpty()) { found = saves.first(); break }
            Thread.sleep(250)
        }
        assertNotNull("no .srm save was produced under native-states-v1/gba (found $lastCount)", found)
        return found!!
    }

    private fun saveFiles(appFiles: File): List<File> {
        val root = File(appFiles, "native-states-v1/gba")
        if (!root.isDirectory) return emptyList()
        return root.walkTopDown()
            .filter { it.isFile && it.name.endsWith(".srm") && it.length() > 0 }
            .toList()
    }

    private fun deleteExistingSaves(appFiles: File) {
        saveFiles(appFiles).forEach { it.delete() }
    }

    private fun selectFixtureInPicker(device: UiDevice) {
        assertTrue(
            "the Storage Access Framework picker did not open",
            device.wait(Until.hasObject(By.pkg("com.google.android.documentsui")), 15_000),
        )
        val searchButton = device.wait(
            Until.findObject(By.res("com.google.android.documentsui:id/option_menu_search")), 7_000,
        )
        searchButton?.click()
        val searchField = device.wait(
            Until.findObject(By.res("com.google.android.documentsui:id/search_src_text")), 7_000,
        ) ?: throw AssertionError("the picker search field did not appear")
        searchField.text = FIXTURE_NAME
        // The soft keyboard keeps focus; the first tap on a result would only
        // dismiss the IME, so close it first.
        device.pressBack()
        device.waitForIdle()
        val row = device.wait(Until.findObject(By.text(FIXTURE_NAME)), 15_000)
            ?: throw AssertionError("the fixture $FIXTURE_NAME was not found in the picker")
        var target = row
        while (!target.isClickable && target.parent != null) target = target.parent
        target.click()
        assertTrue(
            "the picker did not return to the app",
            device.wait(Until.hasObject(By.pkg("space.an3tocom.offline")), 8_000),
        )
    }

    private fun awaitWebView(timeoutMillis: Long = 20_000) {
        val deadline = System.currentTimeMillis() + timeoutMillis
        var lastError: Throwable? = null
        while (System.currentTimeMillis() < deadline) {
            try {
                onView(isAssignableFrom(WebView::class.java)).check(matches(isDisplayed()))
                return
            } catch (error: Throwable) {
                lastError = error
                Thread.sleep(250)
            }
        }
        throw AssertionError("the AN3 WebView did not attach within $timeoutMillis ms", lastError)
    }

    private fun awaitElement(selector: String, timeoutMillis: Long = 20_000) {
        val deadline = System.currentTimeMillis() + timeoutMillis
        var lastError: Throwable? = null
        while (System.currentTimeMillis() < deadline) {
            try {
                onWebView()
                    .withElement(findElement(Locator.CSS_SELECTOR, selector))
                    .check(webMatches(getText(), org.hamcrest.Matchers.any(String::class.java)))
                return
            } catch (error: Throwable) {
                lastError = error
                Thread.sleep(250)
            }
        }
        throw AssertionError("DOM element $selector did not appear within $timeoutMillis ms", lastError)
    }

    private fun awaitActivity(simpleName: String, timeoutMillis: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMillis
        while (System.currentTimeMillis() < deadline) {
            var resumed: Activity? = null
            InstrumentationRegistry.getInstrumentation().runOnMainSync {
                resumed = ActivityLifecycleMonitorRegistry.getInstance()
                    .getActivitiesInStage(Stage.RESUMED)
                    .firstOrNull { it::class.java.simpleName == simpleName }
            }
            if (resumed != null) return true
            Thread.sleep(250)
        }
        return false
    }

    private companion object {
        const val FIXTURE_NAME = "an3-homebrew-test-visible-20260923.gba"
        const val SIGNATURE = "AN3B"
        const val COUNTER_OFFSET = 4
        const val GBA_SRAM_BYTES = 32768
        const val BOOT_WINDOW_MILLIS = 4_000L
        const val SETTLE_MILLIS = 2_000L
    }
}

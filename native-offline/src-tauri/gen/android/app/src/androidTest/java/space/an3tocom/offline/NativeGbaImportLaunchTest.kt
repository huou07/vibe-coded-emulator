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
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * End-to-end T1: import the lawful GBA fixture through the real ROM import UI
 * (AN3 WebView via Espresso-Web, Android's Storage Access Framework picker via
 * UiAutomator) and launch it through the real game card.
 *
 * Prerequisite (documented, done by the runner, not by the test): the fixture is
 * pushed to the device's public Downloads:
 *   python3 tools/testrom/gba_homebrew_test.py /tmp/an3-homebrew-test.gba
 *   adb push /tmp/an3-homebrew-test.gba /sdcard/Download/an3-homebrew-test.gba
 *
 * One MainActivity launch per instrumentation process (Tauri shell limitation):
 * run this class in its own invocation.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativeGbaImportLaunchTest {

    @Test
    fun importsAndLaunchesTheHomebrewFixture() {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
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

            // The imported card and its Play control appear in the WebView.
            try {
                awaitElement("[data-testid='game-launch']", 30_000)
            } catch (error: Throwable) {
                val visible = device.findObjects(By.pkg("space.an3tocom.offline"))
                    .mapNotNull { it.text }
                    .filter { it.isNotBlank() }
                    .take(30)
                throw AssertionError("game-launch did not appear after import. App text: $visible", error)
            }
            onWebView()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='game-launch']"))
                .perform(webClick())

            // NativeGameActivity runs in the separate :game process, so the
            // lifecycle monitor (test process only) cannot see it. Assert on its
            // real overlay and frame readout, which UiAutomator observes across
            // processes.
            assertTrue(
                "The native game surface did not appear after Play",
                device.wait(Until.hasObject(By.text("Menu")), 30_000),
            )
            // The emulator core runs in its own :game process; its presence
            // proves the core process started (the FPS readout is only shown
            // when "Show FPS" is enabled).
            val gamePid = device.executeShellCommand("pidof space.an3tocom.offline:game").trim()
            assertTrue("The native :game process did not start", gamePid.isNotEmpty())
            assertTrue(
                "The native game controls did not render",
                device.wait(Until.hasObject(By.text("Start")), 10_000),
            )
        }
    }

    /**
     * Drive the SAF picker without assuming its layout: use its search field (the
     * browse list does not surface an adb-pushed `.gba`), then select the row.
     */
    private fun selectFixtureInPicker(device: UiDevice) {
        // The picker is a different package; wait for it to appear.
        assertTrue(
            "The Storage Access Framework picker did not open",
            device.wait(Until.hasObject(By.pkg("com.google.android.documentsui")), 15_000),
        )

        // Open search (fall back to the search field directly if the button is
        // absent on this build).
        val searchButton = device.wait(
            Until.findObject(By.res("com.google.android.documentsui:id/option_menu_search")), 7_000,
        )
        searchButton?.click()

        val searchField = device.wait(
            Until.findObject(By.res("com.google.android.documentsui:id/search_src_text")), 7_000,
        ) ?: throw AssertionError("The picker search field did not appear")
        searchField.text = FIXTURE_NAME
        // The search field keeps focus with the soft keyboard up; the first tap
        // on a result would only dismiss the IME. Close it first.
        device.pressBack()
        device.waitForIdle()

        val row = device.wait(Until.findObject(By.text(FIXTURE_NAME)), 15_000)
        if (row == null) {
            // Surface what the picker actually shows so failures are actionable.
            val visible = device.findObjects(By.clazz("android.widget.TextView"))
                .mapNotNull { it.text }
                .filter { it.isNotBlank() }
                .take(25)
            throw AssertionError("The fixture $FIXTURE_NAME was not found in the picker. Visible: $visible")
        }
        // The title TextView is not always the clickable node; select the row.
        var target = row
        while (!target.isClickable && target.parent != null) target = target.parent
        target.click()
        if (!device.wait(Until.hasObject(By.pkg("space.an3tocom.offline")), 8_000)) {
            val foreground = device.currentPackageName
            val texts = device.findObjects(By.clazz("android.widget.TextView"))
                .mapNotNull { it.text }.filter { it.isNotBlank() }.take(25)
            val buttons = device.findObjects(By.clazz("android.widget.Button"))
                .mapNotNull { it.text }.filter { it.isNotBlank() }.take(12)
            throw AssertionError("Picker did not return to the app (foreground=$foreground). texts=$texts buttons=$buttons")
        }
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
        throw AssertionError("The AN3 WebView did not attach within ${timeoutMillis} ms", lastError)
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
        throw AssertionError("DOM element $selector did not appear within ${timeoutMillis} ms", lastError)
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
        const val FIXTURE_NAME = "an3-homebrew-test.gba"
    }
}

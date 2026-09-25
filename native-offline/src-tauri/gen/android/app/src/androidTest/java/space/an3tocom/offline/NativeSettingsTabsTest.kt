// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.content.pm.ActivityInfo
import android.view.View
import android.view.ViewGroup
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
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Track C, at runtime: the real AN3 Android WebView renders three Settings tabs
 * (Emulator / Sync / Phone Controller) that switch exactly one pane each while
 * every existing settings card stays reachable; and Controller Mode, reached
 * through the real JS bridge, locks the library activity to landscape and
 * restores the sensor orientation when it leaves.
 *
 * Pane visibility is read from the live DOM after a real Espresso-Web click, so
 * this proves the shipped HTML/JS/CSS and the Kotlin bridge, not the mock used
 * by the Node unit tests.
 *
 * One MainActivity launch per instrumentation process (Tauri shell
 * limitation): everything is asserted in one navigation sequence.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativeSettingsTabsTest {

    @Test
    fun settingsTabsSwitchPanesAndControllerModeLocksLandscape() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            awaitWebView()
            onWebView().forceJavascriptEnabled()

            // Real navigation into Settings.
            click(scenario, "[data-testid='nav-settings']")
            awaitElement("[data-testid='settings-tab-emulator']")

            val initial = awaitPanes(scenario, listOf("emulator"))
            assertEquals("the Settings section is active", "Settings", initial.getString("section"))
            assertEquals("three settings tabs render", 3, initial.getInt("tabCount"))
            assertTrue(
                "the emulator tab is selected by default",
                initial.getJSONArray("selected").strings().contains("emulator"),
            )

            // Sync tab reveals only the Sync pane, including its new test hooks.
            click(scenario, "[data-testid='settings-tab-sync']")
            val sync = awaitPanes(scenario, listOf("sync"))
            assertTrue("the Sync pane renders the sync card", sync.getBoolean("syncSettings"))
            assertTrue("the Sync pane renders the LAN Sync toggle", sync.getBoolean("lanToggle"))
            assertTrue("the Sync pane renders the full library action", sync.getBoolean("librarySync"))

            // Phone Controller tab reveals only the controller pane.
            click(scenario, "[data-testid='settings-tab-controller']")
            val controller = awaitPanes(scenario, listOf("controller"))
            assertTrue(
                "the Phone Controller card is reachable without a running session",
                controller.getBoolean("controllerCardPresent"),
            )

            // Returning to Emulator keeps every pre-existing settings card.
            click(scenario, "[data-testid='settings-tab-emulator']")
            val back = awaitPanes(scenario, listOf("emulator"))
            assertTrue("the application settings card survives", back.getBoolean("appSettings"))
            assertTrue("the per-core game settings card survives", back.getBoolean("gameSettings"))
            assertTrue("the bug report card survives", back.getBoolean("bugReport"))

            // The live system selector must render separate scopes, and a
            // renderer edit for one core must not leak into another. Save the
            // effective values first so the instrumentation leaves the app's
            // existing preferences unchanged.
            awaitElement("[data-gs-system='gba']")
            val gbaUi = evalJson(
                scenario,
                """(function(){
                    var button = document.querySelector('[data-gs-system="gba"]');
                    if (button) button.click();
                    var select = document.querySelector('[data-gs-group] select');
                    return JSON.stringify({system: button && button.dataset.gsSystem, value: select && select.value});
                })()""",
            )
            assertEquals("the Game Settings UI exposes the GBA scope", "gba", gbaUi.getString("system"))
            val ndsUi = evalJson(
                scenario,
                """(function(){
                    var button = document.querySelector('[data-gs-system="nds"]');
                    if (button) button.click();
                    var select = document.querySelector('[data-gs-group] select');
                    return JSON.stringify({system: button && button.dataset.gsSystem, value: select && select.value});
                })()""",
            )
            assertEquals("the Game Settings UI exposes the NDS scope", "nds", ndsUi.getString("system"))

            val isolated = evalJson(
                scenario,
                """(function(){
                    function parse(value) { return JSON.parse(value || '{}'); }
                    var before = parse(window.AN3AndroidSettings.all());
                    var gbaBefore = before.systems.gba.renderer;
                    var ndsBefore = before.systems.nds.renderer;
                    var saved = parse(window.AN3AndroidSettings.save(JSON.stringify({
                        'renderer-gba': 'opengl',
                        'renderer-nds': 'vulkan'
                    })));
                    var after = parse(window.AN3AndroidSettings.all());
                    var restored = parse(window.AN3AndroidSettings.save(JSON.stringify({
                        'renderer-gba': gbaBefore,
                        'renderer-nds': ndsBefore
                    })));
                    var finalState = parse(window.AN3AndroidSettings.all());
                    return JSON.stringify({
                        saved: saved.ok === true,
                        gba: after.systems.gba.renderer,
                        nds: after.systems.nds.renderer,
                        restored: restored.ok === true,
                        gbaFinal: finalState.systems.gba.renderer,
                        ndsFinal: finalState.systems.nds.renderer,
                        gbaBefore: gbaBefore,
                        ndsBefore: ndsBefore
                    });
                })()""",
            )
            assertTrue("per-core renderer edits are accepted", isolated.getBoolean("saved"))
            assertEquals("the GBA renderer edit stays in GBA", "opengl", isolated.getString("gba"))
            assertEquals("the NDS renderer edit stays in NDS", "vulkan", isolated.getString("nds"))
            assertTrue("the original GBA setting is restored", isolated.getBoolean("restored"))
            assertEquals(isolated.getString("gbaBefore"), isolated.getString("gbaFinal"))
            assertEquals(isolated.getString("ndsBefore"), isolated.getString("ndsFinal"))

            // Controller Mode: the app bridge asks the host for landscape. This
            // exercises the real native-bootstrap.js -> Kotlin -> Activity path.
            assertEquals(
                "the library starts at the default (unspecified) orientation",
                ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED,
                requestedOrientation(scenario),
            )
            evalJs(scenario, "window.AN3NativeController && window.AN3NativeController.enterControllerMode();")
            assertEquals(
                "Controller Mode locks the library activity to landscape",
                ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE,
                awaitOrientation(scenario, ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE),
            )
            evalJs(scenario, "window.AN3NativeController && window.AN3NativeController.exitControllerMode();")
            assertEquals(
                "leaving Controller Mode restores the sensor orientation",
                ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED,
                awaitOrientation(scenario, ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED),
            )

            // Keep a real app-scoped LAN host running through the same tab and
            // presentation transitions. Orientation is a UI concern and must
            // not stop or replace the authenticated controller transport.
            click(scenario, "[data-testid='settings-tab-controller']")
            awaitPanes(scenario, listOf("controller"))
            var hostStarted = false
            try {
                click(scenario, "#nativeControllerStart")
                hostStarted = true
                val started = awaitControllerStatus(scenario, true)
                val code = started.optString("code")

                evalJs(scenario, "window.AN3NativeController.enterControllerMode();")
                assertEquals(
                    "Controller Mode can enter while the LAN host is active",
                    ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE,
                    awaitOrientation(scenario, ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE),
                )
                val afterEnter = awaitControllerStatus(scenario, true)
                assertTrue("the LAN host remains running after landscape entry", afterEnter.getBoolean("running"))
                if (code.isNotEmpty()) assertEquals("the LAN pairing code survives entry", code, afterEnter.optString("code"))

                click(scenario, "[data-testid='settings-tab-sync']")
                awaitPanes(scenario, listOf("sync"))
                click(scenario, "[data-testid='settings-tab-controller']")
                awaitPanes(scenario, listOf("controller"))
                val afterTabs = awaitControllerStatus(scenario, true)
                assertTrue("the LAN host remains running across settings tabs", afterTabs.getBoolean("running"))
                if (code.isNotEmpty()) assertEquals("the LAN pairing code survives tab navigation", code, afterTabs.optString("code"))

                evalJs(scenario, "window.AN3NativeController.exitControllerMode();")
                assertEquals(
                    "Controller Mode can exit while the LAN host is active",
                    ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED,
                    awaitOrientation(scenario, ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED),
                )
                val afterExit = awaitControllerStatus(scenario, true)
                assertTrue("the LAN host remains running after returning to sensor orientation", afterExit.getBoolean("running"))
            } finally {
                if (hostStarted) evalJs(scenario, "window.AN3NativeController.stop();")
            }
        }
    }

    /** A real user click, after bringing the element into the viewport. */
    private fun click(scenario: ActivityScenario<MainActivity>, selector: String) {
        val quoted = JSONObject.quote(selector)
        evalJs(scenario, "(function(){ var el = document.querySelector($quoted); if (el) el.scrollIntoView({block:'center'}); })()")
        onWebView()
            .withElement(findElement(Locator.CSS_SELECTOR, selector))
            .perform(webClick())
    }

    /** Snapshot of the live settings DOM, parsed from the WebView's own JS. */
    private fun domState(scenario: ActivityScenario<MainActivity>): JSONObject =
        JSONObject(evalJs(scenario, DOM_STATE_SCRIPT))

    /** Evaluate a JS expression whose result is JSON.stringify(value). */
    private fun evalJson(scenario: ActivityScenario<MainActivity>, script: String): JSONObject {
        val raw = evalJs(scenario, script)
        val decoded = JSONTokener(raw).nextValue()
        return JSONObject(if (decoded is String) decoded else decoded.toString())
    }

    /** Poll the real Android controller bridge until its running state settles. */
    private fun awaitControllerStatus(
        scenario: ActivityScenario<MainActivity>,
        expectedRunning: Boolean,
        timeoutMillis: Long = 10_000,
    ): JSONObject {
        val deadline = System.currentTimeMillis() + timeoutMillis
        var last: JSONObject? = null
        while (System.currentTimeMillis() < deadline) {
            val current = evalJson(
                scenario,
                """(function(){
                    // evaluateJavascript does not await a returned Promise;
                    // read the synchronous Kotlin interface for polling.
                    return window.AN3AndroidNativeController.status();
                })()""",
            )
            last = current
            if (current.optBoolean("running", false) == expectedRunning) return current
            Thread.sleep(150)
        }
        throw AssertionError("Expected controller running=$expectedRunning, last status=$last")
    }

    /** Bounded poll until exactly the expected pane set is visible. */
    private fun awaitPanes(
        scenario: ActivityScenario<MainActivity>,
        expected: List<String>,
        timeoutMillis: Long = 10_000,
    ): JSONObject {
        val deadline = System.currentTimeMillis() + timeoutMillis
        var last: JSONObject? = null
        while (System.currentTimeMillis() < deadline) {
            val state = domState(scenario)
            last = state
            val visible = state.getJSONArray("visiblePanes").strings()
            if (visible == expected) return state
            Thread.sleep(150)
        }
        throw AssertionError("Expected visible panes $expected, last saw ${last?.get("visiblePanes")}")
    }

    private fun requestedOrientation(scenario: ActivityScenario<MainActivity>): Int {
        var value = Int.MIN_VALUE
        scenario.onActivity { value = it.requestedOrientation }
        return value
    }

    private fun awaitOrientation(
        scenario: ActivityScenario<MainActivity>,
        expected: Int,
        timeoutMillis: Long = 5_000,
    ): Int {
        val deadline = System.currentTimeMillis() + timeoutMillis
        var value = requestedOrientation(scenario)
        while (System.currentTimeMillis() < deadline && value != expected) {
            Thread.sleep(100)
            value = requestedOrientation(scenario)
        }
        return value
    }

    /**
     * Evaluate JS in the shell's WebView. Called from the instrumentation thread;
     * the callback is delivered on the main thread, so the latch is awaited off
     * the main thread to avoid deadlock.
     */
    private fun evalJs(scenario: ActivityScenario<MainActivity>, script: String): String {
        val latch = CountDownLatch(1)
        val result = arrayOf<String?>(null)
        scenario.onActivity { activity ->
            val webView = findWebView(activity.window.decorView)
                ?: throw AssertionError("The AN3 WebView is not attached")
            webView.evaluateJavascript(script) { value ->
                result[0] = value
                latch.countDown()
            }
        }
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw AssertionError("WebView JS evaluation timed out: $script")
        }
        return result[0] ?: "null"
    }

    private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }

    private fun findWebView(view: View): WebView? {
        if (view is WebView) return view
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                findWebView(view.getChildAt(index))?.let { return it }
            }
        }
        return null
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

    private fun awaitElement(selector: String, timeoutMillis: Long = 15_000) {
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

    private companion object {
        val DOM_STATE_SCRIPT = """
            (function(){
              var panes = Array.prototype.slice.call(document.querySelectorAll('[data-settings-pane]'));
              var tabs = Array.prototype.slice.call(document.querySelectorAll('[data-settings-tab]'));
              var title = document.querySelector('[data-section-title]');
              return {
                section: title ? title.textContent : '',
                tabCount: tabs.length,
                tabs: tabs.map(function(t){ return t.dataset.settingsTab; }),
                visiblePanes: panes.filter(function(p){ return !p.hidden; }).map(function(p){ return p.dataset.settingsPane; }),
                selected: tabs.filter(function(t){ return t.getAttribute('aria-selected') === 'true'; }).map(function(t){ return t.dataset.settingsTab; }),
                syncSettings: !!document.querySelector('[data-testid="sync-settings"]'),
                lanToggle: !!document.querySelector('[data-testid="lan-sync-toggle"]'),
                librarySync: !!document.getElementById('nativeSyncLibrary'),
                controllerCardPresent: !!document.getElementById('nativeControllerCard'),
                appSettings: !!document.getElementById('nativeApplicationSettingsCard'),
                gameSettings: !!document.getElementById('nativeGameSettingsCard'),
                bugReport: !!document.getElementById('nativeBugReportCard')
              };
            })()
        """.trimIndent()
    }
}

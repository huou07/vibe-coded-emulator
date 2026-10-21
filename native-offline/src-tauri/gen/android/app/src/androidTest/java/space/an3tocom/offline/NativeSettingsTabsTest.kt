// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.util.Log
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
import org.json.JSONObject
import org.json.JSONTokener
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Exercises the real packaged Settings page after network-controller removal.
 * It keeps application and per-core settings reachable without any controller
 * tab or bridge, and verifies that a renderer edit remains scoped to its core.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativeSettingsTabsTest {

    @Test
    fun settingsKeepLocalCoreOptionsAndExposeNoPhoneController() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            awaitWebView()
            onWebView().forceJavascriptEnabled()

            click(scenario, "[data-testid='nav-settings']")
            val settings = evalJson(scenario, SETTINGS_STATE_SCRIPT)
            assertEquals("Settings", settings.getString("section"))
            assertTrue("the local settings panel is visible", settings.getBoolean("settingsVisible"))
            assertEquals("settings no longer has feature tabs", 0, settings.getInt("settingsTabCount"))
            assertFalse("Phone Controller card is absent", settings.getBoolean("phoneControllerCard"))
            assertFalse("Phone Controller bridge is absent", settings.getBoolean("phoneControllerBridge"))
            assertTrue("application settings remain reachable", settings.getBoolean("appSettings"))
            assertTrue("per-core game settings remain reachable", settings.getBoolean("gameSettings"))
            assertTrue("bug report remains reachable", settings.getBoolean("bugReport"))

            awaitElement("[data-gs-system='gba']")
            val isolated = evalJson(
                scenario,
                """(function(){
                    function parse(value) { return JSON.parse(value || '{}'); }
                    var gbaButton = document.querySelector('[data-gs-system="gba"]');
                    if (gbaButton) gbaButton.click();
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
                        gbaSystem: gbaButton && gbaButton.dataset.gsSystem,
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
            assertEquals("gba", isolated.getString("gbaSystem"))
            assertTrue("per-core renderer edits are accepted", isolated.getBoolean("saved"))
            assertEquals("GBA renderer stays in GBA", "opengl", isolated.getString("gba"))
            assertEquals("NDS renderer stays in NDS", "vulkan", isolated.getString("nds"))
            assertTrue("original settings restore", isolated.getBoolean("restored"))
            assertEquals(isolated.getString("gbaBefore"), isolated.getString("gbaFinal"))
            assertEquals(isolated.getString("ndsBefore"), isolated.getString("ndsFinal"))

            Log.i("AN3_ACCEPTANCE", "ASSERTIONS_PASSED:NativeSettingsTabsTest")
        }
    }

    private fun click(scenario: ActivityScenario<MainActivity>, selector: String) {
        val quoted = JSONObject.quote(selector)
        evalJs(scenario, "(function(){ var el = document.querySelector($quoted); if (el) el.scrollIntoView({block:'center'}); })()")
        onWebView().withElement(findElement(Locator.CSS_SELECTOR, selector)).perform(webClick())
    }

    private fun evalJson(scenario: ActivityScenario<MainActivity>, script: String): JSONObject {
        val raw = evalJs(scenario, script)
        val decoded = JSONTokener(raw).nextValue()
        return JSONObject(if (decoded is String) decoded else decoded.toString())
    }

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
        if (!latch.await(10, TimeUnit.SECONDS)) throw AssertionError("WebView JS evaluation timed out: $script")
        return result[0] ?: "null"
    }

    private fun findWebView(view: View): WebView? {
        if (view is WebView) return view
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) findWebView(view.getChildAt(index))?.let { return it }
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
        const val SETTINGS_STATE_SCRIPT = """
            (function(){
              var panel = document.querySelector('[data-panel="settings"]');
              var title = document.querySelector('[data-section-title]');
              return JSON.stringify({
                section: title ? title.textContent : '',
                settingsVisible: !!panel && !panel.hidden,
                settingsTabCount: document.querySelectorAll('[data-settings-tab]').length,
                phoneControllerCard: !!document.getElementById('nativeControllerCard'),
                phoneControllerBridge: !!(window.AN3NativeController || window.AN3AndroidNativeController),
                appSettings: !!document.getElementById('nativeApplicationSettingsCard'),
                gameSettings: !!document.getElementById('nativeGameSettingsCard'),
                bugReport: !!document.getElementById('nativeBugReportCard')
              });
            })()
        """
    }
}

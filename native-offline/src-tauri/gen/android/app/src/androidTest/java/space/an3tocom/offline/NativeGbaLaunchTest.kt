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
import org.hamcrest.Matchers.containsString
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Proves the real user-facing launch path: navigate the WebView to the library,
 * press the game card's Play control, and confirm the native game activity is
 * brought to the foreground.
 *
 * Run alone in its own instrumentation invocation (a fresh process), because
 * Tauri's shell does not tolerate re-launching MainActivity twice in one
 * process. This test requires the GBA fixture to be imported into the app.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativeGbaLaunchTest {

    @Test
    fun playControlStartsTheNativeGameActivity() {
        ActivityScenario.launch(MainActivity::class.java).use {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='quick-library']"))
                .perform(webClick())

            awaitElement("[data-testid='game-launch']")
            // A game card for the imported homebrew fixture exists; press Play.
            onWebView()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='game-launch']"))
                .perform(webClick())

            assertTrue(
                "The native game activity did not reach RESUMED after Play",
                awaitActivity("NativeGameActivity", 30_000),
            )
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
}

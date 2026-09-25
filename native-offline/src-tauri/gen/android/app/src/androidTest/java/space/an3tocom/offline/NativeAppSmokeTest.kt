// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

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
import org.hamcrest.Matchers.containsString
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Drives the real AN3 Android WebView by stable DOM selector instead of
 * coordinate taps. The previous coordinate/uiautomator approach was defeated by
 * the search field stealing focus and the IME covering the game cards.
 *
 * Tauri attaches its WebView asynchronously after the activity is created, so
 * the test waits for the WebView to appear before interacting. Identifiers are
 * test hooks only; they do not change visible UX.
 *
 * One launch per test: Tauri's shell does not tolerate re-launching
 * MainActivity within a single instrumentation run, so everything is asserted
 * in a single navigation sequence.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativeAppSmokeTest {

    /** The shell attaches its WebView; a real control navigates it and the
     *  resulting application state is asserted. */
    @Test
    fun libraryNavigationDrivesTheRealWebView() {
        ActivityScenario.launch(MainActivity::class.java).use {
            awaitWebView()
            awaitElement("[data-testid='quick-library']")

            // Navigate through a real, user-visible control.
            onWebView().forceJavascriptEnabled()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='quick-library']"))
                .perform(webClick())

            // The section title reflects the navigation (real state change).
            onWebView()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-section-title]"))
                .check(webMatches(getText(), containsString("Library")))

            // The Library surface exposes the import affordance and Open ROM.
            onWebView()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='add-rom']"))
                .check(webMatches(getText(), containsString("Add ROM")))
            onWebView()
                .withElement(findElement(Locator.CSS_SELECTOR, "[data-testid='open-rom']"))
                .check(webMatches(getText(), containsString("Open ROM")))
        }
    }

    /**
     * Tauri attaches the shell's WebView after the activity starts. Wait for it
     * with a bounded poll instead of a fixed sleep, and fail with a clear
     * message (and the elapsed time) if it never appears.
     */
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

    /**
     * Wait until a DOM element exists inside the WebView. The page is populated
     * by the shell's JavaScript after the WebView attaches, so a naive lookup
     * can race the DOM; this is a bounded poll, not a fixed sleep.
     */
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
}

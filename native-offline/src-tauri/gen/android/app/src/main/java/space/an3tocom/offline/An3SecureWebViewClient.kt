// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.graphics.Bitmap
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader
import java.io.File
import java.util.HashMap

// Kept outside Tauri's generated package so Android builds retain the secure
// renderer behaviour when Tauri regenerates its bridge files. Android WebView
// treats this AssetLoader hostname as a secure local origin; Rust still serves
// every byte from the packaged runtime, with no network fallback.
class An3SecureWebViewClient(private val runtimeWebView: RustWebView) : WebViewClient() {
    private companion object {
        const val ASSET_HOST = "appassets.androidplatform.net"
    }

    private val interceptedState = mutableMapOf<String, Boolean>()
    private var lastInterceptedUrl: Uri? = null
    private var pendingUrlRedirect: String? = null
    var currentUrl: String = "about:blank"

    private val assetLoader = WebViewAssetLoader.Builder()
        .setDomain(ASSET_HOST)
        .addPathHandler(
            "/native-rom/",
            WebViewAssetLoader.InternalStoragePathHandler(
                runtimeWebView.context,
                File(runtimeWebView.context.dataDir, "an3-roms"),
            ),
        )
        .addPathHandler("/", WebViewAssetLoader.AssetsPathHandler(runtimeWebView.context))
        .build()

    private fun withIsolationHeaders(response: WebResourceResponse?): WebResourceResponse? {
        response?.let {
            val headers = HashMap(it.responseHeaders ?: emptyMap())
            headers["Cache-Control"] = "no-store"
            headers["Cross-Origin-Opener-Policy"] = "same-origin"
            headers["Cross-Origin-Embedder-Policy"] = "require-corp"
            headers["Cross-Origin-Resource-Policy"] = "same-origin"
            headers["X-Content-Type-Options"] = "nosniff"
            it.responseHeaders = headers
        }
        return response
    }

    private fun runtimeResponse(request: WebResourceRequest): WebResourceResponse? =
        withIsolationHeaders(Rust.handleRequest(
            runtimeWebView.id,
            request,
            runtimeWebView.isDocumentStartScriptEnabled,
        ))

    override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
        pendingUrlRedirect?.let {
            Handler(Looper.getMainLooper()).post { view.loadUrl(it) }
            pendingUrlRedirect = null
            return null
        }
        lastInterceptedUrl = request.url
        val response = if (request.url.host == ASSET_HOST) {
            withIsolationHeaders(assetLoader.shouldInterceptRequest(request.url))
        } else {
            runtimeResponse(request)
        }
        interceptedState[request.url.toString()] = response != null
        return response
    }

    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        // This is our local packaged origin, not an external navigation. Let
        // normal player links (`?play=…`) load in the same WebView.
        if (request.url.host == ASSET_HOST) return false
        return Rust.shouldOverride(runtimeWebView.id, request.url.toString())
    }

    override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
        currentUrl = url
        if (interceptedState[url] == false) {
            for (script in runtimeWebView.initScripts) view.evaluateJavascript(script, null)
        }
        Rust.onPageLoading(runtimeWebView.id, url)
    }

    override fun onPageFinished(view: WebView, url: String) {
        Rust.onPageLoaded(runtimeWebView.id, url)
    }

    override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
        if (error.errorCode == ERROR_CONNECT && request.isForMainFrame && request.url != lastInterceptedUrl) {
            view.stopLoading()
            view.loadUrl(request.url.toString())
            pendingUrlRedirect = request.url.toString()
        } else {
            super.onReceivedError(view, request, error)
        }
    }
}

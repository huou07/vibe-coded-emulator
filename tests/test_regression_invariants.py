import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAYER = (ROOT / "static/player.js").read_text(encoding="utf-8")
OFFLINE = (ROOT / "static/offline.js").read_text(encoding="utf-8")
SITE_JS = (ROOT / "static/site.js").read_text(encoding="utf-8")
SERVICE_WORKER = (ROOT / "static/service-worker.js").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


class RegressionInvariantTests(unittest.TestCase):
    def test_admin_progress_and_analytics_respect_normal_csp(self):
        self.assertIn('id="adminProgress" class="upload-progress" max="100" value="0"', APP)
        self.assertIn('id="bulkProgress" class="upload-progress" max="100" value="0"', APP)
        self.assertIn('class="chart-progress chart-visits"', APP)
        self.assertNotIn('style="height:', APP)
        self.assertIn("bar.value = Math.max", SITE_JS)
        self.assertNotIn("bar.style.width", SITE_JS)

    def test_nds_uses_melonds_auto_start_and_touch_bridge(self):
        self.assertIn('nds:"melonds"', PLAYER)
        self.assertIn("window.EJS_startOnLoaded = true", PLAYER)
        self.assertIn('retroarch_core:"melonds"', PLAYER)
        self.assertIn('window.EJS_disableLocalStorage = ndsPad', PLAYER)
        self.assertIn('canvas.classList.remove("ejs-canvas-no-pointer")', PLAYER)
        self.assertIn('setProperty("pointer-events","auto","important")', PLAYER)
        self.assertIn('setProperty("touch-action","none","important")', PLAYER)
        self.assertIn("new MutationObserver(protectNdsCanvas)", PLAYER)
        self.assertIn("dispatchNdsMouse", PLAYER)
        self.assertIn("getBoundingClientRect", PLAYER)
        self.assertIn('Object.defineProperty(event,name', PLAYER)
        self.assertIn('"offsetX"', PLAYER)
        self.assertIn('"offsetY"', PLAYER)
        self.assertIn('new URLSearchParams(location.search).get("touch")', PLAYER)
        self.assertIn('get("touch") || "geometry-mapped"', PLAYER)
        self.assertIn('["native","root","root-touch","overlay","hybrid-root","geometry-only","geometry-mapped"]', PLAYER)
        self.assertIn('elementFromPoint(event.clientX,event.clientY)', PLAYER)
        self.assertIn('gameRoot.setPointerCapture(event.pointerId)', PLAYER)
        self.assertIn('!["touch","touch-passive","pointer-touch","hybrid"].includes(touchVariant)', PLAYER)
        self.assertIn('event.touches||[]', PLAYER)
        self.assertIn('document.addEventListener("touchmove",move', PLAYER)
        self.assertIn('touchVariant === "touch-passive"', PLAYER)
        self.assertIn('touchVariant === "pointer-no-capture"', PLAYER)
        self.assertIn('["delta","geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('touchVariant === "pointer-touch"', PLAYER)
        self.assertIn('["hybrid","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('["root-touch","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('const isolatedNdsMovement = ["geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('"__an3NdsLastMousePoint"', PLAYER)
        self.assertIn('"__an3NdsLastPointerPoint"', PLAYER)
        self.assertIn('const pointKey=isolatedNdsMovement', PLAYER)
        self.assertIn('const mapNdsCursor =', PLAYER)
        self.assertIn('gl?.getParameter(gl.VIEWPORT)', PLAYER)
        self.assertIn('raw[0]+raw[2]<=backingWidth', PLAYER)
        self.assertIn('raw[1]+raw[3]<=backingHeight', PLAYER)
        self.assertIn('movementX=mapped.x-ndsMappedCursor.x', PLAYER)
        self.assertIn('movementY=mapped.y-ndsMappedCursor.y', PLAYER)
        self.assertIn('if (type === "mousedown") ndsViewportCache.delete(canvas)', PLAYER)
        hybrid_block = PLAYER[PLAYER.index('if (["hybrid","hybrid-root","geometry-only","geometry-mapped"]'):PLAYER.index('dispatchNdsMouse(canvas, type, source, buttons);', PLAYER.index('if (["hybrid","hybrid-root","geometry-only","geometry-mapped"]')) + len('dispatchNdsMouse(canvas, type, source, buttons);')]
        self.assertLess(hybrid_block.index("dispatchNdsPointer"), hybrid_block.index("dispatchNdsMouse"))
        self.assertIn('...(touchVariant === "core-touch" ? {melonds_touch_mode:"Touch"} : {})', PLAYER)
        self.assertNotIn('touchVariant === "geometry-mapped" ? {melonds_touch_mode', PLAYER)
        self.assertNotIn("desmume", PLAYER.lower())
        self.assertNotIn("startButtonClicked", PLAYER)
        self.assertIn('new URL(event.request.url).pathname', SERVICE_WORKER)
        self.assertIn('an3-arcade-pwa-v21', SERVICE_WORKER)
        self.assertIn('/static/default-cover.webp', SERVICE_WORKER)
        self.assertIn('/static/default-cover.webp', APP)

    def test_virtual_controls_overlay_has_persistent_touch_toggle_and_per_control_size(self):
        for source in (APP, OFFLINE):
            self.assertIn('id="toggleTouch"', source)
            self.assertIn('id="padTarget"', source)
            self.assertIn('id="padSizeValue"', source)
        self.assertIn('touchToggle?.addEventListener("click",togglePad)', PLAYER)
        self.assertIn('settings.sizes[padTarget.value]', PLAYER)
        self.assertIn('--control-scale', PLAYER)
        self.assertIn('stage?.classList.toggle("pad-overlay",visible)', PLAYER)
        self.assertNotIn('stage?.classList.toggle("pad-docked",visible)', PLAYER)
        self.assertIn('window.EJS_emulator?.gameManager?.simulateInput(0,index,value)', PLAYER)

    def test_performance_profiles_are_conservative_and_persisted(self):
        self.assertIn('const performanceStorageKey = "an3-player-performance-v1"', PLAYER)
        self.assertIn('version:1,', PLAYER)
        self.assertIn('selectedProfile:normalizeProfileId(storedPerformance.selectedProfile)', PLAYER)
        self.assertIn('customOverrides:{', PLAYER)
        self.assertIn('const recommendedProfile = recommendPerformanceProfile(capabilityProbe);', PLAYER)
        self.assertIn('return "balanced";', PLAYER)
        self.assertIn('probe.deviceMemory && probe.deviceMemory<=2 && probe.hardwareConcurrency && probe.hardwareConcurrency<=4', PLAYER)
        self.assertIn('(ndsPad && !probe.webgl2)', PLAYER)
        self.assertIn('window.EJS_forceLegacyCores = performancePlan.forceLegacyNds;', PLAYER)
        self.assertIn('const coreUsesWebgl2=!performancePlan.forceLegacyNds', PLAYER)
        self.assertIn('window.EJS_disableLocalStorage = ndsPad;', PLAYER)
        self.assertNotIn('frameskip', PLAYER.lower())
        self.assertNotIn('render_scale', PLAYER.lower())
        for source in (APP, OFFLINE):
            self.assertIn('name="performanceProfile" value="auto"', source)
            self.assertIn('name="performanceProfile" value="low"', source)
            self.assertIn('name="performanceProfile" value="balanced"', source)
            self.assertIn('name="performanceProfile" value="quality"', source)
            self.assertIn('name="performanceProfile" value="custom"', source)
            self.assertIn('id="useRecommended"', source)
            self.assertIn('id="applyPerformanceProfile"', source)

    def test_speed_controls_are_session_only_and_runtime_gated(self):
        self.assertIn('window.EJS_hideSettings = ["fastForward","ff-ratio","slowMotion","sm-ratio"];', PLAYER)
        self.assertIn('const speedSteps=Object.freeze([.5,1,1.5,2]);', PLAYER)
        self.assertIn('const speedManager = () => {', PLAYER)
        self.assertIn('return gameStarted && manager && required.every', PLAYER)
        self.assertIn('manager.setFastForwardRatio(value);', PLAYER)
        self.assertIn('manager.toggleFastForward(1);', PLAYER)
        self.assertIn('manager.setSlowMotionRatio(1/value);', PLAYER)
        self.assertIn('manager.toggleSlowMotion(1);', PLAYER)
        self.assertIn('manager.toggleFastForward(0);', PLAYER)
        self.assertIn('manager.toggleSlowMotion(0);', PLAYER)
        self.assertNotIn('an3-player-speed', PLAYER)
        self.assertIn('id="speedDown"', APP)
        self.assertIn('id="speedUp"', APP)
        self.assertIn('id="speedValue"', APP)
        self.assertIn('const speedSettingsMarkup = system => {', OFFLINE)
        self.assertIn('speedSettingsMarkup(system)', OFFLINE)

    def test_fullscreen_keeps_the_app_toolbar_and_status_in_scope(self):
        self.assertIn('else shell.requestFullscreen?.();', PLAYER)
        self.assertNotIn('stage.requestFullscreen?.()', PLAYER)
        self.assertIn('.player-page .player-shell:fullscreen', (ROOT / "static/site.css").read_text(encoding="utf-8"))

    def test_nds_default_pad_matches_approved_portrait_layout(self):
        self.assertIn('portrait:{dpad:{x:23.4,y:81.6},a:{x:89,y:80},b:{x:78.2,y:89.7},x:{x:78,y:70.2},y:{x:67.3,y:79.9},l:{x:8.1,y:63.3},r:{x:91.2,y:62.5},start:{x:47.4,y:62.1},select:{x:57.9,y:62}}', PLAYER)
        self.assertIn('{scale:1,opacity:.48,visible:true,sizes:{dpad:1.4,start:.7,select:.7}}', PLAYER)
        self.assertIn('id="padOpacity" type="range" min="30" max="100" step="1"', APP)
        self.assertIn('id="padOpacity" type="range" min="30" max="100" step="1"', OFFLINE)
        self.assertIn('sizes:{...defaultSettings.sizes,...(storedSettings.sizes || {})}', PLAYER)
        self.assertIn('settings.sizes={...defaultSettings.sizes}', PLAYER)
        self.assertIn('if(padRoot.clientWidth<=480&&element.firstElementChild)', PLAYER)

    def test_nds_debug_is_bounded_exportable_and_fail_closed(self):
        self.assertIn('NDS_DEBUG_ALLOWED = ENVIRONMENT in {"staging", "development"}', APP)
        self.assertIn('"ndsDebugAllowed": NDS_DEBUG_ALLOWED', APP)
        self.assertIn('config.ndsDebugAllowed === true && new URLSearchParams(location.search).get("ndsdebug") === "1"', PLAYER)
        self.assertIn('const NDS_DEBUG_LIMIT = 160', PLAYER)
        self.assertIn('ndsDebugEvents.splice(0,ndsDebugEvents.length-NDS_DEBUG_LIMIT)', PLAYER)
        self.assertIn('window.AN3NdsDebug=Object.freeze', PLAYER)
        self.assertIn('exportJSON', PLAYER)
        self.assertIn('{capture:true,passive:true}', PLAYER)
        debug_block = PLAYER[PLAYER.index("const NDS_DEBUG_LIMIT"):PLAYER.index("const dispatchNdsMouse")]
        self.assertNotIn("preventDefault", debug_block)
        self.assertNotIn("setPointerCapture", debug_block)
        self.assertNotIn("dispatchEvent", debug_block)
        self.assertNotIn("getComputedStyle", debug_block)
        self.assertIn("activeTouchIds", debug_block)
        self.assertIn("activePointerIds", debug_block)
        self.assertIn("!inside && !trackedTouch && !trackedPointer", debug_block)
        for field in (
            "eventType", "isTrusted", "pointerType", "clientX", "clientY", "pageX", "pageY",
            "target", "pointerCaptureOwner", "canvasRect", "canvasBackingWidth", "canvasBackingHeight",
            "canvasCssWidth", "canvasCssHeight", "devicePixelRatio", "mappedX", "mappedY",
            "normalizedX", "normalizedY", "movementX", "movementY", "orientation", "viewportOrientation",
            "screenOrientation", "fullscreen", "touchVariant", "activeCore", "configuredCore", "runtimeCore",
        ):
            self.assertIn(field, debug_block)

    def test_core_storage_is_emulatorjs_indexeddb_and_report_first(self):
        for source in (PLAYER, OFFLINE):
            self.assertIn('indexedDB.open("EmulatorJS-core",1)', source)
            self.assertIn('transaction("core"', source)
            self.assertIn('"?EJS_KEYS!"', source)
        self.assertIn("report?.options?.defaultWebGL2", PLAYER)
        self.assertIn("putCoreRecord(coreFile,coreData,report.buildStart)", PLAYER)
        self.assertIn("an3-arcade-cores-v1", PLAYER)
        self.assertIn('const CORE_CACHE = "an3-arcade-cores-v1"', SERVICE_WORKER)

    def test_nds_delivery_keeps_original_archive_and_range_support(self):
        self.assertIn('path.startswith("/game-file/") and game["system"] != "nds"', APP)
        self.assertIn('self.send_header("Accept-Ranges", "bytes")', APP)
        self.assertIn('self.send_header("Content-Range", f"bytes {start}-{end}/{size}")', APP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
